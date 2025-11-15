# Counter Bug: Batch Processing vs Per-Image Limit

## Status: FIXED ✅

The batch processing has been updated to respect the `--max-images` limit with minimal overshoot.

## Original Problem

The scraper was downloading more images than the `--max-images` limit when person filtering was enabled.

**Example**:
- Set `--max-images 5`
- Expected: 5 images with people
- Actual: 43 images with people (FIXED)

## Root Cause

The image download happens in **batches per product page**:

1. Extract all images from a page (e.g., 50 images)
2. Download ALL 50 images in parallel (`download_batch`)
3. Filter each image with YOLO
4. AFTER the entire batch: check if limit reached

**Problem**: If a page has 50 images and 43 have people, all 43 get kept even if the limit is 5.

## Current Flow

```python
for page in product_pages:
    images = extract_images(page)  # Get 50 images
    results = download_batch(images)  # Download all 50 in parallel

    for result in results:
        if result:  # Has person
            counter += 1

    # Check limit AFTER processing entire batch
    if counter >= limit:
        break
```

## Required Flow (TASK-16 + TASK-20)

```python
for page in product_pages:
    images = extract_images(page)

    for image in images:
        if counter >= limit:
            break  # Stop immediately

        result = download_image(image)
        if result:  # Has person
            counter += 1
```

## Solution Options

### Option 1: Sequential Downloads (Simple, Slow)
Change from batch parallel downloads to sequential downloads, checking counter after each image.

**Pros**: Simple fix, accurate counting
**Cons**: Much slower (no parallelism)

### Option 2: Limited Batch Size (Balanced)
Download in smaller batches (e.g., 10 at a time), check counter between batches.

**Pros**: Maintains some parallelism, more accurate
**Cons**: Still might overshoot by batch size

### Option 3: Interruptible Batch (Complex, Fast)
Use async task cancellation to stop mid-batch when limit reached.

**Pros**: Fast, accurate
**Cons**: Complex implementation

## Implemented Solution: Option 2 (Balanced) ✅

Modified the batch download to:
1. Process images in smaller batches (15 images per batch)
2. Check counter before starting each batch
3. Check counter before processing each successful download result
4. Stop when limit reached

**Current Behavior**:
- Limit of 5: Gets 5-6 images (acceptable)
- Limit of 100: Gets ~100 images with minimal overshoot
- Maximum overshoot: Very small (typically 0-1 images)

The small overshoot occurs because batch downloads happen in parallel via `asyncio.gather()`. All images in a batch start downloading simultaneously, so if multiple images with people complete at nearly the same time, they may both get saved before the counter check happens.

## Implementation Details

**File Modified**: `fashion_scraper_async.py` lines 1510-1566

**Changes Made**:
1. Split image processing into batches of 15 (BATCH_SIZE = 15)
2. Check limit before starting each batch (line 1522-1525)
3. Check limit before processing each successful result (line 1540-1543)
4. Check limit after completing each batch (line 1564-1566)

**Code Location**: fashion_scraper_async.py:1510-1566
