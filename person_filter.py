#!/usr/bin/env python3
"""
Person Detection Filter using YOLO

Filters fashion images to keep only those containing at least one person.
Uses YOLOv8 with pre-trained COCO model for person detection.

TASK-20: Implement YOLO person detection for image filtering
"""

import argparse
import csv
import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

from ultralytics import YOLO
import torch


class PersonDetectionFilter:
    """Filters images based on person detection using YOLO."""

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        confidence_threshold: float = 0.25,
        device: str = None
    ):
        """Initialize the person detection filter.

        Args:
            model_name: YOLO model to use (n=nano, s=small, m=medium, l=large, x=extra-large)
            confidence_threshold: Minimum confidence score for person detection (0.0-1.0)
            device: Device to run inference on ('cpu', 'cuda', 'mps', or None for auto-detect)
        """
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.logger = self._setup_logging()

        # Determine device
        self.device = self._select_device(device)
        self.logger.info(f"Using device: {self.device}")

        # Initialize YOLO model
        self.logger.info(f"Loading YOLO model: {model_name}")
        self.model = YOLO(model_name)

        # Move model to selected device
        self.model.to(self.device)

        # COCO class ID for 'person' is 0
        self.person_class_id = 0

        # Statistics
        self.stats = {
            'images_processed': 0,
            'images_with_people': 0,
            'images_without_people': 0,
            'images_deleted': 0,
            'errors': 0
        }

    def _select_device(self, device: str = None) -> str:
        """Select the best available device for inference.

        Args:
            device: User-specified device ('cpu', 'cuda', 'mps', or None for auto-detect)

        Returns:
            Device string to use ('cpu', 'cuda', or 'mps')
        """
        if device is not None:
            # User explicitly specified a device
            device_lower = device.lower()
            if device_lower == 'cuda':
                if torch.cuda.is_available():
                    return 'cuda'
                else:
                    self.logger.warning("CUDA requested but not available, falling back to CPU")
                    return 'cpu'
            elif device_lower == 'mps':
                if torch.backends.mps.is_available():
                    return 'mps'
                else:
                    self.logger.warning("MPS requested but not available, falling back to CPU")
                    return 'cpu'
            elif device_lower == 'cpu':
                return 'cpu'
            else:
                self.logger.warning(f"Unknown device '{device}', falling back to auto-detect")

        # Auto-detect best available device
        if torch.cuda.is_available():
            return 'cuda'
        elif torch.backends.mps.is_available():
            return 'mps'
        else:
            return 'cpu'

    def _setup_logging(self) -> logging.Logger:
        """Setup logging for the filter."""
        logger = logging.getLogger('PersonFilter')
        logger.setLevel(logging.INFO)

        # Console handler
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)

        # File handler
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(log_dir / f"person_filter_{timestamp}.log")
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        logger.addHandler(file_handler)

        return logger

    def detect_person(self, image_path: str) -> Tuple[bool, int]:
        """Detect if image contains at least one person.

        Args:
            image_path: Path to image file

        Returns:
            Tuple of (has_person, person_count)
        """
        try:
            # Run inference on the specified device
            results = self.model(image_path, verbose=False, device=self.device)

            # Count persons detected above confidence threshold
            person_count = 0
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        # Check if detected class is person and meets confidence threshold
                        if (int(box.cls[0]) == self.person_class_id and
                            float(box.conf[0]) >= self.confidence_threshold):
                            person_count += 1

            return (person_count > 0, person_count)

        except Exception as e:
            self.logger.error(f"Error detecting person in {image_path}: {str(e)}")
            self.stats['errors'] += 1
            return (False, 0)

    def filter_images(
        self,
        image_dir: str,
        delete: bool = False,
        update_csv: bool = True,
        csv_path: str = None
    ) -> Dict[str, int]:
        """Filter images in directory, keeping only those with people.

        Args:
            image_dir: Directory containing images to filter
            delete: If True, delete images without people. If False, just report.
            update_csv: If True, update the image source CSV to remove deleted entries
            csv_path: Path to image source CSV file (auto-detected if None)

        Returns:
            Statistics dictionary
        """
        image_dir_path = Path(image_dir)

        # Find all images
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        image_files = [
            f for f in image_dir_path.iterdir()
            if f.suffix.lower() in image_extensions and f.is_file()
        ]

        total_images = len(image_files)
        self.logger.info(f"Found {total_images} images to process")

        # Auto-detect CSV file if not provided
        if update_csv and csv_path is None:
            csv_files = sorted(image_dir_path.glob("image_sources_*.csv"), reverse=True)
            if csv_files:
                csv_path = str(csv_files[0])
                self.logger.info(f"Using CSV file: {csv_path}")

        # Track images to delete
        images_to_delete = []

        # Process each image
        for i, image_file in enumerate(image_files, 1):
            self.stats['images_processed'] += 1

            # Progress reporting
            if i % 100 == 0 or i == 1:
                self.logger.info(
                    f"Progress: {i}/{total_images} "
                    f"(With people: {self.stats['images_with_people']}, "
                    f"Without: {self.stats['images_without_people']})"
                )

            # Detect person in image
            has_person, person_count = self.detect_person(str(image_file))

            if has_person:
                self.stats['images_with_people'] += 1
            else:
                self.stats['images_without_people'] += 1
                images_to_delete.append(image_file)

        # Delete images without people if requested
        if delete and images_to_delete:
            self.logger.info(f"\nDeleting {len(images_to_delete)} images without people...")

            for image_file in images_to_delete:
                try:
                    image_file.unlink()
                    self.stats['images_deleted'] += 1
                except Exception as e:
                    self.logger.error(f"Error deleting {image_file}: {str(e)}")
                    self.stats['errors'] += 1

            # Update CSV file to remove deleted entries
            if update_csv and csv_path and os.path.exists(csv_path):
                self._update_csv(csv_path, images_to_delete)

        return self.stats

    def _update_csv(self, csv_path: str, deleted_images: List[Path]) -> None:
        """Update CSV file to remove entries for deleted images.

        Args:
            csv_path: Path to CSV file
            deleted_images: List of deleted image file paths
        """
        try:
            # Create set of deleted filenames for fast lookup
            deleted_filenames = {img.name for img in deleted_images}

            # Read existing CSV
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                fieldnames = reader.fieldnames

            # Filter out deleted images
            filtered_rows = [
                row for row in rows
                if row.get('local_filename') not in deleted_filenames
            ]

            removed_count = len(rows) - len(filtered_rows)

            # Write updated CSV
            with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(filtered_rows)

            self.logger.info(f"Updated CSV: removed {removed_count} entries")

        except Exception as e:
            self.logger.error(f"Error updating CSV {csv_path}: {str(e)}")
            self.stats['errors'] += 1

    def print_summary(self) -> None:
        """Print summary statistics."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("PERSON DETECTION FILTER - SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Total images processed: {self.stats['images_processed']}")
        self.logger.info(f"Images with people: {self.stats['images_with_people']}")
        self.logger.info(f"Images without people: {self.stats['images_without_people']}")
        self.logger.info(f"Images deleted: {self.stats['images_deleted']}")
        self.logger.info(f"Errors encountered: {self.stats['errors']}")

        if self.stats['images_processed'] > 0:
            percentage_with_people = (
                self.stats['images_with_people'] / self.stats['images_processed'] * 100
            )
            self.logger.info(f"Percentage with people: {percentage_with_people:.1f}%")

        self.logger.info("=" * 60)


def main():
    """Main entry point for person detection filter."""
    parser = argparse.ArgumentParser(
        description="Filter fashion images to keep only those containing people"
    )
    parser.add_argument(
        '--image-dir',
        default='output',
        help='Directory containing images to filter (default: output)'
    )
    parser.add_argument(
        '--model',
        default='yolov8n.pt',
        choices=['yolov8n.pt', 'yolov8s.pt', 'yolov8m.pt', 'yolov8l.pt', 'yolov8x.pt'],
        help='YOLO model size (n=nano/fastest, x=extra-large/most accurate, default: yolov8n.pt)'
    )
    parser.add_argument(
        '--confidence',
        type=float,
        default=0.25,
        help='Minimum confidence threshold for person detection (0.0-1.0, default: 0.25)'
    )
    parser.add_argument(
        '--delete',
        action='store_true',
        help='Delete images without people (default: just report, don\'t delete)'
    )
    parser.add_argument(
        '--no-update-csv',
        action='store_true',
        help='Do not update the image source CSV file when deleting images'
    )
    parser.add_argument(
        '--csv',
        help='Path to image source CSV file (auto-detected if not specified)'
    )
    parser.add_argument(
        '--device',
        choices=['cpu', 'cuda', 'mps', 'auto'],
        default='auto',
        help='Device to run inference on (cpu, cuda, mps, or auto for auto-detect, default: auto)'
    )

    args = parser.parse_args()

    # Initialize filter
    device = None if args.device == 'auto' else args.device
    filter_instance = PersonDetectionFilter(
        model_name=args.model,
        confidence_threshold=args.confidence,
        device=device
    )

    # Run filtering
    print("\n" + "=" * 60)
    print("Person Detection Filter (YOLO-based)")
    print("=" * 60)
    print(f"Model: {args.model}")
    print(f"Device: {filter_instance.device}")
    print(f"Confidence threshold: {args.confidence}")
    print(f"Delete mode: {'ENABLED' if args.delete else 'DISABLED (dry-run)'}")
    print(f"Update CSV: {'NO' if args.no_update_csv else 'YES'}")
    print("=" * 60 + "\n")

    # Filter images
    stats = filter_instance.filter_images(
        image_dir=args.image_dir,
        delete=args.delete,
        update_csv=not args.no_update_csv,
        csv_path=args.csv
    )

    # Print summary
    filter_instance.print_summary()

    return 0


if __name__ == "__main__":
    sys.exit(main())
