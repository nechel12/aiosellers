# All-In-One Sellers API

**English** | [Русский](README.ru.md)

[![CI](https://github.com/nechel12/aiosellers/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/nechel12/aiosellers/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/nechel12/aiosellers)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Last commit](https://img.shields.io/github/last-commit/nechel12/aiosellers)](https://github.com/nechel12/aiosellers/commits/main)
[![Fork of Zewsic/aiosellers](https://img.shields.io/badge/fork-Zewsic%2Faiosellers-blueviolet?logo=github)](https://github.com/Zewsic/aiosellers)
[![Security policy](https://img.shields.io/badge/security-policy-green)](SECURITY.md)
[![CodeQL](https://github.com/nechel12/aiosellers/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/nechel12/aiosellers/security/code-scanning)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)

Asynchronous Python wrapper for digital trading platforms: **FunPay**, **PlayerOK**
and **GGsel**. One package, one event model, one multi-account hub.

> [!NOTE]
> This repository is a **fork** of
> [Zewsic/aiosellers](https://github.com/Zewsic/aiosellers), maintained by
> [@nechel12](https://github.com/nechel12). The fork adds the GGsel adapter, the
> shared `aiosellers.core` layer (platforms, capabilities, `SellerHub`), durable
> listener state, transport hardening and tests. The `aiosellers` package on PyPI
> is published by the upstream project and does **not** contain these changes —
> install the fork from GitHub (see [Installation](#installation)).

Stack: **Python 3.12+**, asyncio, Pydantic v2, TLS requests, websockets and
SQLite. The library talks to the platforms directly: FunPay over HTTP forms and
HTML parsing, PlayerOK over GraphQL and WebSocket subscriptions, GGsel over the
official Seller API V1. There is no proxy service, telemetry, or third-party
backend in the request path.

> Status: pre-1.0. The core, transports and listeners are covered by tests, and
> the public API is documented in docstrings and this README; coverage of the
> high-level wrappers is still growing. Minor releases may still change behavior.
> See [CHANGELOG.md](CHANGELOG.md).

## Installation

Install the fork from GitHub (works today):

```bash
pip install "git+https://github.com/nechel12/aiosellers.git"
```

or via uv:

```bash
uv add "git+https://github.com/nechel12/aiosellers.git"
```

The distribution name is `aiosellers-nechel12` and the import package remains
`aiosellers`. Once the first PyPI release is published, this also works:

```bash
pip install aiosellers-nechel12
```

`pip install aiosellers` installs the **upstream** package from PyPI, not this
fork. Pin a commit or tag for reproducible installs:

```bash
pip install "git+https://github.com/nechel12/aiosellers.git@<tag>"
```

**Requirements:** Python 3.12+.

## Configuration

Tokens can be passed to the constructor or through environment variables:

```bash
export PLAYEROK_ACCESS_TOKEN="your_token_here"
export FUNPAY_GOLDEN_KEY="your_golden_key"
export GGSEL_API_KEY="your_api_key"
export GGSEL_SELLER_ID="123456"
```

Set `bot_mark=False` in `FunPayClientConfig` to stop adding the invisible bot
marker to outgoing messages and reviews.

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

## Multi-account hub

`SellerHub` runs several FunPay, Playerok and GGsel sessions together and merges
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
    hub.add(FunPay("your-golden-key"), platform=Platform.FUNPAY, session_id="funpay-main")
    hub.add(
        Playerok("your-access-token"),
        platform=Platform.PLAYEROK,
        session_id="playerok-main",
        listen_options={"reviews": True},
    )
    hub.add(
        GGsel(GGselClientConfig(api_key="your-api-key", seller_id=123456)),
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
ids and order snapshots across process restarts. Without a store, listeners
rebuild their state on every launch and emit only the initial snapshots.

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

    # ... run the clients ...

    await store.close()

asyncio.run(main())
```

`MemoryStateStore` keeps the same semantics in process memory, which is handy
for tests. State keys are `funpay:{account_id}:listener`,
`playerok:{user_id}:listener` and `ggsel:{seller_id}:listener`; a malformed
snapshot is ignored with a warning, and a failed write never stops polling.

## Examples

Runnable samples are in [`examples/`](examples/).

| Script | What it does |
|:-------|:-------------|
| [`playerok_account.py`](examples/playerok_account.py) | Profile and balance |
| [`playerok_chats.py`](examples/playerok_chats.py) | Unread chats and latest messages |
| [`playerok_deals.py`](examples/playerok_deals.py) | Paid and sent deals |
| [`playerok_market.py`](examples/playerok_market.py) | Search items and average price |
| [`playerok_bot.py`](examples/playerok_bot.py) | Commands and deal events |
| [`transactions.py`](examples/transactions.py) | Pending transactions and cards |
| [`funpay_account.py`](examples/funpay_account.py) | Profile, balance, transactions |
| [`funpay_orders.py`](examples/funpay_orders.py) | Sales and an order card |
| [`funpay_chats.py`](examples/funpay_chats.py) | Chats and message history |
| [`funpay_lots.py`](examples/funpay_lots.py) | Your lots |
| [`funpay_bot.py`](examples/funpay_bot.py) | New order and a chat reply |
| [`funpay_reviews.py`](examples/funpay_reviews.py) | Reply to a new review |
| [`funpay_backtest.py`](examples/funpay_backtest.py) | Replay saved chat history |
| [`ggsel_account.py`](examples/ggsel_account.py) | Balance and receipts |
| [`ggsel_bot.py`](examples/ggsel_bot.py) | Chat replies and new sales |

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

Not implemented yet: the V2 offer API (offer creation/editing) and the legacy
XML `/xml/shop_search.asp` endpoint. The V1 adapter is enough for order
processing, messaging, reviews and price updates.

## Limitations

- FunPay and PlayerOK do not provide official seller APIs; those adapters rely
  on the same HTTP forms, GraphQL documents and WebSocket feeds the websites
  use. Platform changes can break them, so pin a version and watch the
  [CHANGELOG](CHANGELOG.md).
- GGsel is implemented against Seller API V1 only.
- The library is a client, not a scheduler: you run the event loop and decide
  how to deploy, scale and supervise your bots.
- Platform rules, rate limits and account bans are outside the library's
  control. Use the APIs responsibly and at your own risk.

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting. The library stores
tokens in memory, passes them only to the platform endpoints, and keeps
listener state in the `StateStore` you provide. Do not log credentials, and
protect the SQLite state file if it contains chat metadata.

Report vulnerabilities through GitHub's private advisory flow, not a public
issue.

## Development

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy aiosellers
uv run pytest -q
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
- [PlayerokAPI](https://github.com/alleexxeeyy/PlayerokAPI/) — PlayerOK API
  reference.
- [FunPayAPI](https://github.com/LIMBODS/FunPayAPI) — FunPay API reference.
- [FunPayCardinal](https://github.com/sidor0912/FunPayCardinal) — FunPay bot
  built on the same ideas.
- [fpx](https://github.com/funpayx/fpx) — another FunPay client.

## Contributing

Bug reports and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md)
for the development workflow. By participating, you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md). Before sending a change, run
`uv run ruff check .` and `uv run pytest -q`. Report security issues through
[SECURITY.md](SECURITY.md), not a public issue. Release notes live in
[CHANGELOG.md](CHANGELOG.md); maintainers can follow [RELEASING.md](RELEASING.md).

## License

The code is licensed under Apache-2.0; see [LICENSE](LICENSE). The upstream
copyright and license notices are preserved. The PyPI package `aiosellers` is
maintained by the upstream project and is not affiliated with this fork.

---

## Support the project

All-In-One Sellers API is free and open source. If it saves you time, you can
support further development:

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
> Send only the matching asset on the specified network. Transfers to another
> network cannot be recovered.
