# API overview

This page summarizes the public API. See the `aiosellers` package source for
signatures and docstrings.

## Top-level package

```python
from aiosellers import (
    FunPay,
    FunPayClientConfig,
    GGsel,
    GGselClientConfig,
    AuthError,
    Playerok,
    PlayerokClientConfig,
    SellerHub,
    SellerSession,
    Platform,
    Capability,
    EventKind,
    HubEvent,
    StateStore,
    MemoryStateStore,
    SQLiteStateStore,
)
```

`import aiosellers` does not perform network requests. Construct a client and
use it as an async context manager, or call `start()` / `close()` explicitly.

## Shared core

### Clients and hub

- `SellerHub` — starts several platform sessions and merges their events into
  one `HubEvent` stream.
- `SellerHub.add(client, platform=..., session_id=..., listen_options=...)`.
- `SellerHub.start()`, `SellerHub.close()`, `SellerHub.stream()`.
- `Session.capabilities` returns a `Capability` bitmask.
- `SellerSession(client, timeout=...)` wraps an already started FunPay, PlayerOK
  or GGsel client. It provides `messages.send(chat_id, text)`,
  `messages.list(chat_id, limit=...)`, `listings.list(limit=...)`, and
  `orders.list(limit=...)`. FunPay's listing operation requires `subcategory_id`.
  The result rows keep their platform types, and PlayerOK's order operation
  reads its deal feed. No cross-platform price write is provided.

Set `SellerSession(..., timeout=60)` to limit a complete call, including
pagination and retry delays. Wrap other API calls in `asyncio.timeout()`
when a total deadline is needed. A timeout does not establish whether a write
was applied; do not automatically resend a message on that basis.

### Platforms and events

- `Platform.FUNPAY`, `Platform.PLAYEROK`, `Platform.GGSEL`.
- `Capability` flags: `MESSAGES`, `ORDERS`, `PURCHASES`, `DEALS`, `REVIEWS`,
  `LIST_MANAGEMENT`, `IMAGE_UPLOAD`, `ITEM_PRIORITY`, `WEBSOCKET`.
- `EventKind`: `INITIAL`, `MESSAGE`, `REVIEW`, `ORDER`, `PURCHASE`, `DEAL`,
  `LIST`, `OTHER`, `ERROR`, `STATUS`.
- `HubEvent` carries `platform`, `session_id`, `kind` and the original typed
  event in `event`.
- `HubEvent.to_dict()` returns a versioned, JSON-compatible envelope with
  `account_id`, `raw_type`, `event_id`, `occurred_at`, and an explicit `payload`.
  Message payloads carry `chat_id`, `message_id`, `sender_id`, and `text`. IDs
  are strings; a missing ID or source timestamp is not invented. `event_id`
  is stable for account-scoped occurrences with a source ID, not every event
  kind. Error payloads contain a safe code, not exception text or raw responses.

Set `error_policy="raise"` to propagate a listener exception and stop all
streams (appropriate for a single-session worker). Use `error_policy="yield"`
to receive an `EventKind.ERROR` for the affected session while others continue.
In Python, `event.error` retains the original exception. The default `"log"`
keeps the historical behavior. Use `contextlib.aclosing()` to close the stream
explicitly on early exit.

```python
from contextlib import aclosing

async def forward(hub, inbox):
    async with aclosing(hub.stream(error_policy="yield", buffered=False)) as events:
        async for event in events:
            await inbox.store(event.to_dict())
```

With `buffered=False`, the source iterator does not advance until the consumer
requests the next item. Persist or handle the current event before requesting
another one to keep that listener's checkpoint behind the consumer. This
does not extend a platform's recovery window or guarantee exactly-once
delivery. Buffered mode can advance a source checkpoint after enqueueing.

### State stores

- `StateStore` — async `get` / `set` / `delete` / `close` protocol.
- `MemoryStateStore` — process-local store for tests.
- `SQLiteStateStore(path)` — durable store; parent directories are created and
  `~` is expanded.

State keys are `funpay:{account_id}:listener`,
`playerok:{user_id}:listener` and `ggsel:{seller_id}:listener`.

## FunPay

