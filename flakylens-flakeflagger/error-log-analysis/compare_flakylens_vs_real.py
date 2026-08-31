"""
Compares FlakyLens's predictions against the real error data, to answer:
"which flaky category is FlakyLens missing the most?"

INPUTS (both already exist on your machine):
  1. flakeflagger_799_consolidated.csv
     -- FlakyLens's own predictions per test (from running infer_flakeflagger.py
        across all 4 fold models). Has 'majority_category' = what FlakyLens
        thinks each test is.
  2. flakeflagger_799_with_failures_FINAL.csv
     -- The REAL error data per test (from match_failure_logs.py, which reads
        FlakeFlagger's actual archived failure logs). Has 'error_log_guessed_category'
        = my heuristic guess at what category the REAL error suggests.

WHAT THIS SCRIPT DOES, STEP BY STEP:
  Step 1: Load both CSVs.
  Step 2: Match each test between the two files. This needs a small fix --
          file #1 strips JUnit5 parameterized-test suffixes like "[0]" from
          method names, but file #2 doesn't, so we strip them here too before
          matching, or every parameterized test would fail to match.
  Step 3: Split into two groups:
          - Tests FlakyLens called "Not Flaky" (its MISSES)
          - Tests FlakyLens flagged as some flaky category (its "catches")
  Step 4: For the misses, count what the REAL error category actually was.
          This answers "what is FlakyLens missing the most?"
  Step 5: For the catches, check how often FlakyLens's predicted category
          actually matches the real error category. This checks not just
          "did it detect flakiness" but "did it get the REASON right?"

Run it yourself and compare your printed numbers against what's already in
the repo -- they should match exactly, since this is the same logic.
"""
import csv
import re
from collections import Counter

PREDICTIONS_FILE = "flakeflagger_799_consolidated.csv"
FAILURES_FILE = "flakeflagger_799_with_failures_FINAL.csv"
OUTPUT_FILE = "flakeflagger_flakylens_vs_real_comparison_VERIFY.csv"


def strip_parameterized_suffix(method_name):
    """Turns 'myTest[0]' into 'myTest' -- JUnit5 runs the same method multiple
    times with different parameters, and the two files handle this suffix
    differently, so we normalize it here before matching."""
    return re.sub(r"\[\d+\]\s*$", "", method_name).strip()


def main():
    # --- Step 1: load both files ---
    with open(PREDICTIONS_FILE, newline="", encoding="utf-8") as f:
        predictions = list(csv.DictReader(f))
    with open(FAILURES_FILE, newline="", encoding="utf-8") as f:
        failures = list(csv.DictReader(f))

    print(f"Loaded {len(predictions)} predictions and {len(failures)} failure records")

    # Build a lookup: (project, method_name) -> that test's FlakyLens prediction row
    pred_lookup = {(r["project"], r["test_name"]): r for r in predictions}

    # --- Step 2: match every test between the two files ---
    joined = []
    unmatched = []
    for r in failures:
        # 'test' in the failures file looks like "org.foo.MyTest#myMethod[0]"
        # -- we only need the method name (after the '#') to match.
        method_name = r["test"].rsplit("#", 1)[-1]
        method_name = strip_parameterized_suffix(method_name)
        key = (r["project"], method_name)

        pred = pred_lookup.get(key)
        if pred is None:
            unmatched.append(r["test"])
            continue

        joined.append({
            "project": r["project"],
            "test": r["test"],
            "flakylens_predicted": pred["majority_category"],
            "real_error_category": r["error_log_guessed_category"],
            "exception_type": r["exception_type"],
        })

    print(f"Matched {len(joined)} / {len(failures)} tests ({len(unmatched)} unmatched)")
    if unmatched:
        print("First few unmatched (should be empty or explainable):", unmatched[:5])
    print()

    # --- Step 3: split into "FlakyLens missed it" vs "FlakyLens caught it" ---
    missed = [j for j in joined if j["flakylens_predicted"] == "Not Flaky"]
    caught = [j for j in joined if j["flakylens_predicted"] != "Not Flaky"]

    # --- Step 4: what does the real data say about what FlakyLens missed? ---
    print("=" * 60)
    print(f"Tests FlakyLens called 'Not Flaky' (misses): {len(missed)} / {len(joined)}")
    print("Of those misses, what the REAL error category actually was:")
    miss_breakdown = Counter(j["real_error_category"] for j in missed)
    for cat, count in miss_breakdown.most_common():
        pct = 100 * count / len(missed)
        print(f"  {cat:24s} {count:4d}  ({pct:.1f}% of misses)")

    # --- Step 5: for tests FlakyLens DID flag, did it get the category right? ---
    print()
    print(f"Tests FlakyLens flagged as some flaky category: {len(caught)} / {len(joined)}")
    exact_match = sum(1 for j in caught if j["flakylens_predicted"] == j["real_error_category"])
    print(f"Of those, FlakyLens's predicted category matched the real one: {exact_match} / {len(caught)}")
    print()
    print("Full breakdown -- what FlakyLens predicted vs. what the real error was:")
    cross = Counter((j["flakylens_predicted"], j["real_error_category"]) for j in caught)
    for (pred, real), count in cross.most_common():
        print(f"  predicted={pred:24s} real={real:24s} count={count}")

    # --- Save the full joined data so you can inspect individual rows ---
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["project", "test", "flakylens_predicted", "real_error_category", "exception_type"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(joined)
    print()
    print(f"Full joined data written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
