#!/usr/bin/env python3
"""
Playwright-based crawler for JavaScript-rendered fashion sites.

This module provides a headless browser-based crawler that can handle
modern JavaScript-heavy luxury fashion websites.
"""

import asyncio
from collections import deque
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright, Page, Browser
from bs4 import BeautifulSoup

# Optional stealth mode - gracefully degrade if not available
try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    stealth_async = None


class PlaywrightCrawler:
    """Headless browser crawler for JavaScript-rendered sites."""

    def __init__(self, logger):
        """Initialize Playwright crawler.

        Args:
            logger: Logger instance for error reporting
        """
        self.logger = logger
        self.browser: Optional[Browser] = None
        self.playwright = None
        # TASK-21: Track API endpoints discovered via network interception
        self.discovered_api_endpoints = set()
        self.product_api_patterns = ['product', 'item', 'catalog', 'collection', 'api/v']

    async def __aenter__(self):
        """Start Playwright and browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security'
            ]
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close browser and Playwright."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def discover_product_pages(self, base_url: str, designer: str,
                                     max_pages: int = 20, site_config: dict = None) -> List[str]:
        """TASK-22: Discover product pages using headless browser with multi-level crawling.

        Args:
            base_url: Base URL of the website
            designer: Designer name for logging
            max_pages: Maximum number of product pages to find
            site_config: Optional site-specific configuration

        Returns:
            List of product page URLs
        """
        # TASK-22: Get max depth and start_url from site config
        max_depth = site_config.get('max_depth', 2) if site_config else 2
        start_url = site_config.get('start_url', base_url) if site_config else base_url

        product_pages = []
        visited_urls = set()

        # BFS queue with (url, depth) tuples
        queue = deque([(start_url, 0)])
        base_domain = urlparse(base_url).netloc
        max_visits = max_pages * 5  # Allow more visits for multi-level crawling

        stealth_status = "with stealth mode" if STEALTH_AVAILABLE else "without stealth mode"
        self.logger.info(f"Using Playwright for {designer} (JavaScript rendering, max_depth={max_depth}, {stealth_status})")

        # Create a new page with realistic viewport
        page = await self.browser.new_page(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        # Apply stealth mode to avoid bot detection (if available)
        if STEALTH_AVAILABLE:
            await stealth_async(page)
        else:
            self.logger.debug("Stealth mode not available (install tf-playwright-stealth for enhanced bot evasion)")

        # TASK-21: Enable network interception to discover API endpoints
        await self._setup_network_interception(page)

        # Set realistic headers to avoid detection
        await page.set_extra_http_headers({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        })

        # Add common catalog URLs to seed the crawl at depth 1 (only if using base_url, not custom start_url)
        if start_url == base_url:
            catalog_paths = ['/women', '/men', '/shop', '/products', '/new-arrivals', '/collections']
            for path in catalog_paths:
                potential_url = f"{base_url.rstrip('/')}{path}"
                queue.append((potential_url, 1))

        try:
            while queue and len(product_pages) < max_pages and len(visited_urls) < max_visits:
                url, depth = queue.popleft()

                # Skip if already visited or exceeded depth limit
                if url in visited_urls or depth > max_depth:
                    continue

                visited_urls.add(url)

                try:
                    self.logger.info(f"  Visiting (depth={depth}): {url[:100]}...")

                    # Navigate and wait for page to load
                    await page.goto(url, wait_until='networkidle', timeout=30000)

                    # Wait for specific selector if configured
                    if site_config and 'wait_for' in site_config:
                        wait_selector = site_config['wait_for']
                        wait_timeout = site_config.get('wait_timeout', 30000)
                        try:
                            self.logger.debug(f"Waiting for selector: {wait_selector}")
                            await page.wait_for_selector(wait_selector, timeout=wait_timeout)
                        except Exception as e:
                            self.logger.debug(f"Timeout waiting for {wait_selector}: {e}")

                    # TASK-17: Scroll to trigger lazy-load content
                    try:
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(1)  # Wait for content to load
                        await page.evaluate("window.scrollTo(0, 0)")  # Scroll back up
                        await asyncio.sleep(1)
                    except Exception as scroll_error:
                        self.logger.debug(f"Scrolling failed for {url}: {scroll_error}")

                    # Wait for network to stabilize after scrolling
                    try:
                        await page.wait_for_load_state('networkidle', timeout=10000)
                    except Exception:
                        pass  # Continue even if network doesn't stabilize

                    # Get page content after JavaScript execution and scrolling
                    content = await page.content()
                    soup = BeautifulSoup(content, 'lxml')

                    # Check if this is a product detail page
                    is_product = self._is_product_page(soup, url, site_config)

                    if is_product:
                        product_pages.append(url)
                        self.logger.info(f"  ✓ Found product page (depth={depth}): {url[:80]}...")
                        # Don't crawl deeper from product pages
                    else:
                        # Category/listing page - extract links and add to queue with depth+1
                        new_links = await self._extract_links(page, base_url, base_domain)
                        self.logger.info(f"  → Category page (depth={depth}): found {len(new_links)} links from {url[:60]}...")

                        # Sort links to prioritize product-related URLs
                        priority_keywords = ['product', 'collection', 'shop', 'women', 'men', 'bags', 'shoes', 'clothing']
                        new_links = sorted(new_links, key=lambda x: any(kw in x.lower() for kw in priority_keywords), reverse=True)

                        for link in new_links[:50]:  # Increased from 30
                            if link not in visited_urls:
                                queue.append((link, depth + 1))

                        self.logger.info(f"  Queue now has {len(queue)} URLs to visit")

                except Exception as e:
                    self.logger.info(f"  ✗ Error crawling {url}: {str(e)}")
                    continue

        finally:
            await page.close()

        self.logger.info(f"Discovered {len(product_pages)} product pages with Playwright (visited {len(visited_urls)} pages, max_depth={max_depth})")

        # TASK-21: Log discovered API endpoints
        if self.discovered_api_endpoints:
            self.logger.info(f"Discovered {len(self.discovered_api_endpoints)} API endpoints:")
            for endpoint in list(self.discovered_api_endpoints)[:10]:  # Show first 10
                self.logger.info(f"  API: {endpoint[:120]}...")

        return product_pages

    def _is_product_api(self, url: str) -> bool:
        """TASK-21: Determine if a URL is a product-related API endpoint.

        Args:
            url: Request URL to check

        Returns:
            True if URL appears to be a product API endpoint
        """
        url_lower = url.lower()

        # Check if it matches product API patterns
        return any(pattern in url_lower for pattern in self.product_api_patterns)

    async def _setup_network_interception(self, page: Page) -> None:
        """TASK-21: Setup network request interception to discover API endpoints.

        Args:
            page: Playwright page object
        """
        async def handle_request(request):
            """Intercept and log API requests."""
            url = request.url

            # Log product-related API endpoints
            if self._is_product_api(url) and '/api/' in url.lower():
                self.discovered_api_endpoints.add(url)
                self.logger.debug(f"Discovered API endpoint: {url[:100]}...")

        # Listen to all network requests
        page.on("request", handle_request)

    def _is_product_page(self, soup: BeautifulSoup, url: str, site_config: dict = None) -> bool:
        """TASK-22: Determine if a page is an actual product detail page (not category/catalog).

        For multi-level crawling, we need to distinguish:
        - Product detail pages (return True - these are terminal pages)
        - Category/catalog pages (return False - these should be crawled deeper)

        Args:
            soup: BeautifulSoup parsed HTML
            url: Page URL
            site_config: Optional site-specific configuration

        Returns:
            True if page is a product detail page, False if it's a category/listing page
        """
        # Individual product detail page indicators (strong signals)
        product_detail_indicators = [
            # URL patterns for product detail pages
            ('/product/' in url.lower() or '/p/' in url.lower() or '/item/' in url.lower())
            and not url.lower().endswith(('/products', '/products/', '/product', '/product/')),

            # HTML patterns for product details (strong indicators)
            soup.find('button', string=lambda s: s and ('add to cart' in s.lower() or
                                                         'add to bag' in s.lower() or
                                                         'buy now' in s.lower())),
            soup.select_one('[itemtype*="Product"]'),
            soup.find('meta', property='og:type', content='product'),
            soup.select_one('.product-details, #product-detail, [class*="product-detail"]'),
        ]

        # Category/catalog page indicators (these should be crawled deeper)
        catalog_indicators = [
            # URL endings that indicate catalog pages
            url.lower().endswith(('/women', '/women/', '/men', '/men/', '/shop', '/shop/',
                                '/bags', '/bags/', '/shoes', '/shoes/', '/clothing', '/clothing/',
                                '/accessories', '/accessories/', '/collections', '/collections/',
                                '/products', '/products/', '/new-arrivals', '/new-arrivals/')),

            # HTML patterns for product listings (multiple products)
            len(soup.select('.product-tile, .product-card, .product-item, [class*="product-tile"], [class*="product-card"]')) >= 3,
            len(soup.select('.product-grid, .product-list, [class*="product-grid"]')) > 0,

            # Check for multiple product links (indicates listing page)
            len(soup.select('a[href*="/product/"], a[href*="/p/"], a[href*="/item/"]')) >= 3,
        ]

        is_product_detail = any(product_detail_indicators)
        is_catalog = any(catalog_indicators)

        # If it's clearly a catalog page, return False (crawl deeper)
        if is_catalog and not is_product_detail:
            self.logger.debug(f"Category/catalog page (will crawl deeper): {url[:80]}")
            return False

        # If it has product detail indicators, it's a product page
        if is_product_detail:
            self.logger.debug(f"Product detail page: {url[:80]}")
            return True

        # Default: uncertain pages are not considered product pages
        return False

    async def _extract_links(self, page: Page, base_url: str,
                            base_domain: str) -> List[str]:
        """Extract links from the page using Playwright.

        Args:
            page: Playwright page object
            base_url: Base URL for resolving relative links
            base_domain: Domain to filter links

        Returns:
            List of links from the same domain
        """
        links = []
        filtered_out = 0
        different_domain = 0

        try:
            # Get all links from the page
            link_elements = await page.query_selector_all('a[href]')
            self.logger.debug(f"Found {len(link_elements)} link elements on page")

            for element in link_elements:
                href = await element.get_attribute('href')
                if not href:
                    continue

                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)

                # Only keep links from the same domain
                if parsed.netloc == base_domain:
                    # Filter out non-product links
                    if not any(x in full_url.lower() for x in
                              ['login', 'signup', 'account', 'cart', 'checkout',
                               'privacy', 'terms', 'contact', 'about', 'stores',
                               'customer-service', 'help']):
                        links.append(full_url)
                    else:
                        filtered_out += 1
                else:
                    different_domain += 1

            self.logger.debug(f"Extracted {len(links)} links (filtered out {filtered_out} utility pages, {different_domain} different domains)")

        except Exception as e:
            self.logger.info(f"Error extracting links: {str(e)}")

        return links

    async def get_page_content(self, url: str) -> Optional[str]:
        """Fetch page content with JavaScript rendering.

        Args:
            url: URL to fetch

        Returns:
            HTML content after JavaScript execution, or None on error
        """
        page = await self.browser.new_page()

        try:
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(1)  # Wait for dynamic content
            content = await page.content()
            return content
        except Exception as e:
            self.logger.debug(f"Error fetching {url}: {str(e)}")
            return None
        finally:
            await page.close()


async def test_playwright_crawler():
    """Test the Playwright crawler with a luxury site."""
    from fashion_scraper_async import ScraperLogger

    logger = ScraperLogger("test_logs")

    async with PlaywrightCrawler(logger) as crawler:
        # Test with Prada
        products = await crawler.discover_product_pages(
            "https://www.prada.com/us/en.html",
            "Prada",
            max_pages=5
        )

        print(f"\nFound {len(products)} product pages:")
        for url in products:
            print(f"  - {url}")


if __name__ == "__main__":
    asyncio.run(test_playwright_crawler())
