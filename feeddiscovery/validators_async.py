import httpx
from lxml import etree
import io

async def validate_feed(client: httpx.AsyncClient, url: str) -> bool:
    try:
        # Increase limit for large feed files
        r = await client.get(url, follow_redirects=True, timeout=10.0)
        
        if r.status_code != 200:
            return False

        content = r.content.strip()
        if not content:
            return False

        # FIX: Don't rely strictly on headers. Some feeds return 'text/plain'
        # Check first 500 bytes for common XML feed signatures
        snippet = content[:500].lower()
        if not any(tag in snippet for tag in [b"<rss", b"<feed", b"<channel", b"xmlns="]):
            return False

        # Use a parser that recovers from minor syntax errors
        parser = etree.XMLParser(recover=True, remove_comments=True)
        root = etree.fromstring(content, parser=parser)
        
        # Handle Namespaces: Strip the namespace from the tag for easy checking
        tag = root.tag
        if '}' in tag:
            tag = tag.split('}', 1)[1]
            
        return tag.lower() in ["rss", "feed", "rdf"]
    except Exception:
        return False

async def validate_sitemap(client: httpx.AsyncClient, url: str) -> bool:
    try:
        r = await client.get(url, follow_redirects=True, timeout=10.0)
        if r.status_code != 200:
            return False
            
        content = r.content.strip()
        
        # Sitemaps can be huge; use iterparse or simple checks for snippet
        snippet = content[:500].lower()
        if b"sitemap" not in snippet and b"urlset" not in snippet:
            return False

        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(content, parser=parser)
        
        tag = root.tag
        if '}' in tag:
            tag = tag.split('}', 1)[1]
            
        return tag.lower() in ["sitemapindex", "urlset"]
    except Exception:
        return False