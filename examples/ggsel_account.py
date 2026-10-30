"""Print the GGsel balance and the latest receipts.

uv run python examples/ggsel_account.py
"""

import asyncio

from aiosellers.ggsel import GGsel


async def main() -> None:
    async with GGsel() as client:
        balance = await client.account.balance()
        print(f"Seller id: {client.seller_id}")
        print(f"Free: {balance.free} | Locked: {balance.locked} | Plus: {balance.plus}")

        receipts = await client.account.receipts(count=10)
        for item in receipts.items:
            print(f"{item.date} | {item.operation_type} | {item.price} {item.currency}")


if __name__ == "__main__":
    asyncio.run(main())
