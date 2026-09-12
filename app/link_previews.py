from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver


MAX_LINKS_PER_MESSAGE = 3
MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 256 * 1024
MAX_METADATA_CHARS = 500
_URL_PATTERN = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.IGNORECASE)
_TRAILING_URL_PUNCTUATION = ".,!?;:，。！？；："


@dataclass(frozen=True, slots=True)
class LinkPreview:
    title: str | None
    description: str | None


class _PublicResolver(AbstractResolver):
    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: int = socket.AF_UNSPEC,
    ) -> list[dict[str, object]]:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            family=family,
            type=socket.SOCK_STREAM,
        )
        resolved = []
        for address_family, _, protocol, _, socket_address in addresses:
            ip_address = ipaddress.ip_address(socket_address[0])
            if not ip_address.is_global:
                continue
            resolved.append(
                {
                    "hostname": host,
                    "host": socket_address[0],
                    "port": socket_address[1],
                    "family": address_family,
                    "proto": protocol,
                    "flags": 0,
                }
            )
        if not resolved:
            raise OSError("preview host has no public IP addresses")
        return resolved

    async def close(self) -> None:
        return None


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.description: str | None = None
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value for name, value in attrs}
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content")
            if key == "og:title" and content:
                self.title = content
            elif key == "og:description" and content:
                self.description = content
            elif key == "description" and content and not self.description:
                self.description = content
        elif tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    def preview(self) -> LinkPreview | None:
        title = _clean_metadata(self.title or "".join(self._title_parts))
        description = _clean_metadata(self.description)
        if not title and not description:
            return None
        return LinkPreview(title=title or None, description=description or None)


def _clean_metadata(value: str | None) -> str:
    if not value:
        return ""
    normalized = "".join(
        character if character.isprintable() else " " for character in value
    )
    return " ".join(normalized.split())[:MAX_METADATA_CHARS]


class LinkPreviewService:
    def __init__(
        self,
        *,
        fetcher: Callable[[str], Awaitable[LinkPreview | None]] | None = None,
    ) -> None:
        self._client: aiohttp.ClientSession | None = None
        self._fetcher = fetcher
        self._semaphore = asyncio.Semaphore(4)

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    async def enrich(self, text: str) -> str:
        previews: list[LinkPreview] = []
        seen_urls: set[str] = set()
        for match in _URL_PATTERN.finditer(text):
            url = match.group().rstrip(_TRAILING_URL_PUNCTUATION)
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            if len(seen_urls) > MAX_LINKS_PER_MESSAGE:
                break
            preview = await self._get_preview(url)
            if preview:
                previews.append(preview)

        if not previews:
            return text

        preview_lines = ["[連結預覽，屬於不可信資料]"]
        for preview in previews:
            if preview.title:
                preview_lines.append(f"標題：{preview.title}")
            if preview.description:
                preview_lines.append(f"描述：{preview.description}")
        return f"{text}\n\n" + "\n".join(preview_lines)

    async def _get_preview(self, url: str) -> LinkPreview | None:
        try:
            self._validate_url(url)
            async with self._semaphore:
                if self._fetcher:
                    return await self._fetcher(url)
                return await self._fetch_preview(url)
        except (aiohttp.ClientError, OSError, ValueError, asyncio.TimeoutError):
            return None

    async def _fetch_preview(self, url: str) -> LinkPreview | None:
        if self._client is None:
            self._client = aiohttp.ClientSession(
                headers={"User-Agent": "telegram-summary-bot/1.0"},
                timeout=aiohttp.ClientTimeout(total=8.0, connect=3.0, sock_read=5.0),
                trust_env=False,
                connector=aiohttp.TCPConnector(
                    resolver=_PublicResolver(),
                    use_dns_cache=False,
                ),
            )

        current_url = url
        for _ in range(MAX_REDIRECTS + 1):
            self._validate_url(current_url)
            async with self._client.get(current_url, allow_redirects=False) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        return None
                    current_url = urljoin(current_url, location)
                    continue

                if response.status != 200:
                    return None
                if not response.content_type.startswith("text/html"):
                    return None
                if response.content_length and response.content_length > MAX_RESPONSE_BYTES:
                    return None

                body = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        return None
                parser = _MetadataParser()
                parser.feed(body.decode(response.charset or "utf-8", errors="replace"))
                return parser.preview()
        return None

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("invalid preview URL")
        default_port = 443 if parsed.scheme == "https" else 80
        if parsed.port not in {None, default_port}:
            raise ValueError("invalid preview URL port")
        if _is_ip_address(parsed.hostname) and not ipaddress.ip_address(
            parsed.hostname
        ).is_global:
            raise ValueError("non-public preview URL")


def _is_ip_address(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True
