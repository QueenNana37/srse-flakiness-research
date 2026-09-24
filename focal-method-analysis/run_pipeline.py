"""
run_pipeline.py — chains Devanshi's focal_extract.py (steps 1,2,3,5)
straight into your scorer (steps 4,6), across ALL your Java test
files in one go. No manual copy-pasting JSON between the two steps.

SETUP (one-time):
  pip install javalang --break-system-packages
  (needed by focal_extract.py to parse Java files)

USAGE:
  1. Put all your test .java files in one folder, e.g. "my_tests/"
     (can have subfolders, it searches recursively)
  2. Run:
       python run_pipeline.py my_tests/ results.json
  3. Open results.json — one entry per @Test method found, with its
     focal method, score, and any ambiguous/no-candidate flags.

WHAT IT DOES UNDER THE HOOD:
  For each .java file found:
    -> calls focal_extract.main(filepath)   [Devanshi's steps 1,2,3,5]
    -> gets back a list of {test_name, test_tokens, candidates}
    -> feeds that straight into process_all()  [your steps 4,6]
    -> collects results, tagging which file each came from

If a file fails to parse (syntax error, can't find src/main, etc),
it's skipped and logged separately at the end instead of crashing
the whole run — so one bad file doesn't block your other 9 tests.
"""

import sys
import os
import json
import glob

import focal_extract
from focal_method_finder_batch import process_all


def find_java_files(target: str) -> list:
    """
    Accepts either a single .java file or a folder (searched
    recursively for *.java files).
    """
    if os.path.isfile(target):
        return [target]
    if os.path.isdir(target):
        pattern = os.path.join(target, "**", "*.java")
        return sorted(glob.glob(pattern, recursive=True))
    return []


def run_pipeline(target: str, output_path: str):
    java_files = find_java_files(target)

    if not java_files:
        print(f"No .java files found at: {target}")
        return

    print(f"Found {len(java_files)} .java file(s) to process.\n")

    all_scored_results = []
    failed_files = []

    for filepath in java_files:
        print(f"Processing: {filepath}")
        extracted = focal_extract.main(filepath)

        # focal_extract.main() returns either:
        #   - a dict with "error" key if something went wrong
        #   - a list of {test_name, test_tokens, candidates} dicts
        if isinstance(extracted, dict) and "error" in extracted:
            print(f"  SKIPPED: {extracted['error']}")
            failed_files.append({"file": filepath, "error": extracted["error"]})
            continue

        # Score every test found in this file
        scored = process_all(extracted)

        # Tag each result with which file it came from, so you can
        # trace back to the source when reviewing results.json
        for r in scored:
            r["source_file"] = filepath

        all_scored_results.extend(scored)

        for r in scored:
            flag = ""
            if r["no_candidates_found"]:
                flag = "  [NO CANDIDATES]"
            elif r["ambiguous"]:
                flag = "  [AMBIGUOUS TIE]"
            print(f"    {r['test_name']:35s} -> {r['focal_method']} (score={r['score']}){flag}")

    # Save combined results
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_scored_results, f, indent=2)

    print(f"\n{'=' * 50}")
    print(f"Done. {len(all_scored_results)} test(s) scored across {len(java_files) - len(failed_files)} file(s).")
    print(f"Results written to: {output_path}")

    if failed_files:
        print(f"\n{len(failed_files)} file(s) failed and were skipped:")
        for f_info in failed_files:
            print(f"  - {f_info['file']}: {f_info['error']}")
        print("(these are worth checking manually / flagging to Shanto)")

    # Also surface any ambiguous or no-candidate cases in one place
    # at the end, so you don't have to scroll back up to find them
    flagged = [r for r in all_scored_results if r["ambiguous"] or r["no_candidates_found"]]
    if flagged:
        print(f"\n{len(flagged)} test(s) flagged for manual review:")
        for r in flagged:
            reason = "no candidates" if r["no_candidates_found"] else "ambiguous tie"
            print(f"  - {r['test_name']} ({reason}) in {r['source_file']}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python run_pipeline.py <folder_or_file> <output.json>")
        print("Example: python run_pipeline.py my_tests/ results.json")
        sys.exit(1)

    run_pipeline(sys.argv[1], sys.argv[2])