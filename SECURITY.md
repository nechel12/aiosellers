# Security Policy

## Supported versions

Security fixes are provided for `main` and the latest published
[`aiosellers-nechel12` release on PyPI](https://pypi.org/project/aiosellers-nechel12/)
on a best-effort basis. Older versions and downstream forks are not supported.

## Reporting a vulnerability

Sign in to GitHub and use
[Report a vulnerability](https://github.com/nechel12/aiosellers/security/advisories/new).
Include the affected version or commit, the adapter or component, a minimal
reproduction with fake credentials, and the impact.

Do not open a public issue and do not include real API keys, golden keys, access
tokens, session cookies, buyer personal data or chat contents. If private
reporting is unavailable, contact the maintainer privately if you already have
a private channel. Do not post the vulnerability or any identifying details in
a public issue.

## What to expect

- Acknowledgement within 7 days, best effort.
- Triage and a fix/mitigation plan; timelines depend on severity.
- No bug bounty.
- Credit in the advisory if desired.

## Scope

In scope:

- Credential handling: FunPay `golden_key`, Playerok `access_token`, GGsel
  `api_key`/`seller_id`, login signing, token caching and refresh.
- Transport security: TLS verification, redirects, retries, rate limiting and
  request signing.
- The Playerok download host allowlist and any place where the library makes
  requests to user-supplied URLs.
- Listener state: what `MemoryStateStore`/`SQLiteStateStore` persists and
  whether it can leak secrets.
- Input parsing of platform responses (HTML, JSON, GraphQL, WebSocket frames)
  where malformed data could cause code execution, injection or crashes.
- Packaging, CI workflows and release artifacts.

Out of scope:

- Platform terms of service, rate limits, account bans or API changes.
- Vulnerabilities in FunPay, PlayerOK, GGsel or their websites.
- Third-party dependencies (report them upstream; we will bump versions).
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

`PlayerokTransport.download()` restricts downloads to the Playerok host
allowlist and uses a separate client without the session cookie. In contrast,
`prepare_image_file()` accepts arbitrary user-supplied image URLs by design;
it resolves every redirect and rejects private, loopback, link-local and other
non-public addresses, but callers should still validate untrusted URLs before
passing them. The TLS library performs its own DNS resolution, so a hostname
that changes between the check and the request remains outside the library's
control; use an allowlist at the application boundary when URLs are untrusted.

## Safe harbor

Good-faith research on your own accounts and infrastructure is welcome. Do not
test against other people's accounts, do not access data you do not own, and
follow applicable law.
