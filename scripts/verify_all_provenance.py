#!/usr/bin/env python3
"""
Verify provenance signatures for all helpers.

This script checks that all helpers have valid provenance signatures
and reports any that fail verification.

Usage:
    python scripts/verify_all_provenance.py

Options:
    --verbose    Show detailed verification info for each helper
    --json       Output results as JSON
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(
        description="Verify provenance signatures for all helpers"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed verification info"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    if not args.json:
        print("Verifying provenance for all helpers...")
        print("=" * 50)

    try:
        from bridge.provenance import verify_helper_provenance
        from helpers.sdk import helper_registry
    except ImportError as e:
        if args.json:
            print(json.dumps({"error": f"Import failed: {e}"}))
        else:
            print(f"ERROR: Failed to import required modules: {e}")
        return 1

    helpers_dir = project_root / "helpers"

    try:
        validation_summary = helper_registry.get_validation_summary()
        helpers = validation_summary.get("helpers", {})
    except Exception as e:
        if args.json:
            print(json.dumps({"error": f"Registry failed: {e}"}))
        else:
            print(f"ERROR: Failed to get helper registry: {e}")
        return 1

    results = {
        "valid": [],
        "invalid": [],
        "missing": [],
        "errors": []
    }

    for helper_id in sorted(helpers.keys()):
        helper_dir = helpers_dir / helper_id
        provenance_file = helper_dir / "provenance.json"

        if not helper_dir.exists():
            results["missing"].append({
                "helper_id": helper_id,
                "reason": "directory_not_found"
            })
            if not args.json:
                print(f"  MISSING: {helper_id} (directory not found)")
            continue

        if not provenance_file.exists():
            results["missing"].append({
                "helper_id": helper_id,
                "reason": "provenance_file_not_found"
            })
            if not args.json:
                print(f"  MISSING: {helper_id} (no provenance.json)")
            continue

        try:
            is_valid, reason, details = verify_helper_provenance(helper_id, helper_dir)

            if is_valid:
                results["valid"].append({
                    "helper_id": helper_id,
                    "digest": details.get("digest", "")[:16] + "..." if details.get("digest") else "N/A"
                })
                if not args.json:
                    if args.verbose:
                        print(f"  VALID: {helper_id}")
                        print(f"         Digest: {details.get('digest', 'N/A')[:16]}...")
                    else:
                        print(f"  VALID: {helper_id}")
            else:
                results["invalid"].append({
                    "helper_id": helper_id,
                    "reason": reason
                })
                if not args.json:
                    print(f"  INVALID: {helper_id} - {reason}")

        except Exception as e:
            results["errors"].append({
                "helper_id": helper_id,
                "error": str(e)
            })
            if not args.json:
                print(f"  ERROR: {helper_id} - {str(e)}")

    # Summary
    summary = {
        "total": len(helpers),
        "valid": len(results["valid"]),
        "invalid": len(results["invalid"]),
        "missing": len(results["missing"]),
        "errors": len(results["errors"])
    }

    if args.json:
        output = {
            "summary": summary,
            "results": results
        }
        print(json.dumps(output, indent=2))
    else:
        print()
        print("=" * 50)
        print(f"Summary: {summary['valid']}/{summary['total']} valid")
        print(f"  Valid: {summary['valid']}")
        print(f"  Invalid: {summary['invalid']}")
        print(f"  Missing: {summary['missing']}")
        print(f"  Errors: {summary['errors']}")

        if summary["invalid"] > 0 or summary["errors"] > 0:
            print("\nWARNING: Some helpers have invalid or missing provenance.")
            print("Run 'python scripts/resign_all_helpers.py' to fix.")
            return 1

    return 0 if summary["invalid"] == 0 and summary["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
