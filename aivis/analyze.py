"""Find which brands an AI answer mentions, in what order, and whether their sites are cited."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .config import Brand

URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


@dataclass
class BrandResult:
    brand: str
    is_you: bool
    mentioned: bool
    rank: int | None      # 1 = first brand named in the answer
    cited: bool           # brand's domain appears among cited/linked sources


def _pattern(name: str) -> re.Pattern:
    # Word boundaries so "Brevo" doesn't match inside another word, tolerant of
    # possessives ("HubSpot's") and punctuation around the name.
    return re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])", re.IGNORECASE)


def first_mention(text: str, brand: Brand) -> int | None:
    hits = [m.start() for n in brand.names if n for m in [_pattern(n).search(text)] if m]
    return min(hits) if hits else None


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def domain_cited(domain: str, urls: list[str]) -> bool:
    if not domain:
        return False
    d = domain.lower().removeprefix("www.")
    return any(h == d or h.endswith("." + d) for h in map(_host, urls))


def analyze(text: str, citations: list[str], brands: list[Brand]) -> list[BrandResult]:
    urls = list(citations) + URL_RE.findall(text)
    positions = {b.name: first_mention(text, b) for b in brands}
    order = sorted((pos, name) for name, pos in positions.items() if pos is not None)
    ranks = {name: i + 1 for i, (_, name) in enumerate(order)}
    return [
        BrandResult(b.name, b.is_you, positions[b.name] is not None, ranks.get(b.name),
                    domain_cited(b.domain, urls))
        for b in brands
    ]
