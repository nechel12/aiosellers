# Migration from upstream aiosellers

The fork keeps the import package `aiosellers` and the familiar adapter names.
Only the **distribution** name is different, so it can coexist with the upstream
PyPI project.

## Install name

| Source | Command |
|---|---|
| GitHub (works now) | `pip install "git+https://github.com/nechel12/aiosellers.git"` |
| GitHub, pinned | `pip install "git+https://github.com/nechel12/aiosellers.git@v0.3.0"` |
| PyPI, after first publish | `pip install aiosellers-nechel12` |
| Upstream (not this fork) | `pip install aiosellers` |

The import package is always:

```python
import aiosellers
```

## What changed in 0.3.0

- `SellerHub.stream()` no longer deadlocks when the consumer leaves the stream
  while the bounded queue is full.
- `Chat.iter_messages()` now works and returns an async iterator. Use it with
  `async for`; do not `await` the method itself.
- `Account.lastItemCreatedAt` accepts `null`, which is required for sellers
  without items.
- Custom Playerok/GGsel `base_url` values without a trailing slash are
  normalized.
- `SQLiteStateStore("~/state.db")` expands `~`.
- `stop()` is available on every client.
- GGsel is part of the shared `Platform`/`EventKind`/`SellerHub` model.
- The distribution is `aiosellers-nechel12`; the import package is still
  `aiosellers`.
- CI now enforces formatting, mypy, coverage and Python 3.12/3.13/3.14.

## Upgrade steps

1. If you installed upstream `aiosellers` from PyPI, uninstall it before
   installing the fork, or use a separate virtual environment.
2. Install the fork from GitHub or `aiosellers-nechel12` when available.
3. Replace any `await chat.iter_messages()` call with `async for message in
   chat.iter_messages():`.
4. If you pass a custom `base_url`, it may now omit the trailing slash.
5. If you use `SQLiteStateStore`, `~` in the path is expanded. Existing
   relative/absolute paths are unchanged.
6. If you use `SellerHub.stream()`, early exits are now safe even when the
   queue is full.
7. Review the [CHANGELOG](../CHANGELOG.md) for the complete list.

## State compatibility

The listener state schema version is still `1`. Existing keys work:

```text
funpay:{account_id}:listener
playerok:{user_id}:listener
ggsel:{seller_id}:listener
```

`MemoryStateStore` is for tests. `SQLiteStateStore` persists chat cursors,
processed message ids and order snapshots; treat the database file as sensitive.

## Need help

Open an issue with the platform, version/tag, Python version and a minimal
reproduction. Do not include API keys, golden keys, access tokens or buyer data.
