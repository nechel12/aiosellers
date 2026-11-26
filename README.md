# All-In-One Sellers API

**English** | [Русский](https://github.com/nechel12/aiosellers/blob/main/README.ru.md)

Asynchronous Python clients for **FunPay**, **PlayerOK**, and **GGsel**, with
a multi-account event stream and persistent listener state.

[![CI](https://github.com/nechel12/aiosellers/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/nechel12/aiosellers/actions/workflows/ci.yml)
[![CodeQL](https://github.com/nechel12/aiosellers/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/nechel12/aiosellers/actions/workflows/codeql.yml)
[![PyPI](https://img.shields.io/pypi/v/aiosellers-nechel12)](https://pypi.org/project/aiosellers-nechel12/)
[![Tested Python versions](https://img.shields.io/pypi/pyversions/aiosellers-nechel12)](https://pypi.org/project/aiosellers-nechel12/)
[![License](https://img.shields.io/github/license/nechel12/aiosellers)](https://github.com/nechel12/aiosellers/blob/main/LICENSE)

## Contents

- [Installation](#installation)
- [Documentation](#documentation)
- [Configuration](#configuration)
- [Quick Start: PlayerOK](#quick-start-playerok)
- [Quick Start: FunPay](#quick-start-funpay)
- [Quick Start: GGsel](#quick-start-ggsel)
- [Multi-account hub](#multi-account-hub)
- [Durable listener state](#durable-listener-state)
- [Examples](#examples)
- [Development Status: PlayerOK](#development-status-playerok)
- [Development Status: FunPay](#development-status-funpay)
- [Development Status: GGsel](#development-status-ggsel)
- [Limitations](#limitations)
- [Security](#security)
- [Development](#development)
- [Related projects](#related-projects)
- [Contributing](#contributing)
- [License](#license)
- [Support the project](#support-the-project)

> [!NOTE]
> This repository is a **fork** of
> [Zewsic/aiosellers](https://github.com/Zewsic/aiosellers), maintained by
> [@nechel12](https://github.com/nechel12). The fork adds the GGsel adapter, the
> shared `aiosellers.core` layer (platforms, capabilities, `SellerHub`), durable
> listener state, transport changes, and tests. The `aiosellers` package on PyPI
> is published by the upstream project and does **not** contain these changes;
> the fork is distributed as `aiosellers-nechel12` (see
> [Installation](#installation)).

Stack: **Python 3.12+**, asyncio, Pydantic v2, TLS requests, websockets and
SQLite. The library connects to the platforms directly: FunPay over HTTP forms and
HTML parsing, PlayerOK over GraphQL and WebSocket subscriptions, GGsel over the
official Seller API V1. The library does not collect telemetry or require a
separate server or proxy service.

> Status: pre-1.0. Tests cover the core, transports, and event listeners.
> Coverage of the high-level API is incomplete. Behavior may change in minor
> releases.
> See [CHANGELOG.md](https://github.com/nechel12/aiosellers/blob/main/CHANGELOG.md).

## Installation

Requires **Python 3.12+**. Install the published fork from PyPI:

```bash
pip install aiosellers-nechel12
# or, in a uv project:
uv add aiosellers-nechel12
```

Import the library as `aiosellers`. `pip install aiosellers` installs the
**upstream** distribution, not this fork. Use separate environments for the
two distributions because they install the same import package.

To try changes from GitHub before a PyPI release:

```bash
pip install "git+https://github.com/nechel12/aiosellers.git"
```

Append `@<tag-or-commit>` to pin a GitHub install.

## Documentation

- [API overview](https://github.com/nechel12/aiosellers/blob/main/docs/API.md) — public entry points and modules.
- [Migration from upstream](https://github.com/nechel12/aiosellers/blob/main/docs/MIGRATION.md) — install name, changed behavior
  and upgrade steps.

## Configuration

Tokens can be passed to the constructor or through environment variables:

```bash
export PLAYEROK_ACCESS_TOKEN="your_token_here"
export FUNPAY_GOLDEN_KEY="your_golden_key"
export GGSEL_API_KEY="your_api_key"
export GGSEL_SELLER_ID="123456"
```

`Playerok()`, `FunPay()` and `GGsel()` read these variables. Credentials can
also be passed directly: `Playerok("token")`, `FunPay("golden-key")` or
`GGsel(GGselClientConfig(api_key="key", seller_id=123456))`.

Set `bot_mark=False` in `FunPayClientConfig` to stop adding the invisible bot
marker to outgoing messages and reviews.

Media arguments (`image`, `photo`) accept bytes, an uploaded-file id, a URL where
the platform supports one, and a local path — which is read from the disk of the
running process. A host that lets less-trusted code build those arguments can
confine the read target with `AIOSELLERS_MEDIA_ROOTS`:

```bash
# colon-separated (os.pathsep) list of allowed directories
export AIOSELLERS_MEDIA_ROOTS="/srv/app/media"
# empty value: no local path is opened at all
export AIOSELLERS_MEDIA_ROOTS=""
```

The variable is optional: unset keeps the historical behaviour of opening any
readable path. With it set, paths outside the listed roots raise
`MediaPathNotAllowedError` before anything is read.

All adapters accept an optional `proxy` URL:

```python
FunPay(FunPayClientConfig(golden_key="...", proxy="http://user:pass@proxy:8080"))
Playerok(PlayerokClientConfig(access_token="...", proxy="http://proxy:8080"))
GGsel(GGselClientConfig(api_key="...", seller_id=123456, proxy="http://proxy:8080"))
```

PlayerOK uses it for HTTP requests, uploads, downloads, and WebSocket
subscriptions. GGsel uses it for ApiLogin and all Seller API requests. Proxy
credentials are omitted from configuration representations (`repr`).

PlayerOK skips the seller's own messages by default. Set `include_own=True` in
`PlayerokClientConfig` or pass it to `listen()` or `start_polling()` to see them.
Each entity cache has a per-client limit of 5,000 entries by default
(`identity_map_limit`); `None` removes the limit.
`listen()` and `start_polling()` accept listener-specific options such as
`order_page_limit`, `chat_history_batches` (FunPay) and page/history limits
(GGsel).

## Quick Start: PlayerOK

```python
import asyncio
from aiosellers.playerok import Playerok

async def main():
    async with Playerok() as client:
        me = await client.account.me()
        profile = await client.account.profile()
        print(f"{me.username} | {me.email}")
        print(f"Rating: {profile.rating} ({profile.reviews_count} reviews)")
        print(f"Available: {profile.balance.available}")
        print(f"Pending: {profile.balance.pending_income}")

asyncio.run(main())
```

## Quick Start: FunPay

```python
import asyncio
from aiosellers.funpay import FunPay

async def main():
    async with FunPay() as client:
        me = await client.account.profile()
        balance = await client.finance.balance()
        print(f"{me.username} id={me.id}")
        print(f"RUB {balance.rub} | USD {balance.usd} | EUR {balance.eur}")

asyncio.run(main())
```

## Quick Start: GGsel

The GGsel adapter uses the official Seller API V1: the client signs a login
request with the API key, keeps the access token and polls chats, sales and
reviews because GGsel has no webhooks.

```python
import asyncio
from aiosellers.ggsel import GGsel

async def main() -> None:
    # Or pass GGselClientConfig(api_key="...", seller_id=123456)
    async with GGsel() as client:
        balance = await client.account.balance()
        print(f"Seller {client.seller_id}: free={balance.free} locked={balance.locked}")

        chats = await client.chats.list()
        for chat in chats:
            print(chat.id, chat.buyer_email, chat.unread_count)

        products = await client.products.my(limit=5)
        for product in products:
            print(product.id, product.name, product.price, product.currency)

asyncio.run(main())
```

`GGsel()` reads `GGSEL_API_KEY` and `GGSEL_SELLER_ID`; pass
`GGselClientConfig` explicitly to override either value. `client.seller_id` is
populated after the client starts, and `client.products.update_price()` /
`update_prices()` return a task id that can be checked with
`client.products.task_status()`.

## Multi-account hub

`SellerHub` runs several FunPay, PlayerOK, and GGsel sessions together and merges
their events into one stream. Every item carries the platform and session id,
while the payload stays the original typed event.

```python
import asyncio

from aiosellers import (
    FunPay,
    GGsel,
    GGselClientConfig,
    Platform,
    Playerok,
    SellerHub,
)

async def main():
    hub = SellerHub()
    hub.add(FunPay("golden-key"), platform=Platform.FUNPAY, session_id="funpay-main")
    hub.add(
        Playerok("access-token"),
        platform=Platform.PLAYEROK,
        session_id="playerok-main",
        listen_options={"reviews": True},
    )
    hub.add(
        GGsel(GGselClientConfig(api_key="api-key", seller_id=123456)),
        platform=Platform.GGSEL,
        session_id="ggsel-main",
    )

    await hub.start()
    try:
        async for item in hub.stream():
            print(item.platform, item.session_id, item.kind, item.event)
    finally:
        await hub.close()

asyncio.run(main())
```

`item.kind` is a portable `EventKind` (`MESSAGE`, `REVIEW`, `ORDER`, `DEAL`, ...).
`Session.capabilities` tells what a platform supports, so shared code can branch
without hardcoding platform names. Clients also expose `stop()` to end
`start_polling()` from another task.

## Durable listener state

Pass a `StateStore` in the client config to keep chat cursors, processed message
IDs and order statuses across process restarts. Without a store, listeners
still emit live events but rebuild their starting state on every launch.
Recovery is bounded by the adapter's history and polling limits; keep event
handlers idempotent.

```python
import asyncio

from aiosellers import (
    FunPay,
    FunPayClientConfig,
    GGsel,
    GGselClientConfig,
    Playerok,
    PlayerokClientConfig,
    SQLiteStateStore,
)

async def main():
    store = SQLiteStateStore("sellers.db")
    funpay = FunPay(FunPayClientConfig(golden_key="...", state=store))
    playerok = Playerok(PlayerokClientConfig(access_token="...", state=store))
    ggsel = GGsel(
        GGselClientConfig(api_key="...", seller_id=123456, state=store)
    )

    # Run the clients here.

    await store.close()

asyncio.run(main())
```

`MemoryStateStore` keeps the same semantics in process memory, which is handy
for tests. State keys are `funpay:{account_id}:listener`,
`playerok:{user_id}:listener` and `ggsel:{seller_id}:listener`; a malformed
snapshot is ignored with a warning, and a failed write never stops polling.

## Examples

Runnable samples are in [`examples/`](https://github.com/nechel12/aiosellers/tree/main/examples).

| Script | What it does |
|:-------|:-------------|
| [`playerok_account.py`](https://github.com/nechel12/aiosellers/blob/main/examples/playerok_account.py) | Profile and balance |
| [`playerok_chats.py`](https://github.com/nechel12/aiosellers/blob/main/examples/playerok_chats.py) | Unread chats and latest messages |
| [`playerok_deals.py`](https://github.com/nechel12/aiosellers/blob/main/examples/playerok_deals.py) | Paid and sent deals |
| [`playerok_market.py`](https://github.com/nechel12/aiosellers/blob/main/examples/playerok_market.py) | Search items and average price |
| [`playerok_bot.py`](https://github.com/nechel12/aiosellers/blob/main/examples/playerok_bot.py) | Commands and deal events |
| [`transactions.py`](https://github.com/nechel12/aiosellers/blob/main/examples/transactions.py) | Pending transactions and cards |
| [`funpay_account.py`](https://github.com/nechel12/aiosellers/blob/main/examples/funpay_account.py) | Profile, balance, transactions |
| [`funpay_orders.py`](https://github.com/nechel12/aiosellers/blob/main/examples/funpay_orders.py) | Sales and an order card |
| [`funpay_chats.py`](https://github.com/nechel12/aiosellers/blob/main/examples/funpay_chats.py) | Chats and message history |
| [`funpay_lots.py`](https://github.com/nechel12/aiosellers/blob/main/examples/funpay_lots.py) | Lots |
| [`funpay_bot.py`](https://github.com/nechel12/aiosellers/blob/main/examples/funpay_bot.py) | New order and a chat reply |
| [`funpay_reviews.py`](https://github.com/nechel12/aiosellers/blob/main/examples/funpay_reviews.py) | Reply to a new review |
| [`funpay_backtest.py`](https://github.com/nechel12/aiosellers/blob/main/examples/funpay_backtest.py) | Replay saved chat history |
| [`ggsel_account.py`](https://github.com/nechel12/aiosellers/blob/main/examples/ggsel_account.py) | Balance and receipts |
| [`ggsel_bot.py`](https://github.com/nechel12/aiosellers/blob/main/examples/ggsel_bot.py) | Chat replies and new sales |

```bash
uv run python examples/playerok_account.py
uv run python examples/funpay_account.py
uv run python examples/ggsel_account.py
```

## Development Status: PlayerOK

| Module                 | Raw API | High-level |
|:-----------------------|:-------:|:----------:|
| **Account**            |    ✅    |     ✅      |
| **Games / Categories** |    ✅    |     ✅      |
| **Items**              |    ✅    |     ✅      |
| **Deals**              |    ✅    |     ✅      |
| **Chats**              |    ✅    |     ✅      |
| **Transactions**       |    ✅    |     ✅      |
| **Event Feed**         |    ✅    |     ✅      |

## Development Status: FunPay

| Module            | Raw API | High-level |
|:------------------|:-------:|:----------:|
| **Account**       |    ✅    |     ✅      |
| **Balance**       |    ✅    |     ✅      |
| **Orders / Sales**|    ✅    |     ✅      |
| **Chats**         |    ✅    |     ✅      |
| **Lots**          |    ✅    |     ✅      |
| **Reviews**       |    ✅    |     ✅      |
| **Event Feed**    |    ✅    |     ✅      |

## Development Status: GGsel

GGsel is covered through the official Seller API V1 (`https://seller.ggsel.com/`).
There are no webhooks, so the listener polls chats, sales and reviews with
durable cursors when a `StateStore` is configured.

| Module                  | Raw API | High-level |
|:------------------------|:-------:|:----------:|
| **Account / Balance**   |    ✅    |     ✅      |
| **Receipts**            |    ✅    |     ✅      |
| **Categories**          |    ✅    |     ✅      |
| **Products / Prices**   |    ✅    |     ✅      |
| **Sales / Purchases**   |    ✅    |     ✅      |
| **Chats**               |    ✅    |     ✅      |
| **Reviews**             |    ✅    |     ✅      |
| **Event Feed**          |    ✅    |     ✅      |

The adapter does not support Offer API V2 (creating and editing offers) or
the legacy XML endpoint `/xml/shop_search.asp`.

## Limitations

- The FunPay and PlayerOK adapters rely on unofficial website interfaces:
  HTTP forms, GraphQL, and WebSocket feeds. Changes to these interfaces may
  affect compatibility. See the
  [CHANGELOG](https://github.com/nechel12/aiosellers/blob/main/CHANGELOG.md).
- GGsel is implemented against Seller API V1 only.
- The library does not deploy, schedule, scale, or supervise bots.
- Platform operators set their terms of use, rate limits, and account
  enforcement policies.

## Security

Use [GitHub's private vulnerability form](https://github.com/nechel12/aiosellers/security/advisories/new)
rather than a public issue. See the [security policy](https://github.com/nechel12/aiosellers/security/policy)
for scope and handling advice. Use only trusted custom endpoints and proxies.
Redact logs before sharing and protect state databases, which may contain chat
IDs and, for FunPay, message previews.

## Development

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy aiosellers
uv run pytest -q --cov=aiosellers --cov-fail-under=65

uv run python examples/funpay_account.py
uv build
```

Structure: `aiosellers/core` (platforms, events, hub, state stores),
`aiosellers/funpay`, `aiosellers/playerok`, `aiosellers/ggsel` (each with
`api`, `raw`, `schemas`, `entities`, transport and listener), `tests/` and
`examples/`.

## Related projects

- [Zewsic/aiosellers](https://github.com/Zewsic/aiosellers) — the upstream
  project this repository is forked from.
- [PlayerokAPI](https://github.com/alleexxeeyy/PlayerokAPI/) — library for PlayerOK.
- [FunPayAPI](https://github.com/LIMBODS/FunPayAPI) — library for FunPay.
- [FunPayCardinal](https://github.com/sidor0912/FunPayCardinal) — bot for FunPay.
- [fpx](https://github.com/funpayx/fpx) — another FunPay client.

## Contributing

Use the [issue forms](https://github.com/nechel12/aiosellers/issues/new/choose)
for public bug reports and feature requests. See
[CONTRIBUTING.md](https://github.com/nechel12/aiosellers/blob/main/CONTRIBUTING.md)
for local checks and pull requests, and the
[Code of Conduct](https://github.com/nechel12/aiosellers/blob/main/CODE_OF_CONDUCT.md)
for participation guidelines. Maintainers can follow
[RELEASING.md](https://github.com/nechel12/aiosellers/blob/main/RELEASING.md).

## License

The code is licensed under Apache-2.0; see
[LICENSE](https://github.com/nechel12/aiosellers/blob/main/LICENSE) and
[NOTICE](https://github.com/nechel12/aiosellers/blob/main/NOTICE), which lists
what this fork adds relative to upstream. The upstream copyright and license
notices are preserved. The PyPI package `aiosellers` is maintained by the
upstream project and is not associated with this distribution.

---

## Support the project

All-In-One Sellers API is an open-source project. Financial support is
optional:

<p align="center">
  <a href="https://boosty.to/nechel12/donate">
    <img src="https://img.shields.io/badge/Boosty-Donate-F15F2C?style=for-the-badge&logo=boosty&logoColor=white" alt="Donate via Boosty">
  </a>
</p>

### Crypto

| Network | Address |
|:--------|:--------|
| **TRON** | `TMM2Cdm4tJx1nKRRq5RCBcdwfn9cHuJZy9` |
| **TON** | `UQBlVvOfTleWn4pkY384mYWiGyhdHBryoC_N1Si1OSWAxPKl` |
| **Bitcoin** | `bc1qagjtnutjya2rss3u3ls8ur7qk0u7zutc6t6fwc` |
| **BNB Smart Chain** | `0x423aF840f67355371bf32480744A84069dfab5ff` |

> [!WARNING]
> Send only the matching asset on the specified network. Transfers on the
> wrong network may be unrecoverable.
