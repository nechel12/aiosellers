import unittest

from aiosellers.playerok.core.constants import BASE_HEADERS, EXAMPLE_USER_AGENTS
from aiosellers.playerok.core.exceptions import GraphQLError, PersistedQueryExpired
from aiosellers.playerok.core.utils import _raise_on_gql_errors
from aiosellers.playerok.listener import _DRIFT_WARNED, parse_chat, parse_chat_message


class GraphQLErrorTests(unittest.TestCase):
    def test_persisted_query_not_found_is_explicit(self):
        payload = {
            "errors": [
                {
                    "message": "PersistedQueryNotFound",
                    "extensions": {"code": "PERSISTED_QUERY_NOT_FOUND"},
                }
            ]
        }
        with self.assertRaisesRegex(PersistedQueryExpired, "frontend contract"):
            _raise_on_gql_errors(payload)

    def test_persisted_query_code_without_marker_is_still_detected(self):
        payload = {"errors": [{"message": "unknown query", "extensions": {"code": "PERSISTED_QUERY_HASH_MISMATCH"}}]}
        with self.assertRaises(PersistedQueryExpired):
            _raise_on_gql_errors(payload)

    def test_regular_errors_stay_graphql_errors(self):
        payload = {"errors": [{"message": "not authorized"}]}
        with self.assertRaises(GraphQLError) as ctx:
            _raise_on_gql_errors(payload)
        self.assertNotIsInstance(ctx.exception, PersistedQueryExpired)

    def test_no_errors_is_a_noop(self):
        _raise_on_gql_errors({"data": {}})
        _raise_on_gql_errors({})


class SchemaDriftTests(unittest.TestCase):
    def setUp(self):
        _DRIFT_WARNED.clear()

    def test_message_drift_warns_once_and_returns_partial_data(self):
        payload = {
            "id": "m1",
            "text": "hi",
            "createdAt": "2026-01-01T00:00:00Z",
            "isRead": True,
            "user": "not-an-object",
        }
        with self.assertLogs("aiosellers.playerok.listener", level="WARNING") as logs:
            first = parse_chat_message(payload)
            second = parse_chat_message(payload)

        self.assertEqual(first.id, "m1")
        self.assertEqual(first.text, "hi")
        self.assertIsNone(second.user)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("chat message", logs.records[0].getMessage())

    def test_chat_drift_is_reported(self):
        payload = {"id": "c1", "lastMessage": "not-an-object"}
        with self.assertLogs("aiosellers.playerok.listener", level="WARNING") as logs:
            chat = parse_chat(payload)

        self.assertEqual(chat.id, "c1")
        self.assertIsNone(chat.last_message)
        self.assertIn("chat", logs.records[0].getMessage())


class UserAgentTests(unittest.TestCase):
    def test_example_user_agents_match_client_hints(self):
        major = BASE_HEADERS["sec-ch-ua"].split("v=")[1].split('"')[1]
        self.assertTrue(EXAMPLE_USER_AGENTS)
        for agent in EXAMPLE_USER_AGENTS:
            self.assertIn(f"Chrome/{major}.", agent)
            self.assertIn("Macintosh", agent)
