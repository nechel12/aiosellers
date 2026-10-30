# Security Policy

## Supported versions

Security fixes are provided for the latest `main` and the latest tagged release
on a best-effort basis. Older commits, forks and unpublished snapshots are not
supported.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability**
   (`https://github.com/nechel12/aiosellers/security/advisories/new`).
3. Include the affected version or commit, the platform adapter (FunPay,
   Playerok, GGsel, core/hub), a minimal reproduction, and the impact.

Do not open a public issue and do not include real API keys, golden keys, access
tokens, session cookies, buyer personal data or chat contents. If private
reporting is unavailable, open a minimal public issue asking the maintainer for
a private channel without disclosing details.

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
- The GGsel download host allowlist and any place where the library makes
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

The library has no server component and no telemetry. Credentials live in
memory for the lifetime of a client and are sent only to the platform endpoints
the adapter talks to. A configured `StateStore` may persist chat ids, message
ids, order snapshots and cursors; treat the SQLite file as sensitive and
restrict its permissions. The library cannot protect credentials from the
process that embeds it — do not log them, do not commit them, and prefer
environment variables or a secret manager.

## Safe harbor

Good-faith research on your own accounts and infrastructure is welcome. Do not
test against other people's accounts, do not access data you do not own, and
follow applicable law.
