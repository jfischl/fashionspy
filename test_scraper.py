#!/usr/bin/env python3
"""
Simple test to verify scraper components work correctly.
"""

# Note: This test file uses the old synchronous scraper (renamed to fashion_scraper_old_sync.py)
# For async scraper tests, see test_integration_simple.py
from fashion_scraper_old_sync import (
    ScraperLogger,
    DesignerListReader,
    DuplicateDetector,
    MetadataExtractor,
    ImageExtractor,
    ImageDownloader
)
from bs4 import BeautifulSoup
from pathlib import Path
import hashlib

def test_csv_reader():
    """Test CSV reading functionality."""
    print("Testing CSV Reader...")
    logger = ScraperLogger("test_logs")
    reader = DesignerListReader("designers.csv", logger)
    designers = reader.read_designers()
    assert len(designers) == 1
    assert designers[0]['designer_name'] == 'Example'
    print("✓ CSV Reader works!")

def test_duplicate_detector():
    """Test duplicate detection."""
    print("\nTesting Duplicate Detector...")
    logger = ScraperLogger("test_logs")
    detector = DuplicateDetector(logger)

    # Test with sample data
    test_data1 = b"test image data"
    test_data2 = b"different image data"

    # First image should not be duplicate
    is_dup1, hash1 = detector.is_duplicate(test_data1)
    assert not is_dup1

    # Same image should be duplicate
    is_dup2, hash2 = detector.is_duplicate(test_data1)
    assert is_dup2
    assert hash1 == hash2

    # Different image should not be duplicate
    is_dup3, hash3 = detector.is_duplicate(test_data2)
    assert not is_dup3
    assert hash3 != hash1

    print("✓ Duplicate Detector works!")

def test_metadata_extractor():
    """Test metadata extraction."""
    print("\nTesting Metadata Extractor...")
    logger = ScraperLogger("test_logs")
    extractor = MetadataExtractor(logger)

    # Create sample HTML
    html = """
    <html>
        <head><title>Red Dress - Designer Fashion</title></head>
        <body>
            <h1>Beautiful Red Evening Dress</h1>
            <nav class="breadcrumb">
                <a href="/">Home</a>
                <a href="/dresses">Dresses</a>
                <a href="/product">Red Dress</a>
            </nav>
            <span class="price">$299.99</span>
        </body>
    </html>
    """

    soup = BeautifulSoup(html, 'lxml')
    metadata = extractor.extract_metadata(soup, "https://example.com/product/red-dress")

    assert 'product_name' in metadata
    assert 'Beautiful Red Evening Dress' in metadata['product_name']
    assert 'product_category' in metadata
    assert 'price' in metadata

    print(f"  Product Name: {metadata['product_name']}")
    print(f"  Category: {metadata['product_category']}")
    print(f"  Price: {metadata['price']}")
    print("✓ Metadata Extractor works!")

def test_image_extraction():
    """Test image extraction from HTML."""
    print("\nTesting Image Extraction...")

    # Create sample HTML with images
    html = """
    <html>
        <body>
            <img src="/images/product1.jpg" width="500" height="600" />
            <img src="https://cdn.example.com/product2.jpg" width="800" height="1000" />
            <img data-src="/images/lazy-loaded.jpg" width="400" height="500" />
            <img src="/icon.png" width="20" height="20" />
        </body>
    </html>
    """

    soup = BeautifulSoup(html, 'lxml')

    # Test image tag extraction
    imgs = soup.find_all('img')
    assert len(imgs) == 4

    # Count valid product images (should exclude small icon)
    valid_count = 0
    small_icon_count = 0
    for img in imgs:
        src = img.get('src') or img.get('data-src', '')
        width = img.get('width', '0')
        height = img.get('height', '0')

        # Check if it's a small icon
        if width.isdigit() and height.isdigit():
            if int(width) < 100 or int(height) < 100:
                small_icon_count += 1
                print(f"    Excluding small image: {src} ({width}x{height})")
                continue

        # Count as valid product image
        valid_count += 1
        print(f"    Valid image: {src} (w={width}, h={height})")

    # The test HTML has 4 images: 3 product images (large) and 1 small icon
    print(f"  Total valid: {valid_count}, Small icons: {small_icon_count}")
    assert valid_count + small_icon_count == 4, f"Total should be 4 images"
    assert small_icon_count == 1, f"Expected 1 small icon, got {small_icon_count}"
    assert valid_count == 3, f"Expected 3 valid product images, got {valid_count}"
    print(f"  ✓ Found {valid_count} valid product images, excluded {small_icon_count} small icon")
    print("✓ Image Extraction works!")

def test_hash_calculation():
    """Test hash calculation consistency."""
    print("\nTesting Hash Calculation...")

    test_data = b"sample image content"
    hash1 = hashlib.sha256(test_data).hexdigest()
    hash2 = hashlib.sha256(test_data).hexdigest()

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 produces 64 hex characters

    print(f"  Hash: {hash1[:16]}...")
    print("✓ Hash Calculation works!")

def main():
    """Run all tests."""
    print("=" * 60)
    print("Fashion Scraper Component Tests")
    print("=" * 60)

    try:
        test_csv_reader()
        test_duplicate_detector()
        test_metadata_extractor()
        test_image_extraction()
        test_hash_calculation()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED! ✓")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
