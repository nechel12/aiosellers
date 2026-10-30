# All-In-One Sellers API

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

Asynchronous Python wrapper for working with digital trading platforms. Implemented modules: **PlayerOK** and **FunPay**.

![Python](logo.png)


---

## Installation

```bash
pip install aiosellers
```

or via uv:

```bash
uv add aiosellers
```

**Requirements:** Python 3.12+

---

## Configuration

Token can be passed to the constructor or via environment variable:

```bash
export PLAYEROK_ACCESS_TOKEN="your_token_here"
export FUNPAY_GOLDEN_KEY="your_golden_key"
```

Set `bot_mark=False` in `FunPayClientConfig` to stop adding the invisible bot marker
to outgoing messages and reviews.

---

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

## Multi-account hub

`SellerHub` runs several FunPay and Playerok sessions together and merges their events
into one stream. Every item carries the platform and session id, while the payload stays
the original typed event.

```python
import asyncio

from aiosellers import FunPay, Platform, Playerok, SellerHub

async def main():
    hub = SellerHub()
    hub.add(FunPay("your-golden-key"), platform=Platform.FUNPAY, session_id="funpay-main")
    hub.add(
        Playerok("your-access-token"),
        platform=Platform.PLAYEROK,
        session_id="playerok-main",
        listen_options={"reviews": True},
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
`Session.capabilities` tells what a platform supports, so shared code can branch without
hardcoding platform names. Clients also expose `stop()` to end `start_polling()` from
another task.

## Durable listener state

Pass a `StateStore` in the client config to keep chat cursors, processed message ids and
order snapshots across process restarts. Without a store, listeners rebuild their state on
every launch and emit only the initial snapshots.

```python
import asyncio

from aiosellers import (
    FunPay,
    FunPayClientConfig,
    Playerok,
    PlayerokClientConfig,
    SQLiteStateStore,
)

async def main():
    store = SQLiteStateStore("sellers.db")
    funpay = FunPay(FunPayClientConfig(golden_key="...", state=store))
    playerok = Playerok(PlayerokClientConfig(access_token="...", state=store))

    # ... run the clients ...

    await store.close()

asyncio.run(main())
```

`MemoryStateStore` keeps the same semantics in process memory, which is handy for tests.
State keys are `funpay:{account_id}:listener` and `playerok:{user_id}:listener`; a
malformed snapshot is ignored with a warning, and a failed write never stops polling.

---

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

```bash
uv run python examples/playerok_account.py
uv run python examples/funpay_account.py
```

---

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

---

## Acknowledgments

Based on ideas from [PlayerokAPI](https://github.com/alleexxeeyy/PlayerokAPI/), [FunPayAPI](https://github.com/LIMBODS/FunPayAPI), [FunPayCardinal](https://github.com/sidor0912/FunPayCardinal), and [fpx](https://github.com/funpayx/fpx).

---

<p align="center">
  <i>Built by developers for developers.</i>
</p>
