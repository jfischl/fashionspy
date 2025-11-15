#!/usr/bin/env python3
"""
Fashion Image Web Scraper with Source Tracking (Async Version)

High-performance async implementation with aiohttp for faster concurrent scraping.
Implements TASK-10 through TASK-14 performance optimizations.
"""

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse

# Suppress SSL warnings
warnings.filterwarnings('ignore', message='urllib3 v2 only supports OpenSSL')

import aiohttp
from bs4 import BeautifulSoup

# TASK-17: Import Playwright crawler
try:
    from playwright_crawler import PlaywrightCrawler
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# TASK-20: Import person detection filter
try:
    from person_filter import PersonDetectionFilter
    PERSON_FILTER_AVAILABLE = True
except ImportError:
    PERSON_FILTER_AVAILABLE = False


# ============================================================================
# TASK-2: Error Handling and Logging Framework
# ============================================================================

class ScraperLogger:
    """Centralized logging system for the scraper."""

    def __init__(self, log_dir: str = "logs"):
        """Initialize logger with separate error and activity logs.

        Args:
            log_dir: Directory to store log files
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # Set up console logging
        self.logger = logging.getLogger("FashionScraper")
        self.logger.setLevel(logging.INFO)

        # Console handler for user-facing messages
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)

        # File handler for detailed logs
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(
            self.log_dir / f"scraper_{timestamp}.log"
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)

        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)

        # Error log CSV
        self.error_log_path = self.log_dir / f"errors_{timestamp}.csv"
        self._init_error_log()

    def _init_error_log(self):
        """Initialize the error log CSV file."""
        with open(self.error_log_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'designer', 'website', 'error_type',
                'error_message', 'url'
            ])

    def log_error(self, designer: str, website: str, error_type: str,
                  error_message: str, url: str = ""):
        """Log an error to both console and CSV file.

        Args:
            designer: Designer/brand name
            website: Website being processed
            error_type: Type of error (e.g., '404', 'Network', 'Parse')
            error_message: Detailed error message
            url: URL that caused the error
        """
        timestamp = datetime.now().isoformat()

        # Log to console and file
        self.logger.error(
            f"Error processing {designer} ({website}): {error_type} - {error_message}"
        )

        # Log to error CSV
        with open(self.error_log_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp, designer, website, error_type, error_message, url
            ])

    def info(self, message: str):
        """Log an info message."""
        self.logger.info(message)

    def debug(self, message: str):
        """Log a debug message."""
        self.logger.debug(message)


# ============================================================================
# TASK-1: CSV Input Processing for Designers List
# ============================================================================

class DesignerListReader:
    """Reads and validates the designers.csv input file."""

    def __init__(self, csv_path: str, logger: ScraperLogger):
        """Initialize the reader.

        Args:
            csv_path: Path to designers.csv file
            logger: Logger instance for error reporting
        """
        self.csv_path = Path(csv_path)
        self.logger = logger

    def read_designers(self) -> List[Dict[str, str]]:
        """Read designers from CSV file with error handling.

        Returns:
            List of dictionaries with 'designer_name' and 'website_url' keys
        """
        designers = []

        if not self.csv_path.exists():
            self.logger.log_error(
                designer="",
                website="",
                error_type="FileNotFound",
                error_message=f"CSV file not found: {self.csv_path}",
                url=""
            )
            return designers

        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                # Validate headers
                if 'designer_name' not in reader.fieldnames or \
                   'website_url' not in reader.fieldnames:
                    self.logger.log_error(
                        designer="",
                        website="",
                        error_type="InvalidFormat",
                        error_message="CSV must have 'designer_name' and 'website_url' columns",
                        url=""
                    )
                    return designers

                for row_num, row in enumerate(reader, start=2):
                    designer_name = row.get('designer_name', '').strip()
                    website_url = row.get('website_url', '').strip()

                    # Validate row data
                    if not designer_name or not website_url:
                        self.logger.log_error(
                            designer=designer_name or "Unknown",
                            website=website_url or "Unknown",
                            error_type="MalformedEntry",
                            error_message=f"Row {row_num}: Missing designer name or website URL",
                            url=website_url
                        )
                        continue

                    # Validate URL format
                    parsed = urlparse(website_url)
                    if not parsed.scheme or not parsed.netloc:
                        self.logger.log_error(
                            designer=designer_name,
                            website=website_url,
                            error_type="InvalidURL",
                            error_message=f"Row {row_num}: Invalid URL format",
                            url=website_url
                        )
                        continue

                    designers.append({
                        'designer_name': designer_name,
                        'website_url': website_url
                    })
                    self.logger.debug(f"Loaded designer: {designer_name} - {website_url}")

        except csv.Error as e:
            self.logger.log_error(
                designer="",
                website="",
                error_type="CSVError",
                error_message=f"Error reading CSV file: {str(e)}",
                url=""
            )
        except Exception as e:
            self.logger.log_error(
                designer="",
                website="",
                error_type="UnexpectedError",
                error_message=f"Unexpected error reading CSV: {str(e)}",
                url=""
            )

        self.logger.info(f"Loaded {len(designers)} designers from {self.csv_path}")
        return designers


# ============================================================================
# TASK-5: Hash-based Duplicate Detection System
# ============================================================================

class DuplicateDetector:
    """Detects duplicate images using content-based hashing."""

    def __init__(self, logger: ScraperLogger):
        """Initialize the duplicate detector.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.seen_hashes: Set[str] = set()
        self.lock = asyncio.Lock()

    def calculate_hash(self, image_data: bytes) -> str:
        """Calculate SHA-256 hash of image content.

        Args:
            image_data: Binary image data

        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(image_data).hexdigest()

    async def is_duplicate(self, image_data: bytes) -> tuple[bool, str]:
        """Check if image is a duplicate based on content hash.

        Args:
            image_data: Binary image data

        Returns:
            Tuple of (is_duplicate, hash_value)
        """
        image_hash = self.calculate_hash(image_data)

        async with self.lock:
            if image_hash in self.seen_hashes:
                self.logger.debug(f"Duplicate detected: {image_hash}")
                return True, image_hash

            self.seen_hashes.add(image_hash)
            return False, image_hash

    def get_duplicate_count(self) -> int:
        """Get total number of unique images seen."""
        return len(self.seen_hashes)


# ============================================================================
# TASK-14: Per-Domain Rate Limiting
# ============================================================================

class RateLimiter:
    """Per-domain rate limiter for respectful scraping."""

    def __init__(self, requests_per_second: float = 2.0):
        """Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second per domain
        """
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.domain_last_request: Dict[str, float] = {}
        self.locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def wait_if_needed(self, url: str):
        """Wait if necessary to respect rate limit for this domain.

        Args:
            url: URL being requested
        """
        domain = urlparse(url).netloc

        async with self.locks[domain]:
            now = time.time()
            last_request = self.domain_last_request.get(domain, 0)
            time_since_last = now - last_request

            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                await asyncio.sleep(wait_time)

            self.domain_last_request[domain] = time.time()


# ============================================================================
# TASK-13: Response Caching
# ============================================================================

class ResponseCache:
    """Cache for HTTP responses to avoid re-fetching pages."""

    def __init__(self, max_size: int = 1000):
        """Initialize response cache.

        Args:
            max_size: Maximum number of cached responses
        """
        self.cache: Dict[str, tuple[bytes, Dict]] = {}
        self.max_size = max_size
        self.access_times: Dict[str, float] = {}

    async def get(self, url: str) -> Optional[tuple[bytes, Dict]]:
        """Get cached response for URL.

        Args:
            url: URL to look up

        Returns:
            Tuple of (content, headers) or None if not cached
        """
        if url in self.cache:
            self.access_times[url] = time.time()
            return self.cache[url]
        return None

    async def set(self, url: str, content: bytes, headers: Dict):
        """Cache response for URL.

        Args:
            url: URL to cache
            content: Response content
            headers: Response headers
        """
        # Evict oldest if at capacity
        if len(self.cache) >= self.max_size:
            oldest_url = min(self.access_times, key=self.access_times.get)
            del self.cache[oldest_url]
            del self.access_times[oldest_url]

        self.cache[url] = (content, headers)
        self.access_times[url] = time.time()


# ============================================================================
# TASK-7: Metadata Extraction from Product Pages
# ============================================================================

class MetadataExtractor:
    """Extracts product metadata from web pages."""

    def __init__(self, logger: ScraperLogger):
        """Initialize the metadata extractor.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, str]:
        """Extract product metadata from page HTML.

        Args:
            soup: BeautifulSoup object of the page
            url: URL of the page

        Returns:
            Dictionary with metadata fields
        """
        metadata = {
            'product_name': '',
            'product_category': '',
            'price': ''
        }

        try:
            # Try multiple strategies for product name
            metadata['product_name'] = self._extract_product_name(soup)

            # Try to extract category
            metadata['product_category'] = self._extract_category(soup, url)

            # Try to extract price
            metadata['price'] = self._extract_price(soup)

        except Exception as e:
            self.logger.debug(f"Error extracting metadata from {url}: {str(e)}")

        return metadata

    def _extract_product_name(self, soup: BeautifulSoup) -> str:
        """Extract product name using multiple strategies."""
        # Strategy 1: Common product title tags
        for selector in ['h1.product-name', 'h1.product-title', 'h1[itemprop="name"]',
                        'h1', '.product-name', '.product-title']:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                return element.get_text(strip=True)

        # Strategy 2: Meta tags
        for meta in ['og:title', 'twitter:title']:
            element = soup.find('meta', property=meta) or soup.find('meta', attrs={'name': meta})
            if element and element.get('content'):
                return element.get('content').strip()

        # Strategy 3: Title tag
        if soup.title and soup.title.string:
            return soup.title.string.strip()

        return "Unknown Product"

    def _extract_category(self, soup: BeautifulSoup, url: str) -> str:
        """Extract product category from breadcrumbs or URL."""
        # Strategy 1: Breadcrumb navigation
        breadcrumbs = soup.select('.breadcrumb li, .breadcrumbs li, [class*="breadcrumb"] a')
        if breadcrumbs and len(breadcrumbs) > 1:
            # Get the second-to-last item (last is usually the product)
            category = breadcrumbs[-2].get_text(strip=True) if len(breadcrumbs) > 1 else breadcrumbs[-1].get_text(strip=True)
            return category

        # Strategy 2: URL path
        path_parts = [p for p in urlparse(url).path.split('/') if p]
        if path_parts:
            # Common category keywords
            categories = ['dress', 'shoes', 'bags', 'accessories', 'clothing',
                         'handbags', 'jewelry', 'watches', 'sunglasses']
            for part in path_parts:
                if part.lower() in categories:
                    return part.capitalize()

        # Strategy 3: Category meta tags
        category_meta = soup.find('meta', attrs={'name': 'category'}) or \
                       soup.find('meta', property='product:category')
        if category_meta and category_meta.get('content'):
            return category_meta.get('content').strip()

        return "Unknown"

    def _extract_price(self, soup: BeautifulSoup) -> str:
        """Extract price information."""
        # Strategy 1: Common price selectors
        for selector in ['.price', '.product-price', '[class*="price"]',
                        '[itemprop="price"]', '.money']:
            element = soup.select_one(selector)
            if element:
                price_text = element.get_text(strip=True)
                if price_text and any(c.isdigit() for c in price_text):
                    return price_text

        # Strategy 2: Meta tags
        price_meta = soup.find('meta', attrs={'property': 'og:price:amount'}) or \
                    soup.find('meta', attrs={'itemprop': 'price'})
        if price_meta and price_meta.get('content'):
            return price_meta.get('content').strip()

        return ""


