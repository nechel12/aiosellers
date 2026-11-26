# All-In-One Sellers API

[English](README.md) | **Русский**

Асинхронные Python-клиенты для **FunPay**, **PlayerOK** и **GGsel** с общим
потоком событий для нескольких аккаунтов и сохранением состояния между запусками.

[![CI](https://github.com/nechel12/aiosellers/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/nechel12/aiosellers/actions/workflows/ci.yml)
[![CodeQL](https://github.com/nechel12/aiosellers/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/nechel12/aiosellers/actions/workflows/codeql.yml)
[![PyPI](https://img.shields.io/pypi/v/aiosellers-nechel12)](https://pypi.org/project/aiosellers-nechel12/)
[![Версии Python в CI](https://img.shields.io/pypi/pyversions/aiosellers-nechel12)](https://pypi.org/project/aiosellers-nechel12/)
[![Лицензия](https://img.shields.io/github/license/nechel12/aiosellers)](LICENSE)

## Содержание

- [Установка](#установка)
- [Документация](#документация)
- [Настройка](#настройка)
- [Быстрый старт: PlayerOK](#быстрый-старт-playerok)
- [Быстрый старт: FunPay](#быстрый-старт-funpay)
- [Быстрый старт: GGsel](#быстрый-старт-ggsel)
- [Хаб для нескольких аккаунтов](#хаб-для-нескольких-аккаунтов)
- [Состояние слушателей между запусками](#состояние-слушателей-между-запусками)
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

> [!NOTE]
> Это **форк** проекта
> [Zewsic/aiosellers](https://github.com/Zewsic/aiosellers), который
> поддерживает [@nechel12](https://github.com/nechel12). В форке добавлены
> адаптер GGsel, общий слой `aiosellers.core` (платформы, возможности,
> `SellerHub`), сохранение состояния слушателей, изменения транспорта и
> тесты. Пакет `aiosellers` на PyPI публикует исходный проект; он не
> содержит этих изменений. Форк распространяется как `aiosellers-nechel12`
> (см. [Установку](#установка)).

Стек: **Python 3.12+**, asyncio, Pydantic v2, TLS-запросы, websockets и SQLite.
Библиотека общается с площадками напрямую: FunPay — HTTP-формы и разбор HTML,
PlayerOK — GraphQL и WebSocket-подписки, GGsel — официальный Seller API V1.
Библиотека не требует отдельного сервера или прокси-сервиса и не собирает
телеметрию.

> Статус: до версии 1.0. Тесты покрывают ядро, транспорт и слушатели
> событий. Покрытие высокоуровневого API пока неполное. Поведение может
> меняться в минорных выпусках. См. [CHANGELOG.md](CHANGELOG.md).

## Установка

Требуется **Python 3.12+**. Установка опубликованного форка с PyPI:

```bash
pip install aiosellers-nechel12
# Or, in a uv project:
uv add aiosellers-nechel12
```

Импорт библиотеки — `aiosellers`. Команда `pip install aiosellers` установит
**upstream**, а не этот форк. Используйте отдельные окружения: оба дистрибутива
устанавливают один и тот же импортируемый пакет.

Чтобы попробовать изменения до публикации на PyPI, установите версию с GitHub:

```bash
pip install "git+https://github.com/nechel12/aiosellers.git"
```

Добавьте `@<тег-или-коммит>` к адресу, чтобы зафиксировать версию с GitHub.

## Документация

- [Обзор API](docs/API.md) — публичные точки входа и модули.
- [Переход с исходного проекта](docs/MIGRATION.md) — имя дистрибутива, изменения
  поведения и порядок обновления.

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

Параметр `bot_mark=False` в `FunPayClientConfig` отключает невидимую метку
в исходящих сообщениях и отзывах.

Параметры `image` и `photo` могут принимать `bytes`, идентификатор загруженного
файла, URL или локальный путь в зависимости от метода и площадки. Локальный
файл читает процесс, использующий библиотеку. Чтобы ограничить доступ к файлам,
задайте `AIOSELLERS_MEDIA_ROOTS`:

```bash
# List of allowed directories separated by os.pathsep.
export AIOSELLERS_MEDIA_ROOTS="/srv/app/media"
# An empty value disables local file access.
export AIOSELLERS_MEDIA_ROOTS=""
```

Если переменная не задана, доступны все пути, которые процесс может читать.
При заданной переменной попытка открыть путь за пределами разрешённых
каталогов вызывает `MediaPathNotAllowedError` до чтения файла.

Все адаптеры принимают необязательный URL прокси:

```python
FunPay(FunPayClientConfig(golden_key="...", proxy="http://user:pass@proxy:8080"))
Playerok(PlayerokClientConfig(access_token="...", proxy="http://proxy:8080"))
GGsel(GGselClientConfig(api_key="...", seller_id=123456, proxy="http://proxy:8080"))
```

PlayerOK использует его для HTTP-запросов, отправки и скачивания файлов,
а также WebSocket-подписок;
GGsel — для ApiLogin и всех запросов Seller API. Учётные данные прокси не
попадают в `repr` конфигурации.

PlayerOK по умолчанию пропускает собственные сообщения продавца. Чтобы получать
их, задайте `include_own=True` в `PlayerokClientConfig`, `listen()` или
`start_polling()`. Для каждого типа сущностей у клиента свой кэш с лимитом
в 5000 записей по умолчанию (`identity_map_limit`); `None` снимает ограничение.
`listen()` и `start_polling()` принимают опции слушателя, например
`order_page_limit`, `chat_history_batches` для FunPay и лимиты страниц/истории
для GGsel.

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
    # Or pass GGselClientConfig(api_key="...", seller_id=123456).
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

`GGsel()` читает `GGSEL_API_KEY` и `GGSEL_SELLER_ID`. Значения можно
переопределить через `GGselClientConfig`. `client.seller_id` становится
доступен после запуска клиента. Методы `client.products.update_price()` и
`update_prices()` возвращают идентификатор задачи, статус которой можно
проверить через
`client.products.task_status()`.

## Хаб для нескольких аккаунтов

`SellerHub` запускает несколько сессий FunPay, PlayerOK и GGsel и объединяет
их события в один поток. Каждый элемент содержит платформу, идентификатор
сессии и исходное событие с сохранением его типа.

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

`item.kind` указывает общий для адаптеров тип события `EventKind` (`MESSAGE`,
`REVIEW`, `ORDER`, `DEAL`, ...). `Session.capabilities` позволяет проверять
возможности площадки по флагам, а не по её имени. Метод `stop()` завершает
`start_polling()` из другой задачи.

## Состояние слушателей между запусками

Укажите `StateStore` в конфигурации клиента, чтобы сохранять курсоры чатов,
обработанные ID сообщений и статусы заказов между перезапусками процесса. Без
хранилища слушатели по-прежнему выдают новые события, но собирают начальное
состояние заново при каждом запуске. Восстановление ограничено глубиной истории
и опроса площадки; обработчики должны безопасно переносить повторы событий.

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

`MemoryStateStore` хранит данные в памяти процесса и подходит для тестов.
Ключи состояния: `funpay:{account_id}:listener`, `playerok:{user_id}:listener`
и `ggsel:{seller_id}:listener`. Некорректный снимок состояния игнорируется с
предупреждением. Ошибка записи не останавливает опрос.

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
| [`funpay_lots.py`](examples/funpay_lots.py) | Лоты продавца |
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

Адаптер GGsel использует официальный Seller API V1 (`https://seller.ggsel.com/`).
Вместо вебхуков он опрашивает чаты, продажи и отзывы. Если задан `StateStore`,
адаптер сохраняет курсоры между запусками.

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

Не поддерживаются: Offer API V2 (создание и редактирование предложений) и
устаревший XML-эндпоинт `/xml/shop_search.asp`.

## Ограничения

- Адаптеры FunPay и PlayerOK используют неофициальные интерфейсы сайтов:
  HTTP-формы, GraphQL и WebSocket-потоки. Изменения этих интерфейсов могут
  нарушить совместимость. См. [CHANGELOG](CHANGELOG.md).
- Адаптер GGsel поддерживает только Seller API V1.
- Библиотека не управляет развёртыванием, планированием,
  масштабированием или контролем работы ботов.
- Площадки устанавливают правила использования, ограничения частоты
  запросов и правила блокировки аккаунтов.

## Безопасность

Сообщайте об уязвимостях через
[приватную форму GitHub](https://github.com/nechel12/aiosellers/security/advisories/new),
а не в публичном issue. Подробности — в [SECURITY.md](SECURITY.md).
Используйте только доверенные адреса API и прокси. Перед публикацией очищайте
логи от чувствительных данных и защищайте базу состояния: в ней могут быть
ID чатов, а для FunPay — ещё и превью сообщений.

## Разработка

Нужны Python 3.12+ и [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy aiosellers
uv run pytest -q --cov=aiosellers --cov-fail-under=65

uv run python examples/funpay_account.py
uv build
```

Структура: `aiosellers/core` (платформы, события, хаб, хранилища состояния),
`aiosellers/funpay`, `aiosellers/playerok`, `aiosellers/ggsel` (в каждом —
`api`, `raw`, `schemas`, `entities`, транспорт и слушатель событий), `tests/` и
`examples/`.

## Связанные проекты

- [Zewsic/aiosellers](https://github.com/Zewsic/aiosellers) — исходный проект.
- [PlayerokAPI](https://github.com/alleexxeeyy/PlayerokAPI/) — библиотека для
  PlayerOK.
- [FunPayAPI](https://github.com/LIMBODS/FunPayAPI) — библиотека для FunPay.
- [FunPayCardinal](https://github.com/sidor0912/FunPayCardinal) — бот для FunPay.
- [fpx](https://github.com/funpayx/fpx) — ещё один клиент FunPay.

## Участие

Для публичных отчётов об ошибках и предложений используйте
[формы GitHub Issues](https://github.com/nechel12/aiosellers/issues/new/choose).
Локальные проверки и порядок подачи pull request описаны в
[CONTRIBUTING.md](CONTRIBUTING.md), правила участия — в
[Кодексе поведения](CODE_OF_CONDUCT.md). Порядок публикации версий описан в
[RELEASING.md](RELEASING.md).

## Лицензия

Код распространяется по лицензии Apache-2.0. См. [LICENSE](LICENSE) и
[NOTICE](NOTICE) с перечнем изменений относительно исходного проекта.
Уведомления об авторских правах и лицензии сохранены. На PyPI пакет
`aiosellers` относится к исходному проекту, а `aiosellers-nechel12` — к форку.

---

## Поддержать проект

Проект распространяется с открытым исходным кодом. Финансовая поддержка
добровольна:

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
> Отправляйте только соответствующий актив в указанной сети. Перевод в
> другую сеть может быть невозможно восстановить.
