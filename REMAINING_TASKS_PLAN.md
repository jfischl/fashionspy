# Implementation Plan for Remaining Tasks

## Overview

This document outlines the implementation plan for the 3 remaining enhancement tasks (TASK-17, TASK-18, TASK-19) that will enable luxury designer site support.

**Current Status**: REQ-9 is COMPLETED with 17/19 tasks done (89%)
**Remaining**: 3 enhancement tasks for luxury site support

---

## TASK-17: Complete Playwright Integration ⚠️ (Partially Done)

### Current State
✅ **Infrastructure in place**:
- `playwright_crawler.py` created with `PlaywrightCrawler` class
- Browser context management implemented
- `discover_product_pages()` method working
- `get_page_content()` method for JavaScript rendering
- Tested with Prada, Gucci (found 0 products as expected)

⚠️ **Not yet integrated**:
- Playwright not integrated with main `fashion_scraper_async.py`
- No automatic fallback from HTML to Playwright
- No per-site configuration for when to use Playwright

### Implementation Steps

#### 1. Integrate Playwright with Main Scraper (2-3 hours)

**Add configuration to AsyncFashionScraper**:
```python
class AsyncFashionScraper:
    def __init__(self, ..., use_playwright_for: List[str] = None):
        self.use_playwright_for = use_playwright_for or []
        self.playwright_crawler = None
```

**Modify _scrape_designer() to use Playwright conditionally**:
```python
async def _scrape_designer(self, designer_name, website_url, ...):
    # Determine which crawler to use
    if designer_name.lower() in self.use_playwright_for:
        # Use Playwright crawler
        async with PlaywrightCrawler(self.logger) as pw_crawler:
            product_pages = await pw_crawler.discover_product_pages(
                website_url, designer_name, self.max_pages_per_site
            )
    else:
        # Use regular HTML crawler
        product_pages = await crawler.discover_product_pages(
            website_url, designer_name, self.max_pages_per_site
        )
```

**Add CLI argument**:
```python
parser.add_argument(
    '--use-playwright',
    type=str,
    nargs='+',
    metavar='DESIGNER',
    help='Designer names that require Playwright (e.g., --use-playwright Gucci Prada)'
)
```

#### 2. Enhance PlaywrightCrawler for Better Product Detection (2-4 hours)

**Add scrolling to trigger lazy-load**:
```python
async def discover_product_pages(self, base_url, designer, max_pages):
    # ... existing code ...

    # Scroll to trigger lazy-load
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(2)  # Wait for content to load

    # Wait for network to be idle
    await page.wait_for_load_state('networkidle')
```

**Monitor API calls for product data**:
```python
# Intercept API responses
api_products = []

async def handle_response(response):
    if '/api/products' in response.url or '/products.json' in response.url:
        try:
            data = await response.json()
            api_products.append(data)
        except:
            pass

page.on('response', handle_response)
```

#### 3. Testing (1 hour)

**Test with luxury sites**:
```bash
# Test Playwright with Gucci
python3 fashion_scraper_async.py --designer Gucci --max-images 10 --use-playwright Gucci

# Test mixed approach (Anna Sui with HTML, Prada with Playwright)
python3 fashion_scraper_async.py --max-images 10 --use-playwright Prada
```

### Estimated Effort: 5-8 hours

### Success Criteria
- ✅ Playwright integrated into main scraper
- ✅ CLI flag to specify which designers need Playwright
- ✅ Scrolling and network idle waiting implemented
- ✅ Works alongside HTML scraping (hybrid approach)
- ✅ Successfully detects more products on luxury sites

---

## TASK-18: Intelligent Product Page Detection (4-8 hours)

### Goal
Create content-based product page detection instead of relying on URL patterns like `/product/`, `/p/`, `/item/`.

### Current State
❌ **Not implemented**: Current detection uses hardcoded URL patterns:
```python
def _is_product_page(self, soup, url):
    indicators = [
        '/product/' in url.lower(),
        '/p/' in url.lower(),
        '/item/' in url.lower(),
        # ... other checks
    ]
```

This fails for luxury sites using patterns like:
- Prada: `/us/en/womens/bags/c/10128US`
- Gucci: `/category/shoes/...`

### Implementation Steps

#### 1. Create Content Analysis System (3-4 hours)

