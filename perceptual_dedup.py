#!/usr/bin/env python3
"""
Perceptual Hash-Based Near-Duplicate Detection and Removal

TASK-28: Detect and remove visually similar images using perceptual hashing.
Uses pHash to identify images that look similar but have different file hashes.
"""

import argparse
import csv
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Set

try:
    from imagehash import phash
    from PIL import Image
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False
    print("Warning: imagehash not available. Install with: pip install imagehash pillow")


class PerceptualDeduplicator:
    """Remove near-duplicate images using perceptual hashing."""

    def __init__(self, threshold: int = 5, logger: logging.Logger = None):
        """Initialize the perceptual deduplicator.

        Args:
            threshold: Maximum Hamming distance for similarity (0-64, default: 5)
                      Lower = stricter (fewer matches), Higher = looser (more matches)
            logger: Logger instance
        """
        self.threshold = threshold
        self.logger = logger or self._setup_logging()
        self.kept_hashes: Dict[str, Path] = {}  # phash -> filepath
        self.hash_distances: List[Tuple[int, Path, Path]] = []  # (distance, img1, img2)

    def _setup_logging(self) -> logging.Logger:
        """Set up logging."""
        logger = logging.getLogger("PerceptualDedup")
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        return logger

    def find_similar_images(self, image_dir: Path) -> List[Path]:
        """Find images similar to already-kept images.

        Args:
            image_dir: Directory containing images

        Returns:
            List of image paths to delete (near-duplicates)
        """
        to_delete = []

        # Get all images, sorted for consistent ordering
        image_files = sorted(image_dir.glob('*.jpg'))
        total = len(image_files)

        self.logger.info(f"Scanning {total} images for near-duplicates...")

        for idx, img_path in enumerate(image_files, 1):
            if idx % 50 == 0:
                self.logger.info(f"  Progress: {idx}/{total} images processed")

            try:
                img = Image.open(img_path)
                img_hash = phash(img)
                img.close()

                # Check against kept images
                is_similar = False
                for kept_hash_str, kept_path in self.kept_hashes.items():
                    # Convert string back to ImageHash for comparison
                    from imagehash import hex_to_hash
                    kept_hash = hex_to_hash(kept_hash_str)
                    distance = img_hash - kept_hash

                    if distance < self.threshold:
                        # Similar image found
                        to_delete.append(img_path)
                        self.hash_distances.append((distance, img_path, kept_path))
                        self.logger.debug(
                            f"Similar (distance={distance}): "
                            f"{img_path.name} ≈ {kept_path.name}"
                        )
                        is_similar = True
                        break

                if not is_similar:
                    # Not similar - keep it
                    self.kept_hashes[str(img_hash)] = img_path

            except Exception as e:
                self.logger.error(f"Error processing {img_path}: {e}")

        return to_delete

    def remove_similar_images(
        self,
        image_dir: Path,
        delete: bool = True,
        update_csv: bool = True,
        csv_path: Path = None
    ) -> Dict[str, int]:
        """Remove near-duplicate images from directory.

        Args:
            image_dir: Directory containing images
            delete: If True, delete similar images. If False, just report.
            update_csv: If True, update CSV to remove deleted entries
            csv_path: Path to CSV file (auto-detect if None)

        Returns:
            Statistics dict with counts
        """
        # Find similar images
        to_delete = self.find_similar_images(image_dir)

        stats = {
            'total_processed': len(list(image_dir.glob('*.jpg'))),
            'similar_found': len(to_delete),
            'images_deleted': 0,
            'unique_kept': len(self.kept_hashes)
        }

        if delete and to_delete:
            self.logger.info(f"\nDeleting {len(to_delete)} near-duplicate images...")

            for img_path in to_delete:
                img_path.unlink()
                stats['images_deleted'] += 1

            if update_csv:
                self._update_csv(image_dir, to_delete, csv_path)

        return stats

    def _update_csv(self, image_dir: Path, deleted_images: List[Path], csv_path: Path = None):
        """Update CSV file to remove entries for deleted images.

        Args:
            image_dir: Directory containing images
            deleted_images: List of deleted image paths
            csv_path: Path to CSV file (auto-detect if None)
        """
        if csv_path is None:
            # Auto-detect CSV file
            csv_path = image_dir / "image_sources.csv"

        if not csv_path.exists():
            self.logger.warning(f"CSV file not found: {csv_path}")
            return

        # Get filenames of deleted images
        deleted_filenames = {img.name for img in deleted_images}

        # Read existing CSV
        rows_to_keep = []
        removed_count = 0

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames

            for row in reader:
                if row['local_filename'] not in deleted_filenames:
                    rows_to_keep.append(row)
                else:
                    removed_count += 1

        # Write back filtered CSV
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows_to_keep)

        self.logger.info(f"Updated CSV: removed {removed_count} entries")

    def print_similar_pairs(self, top_n: int = 10):
        """Print the most similar image pairs.

        Args:
            top_n: Number of pairs to show
        """
        if not self.hash_distances:
            return

        sorted_pairs = sorted(self.hash_distances, key=lambda x: x[0])

        print(f"\nTop {min(top_n, len(sorted_pairs))} most similar pairs:")
        for distance, img1, img2 in sorted_pairs[:top_n]:
            print(f"  Distance {distance}: {img1.name} ≈ {img2.name}")