# ============================================================================
# TASK-10: Async HTTP Client with aiohttp
# TASK-11: Connection Pooling and Session Management
# ============================================================================

class AsyncHTTPClient:
    """High-performance async HTTP client with connection pooling."""

    def __init__(self, logger: ScraperLogger, rate_limiter: RateLimiter,
                 cache: ResponseCache):
        """Initialize async HTTP client.

        Args:
            logger: Logger instance
            rate_limiter: Rate limiter instance
            cache: Response cache instance
        """
        self.logger = logger
        self.rate_limiter = rate_limiter
        self.cache = cache
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Initialize aiohttp session with optimized settings."""
        # TASK-11: Optimized connection pooling
        connector = aiohttp.TCPConnector(
            limit=100,  # Total connection pool size
            limit_per_host=10,  # Connections per host
            ttl_dns_cache=300,  # DNS cache TTL
            ssl=False  # Disable SSL verification for simplicity
        )

        timeout = aiohttp.ClientTimeout(
            total=30,
            connect=10,
            sock_read=20
        )

        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the session."""
        if self.session:
            await self.session.close()

    async def get(self, url: str, use_cache: bool = True) -> Optional[tuple[bytes, Dict]]:
        """Perform async GET request with rate limiting and caching.

        Args:
            url: URL to fetch
            use_cache: Whether to use cached response

        Returns:
            Tuple of (content, headers) or None on error
        """
        # Check cache first
        if use_cache:
            cached = await self.cache.get(url)
            if cached:
                self.logger.debug(f"Cache hit: {url}")
                return cached

        # Apply rate limiting
        await self.rate_limiter.wait_if_needed(url)

        try:
            async with self.session.get(url) as response:
                response.raise_for_status()
                content = await response.read()
                headers = dict(response.headers)

                # Cache the response
                if use_cache:
                    await self.cache.set(url, content, headers)

                return content, headers

        except aiohttp.ClientError as e:
            self.logger.debug(f"HTTP error fetching {url}: {str(e)}")
            return None
        except asyncio.TimeoutError:
            self.logger.debug(f"Timeout fetching {url}")
            return None
        except Exception as e:
            self.logger.debug(f"Unexpected error fetching {url}: {str(e)}")
            return None


