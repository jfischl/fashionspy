#!/usr/bin/env python3
"""Quick test of async scraper components."""

import asyncio
from fashion_scraper_async import (
    AsyncHTTPClient, RateLimiter, ResponseCache, ScraperLogger
)


async def test_http_client():
    """Test basic HTTP client functionality."""
    logger = ScraperLogger("test_logs")
    rate_limiter = RateLimiter(requests_per_second=5.0)
    cache = ResponseCache(max_size=100)

    print("Testing AsyncHTTPClient...")
    async with AsyncHTTPClient(logger, rate_limiter, cache) as client:
        # Test basic fetch
        result = await client.get("https://httpbin.org/status/200")
        if result:
            print("✅ HTTP GET successful")
        else:
            print("❌ HTTP GET failed")

        # Test caching
        result1 = await client.get("https://httpbin.org/uuid")
        result2 = await client.get("https://httpbin.org/uuid")
        if result1 and result2:
            print("✅ Cache test successful")
        else:
            print("❌ Cache test failed")

    print("\nTest complete!")


if __name__ == "__main__":
    asyncio.run(test_http_client())