**Implement scoring-based detection**:
```python
class ContentBasedDetector:
    """Detects product pages based on content, not URL patterns."""

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def is_product_page(self, soup: BeautifulSoup, url: str) -> tuple[bool, int]:
        """
        Determine if page is a product page using content analysis.

        Returns:
            (is_product, score): Boolean and confidence score
        """
        score = 0

        # Check 1: Large product images (>500px)
        large_images = self._find_large_images(soup)
        if len(large_images) >= 3:
            score += 2
        elif len(large_images) >= 1:
            score += 1

        # Check 2: Price elements
        if self._has_price(soup):
            score += 2

        # Check 3: Add to cart/bag button
        if self._has_cart_button(soup):
            score += 2

        # Check 4: Product schema (JSON-LD)
        if self._has_product_schema(soup):
            score += 3  # Strong indicator

        # Check 5: Single product focus (not a grid)
        if not self._is_product_grid(soup):
            score += 1

        # Check 6: Product description (long text)
        if self._has_product_description(soup):
            score += 1

        # Check 7: Size/color selectors
        if self._has_variant_selectors(soup):
            score += 1

        return score >= self.threshold, score

    def _find_large_images(self, soup) -> List:
        """Find images that are likely product images (>500px)."""
        large_images = []
        for img in soup.find_all('img'):
            # Check width/height attributes
            width = img.get('width', '')
            height = img.get('height', '')
            if width.isdigit() and int(width) > 500:
                large_images.append(img)
            # Check CSS classes
            if any(cls in str(img.get('class', [])).lower()
                   for cls in ['product', 'gallery', 'main-image']):
                large_images.append(img)
        return large_images

    def _has_price(self, soup) -> bool:
        """Check for price indicators."""
        # Look for currency symbols
        text = soup.get_text()
        has_currency = any(symbol in text for symbol in ['$', '€', '£', '¥'])

        # Look for price classes
        price_elements = soup.select('[class*="price"], [class*="Price"]')

        return has_currency or len(price_elements) > 0

    def _has_cart_button(self, soup) -> bool:
        """Check for add to cart/bag button."""
        buttons = soup.find_all(['button', 'a', 'input'])
        for btn in buttons:
            text = btn.get_text().lower()
            if any(keyword in text for keyword in
                   ['add to cart', 'add to bag', 'buy now', 'purchase', 'add to basket']):
                return True
        return False

    def _has_product_schema(self, soup) -> bool:
        """Check for Product structured data (JSON-LD)."""
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get('@type') == 'Product':
                        return True
                    if isinstance(data.get('@graph'), list):
                        for item in data['@graph']:
                            if item.get('@type') == 'Product':
                                return True
            except:
                pass
        return False

    def _is_product_grid(self, soup) -> bool:
        """Detect if page shows multiple products (category page)."""
        # Look for common grid patterns
        grids = soup.select('[class*="grid"], [class*="list"]')
        if len(grids) > 0:
            # Count product links
            product_links = 0
            for grid in grids:
                links = grid.find_all('a', href=True)
                product_links += len(links)

            # If many similar links, likely a category page
            if product_links > 10:
                return True
        return False

    def _has_product_description(self, soup) -> bool:
        """Check for long product description text."""
        # Look for description elements
        desc_elements = soup.select('[class*="description"], [class*="details"]')
        for elem in desc_elements:
            text = elem.get_text(strip=True)
            if len(text) > 100:  # At least 100 chars
                return True
        return False

    def _has_variant_selectors(self, soup) -> bool:
        """Check for size/color variant selectors."""
        # Look for select dropdowns
        selects = soup.find_all('select')
        for select in selects:
            label = select.get('aria-label', '').lower()
            if any(keyword in label for keyword in ['size', 'color', 'colour']):
                return True

        # Look for button groups (size/color buttons)
        buttons = soup.select('[class*="size"], [class*="color"], [class*="variant"]')
        return len(buttons) > 0
```

#### 2. Integrate with Crawlers (1-2 hours)