# ============================================================================
# TASK-19: Site-Specific Configuration System
# ============================================================================

class SiteConfig:
    """Manages site-specific configuration for scraping strategies and selectors.

    Loads configuration from JSON file and provides per-site settings for:
    - Scraping strategy (HTML vs Playwright)
    - Custom CSS selectors
    - Rate limits
    - Detection thresholds
    - Other site-specific behavior
    """

    def __init__(self, config_file: Optional[str] = None, logger=None):
        """Initialize site configuration.

        Args:
            config_file: Path to JSON configuration file (optional)
            logger: Logger instance for debug output
        """
        self.logger = logger
        self.config = {}

        if config_file:
            self.load_config(config_file)

    def load_config(self, config_file: str) -> bool:
        """Load configuration from JSON file.

        Args:
            config_file: Path to JSON configuration file

        Returns:
            True if config loaded successfully, False otherwise
        """
        try:
            config_path = Path(config_file)
            if not config_path.exists():
                if self.logger:
                    self.logger.info(f"Config file not found: {config_file}, using defaults")
                return False

            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)

            # Remove schema/comment keys
            self.config = {k: v for k, v in self.config.items()
                          if not k.startswith('_')}

            if self.logger:
                self.logger.info(f"Loaded site configuration for {len(self.config)} domains")
                self.logger.debug(f"Configured domains: {', '.join(self.config.keys())}")

            return True

        except json.JSONDecodeError as e:
            if self.logger:
                self.logger.warning(f"Invalid JSON in config file: {e}")
            return False
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error loading config file: {e}")
            return False

    def get_site_config(self, url: str) -> Dict:
        """Get configuration for a specific site based on its URL.

        Args:
            url: URL to get configuration for

        Returns:
            Dictionary with site configuration, or empty dict if no config found
        """
        # Extract domain from URL
        parsed = urlparse(url)
        domain = parsed.netloc

        # Try exact match first
        if domain in self.config:
            return self.config[domain]

        # Try without www prefix
        if domain.startswith('www.'):
            domain_no_www = domain[4:]
            if domain_no_www in self.config:
                return self.config[domain_no_www]

        # Try with www prefix
        domain_with_www = f"www.{domain}"
        if domain_with_www in self.config:
            return self.config[domain_with_www]

        # No config found
        return {}

    def should_use_playwright(self, url: str) -> bool:
        """Determine if Playwright should be used for this URL.

        Args:
            url: URL to check

        Returns:
            True if Playwright should be used, False otherwise
        """
        site_config = self.get_site_config(url)
        return site_config.get('strategy', 'html').lower() == 'playwright'

    def get_rate_limit(self, url: str, default: float = 2.0) -> float:
        """Get rate limit for a specific site.

        Args:
            url: URL to get rate limit for
            default: Default rate limit if not configured

        Returns:
            Rate limit in requests per second
        """
        site_config = self.get_site_config(url)
        return site_config.get('rate_limit', default)

    def get_detection_threshold(self, url: str, default: int = 3) -> int:
        """Get product detection threshold for a specific site.

        Args:
            url: URL to get threshold for
            default: Default threshold if not configured

        Returns:
            Minimum score required for product page detection
        """
        site_config = self.get_site_config(url)
        return site_config.get('detection_threshold', default)

    def get_max_pages(self, url: str, default: int = 20) -> int:
        """Get maximum pages to scrape for a specific site.

        Args:
            url: URL to get max pages for
            default: Default max pages if not configured

        Returns:
            Maximum number of product pages to scrape
        """
        site_config = self.get_site_config(url)
        return site_config.get('max_pages', default)

    def get_product_selectors(self, url: str) -> Dict[str, str]:
        """Get custom product selectors for a specific site.

        Args:
            url: URL to get selectors for

        Returns:
            Dictionary of CSS selectors for product elements
        """
        site_config = self.get_site_config(url)
        return site_config.get('product_selectors', {})

    def should_scroll_to_load(self, url: str) -> bool:
        """Determine if page scrolling is needed to trigger lazy loading.

        Args:
            url: URL to check

        Returns:
            True if scrolling should be performed, False otherwise
        """
        site_config = self.get_site_config(url)
        return site_config.get('scroll_to_load', False)

    def get_product_sitemap(self, url: str) -> Optional[str]:
        """Get product sitemap URL for a specific site.

        Args:
            url: URL to get sitemap for

        Returns:
            Sitemap URL if configured, None otherwise
        """
        site_config = self.get_site_config(url)
        return site_config.get('product_sitemap')

    async def fetch_sitemap_products(self, sitemap_url: str, max_products: int = 20) -> List[str]:
        """Fetch product URLs from a sitemap.

        Args:
            sitemap_url: URL of the product sitemap
            max_products: Maximum number of product URLs to return

        Returns:
            List of product page URLs from the sitemap
        """
        import aiohttp
        from bs4 import BeautifulSoup

        product_urls = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(sitemap_url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        xml_content = await response.text()
                        soup = BeautifulSoup(xml_content, 'xml')

                        # Find all <url> elements, then get the first <loc> child (product page URL)
                        # This avoids accidentally including <image:loc> elements
                        urls = soup.find_all('url')
                        for url_elem in urls[:max_products]:
                            loc = url_elem.find('loc', recursive=False)  # Only direct children
                            if loc:
                                product_urls.append(loc.text.strip())

                        if self.logger:
                            self.logger.info(f"Fetched {len(product_urls)} product URLs from sitemap")
                    else:
                        if self.logger:
                            self.logger.warning(f"Failed to fetch sitemap: HTTP {response.status}")

        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error fetching sitemap {sitemap_url}: {e}")

        return product_urls


# ============================================================================
# TASK-3: Web Crawling Engine for Product Page Discovery (Async)
# ============================================================================

class AsyncWebCrawler:
    """Discovers product pages on fashion websites using async requests."""

    def __init__(self, http_client: AsyncHTTPClient, logger: ScraperLogger):
        """Initialize the web crawler.

        Args:
            http_client: Async HTTP client
            logger: Logger instance
        """
        self.http_client = http_client
        self.logger = logger
        self.visited_urls: Set[str] = set()

    async def discover_product_pages(self, base_url: str, designer: str,
                                     max_pages: int = 20) -> List[str]:
        """Discover product pages from a website.

        Args:
            base_url: Base URL of the website
            designer: Designer name for error logging
            max_pages: Maximum number of pages to discover

        Returns:
            List of product page URLs
        """
        product_pages = []
        to_visit = [base_url]
        base_domain = urlparse(base_url).netloc
        max_visits = 30  # Limit total pages visited

        while to_visit and len(product_pages) < max_pages and len(self.visited_urls) < max_visits:
            url = to_visit.pop(0)

            if url in self.visited_urls:
                continue

            self.visited_urls.add(url)

            result = await self.http_client.get(url)
            if not result:
                continue

            content, _ = result
            soup = BeautifulSoup(content, 'lxml')

            # Check if this is a product page
            if self._is_product_page(soup, url):
                product_pages.append(url)
                self.logger.info(f"  Found product page: {url[:80]}...")

            # Find more links to explore
            new_links = self._extract_links(soup, base_url, base_domain)
            for link in new_links[:20]:
                if link not in self.visited_urls and len(to_visit) < 20:
                    to_visit.append(link)

        self.logger.info(f"Discovered {len(product_pages)} product pages (visited {len(self.visited_urls)} pages total)")
        return product_pages

    def _is_product_page(self, soup: BeautifulSoup, url: str) -> bool:
        """Determine if a page is a product page."""
        indicators = [
            '/product/' in url.lower(),
            '/p/' in url.lower(),
            '/item/' in url.lower(),
            soup.find('button', string=lambda s: s and 'add to cart' in s.lower()),
            soup.find('button', string=lambda s: s and 'buy' in s.lower()),
            soup.select_one('[itemtype*="Product"]'),
            soup.select_one('.product-price, .price'),
            soup.find('meta', property='og:type', content='product'),
        ]

        return any(indicators)

    def _extract_links(self, soup: BeautifulSoup, base_url: str,
                      base_domain: str) -> List[str]:
        """Extract and filter links from a page."""
        links = []

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(base_url, href)

            # Only keep links from the same domain
            if urlparse(full_url).netloc == base_domain:
                # Filter out non-product links
                if not any(x in full_url.lower() for x in
                          ['login', 'signup', 'account', 'cart', 'checkout',
                           'privacy', 'terms', 'contact', 'about']):
                    links.append(full_url)

        return links


# ============================================================================
# TASK-4: Image Discovery and Extraction from Product Pages (Async)
# ============================================================================

class AsyncImageExtractor:
    """Extracts images from product pages."""

    def __init__(self, http_client: AsyncHTTPClient, logger: ScraperLogger):
        """Initialize the image extractor.

        Args:
            http_client: Async HTTP client
            logger: Logger instance
        """
        self.http_client = http_client
        self.logger = logger

    async def extract_images(self, url: str, designer: str) -> List[Dict[str, str]]:
        """Extract all product images from a page.

        Args:
            url: URL of the product page
            designer: Designer name for error logging

        Returns:
            List of dictionaries with 'url' and 'source_page' keys
        """
        images = []

        result = await self.http_client.get(url)
        if not result:
            return images

        content, _ = result
        soup = BeautifulSoup(content, 'lxml')

        # Find all image tags
        img_tags = soup.find_all('img')

        for img in img_tags:
            img_url = img.get('src') or img.get('data-src') or img.get('data-lazy')

            if not img_url:
                continue

            # Convert relative URLs to absolute
            img_url = urljoin(url, img_url)

            # Filter out small icons, logos, etc.
            if self._is_valid_product_image(img_url, img):
                images.append({
                    'url': img_url,
                    'source_page': url
                })

        # TASK-19: Fallback for JavaScript-rendered sites - check Open Graph meta tags
        if not images:
            og_image = soup.find('meta', property='og:image')
            twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})

            if og_image and og_image.get('content'):
                img_url = urljoin(url, og_image['content'])
                images.append({
                    'url': img_url,
                    'source_page': url
                })
                self.logger.debug(f"Using og:image for {url}")
            elif twitter_image and twitter_image.get('content'):
                img_url = urljoin(url, twitter_image['content'])
                images.append({
                    'url': img_url,
                    'source_page': url
                })
                self.logger.debug(f"Using twitter:image for {url}")

        self.logger.debug(f"Found {len(images)} images on {url}")
        return images

    def _is_valid_product_image(self, img_url: str, img_tag) -> bool:
        """Check if an image is likely a product image."""
        # Skip data URIs
        if img_url.startswith('data:'):
            return False

        # Skip very small images (likely icons)
        # Only check size if width/height attributes actually exist
        width = img_tag.get('width')
        height = img_tag.get('height')
        if width and height:
            try:
                if width.isdigit() and height.isdigit():
                    if int(width) < 100 or int(height) < 100:
                        return False
            except:
                pass

        # Check for common exclusion patterns
        exclude_patterns = ['logo', 'icon', 'sprite', 'button', 'badge',
                           'flag', 'social', 'payment']
        url_lower = img_url.lower()
        if any(pattern in url_lower for pattern in exclude_patterns):
            return False

        return True


