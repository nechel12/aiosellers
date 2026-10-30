from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from .exceptions import GraphQLError, PersistedQueryExpired
from .types import ImageInput

MAX_IMAGE_DOWNLOAD_BYTES = 10 * 1024 * 1024
IMAGE_REDIRECT_LIMIT = 3


def _dig(obj: dict[str, Any], path: Iterable[str]) -> Any:
    cur: Any = obj
    for key in path:
        if cur is None:
            return None
        cur = cur.get(key)
    return cur


def _raise_on_gql_errors(payload: dict[str, Any]) -> None:
    errors = payload.get("errors")
    if not errors:
        return
    first = errors[0]
    message = first.get("message") if isinstance(first, dict) else str(first)
    code = ""
    if isinstance(first, dict):
        extensions = first.get("extensions")
        if isinstance(extensions, dict):
            code = str(extensions.get("code") or "")
    if "PERSISTED_QUERY" in code.upper() or "persisted" in (message or "").lower():
        raise PersistedQueryExpired(
            "Playerok rejected a persisted GraphQL query "
            f"({message or code}). The frontend contract has probably changed; "
            "refresh the QueryID hashes or send the full query text."
        )
    if isinstance(first, dict) and "message" in first:
        raise GraphQLError(first["message"] + ": " + str(first))
    raise GraphQLError(first)


async def _validate_remote_image_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Unsupported image URL scheme: {parsed.scheme}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Image URLs must not contain credentials")

    host = parsed.hostname
    if not host:
        raise ValueError("Image URL must contain a host")
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise ValueError(f"Invalid image URL port: {url}") from exc

    addresses = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError(f"Image URL host did not resolve: {host!r}")

    for address_info in addresses:
        address = ipaddress.ip_address(str(address_info[4][0]).split("%", 1)[0])
        if (
            address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
            or not address.is_global
        ):
            raise PermissionError(f"Refusing to download an image from a non-public IP: {address}")
    return url


def _image_response_header(response: Any, name: str) -> Any:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    return headers.get(name) or headers.get(name.title())


async def _download_remote_image(url: str, proxy: str | None = None) -> tuple[BytesIO, bool]:
    from tls_requests import AsyncClient

    current_url = await _validate_remote_image_url(url)
    client_kwargs: dict[str, Any] = {}
    if proxy:
        client_kwargs["proxy"] = proxy
    async with AsyncClient(**client_kwargs) as client:
        for redirect_count in range(IMAGE_REDIRECT_LIMIT + 1):
            response = await client.get(current_url, follow_redirects=False)
            status = getattr(response, "status_code", 200)
            if status in (301, 302, 303, 307, 308):
                location = _image_response_header(response, "location")
                if not location:
                    raise RuntimeError(f"Image redirect has no Location header: {current_url}")
                if redirect_count >= IMAGE_REDIRECT_LIMIT:
                    raise RuntimeError(
                        f"Image download exceeded {IMAGE_REDIRECT_LIMIT} redirects: {url}"
                    )
                current_url = await _validate_remote_image_url(urljoin(current_url, location))
                continue

            if status >= 400:
                raise RuntimeError(f"Failed to download image from {current_url}: HTTP {status}")

            content_length = _image_response_header(response, "content-length")
            try:
                if content_length is not None and int(content_length) > MAX_IMAGE_DOWNLOAD_BYTES:
                    raise RuntimeError(
                        f"Image exceeds the {MAX_IMAGE_DOWNLOAD_BYTES}-byte download limit"
                    )
            except ValueError:
                pass

            content = getattr(response, "content", None)
            if content is None:
                content = getattr(response, "text", "").encode()
            if len(content) > MAX_IMAGE_DOWNLOAD_BYTES:
                raise RuntimeError(
                    f"Image exceeds the {MAX_IMAGE_DOWNLOAD_BYTES}-byte download limit"
                )
            return BytesIO(content), False

    raise AssertionError("unreachable")


async def prepare_image_file(image: ImageInput, *, proxy: str | None = None) -> tuple[Any, bool]:
    if isinstance(image, BytesIO):
        return image, False

    if isinstance(image, bytes):
        return BytesIO(image), False

    if isinstance(image, Path):
        image = str(image)

    if isinstance(image, str):
        parsed = urlparse(image)
        is_windows_path = len(image) >= 2 and image[1] == ":"
        if not is_windows_path and "://" in image:
            if parsed.scheme.lower() not in ("http", "https"):
                raise ValueError(f"Unsupported image URL scheme: {parsed.scheme}")
            return await _download_remote_image(image, proxy=proxy)

        file_obj = open(image, "rb")
        return file_obj, True

    raise TypeError(f"Unsupported image type: {type(image)}")
