import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from aiosellers.playerok.api.chats import ChatAPI
from aiosellers.playerok.api.deals import DealAPI
from aiosellers.playerok.events import ChatInitializedEvent, NewMessageEvent, NewReviewEvent
from aiosellers.playerok.listener import EventListener
from aiosellers.playerok.schemas import Chat as ChatSchema
from aiosellers.playerok.schemas import ItemDeal


class _RawChats:
    def __init__(self, page=None, messages=None):
        self.page = page
        self.messages = messages

    async def get_chats(self, **kwargs):
        return self.page

    async def get_chat_messages(self, chat_id, count=12):
        return self.messages

    async def get_chat(self, chat_id):
        return None


class _RawDeals:
    def __init__(self, pages=None, deals=None):
        self.pages = list(pages or [])
        self.deals = dict(deals or {})

    async def get_deals(self, **kwargs):
        if self.pages:
            return self.pages.pop(0)
        return None

    async def get_deal(self, deal_id):
        return self.deals.get(deal_id)


class _Client:
    _use_identity_map = False
    me_id = "me"
    _transport = SimpleNamespace(
        _access_token="token", config=SimpleNamespace(user_agent="test-agent")
    )

    def __init__(self, chats=None, deals=None):
        self._raw = SimpleNamespace(chats=chats or _RawChats(), deals=deals or _RawDeals())
        self.chats = ChatAPI(self)
        self.deals = DealAPI(self)

    def _require_raw(self):
        return self._raw


class _WS:
    def __init__(self):
        self.frames = []

    async def send(self, raw):
        self.frames.append(json.loads(raw))


def _recent_message(message_id="m1", text="hello"):
    return {
        "id": message_id,
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "isRead": True,
    }


def _chat_page(*chats):
    return SimpleNamespace(chats=list(chats))


class FrameLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_ping_is_answered_with_pong(self):
        listener = EventListener(_Client())
        listener._ws = _WS()

        await listener.handle_frame({"type": "ping"})

        self.assertEqual(listener._ws.frames, [{"type": "pong"}])

    async def test_ack_subscribes_and_reuses_subscription_ids(self):
        listener = EventListener(_Client())
        listener.known_chat_ids.add("c1")
        listener._ws = _WS()

        await listener.handle_frame({"type": "connection_ack"})
        first = [frame["id"] for frame in listener._ws.frames]
        await listener.handle_frame({"type": "connection_ack"})
        second = [frame["id"] for frame in listener._ws.frames[len(first) :]]

        self.assertEqual(sorted(first), sorted(second))
        operations = sorted(frame["payload"]["operationName"] for frame in listener._ws.frames)
        self.assertEqual(
            operations,
            ["chatMessageCreated", "chatMessageCreated", "chatUpdated", "chatUpdated", "userUpdated", "userUpdated"],
        )

    async def test_complete_resubscribes_chat_subscription(self):
        listener = EventListener(_Client())
        listener.chat_subscriptions["sub-1"] = "c1"
        listener._ws = _WS()

        await listener.handle_frame({"type": "complete", "id": "sub-1"})

        self.assertNotIn("sub-1", listener.chat_subscriptions)
        self.assertIn("c1", listener.chat_subscriptions.values())
        self.assertEqual(len(listener._ws.frames), 1)
        self.assertEqual(listener._ws.frames[0]["payload"]["operationName"], "chatMessageCreated")

    async def test_complete_resubscribes_control_subscription(self):
        listener = EventListener(_Client())
        control_id = listener.subscription_frames()[0]["id"]
        listener._ws = _WS()

        await listener.handle_frame({"type": "complete", "id": control_id})

        self.assertEqual(len(listener._ws.frames), 1)
        self.assertEqual(listener._ws.frames[0]["id"], control_id)
        self.assertEqual(listener._ws.frames[0]["type"], "subscribe")

    async def test_error_frames_do_not_break_the_stream(self):
        listener = EventListener(_Client())

        self.assertEqual(await listener.handle_frame({"type": "error", "payload": ["boom"]}), [])
        self.assertEqual(await listener.handle_frame({"type": "connection_error", "payload": {}}), [])


class ResyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_resync_emits_new_chat_and_unseen_message(self):
        chat = ChatSchema.model_validate(
            {"id": "c1", "type": "PM", "lastMessage": _recent_message()}
        )
        chats = _RawChats(page=_chat_page(chat))
        listener = EventListener(_Client(chats=chats))

        events = await listener._resync()

        self.assertIsInstance(events[0], ChatInitializedEvent)
        self.assertIsInstance(events[-1], NewMessageEvent)
        self.assertEqual(events[-1].message.id, "m1")
        self.assertIn("c1", listener.known_chat_ids)

    async def test_resync_skips_old_messages(self):
        old = _recent_message()
        old["createdAt"] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        chat = ChatSchema.model_validate({"id": "c1", "type": "PM", "lastMessage": old})
        listener = EventListener(_Client(chats=_RawChats(page=_chat_page(chat))))

        events = await listener._resync()

        self.assertEqual([event for event in events if isinstance(event, NewMessageEvent)], [])


class ReviewsOnlyModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_baseline_deals_are_not_treated_as_new(self):
        raw_deals = _RawDeals(
            pages=[SimpleNamespace(deals=[SimpleNamespace(id="d1"), SimpleNamespace(id="d2")])]
        )
        listener = EventListener(_Client(deals=raw_deals))

        await listener._refresh_known_deals()

        self.assertEqual(listener.known_deal_ids, {"d1", "d2"})
        self.assertEqual(listener.review_deal_ids, [])

    async def test_new_deal_is_polled_for_review_without_messages(self):
        raw_deals = _RawDeals(
            pages=[
                SimpleNamespace(deals=[SimpleNamespace(id="d1")]),
                SimpleNamespace(deals=[SimpleNamespace(id="d1"), SimpleNamespace(id="d2")]),
            ],
            deals={
                "d2": ItemDeal.model_validate(
                    {
                        "id": "d2",
                        "status": "CONFIRMED",
                        "direction": "IN",
                        "testimonial": {"id": "r1", "status": "APPROVED", "rating": 5},
                        "chat": {"id": "c1", "type": "PM"},
                    }
                )
            },
        )
        listener = EventListener(_Client(deals=raw_deals))
        listener.review_delay = 0

        await listener._refresh_known_deals()
        await listener._refresh_known_deals()
        events = await listener.poll_reviews_once()

        self.assertEqual(listener.review_deal_ids, [])
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], NewReviewEvent)
        self.assertEqual(events[0].deal.id, "d2")
        self.assertEqual(events[0].chat.id, "c1")