**Update AsyncWebCrawler**:
```python
class AsyncWebCrawler:
    def __init__(self, http_client, logger, detection_threshold=3):
        # ... existing code ...
        self.detector = ContentBasedDetector(threshold=detection_threshold)

    def _is_product_page(self, soup, url):
        """Use content-based detection with fallback to URL patterns."""
        # Try content-based detection first
        is_product, score = self.detector.is_product_page(soup, url)

        if is_product:
            self.logger.debug(f"Product page detected (score: {score}): {url[:60]}")
            return True

        # Fallback to URL patterns for traditional sites
        url_patterns = ['/product/', '/p/', '/item/', '/products/']
        if any(pattern in url.lower() for pattern in url_patterns):
            self.logger.debug(f"Product page detected (URL pattern): {url[:60]}")
            return True

        return False
```

**Add CLI argument for threshold**:
```python
parser.add_argument(
    '--detection-threshold',
    type=int,
    default=3,
    help='Product page detection threshold (1-10, default: 3)'
)
```

#### 3. Testing (2 hours)

**Test with various sites**:
```bash
# Test with strict threshold
python3 fashion_scraper_async.py --designer Prada --detection-threshold 5

# Test with lenient threshold
python3 fashion_scraper_async.py --designer Prada --detection-threshold 2

# Test with traditional site (should still work)
python3 fashion_scraper_async.py --designer "Anna Sui" --detection-threshold 3
```

### Estimated Effort: 6-8 hours

### Success Criteria
- ✅ Content-based detection implemented with scoring system
- ✅ Detects product pages without URL pattern assumptions
- ✅ Works across different site architectures
- ✅ Configurable threshold via CLI
- ✅ Maintains compatibility with traditional sites
- ✅ Reduces false positives

---

## TASK-19: Site-Specific Configuration System (4-8 hours)

### Goal
Create a configuration file system for site-specific settings, enabling customization per brand without code changes.

### Implementation Steps

#### 1. Design Configuration Schema (1 hour)

**Create `site_configs.json`**:
```json
{
  "prada": {
    "domain": "prada.com",
    "requires_playwright": true,
    "url_patterns": {
      "product": ["/products/", "/p/"],
      "category": ["/c/", "/collections/"]
    },
    "selectors": {
      "product_name": ".product-title, h1.title",
      "price": "[data-price], .price",
      "images": ".product-gallery img, .main-image",
      "description": ".product-description"
    },
    "rate_limit": 2.0,
    "wait_for_selector": ".product-gallery",
    "scroll_to_load": true,
    "api_endpoints": {
      "products": "/api/products/{id}"
    }
  },
  "gucci": {
    "domain": "gucci.com",
    "requires_playwright": true,
    "url_patterns": {
      "product": ["/products/", "/shop/"],
      "category": ["/category/", "/collection/"]
    },
    "selectors": {
      "product_name": "h1[class*='product']",
      "price": ".price-current",
      "images": ".product-image img"
    },
    "rate_limit": 1.5,
    "anti_bot_evasion": {
      "user_agent": "Mozilla/5.0...",
      "referer": "https://www.google.com/"
    }
  },
  "annasui": {
    "domain": "annasui.com",
    "requires_playwright": false,
    "url_patterns": {
      "product": ["/products/", "/collections/"]
    },
    "selectors": {
      "product_name": ".product-title",
      "price": ".price",
      "images": ".product-image img"
    },
    "rate_limit": 3.0
  }
}
```

#### 2. Implement Configuration Loader (2-3 hours)

