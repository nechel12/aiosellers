# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

## [0.4.0] - 2026-11-26

### Changed

- PlayerOK ignores the seller's own messages by default. Set
  `include_own=True` to continue receiving them.
- Identity maps are shared and bounded by default. Set `identity_map_limit=None`
  to retain cached entities for the entire session.
- FunPay rejects sending text and an image in one message and passing
  `leave_as_unread=True` with `ValueError`. These options were previously ignored.
- FunPay `OrderAPI.iter(limit=...)` applies the limit to the entire iterator
  rather than to each page.

### Fixed

- PlayerOK queues active deals for review polling at startup and keeps them
  eligible beyond the previous 15-minute window. It records review IDs to avoid
  re-emitting existing reviews. Checkpoint migration preserves pending reviews.
- After reconnecting, PlayerOK replays unprocessed messages within the history
  window and subscribes to newly discovered chats. Resuming from a checkpoint
  no longer marks messages missed during downtime as seen. Concurrent collectors
  deduplicate payment events.
- PlayerOK image messages produce `NewMessageEvent`, and `NewReviewEvent`
  carries the review.
- PlayerOK filtered chat/deal pagination no longer stops after the first page
  when every row is filtered out.
- PlayerOK `Item.game_id`, `Chat.get_deals().item_id`, missing-user raw lookups,
  false GraphQL boolean filters, `remove_item` results and `GameAPI.limit` are
  fixed.
- PlayerOK `close()` now stops an active listener; `aclose()` wakes a blocked
  event consumer; state loading during `listen()` is retried.
- PlayerOK sends one WebSocket `Origin` header, preserves the scheme and port
  of custom base URLs, and honors an explicit `ws_url`. Cloudflare detection no
  longer matches ordinary chat text.
- FunPay review `stars` filters force a fresh order lookup instead of using a
  cached shortcut order.
- FunPay chat/order gap pagination now grows its page window until the gap is
  collected, and listener options are exposed through `listen()`. Sparse
  message IDs no longer stall new chats, and item descriptions no longer
  affect refund status parsing.
- FunPay identity-map merges are partial for shortcut rows and full for detail
  rows, so list refreshes no longer erase order details.
- FunPay message history pagination, Ukrainian
  system-message classification, locale-independent stale-cookie detection,
  custom-host cookie storage, badge parsing and malformed `sent` state are fixed.
- Concurrent calls share FunPay startup.
- GGsel partial product updates no longer erase fields, new chats only replay
  recent history, one malformed row no longer stops polling, chat lookup covers
  a wider window, and history/category pagination is bounded correctly. Active
  chat cursors survive a small `state_limit` without repeated initialization
  events.
- `SellerHub` auto-generated session ids skip explicitly registered ids.
- Event listeners commit durable state after events are yielded by the public
  `listen()` path, reducing event loss on crashes. For PlayerOK, adding events
  to the internal queue does not commit them, and events from a single payment
  message are committed together.

## [0.3.7] - 2026-11-18

### Changed

- Updated `uv.lock` to match the package version and the `soupsieve` 4.0
  security update (CVE-2026-126190). CI, dependency audit, CodeQL, and the wheel
  build passed for this release.

## [0.3.6] - 2026-11-18

### Fixed

- GraphQL multipart mutations with zero attachments are now sent as form data
  instead of JSON. `createItem` always wraps its query in `operations`/`map`;
  sending that as JSON caused PlayerOK to reject it with
  "GraphQL operations must contain a non-empty `query` or a `persistedQuery` extension".

## [0.3.5] - 2026-11-18

### Fixed

- PlayerOK public item search now sends only `APPROVED` status; the previous
  multi-status filter made the live API return an empty page.
- Non-JSON GraphQL responses raise `GraphQLError` instead of propagating a
  `JSONDecodeError` from `tls_requests`.
- HTTP errors now include a short response-body excerpt for debugging PlayerOK
  400/429/500 replies.
- `Playerok.start_polling()` no longer closes the session on unexpected event-feed
  failures; explicit `stop()`/cancellation still closes it.

## [0.3.4] - 2026-10-31

### Added

- `AIOSELLERS_MEDIA_ROOTS` restricts local file access during media uploads.
  FunPay and PlayerOK read local `str` and `Path` arguments from the process's
  filesystem. When the variable is unset, any readable path is allowed. When it
  is set, paths outside the listed roots raise `MediaPathNotAllowedError`. An
  empty value disallows all local paths.

## [0.3.3] - 2026-10-31

### Changed