# ============================================================================
# TASK-6: Image Download Manager with Deduplication (Async)
# TASK-12: Batch Processing for Image Downloads
# ============================================================================

class AsyncImageDownloader:
    """Downloads images with duplicate detection and batch processing."""

    def __init__(self, http_client: AsyncHTTPClient, output_dir: Path,
                 duplicate_detector: DuplicateDetector, logger: ScraperLogger,
                 person_filter: Optional['PersonDetectionFilter'] = None):
        """Initialize the image downloader.

        Args:
            http_client: Async HTTP client
            output_dir: Directory to save images
            duplicate_detector: Duplicate detection instance
            logger: Logger instance
            person_filter: Optional person detection filter (TASK-20)
        """
        self.http_client = http_client
        self.output_dir = output_dir
        self.duplicate_detector = duplicate_detector
        self.logger = logger
        self.person_filter = person_filter

        # TASK-20: Track filtered image hashes to avoid re-downloading
        self.filtered_hashes: Set[str] = set()
        self._load_filtered_hashes()

    async def download_image(self, img_url: str, designer: str) -> Optional[Dict[str, str]]:
        """Download an image if it's not a duplicate.

        Args:
            img_url: URL of the image
            designer: Designer name for filename

        Returns:
            Dictionary with download info or None if skipped/failed
        """
        result = await self.http_client.get(img_url, use_cache=False)
        if not result:
            return None

        image_data, headers = result

        # Check for duplicates
        is_dup, img_hash = await self.duplicate_detector.is_duplicate(image_data)
        if is_dup:
            return None

        # TASK-20: Check if hash was previously filtered (no person detected)
        if img_hash in self.filtered_hashes:
            return None

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        ext = self._get_extension(img_url, headers.get('content-type', ''))
        filename = f"{designer.lower().replace(' ', '_')}_{timestamp}{ext}"
        filepath = self.output_dir / filename

        # Save image
        try:
            with open(filepath, 'wb') as f:
                f.write(image_data)

            # TASK-20: Filter immediately after download
            has_person = True
            person_count = 0

            if self.person_filter:
                has_person, person_count = self.person_filter.detect_person(str(filepath))

                if not has_person:
                    # No person detected - delete and track hash
                    filepath.unlink()  # Delete file
                    self.filtered_hashes.add(img_hash)
                    self._save_filtered_hashes()
                    return None  # Don't count toward limit

            return {
                'filename': filename,
                'hash': img_hash,
                'size': len(image_data),
                'has_person': has_person,
                'person_count': person_count
            }
        except Exception as e:
            self.logger.debug(f"Error saving image {filename}: {str(e)}")
            return None

    async def download_batch(self, image_urls: List[tuple[str, str]]) -> List[Optional[Dict[str, str]]]:
        """Download multiple images concurrently.

        Args:
            image_urls: List of (image_url, designer) tuples

        Returns:
            List of download results
        """
        tasks = [self.download_image(url, designer) for url, designer in image_urls]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def _get_extension(self, url: str, content_type: str) -> str:
        """Determine file extension from URL or content type."""
        # Try URL first
        path = urlparse(url).path
        if '.' in path:
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                return ext

        # Try content type
        if 'jpeg' in content_type or 'jpg' in content_type:
            return '.jpg'
        elif 'png' in content_type:
            return '.png'
        elif 'gif' in content_type:
            return '.gif'
        elif 'webp' in content_type:
            return '.webp'

        return '.jpg'  # Default

    def _load_filtered_hashes(self):
        """Load filtered hashes from file (TASK-20)."""
        filtered_file = self.output_dir / "filtered_hashes.json"
        if filtered_file.exists():
            try:
                with open(filtered_file, 'r') as f:
                    self.filtered_hashes = set(json.load(f))
                self.logger.debug(f"Loaded {len(self.filtered_hashes)} filtered hashes")
            except Exception as e:
                self.logger.debug(f"Error loading filtered hashes: {e}")

    def _save_filtered_hashes(self):
        """Save filtered hashes to file (TASK-20)."""
        filtered_file = self.output_dir / "filtered_hashes.json"
        try:
            with open(filtered_file, 'w') as f:
                json.dump(list(self.filtered_hashes), f)
        except Exception as e:
            self.logger.debug(f"Error saving filtered hashes: {e}")


