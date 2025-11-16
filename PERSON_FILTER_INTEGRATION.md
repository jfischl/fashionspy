# Person Filter Integration Plan

## Current Status
The person filtering is NOT integrated into the main scraper. Currently:
- `fashion_scraper_async.py` downloads all images without filtering
- `person_filter.py` exists as a separate batch filtering script
- **The --max-images limit counts ALL downloaded images, not just images with people**

## Required Changes (TASK-16 + TASK-20)

According to the task updates, the scraper should:
1. Download image → check duplicate → **run YOLO immediately** → delete if no person → only count if person detected
2. Filtered images should be tracked to avoid re-downloading
3. The `--max-images` limit should apply to KEPT images only (those containing people)

### Integration Steps

#### 1. Add Person Detection Import
**Location**: Top of `fashion_scraper_async.py` (after other imports)
```python
# TASK-20: Import person detection
try:
    from person_filter import PersonDetectionFilter
    PERSON_FILTER_AVAILABLE = True
except ImportError:
    PERSON_FILTER_AVAILABLE = False
```

#### 2. Modify AsyncImageDownloader Class
**Location**: Line ~1016-1107

Add to `__init__`:
```python
def __init__(self, http_client: AsyncHTTPClient, output_dir: Path,
             duplicate_detector: DuplicateDetector, logger: ScraperLogger,
             person_filter: Optional[PersonDetectionFilter] = None):
    ...
    self.person_filter = person_filter
    self.filtered_hashes = set()  # Track filtered image hashes
```

#### 3. Modify download_image Method
**Location**: Line ~1034-1073

Add person detection after saving image:
```python
async def download_image(self, img_url: str, designer: str) -> Optional[Dict[str, str]]:
    ...
    # Save image
    try:
        with open(filepath, 'wb') as f:
            f.write(image_data)

        # TASK-20: Filter immediately after download
        if self.person_filter:
            has_person, person_count = self.person_filter.detect_person(str(filepath))

            if not has_person:
                # No person detected - delete and track hash
                filepath.unlink()  # Delete file
                self.filtered_hashes.add(img_hash)
                return None  # Don't count toward limit

        return {
            'filename': filename,
            'hash': img_hash,
            'size': len(image_data),
            'has_person': has_person if self.person_filter else True,
            'person_count': person_count if self.person_filter else 0
        }
    ...
```

#### 4. Check Filtered Hashes Before Download
**Location**: Beginning of `download_image` method

```python
async def download_image(self, img_url: str, designer: str) -> Optional[Dict[str, str]]:
    # Check if previously filtered (before downloading)
    # (This requires calculating hash from URL first - may need adjustment)

    result = await self.http_client.get(img_url, use_cache=False)
    if not result:
        return None

    image_data, headers = result

    # Check for duplicates
    is_dup, img_hash = await self.duplicate_detector.is_duplicate(image_data)
    if is_dup:
        return None

    # Check if this hash was previously filtered
    if img_hash in self.filtered_hashes:
        return None  # Skip - no person detected previously

    ...
```

#### 5. Initialize PersonDetectionFilter
**Location**: Main scraper initialization (where AsyncImageDownloader is created)

```python
# Initialize person filter if available
person_filter = None
if PERSON_FILTER_AVAILABLE:
    person_filter = PersonDetectionFilter(
        model_name="yolov8n.pt",
        confidence_threshold=0.25
    )
    logger.info("Person detection enabled (YOLO)")

# Initialize downloader with person filter
image_downloader = AsyncImageDownloader(
    http_client=http_client,
    output_dir=output_dir,
    duplicate_detector=duplicate_detector,
    logger=logger,
    person_filter=person_filter
)
```

#### 6. Update Progress Reporting
Show separate counts for:
- Images downloaded (total attempted)
- Images kept (with people)
- Images filtered (without people)
- Images skipped (duplicates + previously filtered)

#### 7. Persist Filtered Hashes
Save/load filtered hashes to/from a JSON file so they persist across runs:
```python
# Load on init
filtered_hashes_file = output_dir / "filtered_hashes.json"
if filtered_hashes_file.exists():
    with open(filtered_hashes_file) as f:
        self.filtered_hashes = set(json.load(f))

# Save on completion
with open(filtered_hashes_file, 'w') as f:
    json.dump(list(self.filtered_hashes), f)
```

## Testing

After integration, test with:
```bash
python3 fashion_scraper_async.py --designer "Stella McCartney" --max-images 10 --max-pages 5
```

Expected behavior:
- Scraper continues downloading until 10 images WITH people are kept
- Images without people are deleted immediately
- Progress shows "Kept: 10, Filtered: X"
- Subsequent runs skip previously filtered images

## Files to Modify

1. `fashion_scraper_async.py` - Main integration
2. Test the integration thoroughly

## Implementation Complexity

This is a **TASK-16 + TASK-20 completion** task that requires:
- Modifying the core download loop
- Adding person detection dependency
- Changing counter logic
- Adding filtered hash persistence
- Updating progress reporting

**Estimated effort**: Medium-High (touches core scraping logic)