```python
from aiosellers.funpay import FunPay, FunPayClientConfig
```

- `FunPay(golden_key)` or `FunPay(FunPayClientConfig(...))`.
- `client.account` — profile and runner identity.
- `client.chats` — chat shortcuts and message history.
- `client.orders` — sales, purchases and order cards.
- `client.lots` — own lots and lot management.
- `client.categories` — categories and subcategories.
- `client.finance` — balance, transactions and wallets.
- `client.listen(...)` and `client.start_polling(...)`.

Important config fields: `golden_key`, `poll_interval`, `request_timeout`,
`max_concurrent_requests`, `state`, `bot_mark`, `handler_timeout`,
`identity_map_limit`. Listener pacing options such as `order_page_limit` and
`chat_history_batches` can be passed to `listen()`/`start_polling()`.

## PlayerOK

```python
from aiosellers.playerok import Playerok, PlayerokClientConfig
```

- `Playerok(access_token)` or `Playerok(PlayerokClientConfig(...))`.
- `client.account` — viewer, profile, users and reviews.
- `client.chats` — chats, messages, templates and attachments.
- `client.deals` — deals and status transitions.
- `client.games` / `client.items` — catalog and seller items.
- `client.transactions` — transactions, providers and cards.
- `client.download(url, max_bytes=..., timeout=...)` — host-allowlisted,
  unauthenticated download, limited to 16 MiB by default. `timeout` is an
  optional deadline for the entire download.
- `client.listen(...)` and `client.start_polling(...)`.

PlayerOK uses GraphQL over HTTP and WebSocket subscriptions. After reconnecting
with backoff, the listener replays unprocessed messages within its recovery
window. The seller's own messages are skipped by default
(`include_own=True` opts in).
Use `listen(connection_events=True)` (or the same option in the hub's
`listen_options`) to report `connected` and `reconnecting` WebSocket state
changes as `EventKind.STATUS` in the hub. An explicitly configured `proxy`
applies to HTTP and WebSocket. Without it, the WebSocket connects directly
unless `PlayerokClientConfig(ws_use_system_proxy=True)` is set.

With a `StateStore`, `client.listen()` checkpoints messages and reviews when
iteration resumes after the relevant events. Closing the stream before
resuming can cause those events to be replayed within the listener's recovery
window. Make handlers idempotent; the stream does not guarantee exactly-once
delivery.
Use `listen(state_flush_interval=...)` to combine state writes over a time
window (seconds). The default `0` writes each dirty checkpoint immediately.
The listener flushes pending acknowledged state on a clean close; batching
widens the window in which a process crash can cause replay.

## GGsel

```python
from aiosellers.ggsel import GGsel, GGselClientConfig
```

- `GGsel(api_key)` when `GGSEL_SELLER_ID` is set, or
  `GGsel(GGselClientConfig(api_key=..., seller_id=...))`.
- `client.account` — balance and receipts.
- `client.categories` — seller categories.
- `client.chats` — chats and message history.
- `client.products` — products and price updates.
- `client.sales` — sales and purchase details.
- `client.reviews` — seller reviews.
- `client.listen(...)` and `client.start_polling(...)`, both accept listener
  limits (`chats_page_size`, `history_limit`, `sales_top`, ...).

GGsel uses Seller API V1 with a signed login, token refresh and polling. There
are no webhooks; a configured `StateStore` keeps chat/sale/review cursors across
restarts.

## Errors and reliability

Catch `AuthError`, `ConfigurationError`, `RateLimitedError`, and
`TransientError` from `aiosellers` without importing platform classes.
`AuthError` means the platform rejected credentials; `ConfigurationError`
means the required settings were missing or invalid. `RateLimitedError` is a
`TransientError` with `retry_after` in seconds, or `None` if unavailable.
Existing platform-specific imports remain valid, including
`aiosellers.playerok.core.exceptions`.

Transport behavior:

- GET requests retry transient network/5xx failures.
- POST requests are not retried unless the platform operation is explicitly
  marked safe to retry.
- `Retry-After` is honored.
- Event handlers have a timeout and a concurrency limit.

## Examples

Runnable scripts live in [`../examples/`](../examples/). The README status
tables describe which platform modules are implemented.
