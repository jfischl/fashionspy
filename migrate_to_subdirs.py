#!/usr/bin/env python3
"""
Migrate existing images from flat structure to designer subdirectories (TASK-29).
"""

import csv
import re
from pathlib import Path
from collections import defaultdict

def sanitize_designer_name(designer: str) -> str:
    """Convert designer name to filesystem-safe folder name."""
    return designer.lower().replace(' ', '_').replace('-', '_')

def extract_designer_from_filename(filename: str) -> str:
    """Extract designer name from old filename format.

    Format: designer_name_YYYYMMDD_HHMMSS_ffffff.jpg
    """
    # Remove extension
    name_without_ext = filename.rsplit('.', 1)[0]

    # Split on timestamp pattern (looks for YYYYMMDD pattern)
    parts = re.split(r'_\d{8}_', name_without_ext)
    if parts and len(parts) > 0:
        designer = parts[0]
        # Convert underscores back to spaces and title case
        return designer.replace('_', ' ').title()

    return None

def migrate_images(output_dir: Path, csv_path: Path = None, dry_run: bool = True):
    """Migrate images to subdirectories."""

    if csv_path is None:
        csv_path = output_dir / "image_sources.csv"

    # Get all images
    image_files = list(output_dir.glob('*.jpg'))
    print(f"Found {len(image_files)} images in {output_dir}")

    # Group by designer
    designer_files = defaultdict(list)

    for img_file in image_files:
        designer = extract_designer_from_filename(img_file.name)
        if designer:
            designer_files[designer].append(img_file)
        else:
            print(f"Warning: Could not extract designer from {img_file.name}")

    print(f"\nGrouped images by {len(designer_files)} designers:")
    for designer, files in sorted(designer_files.items()):
        print(f"  {designer}: {len(files)} images")

    if dry_run:
        print("\nDRY RUN - No files will be moved")
        print("Run with --move to actually migrate files")
        return

    # Create subdirectories and move files
    print("\nMigrating files...")
    moved_count = 0

    for designer, files in designer_files.items():
        folder_name = sanitize_designer_name(designer)
        designer_folder = output_dir / folder_name
        designer_folder.mkdir(exist_ok=True)

        for img_file in files:
            # Create new filename without designer prefix
            # Old: anna_sui_20251115_182650_990906.jpg
            # New: 20251115_182650_990906.jpg
            old_name = img_file.name
            new_name = re.sub(r'^[a-z_]+_(\d{8}_\d{6}_\d{6}\.jpg)$', r'\1', old_name)

            new_path = designer_folder / new_name
            img_file.rename(new_path)
            moved_count += 1

        print(f"  Moved {len(files)} images to {folder_name}/")

    print(f"\nMigrated {moved_count} images to subdirectories")

    # Update CSV if it exists
    if csv_path.exists():
        print(f"\nUpdating CSV: {csv_path}")
        update_csv(csv_path, designer_files, output_dir)

def update_csv(csv_path: Path, designer_files: dict, output_dir: Path):
    """Update CSV with new subdirectory paths."""

    # Read existing CSV
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Update paths
    updated = 0
    for row in rows:
        filename = row['local_filename']

        # If already has subdirectory, skip
        if '/' in filename:
            continue

        # Extract designer from filename
        designer = extract_designer_from_filename(filename)
        if designer:
            folder_name = sanitize_designer_name(designer)
            # Update to new format: folder/timestamp.jpg
            new_name = re.sub(r'^[a-z_]+_(\d{8}_\d{6}_\d{6}\.jpg)$', r'\1', filename)
            row['local_filename'] = f"{folder_name}/{new_name}"
            updated += 1

    # Write updated CSV
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Updated {updated} CSV entries with subdirectory paths")

if __name__ == "__main__":
    import sys

    output_dir = Path("output")
    dry_run = "--move" not in sys.argv

    print("=" * 60)
    print("Image Migration: Flat Structure → Designer Subdirectories")
    print("=" * 60)
    print(f"Output directory: {output_dir}")
    print(f"Mode: {'MOVE FILES' if not dry_run else 'DRY RUN'}")
    print("=" * 60 + "\n")

    migrate_images(output_dir, dry_run=dry_run)

    print("\n" + "=" * 60)
    if dry_run:
        print("To actually move files, run: python3 migrate_to_subdirs.py --move")
    else:
        print("Migration complete!")
    print("=" * 60)
