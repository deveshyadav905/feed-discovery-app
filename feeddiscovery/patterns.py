FEED_PATTERNS = [
    "feed", "feeds", "rss", "rss.xml", "feed.xml", 
    "atom.xml", "blog/feed", "blog/rss", "index.xml",
    "news/feed", "articles/feed", "rss/all.xml",
    # Regional/Category fallbacks
    "regions/asia/rss.xml", "regions/emea/rss.xml"
]

SITEMAP_PATTERNS = [
    "sitemap.xml", "sitemap_index.xml", "wp-sitemap.xml", 
    "sitemap-news.xml", "news-sitemap.xml", "sitemap.php",
    # Index locations
    "sitemaps/default/sitemap.xml"
]

# Specifically exclude noise that often validates as XML but isn't useful
BAD_PATTERNS = [
    'comments/feed', 
    '/reply/', 
    '/shop/', 
    'facebook.com', 
    'twitter.com', 
    'linkedin.com',
    'instagram.com'
]

COMMON_PATHS = FEED_PATTERNS + SITEMAP_PATTERNS