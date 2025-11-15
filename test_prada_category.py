#!/usr/bin/env python3
"""Test Prada category page to find product URLs."""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin


async def test_category():
    """Test a Prada category page."""
    url = "https://www.prada.com/us/en/womens/bags/c/10128US"

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
                content = await response.read()
                print(f"Content length: {len(content)} bytes")

                soup = BeautifulSoup(content, 'lxml')
                print(f"\nTitle: {soup.title.string if soup.title else 'No title'}")

                # Look for product links
                print("\nLooking for product links...")
                all_links = soup.find_all('a', href=True)
                print(f"Total links: {len(all_links)}")

                # Check different patterns
                patterns = ['/products/', '/items/', '.html', '/p_', '_P']
                for pattern in patterns:
                    matching = [a['href'] for a in all_links if pattern in a['href']]
                    if matching:
                        print(f"\nLinks containing '{pattern}': {len(matching)}")
                        print("Examples:")
                        for link in matching[:5]:
                            full_url = urljoin(url, link)
                            print(f"  {full_url}")

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_category())
