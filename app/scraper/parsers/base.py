from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScrapedItem:
    item_number: str          # LEGO set number e.g. "75192"
    name: str                 # Product name as shown on site
    listed_price: int         # Discounted price shown on page (원)
    product_url: str          # Direct link to the product
    source_name: str          # Display name of the source
    source_url: str           # The registered source URL
    additional_discount: Optional[float] = None   # e.g. 0.2 for 20%; None = use global
    original_price: Optional[int] = None          # Strikethrough / pre-discount price from source page (KRW)


class BaseParser(ABC):
    """
    Subclass this to add support for a new site.
    Only two methods are required: can_parse and parse.
    """

    @abstractmethod
    def can_parse(self, url: str) -> bool:
        """Return True if this parser handles the given URL."""

    @abstractmethod
    def parse(self, url: str, source_name: str) -> list[ScrapedItem]:
        """
        Fetch the page at `url` and return all LEGO items found.
        Do NOT apply additional_discount here; the coordinator handles that.
        Raise an exception on unrecoverable fetch/parse errors.
        """

    # ------------------------------------------------------------------
    # Shared helpers available to all parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _price_int(text: str) -> Optional[int]:
        """Strip non-digits and return int, or None if empty."""
        digits = "".join(c for c in text if c.isdigit())
        return int(digits) if digits else None

    @staticmethod
    def _absolute_url(href: str, base_url: str) -> str:
        from urllib.parse import urljoin
        return urljoin(base_url, href)
