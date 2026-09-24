"""
Focal Method Finder — Steps 4 & 6 (Hana)

This module takes:
  - a test method's tokenized name (list of words)
  - a set of candidate methods, each with their own tokenized name

...and returns the candidate that is most likely the "focal method"
(the method actually under test), using Jaccard similarity.

Once Devanshi's part (steps 1, 2, 3, 5) is done, her output becomes
the `test_tokens` and `candidates` input to find_focal_method() below.
For now, this uses made-up mock data so the logic can be built and
tested independently.
"""

from typing import Dict, List, Tuple, Optional


def jaccard_similarity(set1: set, set2: set) -> float:
    """
    Jaccard similarity = (shared words) / (total unique words combined).
    Returns a float between 0 and 1. 0 if both sets are empty.
    """
    if not set1 and not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union else 0.0


def find_focal_method(
    test_tokens: List[str],
    candidates: Dict[str, List[str]],
) -> Tuple[Optional[str], float]:
    """
    Step 4 (compute similarity) + Step 6 (select focal method).

    Args:
        test_tokens: tokenized name of the test method,
                      e.g. ["test", "get", "from", "map"]
        candidates: dict mapping candidate method name -> its tokens,
                      e.g. {"getFromMap": ["get", "from", "map"], ...}

    Returns:
        (best_method_name, best_score)
        best_method_name is None if there are no candidates at all.
    """
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
    """
    Same as find_focal_method, but returns ALL candidates ranked by
    score (highest first) instead of just the winner. Useful for
    debugging, or for spotting close ties/ambiguous cases to flag
    for Shanto (per his note: log cases where it's hard to tell).
    """
    test_set = set(test_tokens)
    scored = [
        (name, jaccard_similarity(test_set, set(tokens)))
        for name, tokens in candidates.items()
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


# ---------------------------------------------------------------------
# Mock data + manual test run
# ---------------------------------------------------------------------
if __name__ == "__main__":
    # Pretend this came from Devanshi's steps 1-3-5 output:
    # test method: testGetFromMap
    mock_test_tokens = ["test", "get", "from", "map"]

    mock_candidates = {
        "getFromMap": ["get", "from", "map"],
        "createMap": ["create", "map"],
        "setUp": ["set", "up"],
        "putIntoMap": ["put", "into", "map"],
    }

    print("=== Single best match ===")
    best_name, best_score = find_focal_method(mock_test_tokens, mock_candidates)
    print(f"Focal method: {best_name}  (score={best_score:.3f})")

    print("\n=== Full ranking (for debugging / ambiguous cases) ===")
    for name, score in find_focal_method_ranked(mock_test_tokens, mock_candidates):
        print(f"  {name:15s} -> {score:.3f}")

    print("\n=== Edge case: no candidates ===")
    empty_result = find_focal_method(mock_test_tokens, {})
    print(f"Result: {empty_result}")

    print("\n=== Edge case: tie between two candidates ===")
    tie_candidates = {
        "getFromMap": ["get", "from", "map"],
        "mapFromGet": ["map", "from", "get"],  # same tokens, different order
    }
    tie_result = find_focal_method_ranked(mock_test_tokens, tie_candidates)
    print(tie_result)