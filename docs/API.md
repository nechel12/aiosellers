# API overview

This page is a map of the public API. Detailed signatures and docstrings live in
the source and in the `aiosellers` package itself.

## Top-level package

```python
from aiosellers import (
    FunPay,
    FunPayClientConfig,
    GGsel,
    GGselClientConfig,
    Playerok,
    PlayerokClientConfig,
    SellerHub,
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

### Platforms and events

- `Platform.FUNPAY`, `Platform.PLAYEROK`, `Platform.GGSEL`.
- `Capability` flags: `MESSAGES`, `ORDERS`, `PURCHASES`, `DEALS`, `REVIEWS`,
  `LIST_MANAGEMENT`, `IMAGE_UPLOAD`, `ITEM_PRIORITY`, `WEBSOCKET`.
- `EventKind`: `INITIAL`, `MESSAGE`, `REVIEW`, `ORDER`, `PURCHASE`, `DEAL`,
  `LIST`, `OTHER`.
- `HubEvent` carries `platform`, `session_id`, `kind` and the original typed
  event in `event`.

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
`max_concurrent_requests`, `state`, `bot_mark`, `handler_timeout`.

## Playerok

```python
from aiosellers.playerok import Playerok, PlayerokClientConfig
```

- `Playerok(access_token)` or `Playerok(PlayerokClientConfig(...))`.
- `client.account` — viewer, profile, users and reviews.
- `client.chats` — chats, messages, templates and attachments.
- `client.deals` — deals and status transitions.
- `client.games` / `client.items` — catalog and seller items.
- `client.transactions` — transactions, providers and cards.
- `client.download(url)` — host-allowlisted file download.
- `client.listen(...)` and `client.start_polling(...)`.

Playerok uses GraphQL over HTTP and a WebSocket subscription feed. The feed
reconnects with backoff and reconciles missed chats after a reconnect.

## GGsel

```python
from aiosellers.ggsel import GGsel, GGselClientConfig
```

- `GGsel(api_key)` or `GGsel(GGselClientConfig(api_key=..., seller_id=...))`.
- `client.account` — balance and receipts.
- `client.categories` — seller categories.
- `client.chats` — chats and message history.
- `client.products` — products and price updates.
- `client.sales` — sales and purchase details.
- `client.reviews` — seller reviews.
- `client.listen(...)` and `client.start_polling(...)`.

GGsel uses Seller API V1 with a signed login, token refresh and polling. There
are no webhooks; a configured `StateStore` keeps chat/sale/review cursors across
restarts.

## Errors and reliability

The adapters expose platform-specific exceptions under
`aiosellers.<platform>.exceptions` (and `core.exceptions` for shared transport
errors). Typical errors include unauthorized sessions, rate limits, transport
failures, GraphQL errors and persisted-query expiry.

Transport behavior:

- GET requests retry transient network/5xx failures.
- POST requests are single-shot unless the platform operation is explicitly
  marked safe to retry.
- `Retry-After` is honored.
- Event handlers have a timeout and a concurrency limit.

## Examples

Runnable scripts live in [`../examples/`](../examples/). The README status
tables describe which platform modules are implemented.
