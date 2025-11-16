#!/usr/bin/env python3
"""
Quick test script for person_filter.py
Tests device selection and person detection functionality.
"""

import sys
from person_filter import PersonDetectionFilter
from pathlib import Path

def test_device_selection():
    """Test device selection functionality."""
    print("\n" + "=" * 60)
    print("Testing Device Selection")
    print("=" * 60)

    # Test auto-detect
    print("\n1. Testing auto-detect:")
    filter_auto = PersonDetectionFilter(device=None)
    print(f"   Auto-detected device: {filter_auto.device}")

    # Test explicit CPU
    print("\n2. Testing explicit CPU:")
    filter_cpu = PersonDetectionFilter(device='cpu')
    print(f"   Device: {filter_cpu.device}")

    # Test MPS (if on Mac)
    print("\n3. Testing MPS (Apple Silicon):")
    filter_mps = PersonDetectionFilter(device='mps')
    print(f"   Device: {filter_mps.device}")

    # Test CUDA (if available)
    print("\n4. Testing CUDA:")
    filter_cuda = PersonDetectionFilter(device='cuda')
    print(f"   Device: {filter_cuda.device}")

    print("\n" + "=" * 60)
    return filter_auto

def test_person_detection(filter_instance):
    """Test person detection on a few sample images."""
    print("\n" + "=" * 60)
    print("Testing Person Detection")
    print("=" * 60)

    output_dir = Path("output")
    if not output_dir.exists():
        print("No output directory found, skipping detection test")
        return

    # Get first 5 images
    image_files = list(output_dir.glob("*.jpg"))[:5]

    if not image_files:
        print("No images found in output directory")
        return

    print(f"\nTesting on {len(image_files)} sample images:\n")

    for img_file in image_files:
        has_person, count = filter_instance.detect_person(str(img_file))
        status = "✓ HAS PERSON" if has_person else "✗ NO PERSON"
        print(f"{status:15} (count: {count:2}) - {img_file.name}")

    print("\n" + "=" * 60)

def main():
    print("\n" + "=" * 60)
    print("Person Filter - Device Selection Test (TASK-24)")
    print("=" * 60)

    try:
        # Test device selection
        filter_instance = test_device_selection()

        # Test person detection
        test_person_detection(filter_instance)

        print("\n✓ All tests completed successfully!\n")
        return 0

    except Exception as e:
        print(f"\n✗ Error during testing: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
