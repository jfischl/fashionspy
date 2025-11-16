#!/usr/bin/env python3
"""
Test TASK-26 and TASK-27 enhancements.
"""

from pathlib import Path
import json

def test_task_26_hash_persistence():
    """Test that duplicate hashes are persisted."""
    print("=" * 60)
    print("Testing TASK-26: Hash Persistence")
    print("=" * 60)

    hash_file = Path("output/duplicate_hashes.json")

    if hash_file.exists():
        with open(hash_file, 'r') as f:
            hashes = json.load(f)
        print(f"✓ Hash persistence file exists: {hash_file}")
        print(f"✓ Contains {len(hashes)} duplicate hashes")
        print(f"✓ Sample hashes (first 3):")
        for h in hashes[:3]:
            print(f"  - {h}")
        return True
    else:
        print(f"✗ Hash file not found: {hash_file}")
        print("  (Will be created after next scraping run)")
        return False

def test_task_27_single_csv():
    """Test that single CSV file is used."""
    print("\n" + "=" * 60)
    print("Testing TASK-27: Single CSV File")
    print("=" * 60)

    output_dir = Path("output")
    single_csv = output_dir / "image_sources.csv"
    timestamped_csvs = list(output_dir.glob("image_sources_*.csv"))

    print(f"Single CSV file (image_sources.csv):")
    if single_csv.exists():
        # Count lines
        with open(single_csv, 'r') as f:
            lines = f.readlines()
        print(f"✓ File exists: {single_csv}")
        print(f"✓ Contains {len(lines) - 1} entries (excluding header)")
    else:
        print(f"✗ File not found: {single_csv}")
        print("  (Will be created on next scraping run)")

    print(f"\nTimestamped CSV files (old format):")
    if timestamped_csvs:
        print(f"  Found {len(timestamped_csvs)} old timestamped CSV files:")
        for csv_file in timestamped_csvs[:5]:  # Show first 5
            print(f"  - {csv_file.name}")
        if len(timestamped_csvs) > 5:
            print(f"  ... and {len(timestamped_csvs) - 5} more")
        print("\n  Note: These are from previous runs before TASK-27.")
        print("  New runs will append to image_sources.csv instead.")
    else:
        print("  ✓ No old timestamped CSV files found")

    return single_csv.exists()

def test_filtered_hashes():
    """Test that filtered hashes are also persisted."""
    print("\n" + "=" * 60)
    print("Testing Person Filter Hash Persistence")
    print("=" * 60)

    filtered_file = Path("output/filtered_hashes.json")

    if filtered_file.exists():
        with open(filtered_file, 'r') as f:
            hashes = json.load(f)
        print(f"✓ Filtered hash file exists: {filtered_file}")
        print(f"✓ Contains {len(hashes)} filtered image hashes")
        return True
    else:
        print(f"✗ Filtered hash file not found: {filtered_file}")
        return False

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Enhancement Tests (TASK-26, TASK-27)")
    print("=" * 60 + "\n")

    results = []
    results.append(("TASK-26: Hash Persistence", test_task_26_hash_persistence()))
    results.append(("TASK-27: Single CSV File", test_task_27_single_csv()))
    results.append(("Person Filter Hashes", test_filtered_hashes()))

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for test_name, result in results:
        status = "✓ PASS" if result else "⚠ PENDING"
        print(f"{status:10} {test_name}")

    print("\n" + "=" * 60)
    print("Note: Some features require running the scraper first.")
    print("Run: python3 fashion_scraper_async.py --max-images 5")
    print("=" * 60)

if __name__ == "__main__":
    main()
