#!/usr/bin/env python3
"""
Delete flagged content from R2 storage.
Removes both image file and metadata.
"""
import argparse
import os
import sys
from urllib.parse import urlparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.r2_storage import get_r2_storage


def delete_by_url(image_url: str, dry_run: bool = False):
    """
    Delete image and metadata by image URL.

    Args:
        image_url: Full image URL (e.g., https://nano.seanfield.org/images/2025/12/14/abc123.png)
        dry_run: If True, only show what would be deleted without actually deleting
    """
    r2 = get_r2_storage()

    if not r2.is_available:
        print("❌ R2 storage not available")
        return False

    # Parse URL to get the S3 key
    parsed = urlparse(image_url)
    # Remove leading slash
    path = parsed.path.lstrip('/')

    if not path.startswith('images/'):
        print(f"❌ Invalid image URL: {image_url}")
        print("   Expected format: https://domain/images/YYYY/MM/DD/filename.png")
        return False

    # Extract the key parts
    # images/2025/12/14/abc123.png → ['images', '2025', '12', '14', 'abc123.png']
    parts = path.split('/')
    if len(parts) < 5:
        print(f"❌ Invalid path format: {path}")
        return False

    year, month, day, filename = parts[1], parts[2], parts[3], parts[4]

    # Construct keys
    image_key = f"images/{year}/{month}/{day}/{filename}"
    metadata_key = f"metadata/{year}/{month}/{day}/{filename.replace('.png', '.json')}"

    print(f"\n{'='*60}")
    print("Deleting flagged content:")
    print(f"{'='*60}")
    print(f"Image URL:    {image_url}")
    print(f"Image Key:    {image_key}")
    print(f"Metadata Key: {metadata_key}")
    print(f"Dry Run:      {dry_run}")
    print(f"{'='*60}\n")

    if dry_run:
        print("🔍 DRY RUN - No files will be deleted\n")

        # Check if files exist
        try:
            r2._client.head_object(Bucket=r2.bucket_name, Key=image_key)
            print(f"✓ Image exists:    {image_key}")
        except:
            print(f"✗ Image not found: {image_key}")

        try:
            r2._client.head_object(Bucket=r2.bucket_name, Key=metadata_key)
            print(f"✓ Metadata exists: {metadata_key}")
        except:
            print(f"✗ Metadata not found: {metadata_key}")

        print("\nRun without --dry-run to actually delete")
        return True

    # Actually delete
    deleted_count = 0

    # Delete image
    try:
        r2._client.delete_object(Bucket=r2.bucket_name, Key=image_key)
        print(f"✅ Deleted image: {image_key}")
        deleted_count += 1
    except Exception as e:
        print(f"⚠️  Failed to delete image: {e}")

    # Delete metadata
    try:
        r2._client.delete_object(Bucket=r2.bucket_name, Key=metadata_key)
        print(f"✅ Deleted metadata: {metadata_key}")
        deleted_count += 1
    except Exception as e:
        print(f"⚠️  Failed to delete metadata: {e}")

    print(f"\n✅ Deleted {deleted_count}/2 files")

    # Purge from Cloudflare CDN
    print("\n⚡ Next step: Purge CDN cache")
    print("   Go to: Cloudflare Dashboard → Caching → Purge Cache")
    print(f"   Purge URL: {image_url}")

    return deleted_count > 0