**Create `site_config.py`**:
```python
import json
from pathlib import Path
from typing import Dict, Optional, List
from urllib.parse import urlparse


class SiteConfig:
    """Configuration for a specific website."""

    def __init__(self, config_dict: dict):
        self.domain = config_dict.get('domain', '')
        self.requires_playwright = config_dict.get('requires_playwright', False)
        self.url_patterns = config_dict.get('url_patterns', {})
        self.selectors = config_dict.get('selectors', {})
        self.rate_limit = config_dict.get('rate_limit', 2.0)
        self.wait_for_selector = config_dict.get('wait_for_selector')
        self.scroll_to_load = config_dict.get('scroll_to_load', False)
        self.api_endpoints = config_dict.get('api_endpoints', {})
        self.anti_bot_evasion = config_dict.get('anti_bot_evasion', {})

    def is_product_url(self, url: str) -> bool:
        """Check if URL matches product patterns."""
        url_lower = url.lower()
        product_patterns = self.url_patterns.get('product', [])
        return any(pattern in url_lower for pattern in product_patterns)

    def is_category_url(self, url: str) -> bool:
        """Check if URL matches category patterns."""
        url_lower = url.lower()
        category_patterns = self.url_patterns.get('category', [])
        return any(pattern in url_lower for pattern in category_patterns)


class SiteConfigManager:
    """Manages site-specific configurations."""

    def __init__(self, config_path: str = "site_configs.json"):
        self.config_path = Path(config_path)
        self.configs: Dict[str, SiteConfig] = {}
        self.load_configs()

    def load_configs(self):
        """Load configurations from JSON file."""
        if not self.config_path.exists():
            # Use default empty config
            return

        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for site_key, config_dict in data.items():
            self.configs[site_key.lower()] = SiteConfig(config_dict)

    def get_config_for_url(self, url: str) -> Optional[SiteConfig]:
        """Get configuration for a specific URL."""
        domain = urlparse(url).netloc

        # Try exact match first
        for site_key, config in self.configs.items():
            if config.domain in domain:
                return config

        return None

    def get_config_for_designer(self, designer_name: str) -> Optional[SiteConfig]:
        """Get configuration by designer name."""
        key = designer_name.lower().replace(' ', '')
        return self.configs.get(key)

    def should_use_playwright(self, designer_name: str, url: str) -> bool:
        """Determine if Playwright should be used for this site."""
        config = self.get_config_for_designer(designer_name)
        if not config:
            config = self.get_config_for_url(url)

        if config:
            return config.requires_playwright

        # Default: use HTML scraping
        return False
```

#### 3. Integrate with Main Scraper (2-3 hours)

**Update AsyncFashionScraper**:
```python
class AsyncFashionScraper:
    def __init__(self, ..., config_file: str = "site_configs.json"):
        # ... existing code ...
        self.config_manager = SiteConfigManager(config_file)

    async def _scrape_designer(self, designer_name, website_url, ...):
        # Get site-specific config
        config = self.config_manager.get_config_for_designer(designer_name)

        # Use Playwright if configured
        if config and config.requires_playwright:
            async with PlaywrightCrawler(self.logger, config) as pw_crawler:
                product_pages = await pw_crawler.discover_product_pages(
                    website_url, designer_name, self.max_pages_per_site
                )
        else:
            product_pages = await crawler.discover_product_pages(
                website_url, designer_name, self.max_pages_per_site
            )
```

**Update PlaywrightCrawler to use config**:
```python
class PlaywrightCrawler:
    def __init__(self, logger, config: Optional[SiteConfig] = None):
        self.logger = logger
        self.config = config
        self.browser = None
        self.playwright = None

    async def discover_product_pages(self, base_url, designer, max_pages):
        # ... existing code ...

        # Use config for waiting
        if self.config and self.config.wait_for_selector:
            await page.wait_for_selector(self.config.wait_for_selector)

        # Use config for scrolling
        if self.config and self.config.scroll_to_load:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

    def _is_product_page(self, soup, url):
        # Use config patterns if available
        if self.config:
            return self.config.is_product_url(url)

        # Fall back to default detection
        return super()._is_product_page(soup, url)
```

#### 4. Create Default Configuration (1 hour)

Create `site_configs.json` with configurations for:
- Anna Sui (working example)
- Top 5 luxury brands (Gucci, Prada, Chanel, Dior, Burberry)
- Document configuration options in README

#### 5. Testing (1 hour)

**Test with different configurations**:
```bash
# Test with default config
python3 fashion_scraper_async.py --designer Prada --max-images 10

# Test with custom config file
python3 fashion_scraper_async.py --designer Gucci --config my_configs.json

# Test fallback for unconfigured site
python3 fashion_scraper_async.py --designer "Unknown Brand"
```

### Estimated Effort: 7-10 hours

### Success Criteria
- ✅ JSON configuration file system implemented
- ✅ Site-specific settings loaded correctly
- ✅ Playwright usage determined by config
- ✅ URL patterns customizable per site
- ✅ CSS selectors configurable
- ✅ Rate limits configurable
- ✅ Fallback to defaults for unconfigured sites
- ✅ Documentation for adding new site configs

---

## Overall Implementation Timeline

### Phase 1: Complete TASK-17 (5-8 hours)
**Priority**: HIGH - Required for TASK-18 and TASK-19
**Deliverable**: Playwright fully integrated with main scraper
**Expected Outcome**: Can scrape luxury sites with --use-playwright flag

