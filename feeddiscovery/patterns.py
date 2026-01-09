# patterns.py
# RSS/Atom/Sitemap patterns
FEED_PATTERNS = [
    "feed", "feeds", "rss", "rss.xml", "feed.xml",
    "atom.xml", "blog/feed", "blog/rss"
]

SITEMAP_PATTERNS = [
    "sitemap.xml", "sitemap_index.xml", "wp-sitemap.xml", "sitemap-news.xml"
]

COMMON_PATHS = FEED_PATTERNS + SITEMAP_PATTERNS
