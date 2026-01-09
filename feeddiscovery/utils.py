# utils.py
from urllib.parse import urlparse, urljoin

def normalize_domain(domain):
    parsed = urlparse(domain)
    if parsed.netloc:
        return parsed.netloc
    return domain.replace("http://", "").replace("https://", "").strip("/")

def join_url(base, path):
    return urljoin(base, path)
