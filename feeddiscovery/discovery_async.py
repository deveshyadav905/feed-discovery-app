import asyncio
import httpx
from lxml import html
from urllib.parse import urljoin, urlparse
# Import the newly expanded patterns
from .patterns import COMMON_PATHS, FEED_PATTERNS, SITEMAP_PATTERNS, BAD_PATTERNS
from .utils import normalize_domain
from .validators_async import validate_feed, validate_sitemap

class AsyncFeedDiscovery:
    def __init__(self, domain_url, timeout=15):
        self.domain = normalize_domain(domain_url)
        self.base_url = f"https://{self.domain}"
        self.timeout = timeout
        self.results = []
        # Track seen URLs to prevent redundant network calls
        self.seen_urls = set()

    async def discover(self):
        # follow_redirects=True is vital for Cultura Colectiva and NewsObserver
        async with httpx.AsyncClient(
            timeout=self.timeout, 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            follow_redirects=True 
        ) as client:
            await asyncio.gather(
                self._guess_common_paths(client),
                self._parse_homepage_and_nav(client),
                self._parse_robots(client),
            )

        # Final deduplication
        unique = {r["url"]: r for r in self.results}
        return list(unique.values())

    async def _parse_homepage_and_nav(self, client):
        try:
            r = await client.get(self.base_url)
            doc = html.fromstring(r.content)
            candidate_links = set()

            # 1. FIXED: Extract ALL link alternates (handles external feeds.mcclatchy.com)
            xpath_query = "//link[@rel='alternate' and (contains(@type, 'rss') or contains(@type, 'xml') or contains(@type, 'atom'))]/@href"
            for href in doc.xpath(xpath_query):
                candidate_links.add(urljoin(self.base_url, href))

            # 2. NAVBAR & CATEGORY LOGIC: Find categories and subdomains
            # We target <nav>, <header>, and <footer> for cleaner link extraction
            nav_links = doc.xpath("//nav//a/@href | //header//a/@href | //footer//a/@href")
            
            for href in nav_links:
                full_url = urljoin(self.base_url, href)
                parsed = urlparse(full_url)

                # Only process links that belong to our target domain or its subdomains
                if self.domain in parsed.netloc:
                    # If it has a path (category), try common suffixes (e.g., /news/feed/)
                    if parsed.path and len(parsed.path) > 1:
                        # Add variations for the category
                        path_base = full_url.rstrip('/')
                        candidate_links.update([
                            f"{path_base}/feed/",
                            f"{path_base}/rss.xml",
                            f"{path_base}/index.xml",
                            f"{path_base}.xml"
                        ])
                    
                    # Handle Subdomains: if 'tech.mobihealthnews.com' is found
                    if parsed.netloc != self.domain:
                        sub_base = f"{parsed.scheme}://{parsed.netloc}"
                        candidate_links.update([
                            urljoin(sub_base, "feed/"),
                            urljoin(sub_base, "rss.xml")
                        ])

            # 3. TEXT SEARCH: Links with "RSS" or "Feed" in the text
            text_links = doc.xpath("//a[contains(translate(., 'RSS', 'rss'), 'rss') or contains(translate(., 'FEED', 'feed'), 'feed')]/@href")
            for href in text_links:
                candidate_links.add(urljoin(self.base_url, href))

            # Validate all candidates in parallel
            tasks = [self._validate_and_add(client, u, "nav_discovery") for u in candidate_links]
            await asyncio.gather(*tasks)

        except Exception:
            pass

    async def _guess_common_paths(self, client):
        # Uses the updated list from patterns.py
        tasks = []
        for path in COMMON_PATHS:
            url = urljoin(self.base_url, path)
            tasks.append(self._validate_and_add(client, url, "common_path"))
        await asyncio.gather(*tasks)

    async def _parse_robots(self, client):
        try:
            r = await client.get(urljoin(self.base_url, "/robots.txt"))
            for line in r.text.splitlines():
                if line.lower().strip().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    await self._validate_and_add(client, sitemap_url, "robots")
        except Exception:
            pass

    async def _validate_and_add(self, client, url, source):
        # Filter out bad patterns (comments, social media) and duplicates
        clean_url = url.split('?')[0].rstrip('/') # Normalize for comparison
        
        if clean_url in self.seen_urls or any(bad in url.lower() for bad in BAD_PATTERNS):
            return
        
        self.seen_urls.add(clean_url)

        try:
            # Check for Feed first (MobiHealthNews / Cultura Colectiva focus)
            if await validate_feed(client, url):
                self.results.append({"url": url, "type": "feed", "source": source})
            # Check for Sitemap second (NewsObserver focus)
            elif await validate_sitemap(client, url):
                self.results.append({"url": url, "type": "sitemap", "source": source})
        except Exception:
            pass