# Fashion Image Web Scraper

A Python web scraping tool that automatically collects fashion and ecommerce product images from designer websites for use as AI/ML training data. The scraper maintains detailed logs of image sources including metadata like designer name, product information, and original URLs.

## Features

- **Automated Image Collection**: Discovers and downloads all product images from fashion websites
- **Duplicate Detection**: Content-based hashing prevents duplicate downloads
- **Metadata Extraction**: Captures product names, categories, prices, and source URLs
- **Comprehensive Logging**: Separate logs for image sources and errors
- **Error Resilience**: Continues processing even when encountering errors
- **Progress Reporting**: Real-time console output showing scraping progress
- **High-Performance Async Version**: 10-50x faster with concurrent requests (NEW!)

## Versions

This project includes two implementations:

1. **`fashion_scraper.py`** - Synchronous version using `requests`
   - Simpler, easier to understand
   - Good for small-scale scraping
   - Processes one request at a time

2. **`fashion_scraper_async.py`** - Async version using `aiohttp` (RECOMMENDED)
   - 10-50x faster with concurrent requests
   - Handles 50-100+ concurrent operations
   - Includes advanced features:
     - Per-domain rate limiting (configurable)
     - Connection pooling and reuse
     - Response caching
     - Batch processing for downloads
   - Best for large-scale scraping

## Installation

1. **Clone or download this repository**

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

   Required packages:
   - `requests` - HTTP client (synchronous version)
   - `beautifulsoup4` - HTML parsing and data extraction
   - `lxml` - Fast XML/HTML parser
   - `aiohttp` - Async HTTP client (async version)
   - `aiodns` - Fast DNS resolver for async (async version)

3. **Prepare your designer list**:
   - Edit `designers.csv` with the designers/brands you want to scrape
   - Format: `designer_name,website_url`

## Usage

### Basic Usage

**Synchronous version** (simple, slower):
```bash
python fashion_scraper.py
```

**Async version** (RECOMMENDED, 10-50x faster):
```bash
python fashion_scraper_async.py
```

Both will:
- Read designers from `designers.csv`
- Save images to the `output/` directory
- Create logs in the `logs/` directory

### Input File Format

The `designers.csv` file should have two columns:

```csv
designer_name,website_url
Gucci,https://www.gucci.com
Prada,https://www.prada.com
Chanel,https://www.chanel.com
```

### Output Structure

After running, you'll find:

**Images Directory** (`output/`):
- All downloaded images with unique filenames
- Format: `{designer}_{timestamp}.{ext}`

**Image Source Log** (`output/image_sources_YYYYMMDD_HHMMSS.csv`):
```csv
source_url,designer_name,product_name,product_category,price,timestamp,image_url,local_filename
```

**Error Log** (`logs/errors_YYYYMMDD_HHMMSS.csv`):
```csv
timestamp,designer,website,error_type,error_message,url
```

**Detailed Log** (`logs/scraper_YYYYMMDD_HHMMSS.log`):
- Complete scraping activity log

## How It Works

1. **Input Processing**: Reads and validates the designers CSV file
2. **Web Crawling**: Discovers product pages on each website
3. **Image Discovery**: Extracts all product images from each page
4. **Metadata Extraction**: Captures product names, categories, and prices
5. **Duplicate Detection**: Uses SHA-256 hashing to skip duplicate images
6. **Download & Logging**: Saves images and logs metadata to CSV

## Technical Details

### Architecture

The scraper is built with modular components:

**Core Components** (both versions):
- `DesignerListReader`: CSV input processing (TASK-1)
- `ScraperLogger`: Error handling and logging framework (TASK-2)
- `WebCrawler` / `AsyncWebCrawler`: Product page discovery (TASK-3)
- `ImageExtractor` / `AsyncImageExtractor`: Image discovery and extraction (TASK-4)
- `DuplicateDetector`: Hash-based duplicate detection (TASK-5)
- `ImageDownloader` / `AsyncImageDownloader`: Image download manager (TASK-6)
- `MetadataExtractor`: Product metadata extraction (TASK-7)
- `ImageSourceLogger`: CSV logging system (TASK-8)
- `FashionScraper` / `AsyncFashionScraper`: Main orchestrator with progress reporting (TASK-9)

