import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aiosellers import MediaPathNotAllowedError
from aiosellers.core.media_policy import allowed_media_roots, resolve_media_path
from aiosellers.funpay.api.chats import _load_image
from aiosellers.playerok.core.utils import prepare_image_file

ENV = "AIOSELLERS_MEDIA_ROOTS"


def patch_env(value: str | None) -> mock.patch:
    """Pin the environment to ``value`` (``None`` = variable unset)."""
    environ = {key: item for key, item in os.environ.items() if key != ENV}
    if value is not None:
        environ[ENV] = value
    return mock.patch.dict(os.environ, environ, clear=True)


class BaseMediaTest(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.tmp) / "media"
        self.root.mkdir()
        self.outside = Path(self.tmp) / "secret.key"
        self.outside.write_bytes(b"TOPSECRET")


class AllowedRootsTest(BaseMediaTest):
    def test_unset_keeps_historical_behaviour(self) -> None:
        with patch_env(None):
            self.assertIsNone(allowed_media_roots())
            self.assertEqual(Path(str(self.outside)), resolve_media_path(str(self.outside)))

    def test_empty_value_denies_every_local_path(self) -> None:
        with patch_env(""):
            self.assertEqual((), allowed_media_roots())
            with self.assertRaises(MediaPathNotAllowedError):
                resolve_media_path(str(self.outside))

    def test_root_allows_inside_and_blocks_outside(self) -> None:
        inside = self.root / "photo.png"
        inside.write_bytes(b"png")
        with patch_env(str(self.root)):
            self.assertEqual(inside.resolve(), resolve_media_path(str(inside)))
            with self.assertRaises(MediaPathNotAllowedError):
                resolve_media_path(str(self.outside))

    def test_dotdot_escape_is_blocked(self) -> None:
        with patch_env(str(self.root)):
            with self.assertRaises(MediaPathNotAllowedError):
                resolve_media_path(str(self.root / ".." / "secret.key"))

    def test_symlink_escape_is_blocked(self) -> None:
        link = self.root / "escape"
        with patch_env(str(self.root)):
            try:
                link.symlink_to(self.outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(MediaPathNotAllowedError):
                resolve_media_path(str(link))

    def test_multiple_roots_are_separated(self) -> None:
        other = Path(self.tmp) / "other"
        other.mkdir()
        with patch_env(os.pathsep.join((str(self.root), str(other)))):
            self.assertEqual(2, len(allowed_media_roots()))
            self.assertEqual(other.resolve(), resolve_media_path(str(other)))


class FunPayLoadImageTest(BaseMediaTest):
    def test_bytes_bypass_the_policy(self) -> None:
        with patch_env(""):
            content, name, _ = _load_image(b"raw-bytes")
            self.assertEqual(b"raw-bytes", content)
            self.assertEqual("image.png", name)

    def test_path_inside_root_is_read(self) -> None:
        inside = self.root / "photo.png"
        inside.write_bytes(b"PNGDATA")
        with patch_env(str(self.root)):
            content, name, _ = _load_image(inside)
            self.assertEqual(b"PNGDATA", content)
            self.assertEqual("photo.png", name)

    def test_path_outside_root_is_denied(self) -> None:
        with patch_env(str(self.root)):
            with self.assertRaises(MediaPathNotAllowedError):
                _load_image(str(self.outside))


class PlayerokPrepareImageTest(BaseMediaTest):
    def test_local_path_denied_while_url_still_downloads(self) -> None:
        with (
            patch_env(""),
            mock.patch("aiosellers.playerok.core.utils._download_remote_image") as download,
        ):
            download.return_value = (None, False)
            with self.assertRaises(MediaPathNotAllowedError):
                asyncio.run(prepare_image_file(str(self.outside)))
            asyncio.run(prepare_image_file("https://example.com/a.png"))
            self.assertEqual(1, download.call_count)

    def test_path_inside_root_still_opens(self) -> None:
        inside = self.root / "photo.png"
        inside.write_bytes(b"PNGDATA")
        with patch_env(str(self.root)):
            file_obj, is_local = asyncio.run(prepare_image_file(str(inside)))
            self.addCleanup(file_obj.close)
            self.assertTrue(is_local)
            self.assertEqual(b"PNGDATA", file_obj.read())


if __name__ == "__main__":
    unittest.main()
