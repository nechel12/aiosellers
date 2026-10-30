"""GGsel bot: answer a chat phrase and log new sales.

uv run python examples/ggsel_bot.py
"""

import asyncio

from aiosellers.ggsel import GGsel
from aiosellers.ggsel.events import NewMessageEvent, NewSaleEvent

client = GGsel()


@client.on_message(text="привет")
async def hi(event: NewMessageEvent) -> None:
    await event.chat.send_text("Ну привет...")


@client.on_new_sale()
async def sold(event: NewSaleEvent) -> None:
    print(f"New sale #{event.sale.invoice_id}: {event.sale.product_name}")


asyncio.run(client.start_polling())
