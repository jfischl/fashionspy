#!/usr/bin/env python3
"""
Diagnostic tool to see what content Playwright captures from a site.
"""

import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup


async def diagnose_site(url: str):
    """Diagnose what we can see on a site with Playwright."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print(f"\n{'='*60}")
        print(f"Diagnosing: {url}")
        print('='*60)

        try:
            # Navigate to the page
            print("\nNavigating to page...")
            await page.goto(url, wait_until='networkidle', timeout=30000)

            # Wait for content to load
            print("Waiting for dynamic content...")
            await asyncio.sleep(3)

            # Get content
            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')

            print(f"\nPage title: {soup.title.string if soup.title else 'No title'}")
            print(f"Content length: {len(content)} bytes")

            # Check for links
            all_links = soup.find_all('a', href=True)
            print(f"\nTotal links found: {len(all_links)}")

            # Analyze link patterns
            patterns = {
                '/product/': 0,
                '/products/': 0,
                '/p/': 0,
                '/item/': 0,
                '.html': 0,
            }

            for link in all_links:
                href = link.get('href', '').lower()
                for pattern in patterns:
                    if pattern in href:
                        patterns[pattern] += 1

            print("\nLink patterns found:")
            for pattern, count in patterns.items():
                if count > 0:
                    print(f"  {pattern}: {count} links")

            # Show first 20 links
            print("\nFirst 20 links:")
            for i, link in enumerate(all_links[:20], 1):
                href = link.get('href', '')[:80]
                text = link.get_text(strip=True)[:40]
                print(f"  {i}. {href} - {text}")

            # Check for product indicators
            print("\nProduct page indicators:")
            print(f"  Price elements: {len(soup.select('.price, [class*=price], [class*=Price]'))}")
            print(f"  'Add to' buttons: {len(soup.find_all('button', string=lambda s: s and 'add to' in s.lower()))}")
            print(f"  Product schema: {len(soup.select('[itemtype*=Product]'))}")
            print(f"  Product IDs: {len(soup.select('[data-product-id]'))}")

            # Take a screenshot for visual inspection
            screenshot_path = f"screenshot_{url.split('//')[1].split('/')[0]}.png"
            await page.screenshot(path=screenshot_path)
            print(f"\nScreenshot saved to: {screenshot_path}")

        except Exception as e:
            print(f"\nError: {e}")
        finally:
            await browser.close()


async def main():
    """Test multiple sites."""
    sites = [
        "https://www.prada.com/us/en.html",
        "https://www.gucci.com/",
        "https://annasui.com/",
    ]

    for site in sites:
        await diagnose_site(site)
        print("\n")


if __name__ == "__main__":
    asyncio.run(main())