def main():
    """Main entry point for perceptual deduplication CLI."""
    parser = argparse.ArgumentParser(
        description='Perceptual Hash Near-Duplicate Detection and Removal (TASK-28)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Dry-run (report only, don't delete)
  python perceptual_dedup.py --image-dir output

  # Delete near-duplicates with default threshold (5)
  python perceptual_dedup.py --image-dir output --delete

  # Stricter threshold (fewer deletions)
  python perceptual_dedup.py --image-dir output --delete --threshold 3

  # Looser threshold (more deletions)
  python perceptual_dedup.py --image-dir output --delete --threshold 10

Similarity Thresholds:
  0-2   : Almost identical (same photo, minor edits)
  3-5   : Very similar (same product, different angle)
  6-10  : Similar (same outfit, different pose/lighting)
  10+   : Different images
        '''
    )

    parser.add_argument(
        '--image-dir',
        type=Path,
        default=Path('output'),
        help='Directory containing images to deduplicate (default: output/)'
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=5,
        help='Maximum Hamming distance for similarity (0-64, default: 5, lower=stricter)'
    )
    parser.add_argument(
        '--delete',
        action='store_true',
        help='Delete near-duplicate images (default: just report, don\'t delete)'
    )
    parser.add_argument(
        '--no-update-csv',
        action='store_true',
        help='Don\'t update CSV file when deleting images'
    )
    parser.add_argument(
        '--csv',
        type=Path,
        help='Path to image source CSV file (auto-detected if not specified)'
    )
    parser.add_argument(
        '--show-pairs',
        type=int,
        default=10,
        help='Number of similar pairs to show (default: 10)'
    )

    args = parser.parse_args()

    if not IMAGEHASH_AVAILABLE:
        print("\nError: imagehash library not available")
        print("Install with: pip install imagehash pillow")
        return 1

    if not args.image_dir.exists():
        print(f"\nError: Image directory not found: {args.image_dir}")
        return 1

    # Run deduplication
    print("=" * 60)
    print("Perceptual Hash Near-Duplicate Detection (TASK-28)")
    print("=" * 60)
    print(f"Image directory: {args.image_dir}")
    print(f"Similarity threshold: {args.threshold}")
    print(f"Delete mode: {'ENABLED' if args.delete else 'DISABLED (dry-run)'}")
    print(f"Update CSV: {'NO' if args.no_update_csv else 'YES'}")
    print("=" * 60 + "\n")

    deduplicator = PerceptualDeduplicator(threshold=args.threshold)
    stats = deduplicator.remove_similar_images(
        args.image_dir,
        delete=args.delete,
        update_csv=not args.no_update_csv,
        csv_path=args.csv
    )

    # Show similar pairs
    if stats['similar_found'] > 0:
        deduplicator.print_similar_pairs(args.show_pairs)

    # Print summary
    print("\n" + "=" * 60)
    print("PERCEPTUAL DEDUPLICATION - SUMMARY")
    print("=" * 60)
    print(f"Total images processed: {stats['total_processed']}")
    print(f"Unique images kept: {stats['unique_kept']}")
    print(f"Near-duplicates found: {stats['similar_found']}")
    print(f"Images deleted: {stats['images_deleted']}")

    if stats['total_processed'] > 0:
        diversity_pct = (stats['unique_kept'] / stats['total_processed']) * 100
        print(f"Dataset diversity: {diversity_pct:.1f}%")

    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
