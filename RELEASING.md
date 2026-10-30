# Releasing

This project has no release automation beyond CI, so a release is a short
manual sequence.

1. **Prepare**
   - Update `CHANGELOG.md`: move `[Unreleased]` items under the new version and
     add the release date.
   - Bump `version` in `pyproject.toml` and run `uv lock` so `uv.lock` matches.
   - Run `uv run ruff check .` and `uv run pytest -q`.

2. **Verify locally**
   - `uv build`
   - Inspect `dist/`: the wheel must contain `aiosellers/`, `py.typed` and the
     metadata must point at this fork.
   - Install the wheel in a clean environment and import every adapter:

```sh
python -m venv /tmp/aiosellers-check
/tmp/aiosellers-check/bin/pip install dist/aiosellers-*.whl
/tmp/aiosellers-check/bin/python -c "from aiosellers import FunPay, Playerok, GGsel, SellerHub"
```

3. **Publish on GitHub**
   - Commit and push `main`; wait for CI.
   - Create an annotated tag: `git tag -a vX.Y.Z -m "vX.Y.Z"`, then
     `git push origin vX.Y.Z`.
   - Create a GitHub release with the changelog notes.

4. **PyPI (optional)**
   - The name `aiosellers` on PyPI belongs to the upstream project, so this fork
     cannot publish under it. Pick a fork-specific distribution name (for
     example `aiosellers-nechel12`), change `[project].name` in `pyproject.toml`
     and keep the import package `aiosellers`.
   - Configure [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
     for the fork repository and publish from a tag-triggered workflow with
     `uv publish`, or run `uv publish` locally with a PyPI token.
   - Update `README.md`, `README.ru.md` and badges with the new install command.

5. **Rollback**
   - Reinstall the previous tag (`pip install "git+...@vX.Y.Z-1"`) or the
     previous PyPI release. Tags make rollback deterministic.

## Versioning

The project follows semantic versioning while pre-1.0: breaking changes bump the
minor version, fixes and additions bump the patch version.
