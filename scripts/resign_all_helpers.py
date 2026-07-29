#!/usr/bin/env python3
"""
Re-sign all helpers with the current provenance key.

This script should be run after rotating the provenance key to ensure
all helpers have valid provenance signatures with the new key.

Usage:
    python scripts/resign_all_helpers.py

Options:
    --dry-run    Show what would be signed without making changes
    --verbose    Show detailed output for each helper
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(
        description="Re-sign all helpers with current provenance key"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be signed without making changes"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output for each helper"
    )

    args = parser.parse_args()

    print("Re-signing all helpers with current provenance key...")
    print("=" * 50)

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made\n")

    try:
        from bridge.provenance import generate_and_save_provenance
        from helpers.sdk import helper_registry
    except ImportError as e:
        print(f"ERROR: Failed to import required modules: {e}")
        print("Make sure you're running from the project root directory.")
        return 1

    helpers_dir = project_root / "helpers"

    try:
        validation_summary = helper_registry.get_validation_summary()
        helpers = validation_summary.get("helpers", {})
    except Exception as e:
        print(f"ERROR: Failed to get helper registry: {e}")
        return 1

    if not helpers:
        print("No helpers found in registry.")
        return 0

    success_count = 0
    error_count = 0
    skip_count = 0

    for helper_id in sorted(helpers.keys()):
        helper_dir = helpers_dir / helper_id

        if not helper_dir.exists():
            print(f"  SKIP: {helper_id} (directory not found)")
            skip_count += 1
            continue

        if args.dry_run:
            print(f"  WOULD SIGN: {helper_id}")
            success_count += 1
            continue

        try:
            ok, reason, provenance_data = generate_and_save_provenance(
                helper_id, helper_dir, "key_rotation"
            )

            if ok:
                if args.verbose:
                    print(f"  OK: {helper_id}")
                    print(f"      Digest: {provenance_data.get('digest', 'N/A')[:16]}...")
                else:
                    print(f"  OK: {helper_id}")
                success_count += 1
            else:
                print(f"  ERROR: {helper_id} - {reason}")
                error_count += 1

        except Exception as e:
            print(f"  ERROR: {helper_id} - {str(e)}")
            error_count += 1

    print()
    print("=" * 50)
    print(f"Summary: {success_count} succeeded, {error_count} failed, {skip_count} skipped")

    if error_count > 0:
        print("\nWARNING: Some helpers failed to sign. Check errors above.")
        return 1

    print("\nAll helpers re-signed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