**Async-Only Components** (performance optimizations):
- `AsyncHTTPClient`: High-performance async HTTP client with connection pooling (TASK-10, TASK-11)
- `ResponseCache`: In-memory caching to avoid re-fetching pages (TASK-13)
- `RateLimiter`: Per-domain rate limiting for respectful scraping (TASK-14)
- Batch processing for concurrent image downloads (TASK-12)

### Performance

**Synchronous version**:
- No rate limiting or artificial delays
- Sequential request processing
- Good for small-scale scraping (1-5 designers)

**Async version**:
- 10-50x faster through concurrent requests
- Connection pooling and reuse (TASK-11)
- Response caching (TASK-13)
- Batch processing for downloads (TASK-12)
- Per-domain rate limiting: 2 requests/second per domain (configurable) (TASK-14)
- Can handle 100+ concurrent requests across multiple domains
- Optimal for large-scale scraping (10+ designers)

### Error Handling

The scraper handles common errors gracefully:

- **403 Forbidden**: Access denied by website
- **404 Not Found**: Page not found
- **Timeouts**: Network request timeouts
- **Malformed Data**: Invalid CSV entries or HTML
- **Download Failures**: Failed image downloads

All errors are logged but don't stop the scraping process.

## Customization

### Synchronous Version

Edit `fashion_scraper.py`:

**Change max pages per site**:
```python
scraper = FashionScraper(
    input_csv="designers.csv",
    output_dir="output",
    log_dir="logs",
    max_pages_per_site=200  # Default is 100
)
```

### Async Version

Edit `fashion_scraper_async.py`:

**Change max pages and rate limiting**:
```python
scraper = AsyncFashionScraper(
    input_csv="designers.csv",
    output_dir="output",
    log_dir="logs",
    max_pages_per_site=100,      # Default is 100
    requests_per_second=3.0      # Default is 2.0 per domain
)
```

**Adjust connection pooling** (in `AsyncHTTPClient.__aenter__`):
```python
connector = aiohttp.TCPConnector(
    limit=200,           # Total connections (default: 100)
    limit_per_host=20,   # Per-host connections (default: 10)
    ttl_dns_cache=300    # DNS cache TTL in seconds
)
```

**Modify batch size** (in `_scrape_designer`):
```python
batch_size = 10  # Process 10 pages at a time (default: 5)
```

### Both Versions

**Adjust User-Agent**:
```python
self.session.headers.update({
    'User-Agent': 'Your Custom User-Agent'
})
```

**Modify image filtering**:
Edit the `_is_valid_product_image()` method in `ImageExtractor` or `AsyncImageExtractor` to change which images are downloaded.

## Requirements

- Python 3.8 or higher
- Internet connection
- Disk space for downloaded images

## Legal and Ethical Considerations

- Respect website Terms of Service
- Consider rate limiting for production use
- Only use scraped images in accordance with copyright law
- This tool is for educational and authorized research purposes

## Troubleshooting

**No product pages found**:
- The website structure may not match expected patterns
- Check if the website blocks automated access
- Review error logs for specific issues

**Many duplicates skipped**:
- This is normal if the same images appear on multiple pages
- Duplicate detection works based on image content, not URLs

**403 Forbidden errors**:
- Website is blocking automated access
- Try adding delays or using a different User-Agent
- Some sites require authentication

## License

This project is provided as-is for educational purposes.

## Project Information

**Requirement ID**: REQ-9
**Project**: PROJ-5
**Status**: Implementation Complete

Built using BrainGrid task management system.
