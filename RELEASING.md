# Releasing

The tag workflow builds the distribution; publishing to PyPI is gated by the
repository variable `PYPI_PUBLISH` so a missing Trusted Publisher cannot break
ordinary tags.

1. **Prepare**
   - Update `CHANGELOG.md`: move `[Unreleased]` items under the new version and
     add the release date.
   - Bump `version` in `pyproject.toml` and run `uv lock` so `uv.lock` matches.
   - Run `uv run ruff check .`, `uv run ruff format --check .`,
     `uv run mypy aiosellers` and `uv run pytest -q`.

2. **Verify locally**
   - `uv build`
   - Inspect `dist/`: the wheel must contain `aiosellers/`, `py.typed` and the
     metadata must point at this fork (`aiosellers-nechel12`).
   - Install the wheel in a clean environment and import every adapter:

```sh
python -m venv /tmp/aiosellers-check
/tmp/aiosellers-check/bin/pip install dist/*.whl
/tmp/aiosellers-check/bin/python -c "from aiosellers import FunPay, Playerok, GGsel, SellerHub"
```

On Windows, use a temporary directory and the `Scripts\python.exe` /
`Scripts\pip.exe` paths instead.

3. **Publish on GitHub**
   - Commit and push `main`; wait for CI.
   - Create an annotated tag: `git tag -a vX.Y.Z -m "vX.Y.Z"`, then
     `git push origin vX.Y.Z`.
   - Create a GitHub release with the changelog notes.

4. **PyPI**
   - The distribution is `aiosellers-nechel12`; the import package remains
     `aiosellers`. The name `aiosellers` on PyPI belongs to the upstream project.
   - Configure [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
     for the `nechel12/aiosellers` repository, workflow `publish.yml`, environment
     `pypi`.
   - Set the GitHub repository variable `PYPI_PUBLISH=true` when the publisher is
     configured. The tag workflow then builds and publishes the wheel; a normal
     tag without the variable only builds and runs the checks.
   - Alternatively, run `uv publish` locally with a PyPI token.
   - Update `README.md`, `README.ru.md` and badges with the new install command.

5. **Rollback**
   - Reinstall the previous tag (for example, the tag before the current one)
     or the previous PyPI release. Tags make rollback deterministic.

## PyPI name

`aiosellers-nechel12` is the distribution name; `aiosellers` remains the import
package. This avoids a conflict with the upstream `aiosellers` project while
keeping the public API compatible.

## Versioning

The project follows semantic versioning while pre-1.0: breaking changes bump the
minor version, fixes and additions bump the patch version.
