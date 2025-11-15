#!/usr/bin/env python3
"""
Playwright-based crawler for JavaScript-rendered fashion sites.

This module provides a headless browser-based crawler that can handle
modern JavaScript-heavy luxury fashion websites.
"""

import asyncio
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright, Page, Browser
from bs4 import BeautifulSoup


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

    async def __aenter__(self):
        """Start Playwright and browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close browser and Playwright."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def discover_product_pages(self, base_url: str, designer: str,
                                     max_pages: int = 20) -> List[str]:
        """Discover product pages using headless browser.

        Args:
            base_url: Base URL of the website
            designer: Designer name for logging
            max_pages: Maximum number of product pages to find

        Returns:
            List of product page URLs
        """
        product_pages = []
        visited_urls = set()
        to_visit = [base_url]
        base_domain = urlparse(base_url).netloc

        self.logger.info(f"Using Playwright for {designer} (JavaScript rendering enabled)")

        # Create a new page
        page = await self.browser.new_page()

        # Set user agent to avoid detection
        await page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

        try:
            while to_visit and len(product_pages) < max_pages and len(visited_urls) < 30:
                url = to_visit.pop(0)

                if url in visited_urls:
                    continue

                visited_urls.add(url)

                try:
                    # Navigate and wait for page to load
                    await page.goto(url, wait_until='networkidle', timeout=30000)

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

                    # Check if this is a product page
                    if self._is_product_page(soup, url):
                        product_pages.append(url)
                        self.logger.info(f"  Found product page: {url[:80]}...")

                    # Find more links
                    new_links = await self._extract_links(page, base_url, base_domain)
                    for link in new_links[:20]:
                        if link not in visited_urls and len(to_visit) < 20:
                            to_visit.append(link)

                except Exception as e:
                    self.logger.debug(f"Error crawling {url}: {str(e)}")
                    continue

        finally:
            await page.close()

        self.logger.info(f"Discovered {len(product_pages)} product pages with Playwright")
        return product_pages

    def _is_product_page(self, soup: BeautifulSoup, url: str) -> bool:
        """Determine if a page is a product page using multiple indicators."""
        indicators = [
            # URL patterns
            '/product/' in url.lower(),
            '/p/' in url.lower(),
            '/item/' in url.lower(),
            '/products/' in url.lower(),

            # HTML patterns
            soup.find('button', string=lambda s: s and ('add to cart' in s.lower() or
                                                         'add to bag' in s.lower() or
                                                         'buy' in s.lower())),
            soup.select_one('[itemtype*="Product"]'),
            soup.select_one('.product-price, .price, [class*="price"]'),
            soup.find('meta', property='og:type', content='product'),

            # Common product page indicators
            soup.select_one('[data-product-id]'),
            soup.select_one('.product-details'),
            soup.select_one('#product'),

            # Look for multiple product images (strong indicator)
            len(soup.select('.product-image, [class*="product-image"], .product-gallery img')) > 2,
        ]

        return any(indicators)

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

        try:
            # Get all links from the page
            link_elements = await page.query_selector_all('a[href]')

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

        except Exception as e:
            self.logger.debug(f"Error extracting links: {str(e)}")

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