# ============================================================================
# TASK-8: CSV Logging System for Image Sources
# ============================================================================

class ImageSourceLogger:
    """Logs image source metadata to CSV."""

    def __init__(self, output_dir: Path, logger: ScraperLogger):
        """Initialize the CSV logger.

        Args:
            output_dir: Directory to save the log file
            logger: Logger instance
        """
        self.output_dir = output_dir
        self.logger = logger
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = output_dir / f"image_sources_{timestamp}.csv"
        self.lock = asyncio.Lock()
        self._init_csv()

    def _init_csv(self):
        """Initialize the CSV file with headers."""
        with open(self.log_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'source_url', 'designer_name', 'product_name',
                'product_category', 'price', 'timestamp',
                'image_url', 'local_filename'
            ])

    async def log_image(self, source_url: str, designer_name: str,
                  metadata: Dict[str, str], image_url: str,
                  local_filename: str):
        """Log an image download to the CSV.

        Args:
            source_url: URL of the product page
            designer_name: Designer/brand name
            metadata: Product metadata dictionary
            image_url: Original image URL
            local_filename: Local filename where image was saved
        """
        timestamp = datetime.now().isoformat()

        async with self.lock:
            with open(self.log_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    source_url,
                    designer_name,
                    metadata.get('product_name', ''),
                    metadata.get('product_category', ''),
                    metadata.get('price', ''),
                    timestamp,
                    image_url,
                    local_filename
                ])


