# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added

- `aiosellers.core`: `Platform`, capability matrix, `EventKind`/`HubEvent` and `SellerHub`
  for running several sessions with one merged event stream.
- `stop()` on both clients to end `start_polling()` from another task.
- `max_concurrent_requests` for FunPay instead of one global request lock.
- `py.typed` marker, package metadata and a dev dependency group.
- CI workflow running lint and tests.
- `StateStore` protocol with `MemoryStateStore` and `SQLiteStateStore`; both listeners
  persist cursors and dedup windows and recover them after a restart.
- Bounded `sent_history_limit` (FunPay) and `processed_history_limit` (Playerok) windows.
- `bot_mark` option to disable the invisible FunPay marker on outgoing messages and reviews.

### Fixed

- Playerok identity map now updates cached entities in place, including on `force_refresh`.
- Playerok API facades raise a clear error when the client is not started.
- `ItemAPI._create_my_item` no longer fails on unknown schema types.
- `ItemAPI.publish`/`set_normal_priority`/`set_premium_priority` select priority by type instead of list position.
- `ChatAPI.send_message` raises `MessageNotDeliveredError` when Playerok returns no message.
- `Playerok.download` uses an unauthenticated client and an allowlist of trusted hosts.
- Playerok transport checks HTTP statuses, handles 429/`Retry-After` and retries GET requests with backoff.
- Playerok WS listener handles ack/ping/pong/error/complete, reconnects with backoff and reconciles missed events.
- Playerok review polling now works with `messages=False`.
- Playerok schema fallbacks log a warning instead of silently accepting drifted payloads.
- Stale persisted GraphQL queries raise `PersistedQueryExpired` with an actionable message.
- Playerok example user agents now match the Chrome 143 client hints.
- Playerok `start()` is atomic: a failed `get_me()` closes the transport and can be retried.
- FunPay polls order lists only when runner counters change, with a periodic full resync.
- FunPay reads all order pages instead of dropping diffs on large or shrunk pages.
- FunPay chat history is paged until the stored cursor and retried after transient failures.
- `FunPay.chats.list()` no longer clears the identity map and breaks existing references.
- FunPay rate limits honour `Retry-After` and retry up to three times.
- FunPay GET requests retry 5xx and network errors with exponential backoff; POST stays single-shot.
- Event handlers run with a per-handler timeout and limited concurrency on both platforms.
- With a configured state store, listeners no longer replay initial snapshots or duplicate
  messages and deals after a restart.
