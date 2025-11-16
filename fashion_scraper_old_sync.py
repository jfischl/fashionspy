#!/usr/bin/env python3
"""
Fashion Image Web Scraper with Source Tracking

A web scraping tool that automatically collects fashion and ecommerce product images
from designer websites to be used as training data for AI/ML models.
"""

import csv
import hashlib
import logging
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse

# Suppress SSL warnings
warnings.filterwarnings('ignore', message='urllib3 v2 only supports OpenSSL')

import requests
from bs4 import BeautifulSoup

# Disable urllib3 warnings
requests.packages.urllib3.disable_warnings()


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

    def calculate_hash(self, image_data: bytes) -> str:
        """Calculate SHA-256 hash of image content.

        Args:
            image_data: Binary image data

        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(image_data).hexdigest()

    def is_duplicate(self, image_data: bytes) -> tuple[bool, str]:
        """Check if image is a duplicate based on content hash.

        Args:
            image_data: Binary image data

        Returns:
            Tuple of (is_duplicate, hash_value)
        """
        image_hash = self.calculate_hash(image_data)

        if image_hash in self.seen_hashes:
            self.logger.debug(f"Duplicate detected: {image_hash}")
            return True, image_hash

        self.seen_hashes.add(image_hash)
        return False, image_hash

    def get_duplicate_count(self) -> int:
        """Get total number of unique images seen."""
        return len(self.seen_hashes)


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
# TASK-3: Web Crawling Engine for Product Page Discovery
# ============================================================================

class WebCrawler:
    """Discovers product pages on fashion websites."""

    def __init__(self, session: requests.Session, logger: ScraperLogger):
        """Initialize the web crawler.

        Args:
            session: Requests session for HTTP requests
            logger: Logger instance
        """
        self.session = session
        self.logger = logger
        self.visited_urls: Set[str] = set()

    def discover_product_pages(self, base_url: str, designer: str,
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
        max_visits = 30  # Limit total pages visited to prevent hanging

        while to_visit and len(product_pages) < max_pages and len(self.visited_urls) < max_visits:
            url = to_visit.pop(0)

            if url in self.visited_urls:
                continue

            self.visited_urls.add(url)

            try:
                response = self.session.get(url, timeout=5)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'lxml')

                # Check if this is a product page
                if self._is_product_page(soup, url):
                    product_pages.append(url)
                    self.logger.info(f"  Found product page: {url[:80]}...")

                # Find more links to explore (but limit how many we add)
                new_links = self._extract_links(soup, base_url, base_domain)
                for link in new_links[:20]:  # Only take first 20 links
                    if link not in self.visited_urls and len(to_visit) < 20:
                        to_visit.append(link)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    self.logger.log_error(designer, base_url, "403 Forbidden",
                                         "Access denied by website", url)
                    break  # Stop crawling if blocked
                elif e.response.status_code == 404:
                    self.logger.log_error(designer, base_url, "404 Not Found",
                                         "Page not found", url)
                else:
                    self.logger.log_error(designer, base_url, f"{e.response.status_code}",
                                         str(e), url)
            except requests.exceptions.Timeout:
                self.logger.log_error(designer, base_url, "Timeout",
                                     "Request timed out", url)
            except Exception as e:
                self.logger.log_error(designer, base_url, "UnexpectedError",
                                     str(e), url)

        self.logger.info(f"Discovered {len(product_pages)} product pages (visited {len(self.visited_urls)} pages total)")
        return product_pages

    def _is_product_page(self, soup: BeautifulSoup, url: str) -> bool:
        """Determine if a page is a product page."""
        # Check for product-specific patterns
        indicators = [
            # URL patterns
            '/product/' in url.lower(),
            '/p/' in url.lower(),
            '/item/' in url.lower(),

            # HTML patterns
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
# TASK-4: Image Discovery and Extraction from Product Pages
# ============================================================================

class ImageExtractor:
    """Extracts images from product pages."""

    def __init__(self, session: requests.Session, logger: ScraperLogger):
        """Initialize the image extractor.

        Args:
            session: Requests session for HTTP requests
            logger: Logger instance
        """
        self.session = session
        self.logger = logger

    def extract_images(self, url: str, designer: str) -> List[Dict[str, str]]:
        """Extract all product images from a page.

        Args:
            url: URL of the product page
            designer: Designer name for error logging

        Returns:
            List of dictionaries with 'url' and 'source_page' keys
        """
        images = []

        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'lxml')

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

            self.logger.debug(f"Found {len(images)} images on {url}")

        except Exception as e:
            self.logger.log_error(designer, url, "ImageExtraction",
                                 f"Error extracting images: {str(e)}", url)

        return images

    def _is_valid_product_image(self, img_url: str, img_tag) -> bool:
        """Check if an image is likely a product image."""
        # Skip data URIs
        if img_url.startswith('data:'):
            return False

        # Skip very small images (likely icons)
        width = img_tag.get('width', '0')
        height = img_tag.get('height', '0')
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
# TASK-6: Image Download Manager with Deduplication
# ============================================================================

class ImageDownloader:
    """Downloads images with duplicate detection."""

    def __init__(self, session: requests.Session, output_dir: Path,
                 duplicate_detector: DuplicateDetector, logger: ScraperLogger):
        """Initialize the image downloader.

        Args:
            session: Requests session for HTTP requests
            output_dir: Directory to save images
            duplicate_detector: Duplicate detection instance
            logger: Logger instance
        """
        self.session = session
        self.output_dir = output_dir
        self.duplicate_detector = duplicate_detector
        self.logger = logger

    def download_image(self, img_url: str, designer: str) -> Optional[Dict[str, str]]:
        """Download an image if it's not a duplicate.

        Args:
            img_url: URL of the image
            designer: Designer name for filename

        Returns:
            Dictionary with download info or None if skipped/failed
        """
        try:
            response = self.session.get(img_url, timeout=10)
            response.raise_for_status()

            image_data = response.content

            # Check for duplicates
            is_dup, img_hash = self.duplicate_detector.is_duplicate(image_data)
            if is_dup:
                return None

            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            ext = self._get_extension(img_url, response.headers.get('content-type', ''))
            filename = f"{designer.lower().replace(' ', '_')}_{timestamp}{ext}"
            filepath = self.output_dir / filename

            # Save image
            with open(filepath, 'wb') as f:
                f.write(image_data)

            return {
                'filename': filename,
                'hash': img_hash,
                'size': len(image_data)
            }

        except Exception as e:
            self.logger.log_error(designer, img_url, "DownloadError",
                                 f"Failed to download image: {str(e)}", img_url)
            return None

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

    def log_image(self, source_url: str, designer_name: str,
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
# Main Scraper Class (Foundation)
# ============================================================================

class FashionScraper:
    """Main scraper orchestrator."""

    def __init__(self, input_csv: str = "designers.csv",
                 output_dir: str = "output",
                 log_dir: str = "logs",
                 max_pages_per_site: int = 100):
        """Initialize the scraper.

        Args:
            input_csv: Path to designers CSV file
            output_dir: Directory to save downloaded images
            log_dir: Directory for log files
            max_pages_per_site: Maximum product pages to process per site
        """
        self.input_csv = input_csv
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.max_pages_per_site = max_pages_per_site

        # Initialize components
        self.logger = ScraperLogger(log_dir)
        self.reader = DesignerListReader(input_csv, self.logger)
        self.duplicate_detector = DuplicateDetector(self.logger)

        # Session for HTTP requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

        # Initialize scraping components
        self.crawler = WebCrawler(self.session, self.logger)
        self.metadata_extractor = MetadataExtractor(self.logger)
        self.image_extractor = ImageExtractor(self.session, self.logger)
        self.image_downloader = ImageDownloader(
            self.session, self.output_dir, self.duplicate_detector, self.logger
        )
        self.source_logger = ImageSourceLogger(self.output_dir, self.logger)

        # Statistics (TASK-9: Progress Reporting)
        self.stats = {
            'images_downloaded': 0,
            'duplicates_skipped': 0,
            'errors_encountered': 0,
            'product_pages_processed': 0
        }

    def run(self):
        """Execute the scraping process."""
        self.logger.info("=" * 60)
        self.logger.info("Fashion Image Web Scraper")
        self.logger.info("=" * 60)

        # Read designers list
        designers = self.reader.read_designers()

        if not designers:
            self.logger.info("No designers to process. Exiting.")
            return

        # Process each designer
        for idx, designer in enumerate(designers, 1):
            self.logger.info(f"\n[{idx}/{len(designers)}] Processing: {designer['designer_name']}")
            self.logger.info(f"Website: {designer['website_url']}")

            try:
                # Scrape this designer's website
                self._scrape_designer(
                    designer['designer_name'],
                    designer['website_url']
                )
            except Exception as e:
                self.logger.log_error(
                    designer['designer_name'],
                    designer['website_url'],
                    "DesignerProcessingError",
                    f"Failed to process designer: {str(e)}",
                    designer['website_url']
                )
                self.stats['errors_encountered'] += 1

        # Print summary
        self._print_summary()

    def _scrape_designer(self, designer_name: str, website_url: str):
        """Scrape a single designer's website.

        Args:
            designer_name: Name of the designer/brand
            website_url: Base URL of the website
        """
        # TASK-3: Discover product pages
        self.logger.info("Discovering product pages...")
        product_pages = self.crawler.discover_product_pages(
            website_url, designer_name, self.max_pages_per_site
        )

        if not product_pages:
            self.logger.info("No product pages found")
            return

        # Process each product page
        for page_idx, page_url in enumerate(product_pages, 1):
            self.logger.info(
                f"  Processing page {page_idx}/{len(product_pages)}: {page_url[:60]}..."
            )

            try:
                # TASK-4: Extract images from page
                images = self.image_extractor.extract_images(page_url, designer_name)

                if not images:
                    self.logger.debug(f"No images found on {page_url}")
                    continue

                # TASK-7: Extract metadata from page
                # We need to fetch the page again to get metadata
                response = self.session.get(page_url, timeout=10)
                soup = BeautifulSoup(response.content, 'lxml')
                metadata = self.metadata_extractor.extract_metadata(soup, page_url)

                # TASK-6 & TASK-8: Download images and log to CSV
                page_downloaded = 0
                page_duplicates = 0

                for img in images:
                    download_result = self.image_downloader.download_image(
                        img['url'], designer_name
                    )

                    if download_result:
                        # Image downloaded successfully
                        self.source_logger.log_image(
                            source_url=page_url,
                            designer_name=designer_name,
                            metadata=metadata,
                            image_url=img['url'],
                            local_filename=download_result['filename']
                        )
                        page_downloaded += 1
                        self.stats['images_downloaded'] += 1
                    else:
                        # Image was a duplicate or failed to download
                        page_duplicates += 1
                        self.stats['duplicates_skipped'] += 1

                # TASK-9: Progress reporting
                self.logger.info(
                    f"    Downloaded: {page_downloaded}, "
                    f"Skipped: {page_duplicates} "
                    f"(Total: {self.stats['images_downloaded']} images)"
                )
                self.stats['product_pages_processed'] += 1

            except Exception as e:
                self.logger.log_error(
                    designer_name,
                    website_url,
                    "PageProcessingError",
                    f"Error processing page: {str(e)}",
                    page_url
                )
                self.stats['errors_encountered'] += 1

    def _print_summary(self):
        """Print final summary statistics (TASK-9: Progress Reporting)."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("SCRAPING COMPLETE")
        self.logger.info("=" * 60)
        self.logger.info(f"Product pages processed: {self.stats['product_pages_processed']}")
        self.logger.info(f"Total images downloaded: {self.stats['images_downloaded']}")
        self.logger.info(f"Duplicates skipped: {self.stats['duplicates_skipped']}")
        self.logger.info(f"Errors encountered: {self.stats['errors_encountered']}")
        self.logger.info(f"\nOutput directory: {self.output_dir.absolute()}")
        self.logger.info(f"Image source log: {self.source_logger.log_path}")
        self.logger.info(f"Error log: {self.logger.error_log_path}")
        self.logger.info(f"Log directory: {self.logger.log_dir.absolute()}")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the scraper."""
    scraper = FashionScraper(
        input_csv="designers.csv",
        output_dir="output",
        log_dir="logs",
        max_pages_per_site=20  # Limit to 20 product pages per site
    )
    scraper.run()


if __name__ == "__main__":
    main()
