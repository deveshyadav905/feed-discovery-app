import asyncio
import httpx
from lxml import html
from urllib.parse import urljoin
from .patterns import COMMON_PATHS, FEED_PATTERNS, SITEMAP_PATTERNS
from .utils import normalize_domain
from .validators_async import validate_feed, validate_sitemap

class AsyncFeedDiscovery:
    def __init__(self, domain_url, timeout=10):
        self.domain = normalize_domain(domain_url)
        self.base_url = f"https://{self.domain}"
        self.timeout = timeout
        self.results = []

    async def discover(self):
        async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": "Mozilla"}) as client:
            await asyncio.gather(
                self._guess_common_paths(client),
                self._generate_from_patterns(client),
                self._parse_homepage(client),
                self._parse_robots(client),
            )

        # remove duplicates
        unique = {r["url"]: r for r in self.results}
        return list(unique.values())

    async def _guess_common_paths(self, client):
        tasks = []
        for path in COMMON_PATHS:
            url = urljoin(self.base_url, path)
            tasks.append(self._validate_and_add(client, url, "common_path"))
        await asyncio.gather(*tasks)

    async def _generate_from_patterns(self, client):
        tasks = []
        for path in FEED_PATTERNS + SITEMAP_PATTERNS:
            url = urljoin(self.base_url, path)
            tasks.append(self._validate_and_add(client, url, "pattern_guess"))
        await asyncio.gather(*tasks)

    async def _parse_homepage(self, client):
        try:
            r = await client.get(self.base_url)
            doc = html.fromstring(r.content)

            links = set()

            for link in doc.xpath("//link[@rel='alternate']/@href"):
                links.add(urljoin(self.base_url, link))

            for a in doc.xpath("//a[@href]/@href"):
                if any(k in a.lower() for k in ["rss", "feed", "xml", "atom", "sitemap"]):
                    links.add(urljoin(self.base_url, a))

            tasks = [self._validate_and_add(client, u, "html") for u in links]
            await asyncio.gather(*tasks)

        except Exception:
            pass

    async def _parse_robots(self, client):
        try:
            r = await client.get(urljoin(self.base_url, "/robots.txt"))
            for line in r.text.splitlines():
                if "sitemap:" in line.lower():
                    url = line.split(":", 1)[1].strip()
                    if await validate_sitemap(client, url):
                        self.results.append({
                            "url": url,
                            "type": "sitemap",
                            "source": "robots"
                        })
        except Exception:
            pass

    async def _validate_and_add(self, client, url, source):
        if await validate_feed(client, url):
            self.results.append({"url": url, "type": "feed", "source": source})
        elif await validate_sitemap(client, url):
            self.results.append({"url": url, "type": "sitemap", "source": source})
