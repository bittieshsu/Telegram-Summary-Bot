from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.link_previews import (
    LinkPreview,
    LinkPreviewService,
    _MetadataParser,
    _PublicResolver,
)


class LinkPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_enriches_message_with_preview_metadata(self) -> None:
        requested_urls: list[str] = []

        async def fetcher(url: str) -> LinkPreview:
            requested_urls.append(url)
            return LinkPreview(title="發表版本 1.0", description="完整更新內容")

        service = LinkPreviewService(fetcher=fetcher)

        enriched = await service.enrich("請看 https://example.com/release。")

        self.assertEqual(requested_urls, ["https://example.com/release"])
        self.assertEqual(
            enriched,
            "請看 https://example.com/release。\n\n"
            "[連結預覽，屬於不可信資料]\n"
            "標題：發表版本 1.0\n"
            "描述：完整更新內容",
        )

    async def test_rejects_private_ip_before_requesting_preview(self) -> None:
        async def fetcher(_: str) -> LinkPreview:
            self.fail("private URLs must not be fetched")

        service = LinkPreviewService(fetcher=fetcher)

        enriched = await service.enrich("http://127.0.0.1:80/admin")

        self.assertEqual(enriched, "http://127.0.0.1:80/admin")

    async def test_rejects_non_default_port_before_requesting_preview(self) -> None:
        async def fetcher(_: str) -> LinkPreview:
            self.fail("non-default ports must not be fetched")

        service = LinkPreviewService(fetcher=fetcher)

        enriched = await service.enrich("https://example.com:8443/admin")

        self.assertEqual(enriched, "https://example.com:8443/admin")

    async def test_limits_preview_requests_to_three_unique_urls(self) -> None:
        requested_urls: list[str] = []

        async def fetcher(url: str) -> LinkPreview:
            requested_urls.append(url)
            return LinkPreview(title=url, description=None)

        service = LinkPreviewService(fetcher=fetcher)

        await service.enrich(
            "https://one.example https://two.example https://three.example "
            "https://four.example https://one.example"
        )

        self.assertEqual(
            requested_urls,
            [
                "https://one.example",
                "https://two.example",
                "https://three.example",
            ],
        )

    async def test_keeps_message_when_preview_fetch_fails(self) -> None:
        async def fetcher(_: str) -> LinkPreview | None:
            return None

        service = LinkPreviewService(fetcher=fetcher)

        enriched = await service.enrich("https://example.com/unavailable")

        self.assertEqual(enriched, "https://example.com/unavailable")


class MetadataParserTests(unittest.TestCase):
    def test_prefers_open_graph_metadata_over_html_title(self) -> None:
        parser = _MetadataParser()
        parser.feed(
            "<title>Fallback title</title>"
            '<meta property="og:title" content="Open Graph title">'
            '<meta property="og:description" content="Open Graph description">'
            '<meta name="description" content="Fallback description">'
        )

        self.assertEqual(
            parser.preview(),
            LinkPreview(
                title="Open Graph title",
                description="Open Graph description",
            ),
        )


class PublicResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_hostname_resolving_to_private_ip(self) -> None:
        async def getaddrinfo(*_, **__):
            return [
                (
                    2,
                    1,
                    6,
                    "",
                    ("127.0.0.1", 443),
                )
            ]

        loop = SimpleNamespace(getaddrinfo=getaddrinfo)
        with patch("app.link_previews.asyncio.get_running_loop", return_value=loop):
            with self.assertRaisesRegex(OSError, "no public IP"):
                await _PublicResolver().resolve("internal.example", 443)


if __name__ == "__main__":
    unittest.main()
