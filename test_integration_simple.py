#!/usr/bin/env python3
"""
Simplified integration tests for the fashion scraper.
Tests that all modules can be imported and key features work correctly.
"""

import asyncio
import sys


def test_imports():
    """Test that all modules can be imported without errors."""
    print("=" * 80)
    print("Integration Test: Module Imports")
    print("=" * 80)

    try:
        from fashion_scraper_async import (
            ScraperLogger,
            DesignerListReader,
            AsyncFashionScraper,
            SiteConfig,
            AsyncWebCrawler,
            AsyncHTTPClient,
            RateLimiter,
            ResponseCache
        )
        print("✅ All modules imported successfully")
        return 0
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return 1


def test_stealth_mode_availability():
    """Test that stealth mode gracefully degrades when unavailable."""
    print("\n" + "=" * 80)
    print("Integration Test: Stealth Mode Availability")
    print("=" * 80)

    try:
        from playwright_crawler import STEALTH_AVAILABLE

        if STEALTH_AVAILABLE:
            print("✅ Stealth mode is AVAILABLE (tf-playwright-stealth installed)")
            from playwright_stealth import stealth_async
            print(f"   stealth_async function: {stealth_async}")
        else:
            print("⚠️  Stealth mode is NOT AVAILABLE (tf-playwright-stealth not installed)")
            print("   Scraper will continue without stealth mode")

        print("\n✅ Stealth mode check passed (graceful degradation working)")
        return 0

    except Exception as e:
        print(f"❌ Error checking stealth mode: {e}")
        return 1


async def test_site_config_passing():
    """Test that site_config is properly passed to AsyncWebCrawler."""
    print("\n" + "=" * 80)
    print("Integration Test: Site Config Passing")
    print("=" * 80)

    from fashion_scraper_async import (
        AsyncWebCrawler, AsyncHTTPClient, SiteConfig,
        RateLimiter, ResponseCache, ScraperLogger
    )

    logger = ScraperLogger("test_logs")
    site_config = SiteConfig("site_config.json", logger)
    rate_limiter = RateLimiter()
    cache = ResponseCache()
    http_client = AsyncHTTPClient(logger, rate_limiter, cache)

    try:
        # Test instantiation with site_config
        crawler = AsyncWebCrawler(http_client, logger, site_config)

        # Verify site_config is stored
        assert crawler.site_config is not None, "site_config should not be None"
        assert crawler.site_config == site_config, "site_config should match input"

        print("✅ AsyncWebCrawler properly accepts and stores site_config")

        # Test instantiation without site_config (should not crash)
        crawler_no_config = AsyncWebCrawler(http_client, logger, None)
        assert crawler_no_config.site_config is None, "site_config should be None"

        print("✅ AsyncWebCrawler works without site_config (graceful degradation)")
        print("\n✅ Site config passing test passed")
        return 0

    except Exception as e:
        print(f"❌ Site config passing test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


async def test_scraper_instantiation():
    """Test that AsyncFashionScraper can be instantiated."""
    print("\n" + "=" * 80)
    print("Integration Test: Scraper Instantiation")
    print("=" * 80)

    from fashion_scraper_async import AsyncFashionScraper

    try:
        # Test instantiation with default parameters
        scraper = AsyncFashionScraper(
            input_csv="designers.csv",
            output_dir="output",
            max_images=2,
            max_pages_per_site=3,
            site_config_file="site_config.json"
        )

        print("✅ AsyncFashionScraper instantiated successfully")

        # Test with designer filter
        scraper_filtered = AsyncFashionScraper(
            input_csv="designers.csv",
            output_dir="output",
            max_images=2,
            max_pages_per_site=3,
            designer_filter="Alexander Wang",
            site_config_file="site_config.json"
        )

        print("✅ AsyncFashionScraper with designer_filter instantiated successfully")
        print("\n✅ Scraper instantiation test passed")
        return 0

    except Exception as e:
        print(f"❌ Scraper instantiation test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


async def main():
    """Run all integration tests."""
    print("\n" + "=" * 80)
    print("FASHION SCRAPER INTEGRATION TESTS (SIMPLIFIED)")
    print("=" * 80)

    exit_code = 0

    # Test 1: Module imports
    result = test_imports()
    exit_code = max(exit_code, result)

    # Test 2: Stealth mode availability
    result = test_stealth_mode_availability()
    exit_code = max(exit_code, result)

    # Test 3: Site config passing
    result = await test_site_config_passing()
    exit_code = max(exit_code, result)

    # Test 4: Scraper instantiation
    result = await test_scraper_instantiation()
    exit_code = max(exit_code, result)

    print("\n" + "=" * 80)
    if exit_code == 0:
        print("✅ ALL INTEGRATION TESTS PASSED")
    else:
        print("❌ SOME INTEGRATION TESTS FAILED")
    print("=" * 80)

    return exit_code


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
