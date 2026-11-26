# Migration from upstream aiosellers

The fork retains the `aiosellers` import package and the upstream adapter names.
The **distribution** name is different, but both distributions install the
same import package. Uninstall upstream first or use a separate environment;
do not install both in one environment.

## Install name

| Source | Command |
|---|---|
| PyPI | `pip install aiosellers-nechel12` |
| GitHub | `pip install "git+https://github.com/nechel12/aiosellers.git"` |
| GitHub, pinned | `pip install "git+https://github.com/nechel12/aiosellers.git@<tag-or-commit>"` |
| Upstream (not this fork) | `pip install aiosellers` |

The import package is always:

```python
import aiosellers
```

## Updating to 0.4.0

- Set `PlayerokClientConfig(include_own=True)` if the application handles the
  seller's own messages. The listener no longer emits them by default.
- Identity-map entries can be evicted once a cache reaches its limit. Set
  `identity_map_limit=None` if the application needs identity to be preserved
  for the entire session.
- Send FunPay text and images separately. Remove `leave_as_unread=True` from
  send calls. FunPay now raises `ValueError` for those unsupported options.
- FunPay `orders.iter(limit=...)` now caps the total number of orders yielded,
  not the number of orders per page.

## What changed in 0.3.0

- `SellerHub.stream()` no longer deadlocks when the consumer leaves the stream
  while the bounded queue is full.
- `Chat.iter_messages()` returns an async iterator. Use it with
  `async for`; do not `await` the method itself.
- `Account.lastItemCreatedAt` accepts `null`, which is required for sellers
  without items.
- Custom PlayerOK and GGsel `base_url` values without a trailing slash are
  normalized.
- `SQLiteStateStore("~/state.db")` expands `~`.
- `stop()` is available on every client.
- GGsel is part of the shared `Platform`/`EventKind`/`SellerHub` model.
- The distribution is `aiosellers-nechel12`; the import package is still
  `aiosellers`.
- CI checks formatting, types, and coverage on Python 3.12, 3.13, and 3.14.

## Upgrade steps

1. Uninstall upstream `aiosellers` before installing the fork, or use a separate
   virtual environment.
2. Install the fork from PyPI or GitHub.
3. Replace any `await chat.iter_messages()` call with `async for message in
   chat.iter_messages():`.
4. A custom `base_url` may now omit the trailing slash.
5. `SQLiteStateStore` expands `~` in the path. Existing relative/absolute paths
   are unchanged.
6. `SellerHub.stream()` early exits are now safe even when the queue is full.
7. Review the [CHANGELOG](../CHANGELOG.md) for the complete list.

## State compatibility

The listener state schema remains at version `1` and uses the following keys:

```text
funpay:{account_id}:listener
playerok:{user_id}:listener
ggsel:{seller_id}:listener
```

`MemoryStateStore` is for tests. `SQLiteStateStore` persists chat cursors,
processed message IDs and order statuses. FunPay state can also contain message
previews; treat the database file as sensitive.

## Need help

Use the [bug report form](https://github.com/nechel12/aiosellers/issues/new/choose)
with the platform, installed package version or Git tag, Python version, and a
minimal reproduction. Do not include API keys, golden keys, access tokens, or
buyer data. Report vulnerabilities through [SECURITY.md](../SECURITY.md).
