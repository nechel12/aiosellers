# Security Policy

## Supported versions

Security fixes are provided for `main` and the latest published
[`aiosellers-nechel12` release on PyPI](https://pypi.org/project/aiosellers-nechel12/)
on a best-effort basis. Older versions and downstream forks are not supported.

## Reporting a vulnerability

Sign in to GitHub and use
[Report a vulnerability](https://github.com/nechel12/aiosellers/security/advisories/new).
Include the affected version or commit, the adapter or component, steps to
reproduce the issue with synthetic test data, and the impact.

Do not report vulnerabilities in public issues or pull requests. Remove real
API keys, golden keys, access tokens, session cookies, personal data, and chat
content even from private reports.

## What to expect

- The target acknowledgement time is seven days.
- The timing of fixes and mitigations depends on severity.
- The project does not offer a bug bounty.
- Reporters may request attribution in a published advisory.

## Scope

In scope:

- Credential handling: FunPay `golden_key`, PlayerOK `access_token`, GGsel
  `api_key`/`seller_id`, login signing, token caching and refresh.
- Transport security: TLS verification, redirects, retries, rate limiting and
  request signing.
- The PlayerOK download host allowlist and requests to user-supplied URLs.
- Exposure of sensitive data in `MemoryStateStore` or `SQLiteStateStore`.
- Input parsing of platform responses (HTML, JSON, GraphQL, WebSocket frames)
  where malformed data could cause code execution, injection or crashes.
- Packaging, CI workflows and release artifacts.

Out of scope:

- Platform terms of service, rate limits, account bans or API changes.
- Vulnerabilities in FunPay, PlayerOK, GGsel or their websites.
- Vulnerabilities in third-party dependencies. Report them to the corresponding
  upstream project.
- Bots and applications built with the library, including how they store or log
  credentials.
- Social engineering, physical access and denial-of-service against platforms.

## Security model

The library has no server component and no telemetry. Clients use credentials
in memory and send them to their configured endpoints. Treat custom `base_url`,
`ws_url`, and proxy settings as trusted configuration, not as user input.
Use a secret manager or environment variables, and redact logs and tracebacks:
errors may include excerpts of platform responses.

A configured `StateStore` may persist chat and message IDs, order statuses,
cursors, and, for FunPay, chat message previews. Restrict access to the SQLite
database, its sidecar files, and backups.

Local upload paths are unrestricted unless `AIOSELLERS_MEDIA_ROOTS` is set.
Limit it to trusted directories, or use an empty value to disable local paths.
Do not pass arbitrary media paths from untrusted callers.

`PlayerokTransport.download()` restricts downloads to the PlayerOK host
allowlist and uses a separate client without the session cookie. In contrast,
`prepare_image_file()` also accepts user-supplied image URLs;
it resolves every redirect and rejects private, loopback, link-local and other
non-public addresses, but callers should still validate untrusted URLs before
passing them. The TLS library performs its own DNS resolution, so a hostname
that changes between the check and the request remains outside the library's
control; use an allowlist at the application boundary when URLs are untrusted.

## Safe harbor

Good-faith research on your own accounts and infrastructure is welcome. Do not
test against other people's accounts, do not access data you do not own, and
follow applicable law.
