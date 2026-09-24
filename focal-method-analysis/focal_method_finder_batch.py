"""
Focal Method Finder — Steps 4 & 6, file-based version

Same logic as focal_method_finder.py, but instead of hardcoded mock
data, this reads input from a JSON file (whatever format Devanshi's
steps 1-3-5 output ends up being, once you two agree on it) and
writes results to an output JSON file.

Expected input JSON format (one entry per flaky test):

[
  {
    "test_name": "testGetFromMap",
    "test_tokens": ["test", "get", "from", "map"],
    "candidates": {
      "getFromMap": ["get", "from", "map"],
      "createMap": ["create", "map"],
      "setUp": ["set", "up"]
    }
  },
  {
    "test_name": "...",
    "test_tokens": [...],
    "candidates": {...}
  }
]

If Devanshi's actual format is different (e.g. she gives raw method
names instead of pre-tokenized lists), just adjust `load_input()`
below — everything else stays the same.

Output JSON format:

[
  {
    "test_name": "testGetFromMap",
    "focal_method": "getFromMap",
    "score": 0.75,
    "ranked_candidates": [["getFromMap", 0.75], ["createMap", 0.2], ...]
  },
  ...
]
"""

import json
import sys
from typing import Dict, List, Tuple, Optional


def jaccard_similarity(set1: set, set2: set) -> float:
    if not set1 and not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union else 0.0


def find_focal_method(
    test_tokens: List[str],
    candidates: Dict[str, List[str]],
) -> Tuple[Optional[str], float]:
    if not candidates:
        return None, 0.0

    test_set = set(test_tokens)
    best_method = None
    best_score = -1.0

    for method_name, tokens in candidates.items():
        score = jaccard_similarity(test_set, set(tokens))
        if score > best_score:
            best_score = score
            best_method = method_name

    return best_method, best_score


def find_focal_method_ranked(
    test_tokens: List[str],
    candidates: Dict[str, List[str]],
) -> List[Tuple[str, float]]:
    test_set = set(test_tokens)
    scored = [
        (name, jaccard_similarity(test_set, set(tokens)))
        for name, tokens in candidates.items()
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def load_input(path: str) -> List[dict]:
    """Load the list of test entries from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def process_all(entries: List[dict]) -> List[dict]:
    """Run focal method detection on every entry, return results list."""
    results = []
    for entry in entries:
        test_name = entry.get("test_name", "UNKNOWN")
        test_tokens = entry.get("test_tokens", [])
        candidates = entry.get("candidates", {})

        ranked = find_focal_method_ranked(test_tokens, candidates)
        best_method, best_score = (ranked[0] if ranked else (None, 0.0))

        # Flag ambiguous cases (per Shanto's note: log where it's hard
        # to tell) — here, "ambiguous" means top two scores are tied
        # or very close (within 0.01).
        is_ambiguous = (
            len(ranked) >= 2 and abs(ranked[0][1] - ranked[1][1]) < 0.01
        )

        results.append({
            "test_name": test_name,
            "focal_method": best_method,
            "score": round(best_score, 3),
            "ranked_candidates": [[n, round(s, 3)] for n, s in ranked],
            "ambiguous": is_ambiguous,
            "no_candidates_found": len(candidates) == 0,
        })
    return results


def save_output(results: List[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


def main():
    # Usage: python focal_method_finder_batch.py input.json output.json
    if len(sys.argv) != 3:
        print("Usage: python focal_method_finder_batch.py <input.json> <output.json>")
        print("Running with built-in mock data instead...\n")
        entries = MOCK_ENTRIES
        output_path = "mock_output.json"
    else:
        entries = load_input(sys.argv[1])
        output_path = sys.argv[2]

    results = process_all(entries)
    save_output(results, output_path)

    print(f"Processed {len(results)} test(s). Results written to {output_path}\n")
    for r in results:
        flag = ""
        if r["no_candidates_found"]:
            flag = "  [NO CANDIDATES - flag for Shanto]"
        elif r["ambiguous"]:
            flag = "  [AMBIGUOUS TIE - flag for Shanto]"
        print(f"  {r['test_name']:20s} -> {r['focal_method']} (score={r['score']}){flag}")


# Mock data used only when no input file is given, so you can still
# sanity-check the script standalone.
MOCK_ENTRIES = [
    {
        "test_name": "testGetFromMap",
        "test_tokens": ["test", "get", "from", "map"],
        "candidates": {
            "getFromMap": ["get", "from", "map"],
            "createMap": ["create", "map"],
            "setUp": ["set", "up"],
            "putIntoMap": ["put", "into", "map"],
        },
    },
    {
        "test_name": "testValidateInput",
        "test_tokens": ["test", "validate", "input"],
        "candidates": {},  # simulates a test with no clear candidates found
    },
]


if __name__ == "__main__":
    main()