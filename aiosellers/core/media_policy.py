"""Policy for local media paths passed to upload helpers.

FunPay and Playerok both accept ``str``/``Path`` media arguments and read them
from the filesystem of the *running process*. A host that feeds those arguments
with data from less-trusted code (a plugin, a webhook, a task queue) would
otherwise let that code read any file the process can open and ship it out
through a seller account.

``AIOSELLERS_MEDIA_ROOTS`` makes the read target explicit:

* unset — every readable path is accepted, i.e. the historical behaviour, down to
  the argument handed to :func:`open`;
* set — only paths under one of the ``os.pathsep``-separated roots are opened,
  after ``..`` and symlink resolution; an empty value denies local paths
  entirely, which is what an untrusted-caller host should use.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

MEDIA_ROOTS_ENV = "AIOSELLERS_MEDIA_ROOTS"


class MediaPathNotAllowedError(ValueError):
    """A media path falls outside the roots allowed by ``AIOSELLERS_MEDIA_ROOTS``."""


def allowed_media_roots() -> tuple[Path, ...] | None:
    """Configured roots, or ``None`` when no policy is set."""
    raw = os.environ.get(MEDIA_ROOTS_ENV)
    if raw is None:
        return None
    return tuple(Path(part).expanduser() for part in raw.split(os.pathsep) if part.strip())


def _confine(path: str | Path, roots: tuple[Path, ...]) -> Path:
    resolved = Path(path).expanduser().resolve()
    for root in roots:
        if resolved.is_relative_to(root.expanduser().resolve()):
            return resolved
    allowed = ", ".join(str(item.expanduser().resolve()) for item in roots) or (
        "<empty: every local path is denied>"
    )
    raise MediaPathNotAllowedError(
        f"media path {str(path)!r} is outside the roots allowed by {MEDIA_ROOTS_ENV} ({allowed})"
    )


def resolve_media_path(path: str | Path) -> Path:
    """Return ``path`` for opening, validated against the configured policy.

    Without a policy the value is only wrapped in :class:`Path`, keeping the
    historical behaviour; with one it is resolved and confined to an allowed root.

    Raises:
        MediaPathNotAllowedError: the policy is set and the path escapes it.
    """
    roots = allowed_media_roots()
    return Path(path) if roots is None else _confine(path, roots)


def open_media(path: str | Path) -> BinaryIO:
    """Open a media file for reading, honouring the policy."""
    roots = allowed_media_roots()
    target: str | Path = _confine(path, roots) if roots is not None else path
    return open(target, "rb")