def delete_orphaned_metadata_by_date(date: str, dry_run: bool = False):
    """
    Delete orphaned metadata for a specific date.
    Orphaned = metadata exists but image file doesn't.

    Args:
        date: Date in YYYY-MM-DD format (e.g., 2025-12-12)
        dry_run: If True, only show what would be deleted
    """
    r2 = get_r2_storage()

    if not r2.is_available:
        print("❌ R2 storage not available")
        return False

    # Parse date
    try:
        from datetime import datetime
        dt = datetime.strptime(date, "%Y-%m-%d")
        year, month, day = dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")
    except ValueError:
        print(f"❌ Invalid date format: {date}")
        print("   Expected: YYYY-MM-DD (e.g., 2025-12-12)")
        return False

    print(f"\n{'='*60}")
    print(f"Cleaning orphaned metadata for {date}")
    print(f"{'='*60}")
    print(f"Date:     {date}")
    print(f"Dry Run:  {dry_run}")
    print(f"{'='*60}\n")

    # List all metadata files for this date
    metadata_prefix = f"metadata/{year}/{month}/{day}/"

    print(f"🔍 Scanning metadata: {metadata_prefix}")

    try:
        response = r2._client.list_objects_v2(
            Bucket=r2.bucket_name,
            Prefix=metadata_prefix
        )

        if "Contents" not in response:
            print(f"✅ No metadata found for {date}")
            return True

        metadata_files = response["Contents"]
        print(f"📊 Found {len(metadata_files)} metadata files\n")

        orphaned = []
        valid = []

        # Check each metadata file
        for meta_obj in metadata_files:
            metadata_key = meta_obj["Key"]

            # Derive image key from metadata key
            # metadata/2025/12/12/abc123.json → images/2025/12/12/abc123.png
            filename = metadata_key.split('/')[-1]  # abc123.json
            image_filename = filename.replace('.json', '.png')
            image_key = f"images/{year}/{month}/{day}/{image_filename}"

            # Check if image exists
            try:
                r2._client.head_object(Bucket=r2.bucket_name, Key=image_key)
                valid.append(metadata_key)
            except:
                # Image doesn't exist - this is orphaned metadata
                orphaned.append(metadata_key)

        print("📊 Analysis Results:")
        print(f"   Total metadata:  {len(metadata_files)}")
        print(f"   Valid (有图片):   {len(valid)}")
        print(f"   Orphaned (孤立): {len(orphaned)}")
        print()

        if not orphaned:
            print(f"✅ No orphaned metadata found for {date}")
            return True

        # Show orphaned files
        print("🗑️  Orphaned metadata files:")
        for i, key in enumerate(orphaned[:10], 1):
            print(f"   {i}. {key}")

        if len(orphaned) > 10:
            print(f"   ... and {len(orphaned) - 10} more")
        print()

        if dry_run:
            print("🔍 DRY RUN - No files will be deleted")
            print(f"   Run without --dry-run to delete {len(orphaned)} orphaned metadata files")
            return True

        # Actually delete orphaned metadata
        print(f"🗑️  Deleting {len(orphaned)} orphaned metadata files...")
        deleted_count = 0

        for metadata_key in orphaned:
            try:
                r2._client.delete_object(Bucket=r2.bucket_name, Key=metadata_key)
                deleted_count += 1
                if deleted_count % 10 == 0:
                    print(f"   Deleted {deleted_count}/{len(orphaned)}...")
            except Exception as e:
                print(f"   ⚠️  Failed to delete {metadata_key}: {e}")

        print(f"\n✅ Deleted {deleted_count}/{len(orphaned)} orphaned metadata files")
        return deleted_count > 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def clean_history_json(dry_run: bool = False):
    """
    Clean all history.json files (remove entries with missing images).

    Args:
        dry_run: If True, only show what would be cleaned
    """
    import json
    r2 = get_r2_storage()

    if not r2.is_available:
        print("❌ R2 storage not available")
        return False

    print(f"\n{'='*60}")
    print("Cleaning history.json files")
    print(f"{'='*60}")
    print(f"Dry Run: {dry_run}")
    print(f"{'='*60}\n")

    # Find all history.json files
    response = r2._client.list_objects_v2(
        Bucket=r2.bucket_name,
        Prefix=''
    )

    if 'Contents' not in response:
        print("✅ No files found in bucket")
        return True

    history_files = [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('history.json')]

    if not history_files:
        print("✅ No history.json files found")
        return True

    print(f"📄 Found {len(history_files)} history.json file(s):\n")

    total_removed = 0
    total_kept = 0

    for history_key in history_files:
        print(f"🔍 Processing: {history_key}")

        try:
            # Download history.json
            response = r2._client.get_object(
                Bucket=r2.bucket_name,
                Key=history_key
            )
            history_data = json.loads(response['Body'].read().decode('utf-8'))

            original_count = len(history_data)
            print(f"   Original entries: {original_count}")

            # Filter out entries with missing images
            valid_entries = []
            removed_entries = []

            for entry in history_data:
                image_url = entry.get('image_url', '')

                # Check if image exists
                if not image_url or image_url == 'N/A':
                    removed_entries.append(entry)
                    continue

                # Extract image key from URL
                # https://nano.seanfield.org/images/2025/12/14/abc.png → images/2025/12/14/abc.png
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(image_url)
                    image_key = parsed.path.lstrip('/')

                    # Check if image exists in R2
                    try:
                        r2._client.head_object(Bucket=r2.bucket_name, Key=image_key)
                        valid_entries.append(entry)
                    except:
                        removed_entries.append(entry)
                except:
                    removed_entries.append(entry)

            removed_count = len(removed_entries)
            kept_count = len(valid_entries)

            print(f"   Valid entries: {kept_count}")
            print(f"   Removed entries: {removed_count}")

            total_removed += removed_count
            total_kept += kept_count

            if removed_count == 0:
                print("   ✅ No changes needed")
                continue

            if dry_run:
                print("   🔍 DRY RUN - would update this file")
            else:
                # Upload updated history.json
                r2._client.put_object(
                    Bucket=r2.bucket_name,
                    Key=history_key,
                    Body=json.dumps(valid_entries, ensure_ascii=False, indent=2).encode('utf-8'),
                    ContentType="application/json"
                )
                print("   ✅ Updated history.json")

            print()

        except Exception as e:
            print(f"   ❌ Error processing {history_key}: {e}\n")
            continue

    print(f"{'='*60}")
    print("Summary:")
    print(f"  Total entries removed: {total_removed}")
    print(f"  Total entries kept:    {total_kept}")
    print(f"{'='*60}")

    if dry_run:
        print("\n🔍 DRY RUN - Run without --dry-run to apply changes")

    return True


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Delete flagged content from R2 storage",
        epilog="""
Examples:
  # Delete specific image by URL
  python scripts/delete_flagged_content.py --url "https://nano.seanfield.org/images/2025/12/14/abc123.png" --dry-run
  python scripts/delete_flagged_content.py --url "https://nano.seanfield.org/images/2025/12/14/abc123.png"

  # Delete multiple URLs
  python scripts/delete_flagged_content.py --url "https://..." --url "https://..."

  # Clean orphaned metadata for a specific date (recommended after bulk deletion)
  python scripts/delete_flagged_content.py --date 2025-12-12 --dry-run
  python scripts/delete_flagged_content.py --date 2025-12-12

  # Clean all history.json files (remove entries with missing images)
  python scripts/delete_flagged_content.py --clean-history --dry-run
  python scripts/delete_flagged_content.py --clean-history
        """
    )

    parser.add_argument(
        "--url",
        action="append",
        help="Image URL to delete (can specify multiple times)"
    )

    parser.add_argument(
        "--date",
        help="Clean orphaned metadata for this date (YYYY-MM-DD format)"
    )

    parser.add_argument(
        "--clean-history",
        action="store_true",
        help="Clean all history.json files (remove entries with missing images)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without actually deleting"
    )

    args = parser.parse_args()

    if not args.url and not args.date and not args.clean_history:
        parser.print_help()
        print("\n❌ Error: Must specify --url, --date, or --clean-history")
        sys.exit(1)

    success_count = 0

    # Delete by URL
    if args.url:
        for url in args.url:
            if delete_by_url(url, dry_run=args.dry_run):
                success_count += 1
            print()  # Blank line between operations

    # Clean orphaned metadata by date
    if args.date and delete_orphaned_metadata_by_date(args.date, dry_run=args.dry_run):
        success_count += 1

    # Clean history.json files
    if args.clean_history and clean_history_json(dry_run=args.dry_run):
        success_count += 1

    if args.dry_run:
        print("\n✅ Dry run completed")
    else:
        print("\n✅ Operation completed")


if __name__ == "__main__":
    main()
