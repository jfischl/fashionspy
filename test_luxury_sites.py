#!/usr/bin/env python3
"""Test what we're actually getting from luxury sites."""

import asyncio
import aiohttp
from bs4 import BeautifulSoup


async def test_site(url, name):
    """Test fetching a luxury site."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print('='*60)

    connector = aiohttp.TCPConnector(ssl=False)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    ) as session:
        try:
            async with session.get(url) as response:
                print(f"Status: {response.status}")
                print(f"Content-Type: {response.headers.get('content-type')}")

                content = await response.read()
                print(f"Content length: {len(content)} bytes")

                # Parse HTML
                soup = BeautifulSoup(content, 'lxml')

                # Check what we got
                print(f"\nTitle: {soup.title.string if soup.title else 'No title'}")
                print(f"Number of links: {len(soup.find_all('a'))}")
                print(f"Number of images: {len(soup.find_all('img'))}")

                # Look for product indicators
                print("\nProduct indicators:")
                print(f"  - Links with '/product/': {len([a for a in soup.find_all('a', href=True) if '/product/' in a['href'].lower()])}")
                print(f"  - Links with '/p/': {len([a for a in soup.find_all('a', href=True) if '/p/' in a['href'].lower()])}")
                print(f"  - Price elements: {len(soup.select('.price, .product-price, [class*=price]'))}")
                print(f"  - 'Add to cart' buttons: {len(soup.find_all('button', string=lambda s: s and 'add to cart' in s.lower()))}")

                # Show first few links
                print("\nFirst 10 links found:")
                for i, a in enumerate(soup.find_all('a', href=True)[:10], 1):
                    href = a.get('href', '')
                    text = a.get_text(strip=True)[:50]
                    print(f"  {i}. {href[:60]} - {text}")

        except Exception as e:
            print(f"Error: {e}")


async def main():
    """Test multiple luxury sites."""
    sites = [
        ("https://www.gucci.com/", "Gucci"),
        ("https://www.prada.com/", "Prada"),
        ("https://www.chanel.com/", "Chanel"),
    ]

    for url, name in sites:
        await test_site(url, name)
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
