# All-In-One Sellers API

[English](README.md) | **Русский**

[![CI](https://github.com/nechel12/aiosellers/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/nechel12/aiosellers/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/nechel12/aiosellers)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/aiosellers-nechel12)](https://pypi.org/project/aiosellers-nechel12/)
[![Last commit](https://img.shields.io/github/last-commit/nechel12/aiosellers)](https://github.com/nechel12/aiosellers/commits/main)
[![Fork of Zewsic/aiosellers](https://img.shields.io/badge/fork-Zewsic%2Faiosellers-blueviolet?logo=github)](https://github.com/Zewsic/aiosellers)
[![Security policy](https://img.shields.io/badge/security-policy-green)](SECURITY.md)
[![CodeQL](https://github.com/nechel12/aiosellers/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/nechel12/aiosellers/security/code-scanning)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)

## Содержание

- [Установка](#установка)
- [Документация](#документация)
- [Настройка](#настройка)
- [Быстрый старт: PlayerOK](#быстрый-старт-playerok)
- [Быстрый старт: FunPay](#быстрый-старт-funpay)
- [Быстрый старт: GGsel](#быстрый-старт-ggsel)
- [Хаб для нескольких аккаунтов](#хаб-для-нескольких-аккаунтов)
- [Персистентное состояние листенеров](#персистентное-состояние-листенеров)
- [Примеры](#примеры)
- [Статус разработки: PlayerOK](#статус-разработки-playerok)
- [Статус разработки: FunPay](#статус-разработки-funpay)
- [Статус разработки: GGsel](#статус-разработки-ggsel)
- [Ограничения](#ограничения)
- [Безопасность](#безопасность)
- [Разработка](#разработка)
- [Связанные проекты](#связанные-проекты)
- [Участие](#участие)
- [Лицензия](#лицензия)
- [Поддержать проект](#поддержать-проект)

Асинхронная Python-обёртка для цифровых торговых площадок: **FunPay**,
**PlayerOK** и **GGsel**. Один пакет, одна модель событий, один хаб для
нескольких аккаунтов.

> [!NOTE]
> Это **форк** проекта
> [Zewsic/aiosellers](https://github.com/Zewsic/aiosellers), который
> поддерживает [@nechel12](https://github.com/nechel12). В форке добавлены
> адаптер GGsel, общий слой `aiosellers.core` (платформы, возможности,
> `SellerHub`), персистентное состояние листенеров, усиление транспорта и
> тесты. Пакет `aiosellers` на PyPI публикует upstream-проект, и он **не**
> содержит этих изменений; форк распространяется как `aiosellers-nechel12`
> (см. [Установку](#установка)).

Стек: **Python 3.12+**, asyncio, Pydantic v2, TLS-запросы, websockets и SQLite.
Библиотека общается с площадками напрямую: FunPay — HTTP-формы и разбор HTML,
PlayerOK — GraphQL и WebSocket-подписки, GGsel — официальный Seller API V1.
В пути запросов нет прокси-сервиса, телеметрии или стороннего бэкенда.

> Статус: pre-1.0. Ядро, транспорт и листенеры покрыты тестами, публичный API
> описан в docstring'ах и README, а покрытие высокоуровневых обёрток ещё растёт.
> В минорных релизах поведение ещё может меняться. См. [CHANGELOG.md](CHANGELOG.md).

## Установка

Установка форка с GitHub:

```bash
pip install "git+https://github.com/nechel12/aiosellers.git"
```

или через uv:

```bash
uv add "git+https://github.com/nechel12/aiosellers.git"
```

Имя дистрибутива — `aiosellers-nechel12`, импортируемый пакет по-прежнему
`aiosellers`. Установка с PyPI:

```bash
pip install aiosellers-nechel12
```

`pip install aiosellers` устанавливает **upstream-пакет** с PyPI, а не этот
форк. Для воспроизводимых установок фиксируй коммит или тег:

```bash
pip install "git+https://github.com/nechel12/aiosellers.git@<tag>"
```

**Требования:** Python 3.12+.

## Документация

- [Обзор API](docs/API.md) — публичные точки входа и модули.
- [Миграция с upstream](docs/MIGRATION.md) — имя установки, изменения поведения
  и шаги обновления.

## Настройка

Токены можно передать в конструктор или через переменные окружения:

```bash
export PLAYEROK_ACCESS_TOKEN="your_token_here"
export FUNPAY_GOLDEN_KEY="your_golden_key"
export GGSEL_API_KEY="your_api_key"
export GGSEL_SELLER_ID="123456"
```

`Playerok()`, `FunPay()` и `GGsel()` читают эти переменные. Учётные данные
можно передать и напрямую: `Playerok("token")`, `FunPay("golden-key")` или
`GGsel(GGselClientConfig(api_key="key", seller_id=123456))`.

Укажи `bot_mark=False` в `FunPayClientConfig`, чтобы не добавлять невидимую
бот-метку в исходящие сообщения и отзывы.

Все адаптеры принимают необязательный URL прокси:

```python
FunPay(FunPayClientConfig(golden_key="...", proxy="http://user:pass@proxy:8080"))
Playerok(PlayerokClientConfig(access_token="...", proxy="http://proxy:8080"))
GGsel(GGselClientConfig(api_key="...", seller_id=123456, proxy="http://proxy:8080"))
```

Playerok использует его для HTTP, загрузок, скачиваний и WebSocket-подписок;
GGsel — для ApiLogin и всех запросов Seller API. Учётные данные прокси не
попадают в `repr` конфигурации.

## Быстрый старт: PlayerOK

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

## Быстрый старт: FunPay

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

## Быстрый старт: GGsel

Адаптер GGsel использует официальный Seller API V1: клиент подписывает запрос
входа API-ключом, хранит access token и опрашивает чаты, продажи и отзывы,
потому что у GGsel нет вебхуков.

```python
import asyncio
from aiosellers.ggsel import GGsel

async def main() -> None:
    # Или GGselClientConfig(api_key="...", seller_id=123456)
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

`GGsel()` читает `GGSEL_API_KEY` и `GGSEL_SELLER_ID`; чтобы переопределить
значения, передай `GGselClientConfig`. `client.seller_id` появляется после
запуска клиента, а `client.products.update_price()` / `update_prices()`
возвращают id задачи, который можно проверить через
`client.products.task_status()`.

## Хаб для нескольких аккаунтов

`SellerHub` запускает несколько сессий FunPay, Playerok и GGsel вместе и
объединяет их события в один поток. Каждый элемент несёт платформу и id
сессии, а полезная нагрузка остаётся исходным типизированным событием.

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

`item.kind` — переносимый `EventKind` (`MESSAGE`, `REVIEW`, `ORDER`, `DEAL`, ...).
`Session.capabilities` показывает, что поддерживает платформа, чтобы общий код
не ветвился по её имени. У клиентов также есть `stop()`, который завершает
`start_polling()` из другой задачи.

## Персистентное состояние листенеров

Передай `StateStore` в конфиг клиента, чтобы сохранять курсоры чатов,
обработанные id сообщений и снимки заказов между перезапусками процесса. Без
хранилища листенеры собирают состояние заново при каждом запуске и отдают
только начальные снимки.

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

    # ... запускаем клиентов ...

    await store.close()

asyncio.run(main())
```

`MemoryStateStore` повторяет ту же семантику в памяти процесса — удобно для
тестов. Ключи состояния: `funpay:{account_id}:listener`,
`playerok:{user_id}:listener` и `ggsel:{seller_id}:listener`; битый снимок
игнорируется с предупреждением, а неудачная запись не останавливает опрос.

## Примеры

Запускаемые примеры лежат в [`examples/`](examples/).

| Скрипт | Что делает |
|:-------|:-----------|
| [`playerok_account.py`](examples/playerok_account.py) | Профиль и баланс |
| [`playerok_chats.py`](examples/playerok_chats.py) | Непрочитанные чаты и последние сообщения |
| [`playerok_deals.py`](examples/playerok_deals.py) | Оплаченные и отправленные сделки |
| [`playerok_market.py`](examples/playerok_market.py) | Поиск товаров и средняя цена |
| [`playerok_bot.py`](examples/playerok_bot.py) | Команды и события сделок |
| [`transactions.py`](examples/transactions.py) | Ожидающие транзакции и карты |
| [`funpay_account.py`](examples/funpay_account.py) | Профиль, баланс, транзакции |
| [`funpay_orders.py`](examples/funpay_orders.py) | Продажи и карточка заказа |
| [`funpay_chats.py`](examples/funpay_chats.py) | Чаты и история сообщений |
| [`funpay_lots.py`](examples/funpay_lots.py) | Твои лоты |
| [`funpay_bot.py`](examples/funpay_bot.py) | Новый заказ и ответ в чате |
| [`funpay_reviews.py`](examples/funpay_reviews.py) | Ответ на новый отзыв |
| [`funpay_backtest.py`](examples/funpay_backtest.py) | Воспроизведение сохранённой истории чата |
| [`ggsel_account.py`](examples/ggsel_account.py) | Баланс и чеки |
| [`ggsel_bot.py`](examples/ggsel_bot.py) | Ответы в чатах и новые продажи |

```bash
uv run python examples/playerok_account.py
uv run python examples/funpay_account.py
uv run python examples/ggsel_account.py
```

## Статус разработки: PlayerOK

| Модуль                 | Raw API | High-level |
|:-----------------------|:-------:|:----------:|
| **Account**            |    ✅    |     ✅      |
| **Games / Categories** |    ✅    |     ✅      |
| **Items**              |    ✅    |     ✅      |
| **Deals**              |    ✅    |     ✅      |
| **Chats**              |    ✅    |     ✅      |
| **Transactions**       |    ✅    |     ✅      |
| **Event Feed**         |    ✅    |     ✅      |

## Статус разработки: FunPay

| Модуль            | Raw API | High-level |
|:------------------|:-------:|:----------:|
| **Account**       |    ✅    |     ✅      |
| **Balance**       |    ✅    |     ✅      |
| **Orders / Sales**|    ✅    |     ✅      |
| **Chats**         |    ✅    |     ✅      |
| **Lots**          |    ✅    |     ✅      |
| **Reviews**       |    ✅    |     ✅      |
| **Event Feed**    |    ✅    |     ✅      |

## Статус разработки: GGsel

GGsel покрыт официальным Seller API V1 (`https://seller.ggsel.com/`). Вебхуков
нет, поэтому листенер опрашивает чаты, продажи и отзывы с персистентными
курсорами, если настроен `StateStore`.

| Модуль                  | Raw API | High-level |
|:------------------------|:-------:|:----------:|
| **Account / Balance**   |    ✅    |     ✅      |
| **Receipts**            |    ✅    |     ✅      |
| **Categories**          |    ✅    |     ✅      |
| **Products / Prices**   |    ✅    |     ✅      |
| **Sales / Purchases**   |    ✅    |     ✅      |
| **Chats**               |    ✅    |     ✅      |
| **Reviews**             |    ✅    |     ✅      |
| **Event Feed**          |    ✅    |     ✅      |

Пока не реализованы: V2 offer API (создание и редактирование офферов) и
устаревший XML-эндпоинт `/xml/shop_search.asp`. V1-адаптера достаточно для
обработки заказов, переписки, отзывов и обновления цен.

## Ограничения

- У FunPay и PlayerOK нет официальных seller API; эти адаптеры используют те же
  HTTP-формы, GraphQL-документы и WebSocket-потоки, что и сайты. Изменения на
  площадках могут их сломать, поэтому фиксируй версию и следи за
  [CHANGELOG](CHANGELOG.md).
- GGsel реализован только для Seller API V1.
- Библиотека — клиент, а не планировщик: цикл событий, деплой, масштабирование
  и присмотр за ботами остаются на тебе.
- Правила площадок, лимиты и блокировки аккаунтов вне контроля библиотеки.
  Используй API ответственно и на свой риск.

## Безопасность

Отчёты об уязвимостях — в [SECURITY.md](SECURITY.md). Библиотека хранит токены
в памяти, передаёт их только эндпоинтам площадок и держит состояние листенеров
в переданном тобой `StateStore`. Не логируй учётные данные и защищай файл
SQLite, если в нём есть метаданные чатов.

Сообщай об уязвимостях через приватные GitHub-адвизори, а не в публичном
issue.

## Разработка

Нужны Python 3.12+ и [uv](https://docs.astral.sh/uv/).

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

Структура: `aiosellers/core` (платформы, события, хаб, хранилища состояния),
`aiosellers/funpay`, `aiosellers/playerok`, `aiosellers/ggsel` (в каждом —
`api`, `raw`, `schemas`, `entities`, транспорт и листенер), `tests/` и
`examples/`.

## Связанные проекты

- [Zewsic/aiosellers](https://github.com/Zewsic/aiosellers) — upstream-проект,
  от которого сделан этот форк.
- [PlayerokAPI](https://github.com/alleexxeeyy/PlayerokAPI/) — референс по API
  PlayerOK.
- [FunPayAPI](https://github.com/LIMBODS/FunPayAPI) — референс по API FunPay.
- [FunPayCardinal](https://github.com/sidor0912/FunPayCardinal) — FunPay-бот на
  тех же идеях.
- [fpx](https://github.com/funpayx/fpx) — ещё один клиент FunPay.

## Участие

Багрепорты и pull request'ы приветствуются. Процесс разработки описан в
[CONTRIBUTING.md](CONTRIBUTING.md). Участвуя, ты соглашаешься с
[Кодексом поведения](CODE_OF_CONDUCT.md). Перед отправкой изменений запусти
`uv run ruff check .` и `uv run pytest -q`. Об уязвимостях сообщай через
[SECURITY.md](SECURITY.md), а не в публичном issue. Заметки о релизах — в
[CHANGELOG.md](CHANGELOG.md); мейнтейнерам — [RELEASING.md](RELEASING.md).

## Лицензия

Код распространяется под Apache-2.0; см. [LICENSE](LICENSE). Копирайт и
лицензионные уведомления upstream сохранены. Пакет `aiosellers` на PyPI
поддерживает upstream-проект, он не связан с этим форком.

---

## Поддержать проект

All-In-One Sellers API — бесплатный проект с открытым исходным кодом. Если он
экономит тебе время, ты можешь поддержать разработку:

<p align="center">
  <a href="https://boosty.to/nechel12/donate">
    <img src="https://img.shields.io/badge/Boosty-Donate-F15F2C?style=for-the-badge&logo=boosty&logoColor=white" alt="Donate via Boosty">
  </a>
</p>

### Криптовалюта

| Сеть | Адрес |
|:-----|:------|
| **TRON** | `TMM2Cdm4tJx1nKRRq5RCBcdwfn9cHuJZy9` |
| **TON** | `UQBlVvOfTleWn4pkY384mYWiGyhdHBryoC_N1Si1OSWAxPKl` |
| **Bitcoin** | `bc1qagjtnutjya2rss3u3ls8ur7qk0u7zutc6t6fwc` |
| **BNB Smart Chain** | `0x423aF840f67355371bf32480744A84069dfab5ff` |

> [!WARNING]
> Отправляй только соответствующий актив в указанной сети. Переводы в другую
> сеть восстановить нельзя.
