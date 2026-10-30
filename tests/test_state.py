import asyncio
import tempfile
import unittest
from pathlib import Path

from aiosellers import MemoryStateStore, SQLiteStateStore, StateStore


class MemoryStateStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_roundtrip_does_not_alias_the_caller_value(self):
        store = MemoryStateStore()
        value = {"cursors": [1, 2], "nested": {"ok": True}}
        await store.set("key", value)
        value["cursors"].append(3)

        self.assertEqual(
            await store.get("key"), {"cursors": [1, 2], "nested": {"ok": True}}
        )

        await store.set("key", {"other": 1})
        self.assertEqual(await store.get("key"), {"other": 1})

    async def test_missing_and_deleted_keys(self):
        store = MemoryStateStore()
        self.assertIsNone(await store.get("missing"))
        await store.set("key", [1])
        await store.delete("key")
        self.assertIsNone(await store.get("key"))
        await store.delete("key")

    async def test_satisfies_protocol(self):
        store = MemoryStateStore()
        self.assertIsInstance(store, StateStore)
        await store.close()


class SQLiteStateStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_survives_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.db"
            store = SQLiteStateStore(path)
            await store.set("key", {"version": 1, "ids": ["a"]})
            await store.close()

            reopened = SQLiteStateStore(path)
            self.assertEqual(
                await reopened.get("key"), {"version": 1, "ids": ["a"]}
            )

            await reopened.set("key", {"version": 2})
            self.assertEqual(await reopened.get("key"), {"version": 2})

            await reopened.delete("key")
            self.assertIsNone(await reopened.get("key"))
            await reopened.close()

    async def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "dir" / "state.db"
            store = SQLiteStateStore(path)
            await store.set("key", "value")
            await store.close()
            self.assertTrue(path.exists())

    async def test_concurrent_access(self):
        store = SQLiteStateStore(":memory:")
        await asyncio.gather(*(store.set(f"key-{index}", index) for index in range(50)))
        values = await asyncio.gather(
            *(store.get(f"key-{index}") for index in range(50))
        )
        self.assertEqual(values, list(range(50)))
        await store.close()

    async def test_operations_after_close_fail(self):
        store = SQLiteStateStore(":memory:")
        await store.close()
        await store.close()
        with self.assertRaises(RuntimeError):
            await store.get("key")
        self.assertIsInstance(store, StateStore)


if __name__ == "__main__":
    unittest.main()
