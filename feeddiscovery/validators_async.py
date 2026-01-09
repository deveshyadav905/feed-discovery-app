import httpx
from lxml import etree

async def validate_feed(client: httpx.AsyncClient, url: str) -> bool:
    try:
        r = await client.get(url)
        if "xml" not in r.headers.get("content-type", "").lower():
            return False
        root = etree.fromstring(r.content)
        return root.tag.lower() in ["rss", "feed"]
    except Exception:
        return False

async def validate_sitemap(client: httpx.AsyncClient, url: str) -> bool:
    try:
        r = await client.get(url)
        root = etree.fromstring(r.content)
        return any(x in root.tag.lower() for x in ["sitemapindex", "urlset"])
    except Exception:
        return False