### Phase 2: Implement TASK-18 (6-8 hours)
**Priority**: MEDIUM - Enhances product detection
**Deliverable**: Content-based product page detection
**Expected Outcome**: Better product discovery across diverse sites

### Phase 3: Implement TASK-19 (7-10 hours)
**Priority**: MEDIUM - Enables easy site customization
**Deliverable**: Site-specific configuration system
**Expected Outcome**: No code changes needed for new sites

### Total Estimated Effort: 18-26 hours

---

## Testing Strategy

### Test Suite 1: Playwright Integration
```bash
# Test 1: Anna Sui without Playwright (baseline)
python3 fashion_scraper_async.py --designer "Anna Sui" --max-images 10

# Test 2: Prada with Playwright
python3 fashion_scraper_async.py --designer Prada --max-images 10 --use-playwright Prada

# Test 3: Mixed approach
python3 fashion_scraper_async.py --max-images 5 --use-playwright Gucci Prada
```

### Test Suite 2: Intelligent Detection
```bash
# Test with various thresholds
python3 fashion_scraper_async.py --designer Prada --detection-threshold 2
python3 fashion_scraper_async.py --designer Prada --detection-threshold 5

# Compare detection rates
python3 fashion_scraper_async.py --designer "Anna Sui" --detection-threshold 3
```

### Test Suite 3: Site Configurations
```bash
# Test configured sites
python3 fashion_scraper_async.py --designer Prada --config site_configs.json
python3 fashion_scraper_async.py --designer Gucci --config site_configs.json

# Test unconfigured site (fallback)
python3 fashion_scraper_async.py --designer "New Brand"
```

---

## Success Metrics

### For TASK-17
- ✅ Playwright successfully renders JavaScript sites
- ✅ Products detected on at least 1 luxury site
- ✅ No regressions for traditional HTML sites
- ✅ Performance acceptable (< 5 seconds per page)

### For TASK-18
- ✅ Product detection works without URL patterns
- ✅ False positive rate < 10%
- ✅ Works across 3+ different site architectures
- ✅ Configurable threshold improves detection

### For TASK-19
- ✅ Configuration loaded correctly for 5+ sites
- ✅ No code changes needed to add new site
- ✅ Fallback works for unconfigured sites
- ✅ Documentation clear enough for non-developers

---

## Risk Assessment

### High Risk
- **Anti-bot protection**: Luxury sites may detect and block automated access
  - **Mitigation**: Start with less aggressive sites, add stealth mode if needed
- **API changes**: Sites may change their structure
  - **Mitigation**: Configuration system allows quick updates

### Medium Risk
- **Performance**: Playwright is resource-intensive
  - **Mitigation**: Use selectively, maintain HTML scraping for traditional sites
- **Complexity**: Three interconnected tasks
  - **Mitigation**: Phase implementation, test thoroughly between phases

### Low Risk
- **Breaking existing functionality**: Well-tested baseline
  - **Mitigation**: Maintain compatibility, use feature flags

---

## Recommendations

### Option A: Full Implementation (18-26 hours)
Implement all 3 tasks sequentially for complete luxury site support.

**Pros**:
- Complete solution for luxury sites
- Highly configurable and maintainable
- Professional-grade implementation

**Cons**:
- Significant time investment
- Luxury sites may still block despite best efforts

### Option B: Phased Approach (Start with TASK-17, 5-8 hours)
Complete TASK-17 first, evaluate results, then decide on TASK-18/19.

**Pros**:
- Quicker initial results
- Can validate luxury site approach before full investment
- Lower risk

**Cons**:
- May need manual configuration per site
- Product detection still relies on patterns

### Option C: Hybrid MVP (10-12 hours)
Implement core of TASK-17 + basic TASK-19, skip TASK-18 initially.

**Pros**:
- Configuration system enables easy customization
- Playwright for sites that need it
- Moderate time investment

**Cons**:
- Still uses URL pattern detection
- Manual configuration required per site

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Choose implementation option** (A, B, or C)
3. **Set up git branch** for remaining tasks work
4. **Start with TASK-17** (highest priority)
5. **Test with 1-2 luxury sites** before full rollout
6. **Document findings** for future reference

---

**Created**: November 15, 2025
**BrainGrid**: PROJ-5 / REQ-9
**Status**: Planning Phase
