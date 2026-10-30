# Contributing

Bug reports and pull requests are welcome. Please keep changes focused and
explain the behavior and tradeoffs in the PR description.

## Development

- Python 3.12+ and [uv](https://docs.astral.sh/uv/).
- A platform account is only needed for manual checks; the test suite uses
  fakes and does not call live APIs.
- Before sending a change:

```sh
uv sync
uv run ruff check .
uv run pytest -q
```

- If you touch packaging, build and inspect the artifacts:

```sh
uv build
```

- If you touch an example, run it against a test account with throwaway
  credentials:

```sh
uv run python examples/ggsel_account.py
```

## Pull requests

- Add or update tests for behavior changes. A bug fix needs a test that fails
  before the change.
- Update `README.md` and `README.ru.md` when user-visible behavior,
  configuration or installation changes.
- Add an entry under `[Unreleased]` in `CHANGELOG.md`.
- Do not commit secrets, `.env` files, SQLite state files, `dist/`, or build
  artifacts.
- Keep CI green; the workflow runs `ruff check` and `pytest` on Python 3.12.

## Adding a platform adapter

- Put the adapter in `aiosellers/<platform>` with `api`, `raw`, `schemas`,
  `entities`, transport and listener modules, following the existing adapters.
- Implement the `SellerClient` protocol and register the platform in
  `aiosellers/core/capabilities.py` and `aiosellers/core/events.py`.
- Add tests under `tests/` with fake transports; do not require live
  credentials in CI.
- Document the adapter in both READMEs, add an example and a changelog entry.

## Reporting security issues

Follow [SECURITY.md](SECURITY.md). Do not open a public issue with exploit
details or real credentials.

## Releases

See [RELEASING.md](RELEASING.md) and [CHANGELOG.md](CHANGELOG.md).

## Conduct

Be respectful and constructive. Harassment, discrimination, and personal
attacks are not acceptable. By participating, you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions are licensed under
Apache-2.0, the project's license. The project is a fork of
[Zewsic/aiosellers](https://github.com/Zewsic/aiosellers); keep upstream
copyright notices intact.