- Minimum `lxml` is now 6.0.2 and minimum `websockets` is now 16. These are the
  first releases with Python 3.14 support, including cp314 wheels. The test suite
  passes with these minimums and with the latest lxml 6.1.3 and websockets 17.4 on
  Python 3.12 and 3.14.
- The `v0.3.3` release tag was signed with a dedicated SSH key.

## [0.3.2] - 2026-10-30

### Added

- `proxy` support for GGsel and Playerok. GGsel routes ApiLogin and all Seller API
  requests through the proxy; Playerok routes HTTP, uploads, downloads, remote
  images and WebSocket subscriptions through it. Proxy credentials are hidden from
  config `repr`.

### Changed

- The `websockets` dependency floor is now 15, the first release with WebSocket
  proxy support. Without an explicit proxy, WebSocket connections keep honouring
  the standard proxy environment variables.

## [0.3.1] - 2026-10-30

### Fixed

- Listeners no longer process events or overwrite durable cursors when the state store
  cannot be read; loading is retried before polling resumes.
- FunPay fetches complete chat/order gaps, rejects unexpected order-page HTML and
  serializes message sends per chat to avoid misattributed delivery confirmations.
- Playerok marks messages, deals and reviews as processed only after event construction,
  reconnects when WebSocket acknowledgement or subscriptions fail, and makes client
  startup single-flight.
- Playerok image downloads reject credentials and non-public addresses, validate every
  redirect and enforce a 10 MiB limit. Download redirects use the host allowlist, and
  read-only GraphQL POST requests retry transient failures while mutations stay single-shot.
- GGsel refreshes expiring tokens correctly, handles concurrent 401 responses without
  discarding newer tokens, avoids repeating non-idempotent POST requests, and reads
  review bursts across pages.
- GGsel startup is single-flight, `SellerHub.start()` also closes the client whose start
  failed, and explicit GGsel initial-chat handlers are dispatched.
- API keys, access tokens, golden keys and proxy credentials are hidden from config `repr`.

## [0.3.0] - 2026-10-30

### Fixed

- `SellerHub.stream()` no longer deadlocks when a consumer leaves the stream
  while the bounded queue is full.
- `Chat.iter_messages()` now returns a working async iterator instead of
  raising `TypeError`.
- `Account` accepts `lastItemCreatedAt: null`, so new sellers can start the
  Playerok client.
- Custom `base_url` values without a trailing slash are normalized for Playerok
  and GGsel transports.
- `SQLiteStateStore` expands `~` in the database path.
- `.gitignore` now covers SQLite state files, including WAL/SHM companions.

### Changed

- The distribution is now named `aiosellers-nechel12`; the import package remains
  `aiosellers` and GitHub installs keep working.
- CI runs on Python 3.12, 3.13 and 3.14 with locked dependencies, a coverage
  floor, mypy, formatting checks and a wheel import smoke test.
- CodeQL scans Python and GitHub Actions on push, pull request and weekly schedule.
- PyPI publishing is available through the tag workflow when the `PYPI_PUBLISH`
  repository variable and Trusted Publishing are configured.
- `SECURITY.md` points at the Playerok download allowlist.
- Bot examples only start polling when executed as scripts.

## [0.2.0] - 2026-10-30

### Added

- `aiosellers.ggsel`: a GGsel seller adapter built on the official Seller API V1
  (signed ApiLogin flow, token refresh, GET retries and 429 handling). It covers
  balance and receipts, categories, products and price updates, sales and purchases,
  chats, reviews, and a polling event listener with durable state.
- `Platform.GGSEL` in the shared core, with its capability set and `EventKind` mapping,
  so `SellerHub` can merge GGsel sessions with FunPay and Playerok.
- `aiosellers.core`: `Platform`, capability matrix, `EventKind`/`HubEvent` and `SellerHub`
  for running several sessions with one merged event stream.
- `stop()` on every client to end `start_polling()` from another task.
- `max_concurrent_requests` for FunPay instead of one global request lock.
- `py.typed` marker, package metadata and a dev dependency group.
- CI workflow running lint and tests.
- Bilingual documentation: `README.md` and `README.ru.md` with a fork notice,
  badges and installation from GitHub, plus `SECURITY.md`, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md` and `RELEASING.md`.
- GitHub issue and pull request templates and Dependabot for uv and Actions.
- `StateStore` protocol with `MemoryStateStore` and `SQLiteStateStore`; all listeners
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
- Event handlers run with a per-handler timeout and limited concurrency on every adapter.
- With a configured state store, listeners no longer replay initial snapshots or duplicate
  messages and deals after a restart.