# ============================================================================
# Main Async Scraper Class
# ============================================================================

class AsyncFashionScraper:
    """Main async scraper orchestrator with performance optimizations."""

    def __init__(self, input_csv: str = "designers.csv",
                 output_dir: str = "output",
                 log_dir: str = "logs",
                 max_pages_per_site: int = 100,
                 requests_per_second: float = 2.0,
                 max_images: Optional[int] = None,
                 designer_filter: Optional[str] = None,
                 max_concurrent_designers: int = 5,
                 use_playwright_for: List[str] = None,
                 detection_threshold: int = 3,
                 site_config_file: Optional[str] = None):
        """Initialize the async scraper.

        Args:
            input_csv: Path to designers CSV file
            output_dir: Directory to save downloaded images
            log_dir: Directory for log files
            max_pages_per_site: Maximum product pages to process per site
            requests_per_second: Rate limit per domain
            max_images: Maximum images to download per designer (None = unlimited)
            designer_filter: Only process this designer by name (None = all designers)
            max_concurrent_designers: Maximum designers to process simultaneously
            use_playwright_for: List of designer names that require Playwright (TASK-17)
            detection_threshold: Minimum score for product page detection (TASK-18, default: 3)
            site_config_file: Path to site configuration JSON file (TASK-19, optional)
        """
        self.input_csv = input_csv
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.max_pages_per_site = max_pages_per_site
        self.max_images = max_images
        self.designer_filter = designer_filter
        self.max_concurrent_designers = max_concurrent_designers
        self.use_playwright_for = [name.lower() for name in (use_playwright_for or [])]
        self.detection_threshold = detection_threshold

        # Initialize components
        self.logger = ScraperLogger(log_dir)
        self.reader = DesignerListReader(input_csv, self.logger)
        self.duplicate_detector = DuplicateDetector(self.logger)
        self.rate_limiter = RateLimiter(requests_per_second)
        self.cache = ResponseCache(max_size=1000)

        # TASK-19: Initialize site configuration
        self.site_config = SiteConfig(site_config_file, self.logger)

        # TASK-18: Initialize content-based product page detector (if available)
        try:
            self.detector = ContentBasedDetector(threshold=detection_threshold, logger=self.logger)
        except NameError:
            # ContentBasedDetector not available in this version
            self.detector = None
            if self.logger:
                self.logger.debug("ContentBasedDetector not available, using basic detection")

        # Async locks for shared resources (TASK-15)
        self.stats_lock = None  # Will be initialized in run()
        self.source_log_lock = None  # Will be initialized in run()

        # Statistics
        self.stats = {
            'images_downloaded': 0,
            'duplicates_skipped': 0,
            'errors_encountered': 0,
            'product_pages_processed': 0
        }

    async def run(self):
        """Execute the async scraping process."""
        self.logger.info("=" * 60)
        self.logger.info("Fashion Image Web Scraper (Async/High-Performance)")
        self.logger.info("=" * 60)

        # Initialize async locks for shared resources (TASK-15)
        self.stats_lock = asyncio.Lock()
        self.source_log_lock = asyncio.Lock()

        # Read designers list
        designers = self.reader.read_designers()

        if not designers:
            self.logger.info("No designers to process. Exiting.")
            return

        # Apply designer filter if specified
        if self.designer_filter:
            original_count = len(designers)
            designers = [d for d in designers
                        if d['designer_name'].lower() == self.designer_filter.lower()]
            if not designers:
                self.logger.info(f"No designer found matching '{self.designer_filter}'. Exiting.")
                return
            self.logger.info(f"Filtering to designer: {self.designer_filter} "
                           f"({len(designers)} of {original_count} total)")

        # Show max images limit if set
        if self.max_images:
            self.logger.info(f"Maximum images per designer: {self.max_images}")

        # Show concurrency info (TASK-15)
        if len(designers) > 1:
            self.logger.info(f"Processing {len(designers)} designers concurrently "
                           f"(max {self.max_concurrent_designers} at a time)")

        # TASK-20: Initialize person filter if available
        person_filter = None
        if PERSON_FILTER_AVAILABLE:
            try:
                person_filter = PersonDetectionFilter(
                    model_name="yolov8n.pt",
                    confidence_threshold=0.25
                )
                self.logger.info("Person detection enabled (YOLO)")
            except Exception as e:
                self.logger.info(f"Person detection unavailable: {e}")

        # Initialize HTTP client
        async with AsyncHTTPClient(self.logger, self.rate_limiter, self.cache) as http_client:
            # Initialize scraping components
            crawler = AsyncWebCrawler(http_client, self.logger)
            metadata_extractor = MetadataExtractor(self.logger)
            image_extractor = AsyncImageExtractor(http_client, self.logger)
            image_downloader = AsyncImageDownloader(
                http_client, self.output_dir, self.duplicate_detector, self.logger,
                person_filter=person_filter
            )
            source_logger = ImageSourceLogger(self.output_dir, self.logger)

            # TASK-15: Process designers concurrently with semaphore to limit concurrency
            designer_semaphore = asyncio.Semaphore(self.max_concurrent_designers)

            async def process_designer_with_semaphore(idx: int, designer: dict):
                """Process a designer with semaphore control."""
                async with designer_semaphore:
                    self.logger.info(f"\n[{idx}/{len(designers)}] Processing: {designer['designer_name']}")
                    self.logger.info(f"Website: {designer['website_url']}")

                    try:
                        await self._scrape_designer(
                            designer['designer_name'],
                            designer['website_url'],
                            crawler,
                            metadata_extractor,
                            image_extractor,
                            image_downloader,
                            source_logger
                        )
                    except Exception as e:
                        self.logger.log_error(
                            designer['designer_name'],
                            designer['website_url'],
                            "DesignerProcessingError",
                            f"Failed to process designer: {str(e)}",
                            designer['website_url']
                        )
                        # Use lock to safely update shared stats
                        async with self.stats_lock:
                            self.stats['errors_encountered'] += 1

            # Launch all designers concurrently
            tasks = [
                process_designer_with_semaphore(idx, designer)
                for idx, designer in enumerate(designers, 1)
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Store source logger path for summary
            self.source_logger_path = source_logger.log_path

        # Print summary
        self._print_summary()

    async def _scrape_designer(self, designer_name: str, website_url: str,
                               crawler: AsyncWebCrawler,
                               metadata_extractor: MetadataExtractor,
                               image_extractor: AsyncImageExtractor,
                               image_downloader: AsyncImageDownloader,
                               source_logger: ImageSourceLogger):
        """Scrape a single designer's website.

        Args:
            designer_name: Name of the designer/brand
            website_url: Base URL of the website
            crawler: Web crawler instance
            metadata_extractor: Metadata extractor instance
            image_extractor: Image extractor instance
            image_downloader: Image downloader instance
            source_logger: Source logger instance
        """
        # TASK-19: Check if site has a product sitemap configured
        sitemap_url = self.site_config.get_product_sitemap(website_url)

        if sitemap_url:
            # Use sitemap to get product URLs (bypasses crawling)
            self.logger.info(f"Using sitemap for product discovery: {sitemap_url}")
            product_pages = await self.site_config.fetch_sitemap_products(
                sitemap_url, self.max_pages_per_site
            )
        else:
            # TASK-17 & TASK-19: Determine if we should use Playwright for this designer
            # Priority: 1) Site config, 2) Manual --use-playwright argument
            use_playwright_from_config = self.site_config.should_use_playwright(website_url)
            use_playwright_from_arg = designer_name.lower() in self.use_playwright_for
            use_playwright = use_playwright_from_config or use_playwright_from_arg

            if use_playwright_from_config:
                self.logger.info(f"Site config specifies Playwright for {urlparse(website_url).netloc}")

            if use_playwright:
                if not PLAYWRIGHT_AVAILABLE:
                    self.logger.log_error(
                        designer_name, website_url, "PlaywrightUnavailable",
                        "Playwright requested but not installed. Install with: pip install playwright",
                        website_url
                    )
                    return

                self.logger.info(f"Using Playwright for JavaScript rendering (designer: {designer_name})")
                # Use Playwright crawler for JavaScript-rendered sites
                async with PlaywrightCrawler(self.logger) as pw_crawler:
                    product_pages = await pw_crawler.discover_product_pages(
                        website_url, designer_name, self.max_pages_per_site
                    )
            else:
                # Use regular HTML crawler
                self.logger.info("Discovering product pages...")
                product_pages = await crawler.discover_product_pages(
                    website_url, designer_name, self.max_pages_per_site
                )

        if not product_pages:
            self.logger.info("No product pages found")
            return

        # Process product pages concurrently (in batches)
        batch_size = 5  # Process 5 pages at a time
        for i in range(0, len(product_pages), batch_size):
            batch = product_pages[i:i + batch_size]
            tasks = [
                self._process_product_page(
                    page_url, designer_name, metadata_extractor,
                    image_extractor, image_downloader, source_logger
                )
                for page_url in batch
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_product_page(self, page_url: str, designer_name: str,
                                     metadata_extractor: MetadataExtractor,
                                     image_extractor: AsyncImageExtractor,
                                     image_downloader: AsyncImageDownloader,
                                     source_logger: ImageSourceLogger):
        """Process a single product page.

        Args:
            page_url: URL of the product page
            designer_name: Designer name
            metadata_extractor: Metadata extractor instance
            image_extractor: Image extractor instance
            image_downloader: Image downloader instance
            source_logger: Source logger instance
        """
        try:
            self.logger.info(f"  Processing: {page_url[:60]}...")

            # Extract images from page
            images = await image_extractor.extract_images(page_url, designer_name)

            if not images:
                return

            # Extract metadata
            result = await image_extractor.http_client.get(page_url)
            if not result:
                return

            content, _ = result
            soup = BeautifulSoup(content, 'lxml')
            metadata = metadata_extractor.extract_metadata(soup, page_url)

            # TASK-16 + TASK-20: Process images in smaller batches to respect --max-images limit
            # Download in batches of 15 to check counter between batches
            BATCH_SIZE = 15
            page_downloaded = 0
            page_duplicates = 0

            # Prepare image URLs for processing
            image_data = [(img['url'], designer_name, img) for img in images]

            # Process in batches
            for batch_start in range(0, len(image_data), BATCH_SIZE):
                # Check limit before starting each batch
                async with self.stats_lock:
                    if self.max_images and self.stats['images_downloaded'] >= self.max_images:
                        self.logger.info(f"    Reached max images limit ({self.max_images})")
                        break

                # Get current batch
                batch_end = min(batch_start + BATCH_SIZE, len(image_data))
                batch = image_data[batch_start:batch_end]

                # Download batch
                image_urls = [(url, designer) for url, designer, _ in batch]
                download_results = await image_downloader.download_batch(image_urls)

                # Process results
                for (url, designer, img), result in zip(batch, download_results):
                    if isinstance(result, dict) and result:
                        # Image downloaded successfully (has person if filter enabled)
                        # Check limit BEFORE processing this image
                        async with self.stats_lock:
                            if self.max_images and self.stats['images_downloaded'] >= self.max_images:
                                self.logger.info(f"    Reached max images limit ({self.max_images})")
                                break

                        # Use source_log_lock to protect source logger writes (TASK-15)
                        async with self.source_log_lock:
                            await source_logger.log_image(
                                source_url=page_url,
                                designer_name=designer_name,
                                metadata=metadata,
                                image_url=img['url'],
                                local_filename=result['filename']
                            )
                        page_downloaded += 1
                        async with self.stats_lock:
                            self.stats['images_downloaded'] += 1
                    else:
                        # Duplicate, failed, or filtered (no person detected)
                        page_duplicates += 1
                        async with self.stats_lock:
                            self.stats['duplicates_skipped'] += 1

                # Check if we've hit the limit after processing this batch
                async with self.stats_lock:
                    if self.max_images and self.stats['images_downloaded'] >= self.max_images:
                        break

            # Read stats with lock for display
            async with self.stats_lock:
                total_images = self.stats['images_downloaded']
            self.logger.info(
                f"    Downloaded: {page_downloaded}, Skipped: {page_duplicates} "
                f"(Total: {total_images} images)"
            )
            async with self.stats_lock:
                self.stats['product_pages_processed'] += 1

        except Exception as e:
            self.logger.log_error(
                designer_name,
                page_url,
                "PageProcessingError",
                f"Error processing page: {str(e)}",
                page_url
            )
            async with self.stats_lock:
                self.stats['errors_encountered'] += 1

    def _print_summary(self):
        """Print final summary statistics."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("SCRAPING COMPLETE")
        self.logger.info("=" * 60)
        self.logger.info(f"Product pages processed: {self.stats['product_pages_processed']}")
        self.logger.info(f"Total images downloaded: {self.stats['images_downloaded']}")
        self.logger.info(f"Duplicates skipped: {self.stats['duplicates_skipped']}")
        self.logger.info(f"Errors encountered: {self.stats['errors_encountered']}")
        self.logger.info(f"\nOutput directory: {self.output_dir.absolute()}")
        self.logger.info(f"Image source log: {self.source_logger_path}")
        self.logger.info(f"Error log: {self.logger.error_log_path}")
        self.logger.info(f"Log directory: {self.logger.log_dir.absolute()}")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the async scraper with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description='Fashion Image Web Scraper - High-performance async version',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Scrape all designers, unlimited images
  python fashion_scraper_async.py

  # Scrape all designers, max 100 images each (for testing)
  python fashion_scraper_async.py --max-images 100

  # Scrape only Gucci, unlimited images
  python fashion_scraper_async.py --designer Gucci

  # Scrape only Anna Sui, max 50 images
  python fashion_scraper_async.py --designer "Anna Sui" --max-images 50

  # Scrape all designers with 10 concurrent at a time
  python fashion_scraper_async.py --concurrent 10

  # Use Playwright for JavaScript-rendered luxury sites
  python fashion_scraper_async.py --use-playwright Gucci Prada --max-images 50

  # Custom input/output paths
  python fashion_scraper_async.py --input mydesigners.csv --output myimages/
        '''
    )

    parser.add_argument(
        '--max-images',
        type=int,
        default=None,
        metavar='N',
        help='Maximum number of images to download per designer (default: unlimited)'
    )

    parser.add_argument(
        '--designer',
        type=str,
        default=None,
        metavar='NAME',
        help='Process only the specified designer by name (default: process all)'
    )

    parser.add_argument(
        '--input',
        type=str,
        default='designers.csv',
        metavar='FILE',
        help='Path to designers CSV file (default: designers.csv)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default='output',
        metavar='DIR',
        help='Output directory for images (default: output/)'
    )

    parser.add_argument(
        '--max-pages',
        type=int,
        default=20,
        metavar='N',
        help='Maximum product pages to process per site (default: 20)'
    )

    parser.add_argument(
        '--rate-limit',
        type=float,
        default=2.0,
        metavar='N',
        help='Requests per second per domain (default: 2.0)'
    )

    parser.add_argument(
        '--concurrent',
        type=int,
        default=5,
        metavar='N',
        help='Maximum designers to process concurrently (default: 5)'
    )

    parser.add_argument(
        '--use-playwright',
        type=str,
        nargs='*',
        metavar='DESIGNER',
        help='Designer names that require Playwright for JavaScript rendering (e.g., --use-playwright Gucci Prada)'
    )

    parser.add_argument(
        '--detection-threshold',
        type=int,
        default=3,
        metavar='N',
        help='Minimum score for product page detection (TASK-18, default: 3, higher = stricter)'
    )

    parser.add_argument(
        '--site-config',
        type=str,
        default=None,
        metavar='FILE',
        help='Path to site configuration JSON file (TASK-19, default: None - uses defaults)'
    )

    args = parser.parse_args()

    # Create scraper with parsed arguments
    scraper = AsyncFashionScraper(
        input_csv=args.input,
        output_dir=args.output,
        log_dir="logs",
        max_pages_per_site=args.max_pages,
        requests_per_second=args.rate_limit,
        max_images=args.max_images,
        designer_filter=args.designer,
        max_concurrent_designers=args.concurrent,
        use_playwright_for=args.use_playwright or [],
        detection_threshold=args.detection_threshold,
        site_config_file=args.site_config
    )

    asyncio.run(scraper.run())


if __name__ == "__main__":
    main()
