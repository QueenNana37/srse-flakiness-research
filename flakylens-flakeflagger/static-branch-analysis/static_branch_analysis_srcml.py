"""
Static branch analysis using srcML: for each test, finds every branch point
(if/for/while/switch/try), the exact source code of each, and every method
call, including which branch (if any) each call happens inside.

VERIFICATION STATUS, being precise about what's confirmed vs. inferred:
  - Branch detection (if/for/while) + exact code extraction: CONFIRMED
    against real srcml output on 3 real tests, matched hand-checked source.
  - Method call extraction (<call>/<name> parsing): CONFIRMED against real
    srcml output for a qualified call (foo.bar()).
  - Call-to-branch containment matching (which call is inside which branch):
    NOT yet tested against a single real combined example. The logic below
    was checked against a hand-built XML combining the two already-verified
    patterns above, not a single real srcml run covering both at once.
    Recommend testing this specific part again before trusting it fully.
  - A call with a plain, non-dotted name (e.g. baz(), not foo.bar()) is
    assumed to use a simpler <name>baz</name> structure with no nesting.
    This is inferred from the dotted case, not independently confirmed.

SETUP:
  You need the srcml command-line tool installed (not pip installable).
  Download it from https://www.srcml.org/ -- there's a Windows installer.
  Confirm it works with: srcml --version

USAGE:
  python3 static_branch_analysis_srcml.py <tests_csv> <output_dir>
"""
import csv
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter

SRC_NS = "{http://www.srcML.org/srcML/src}"
POS_NS = "{http://www.srcML.org/srcML/position}"

# NOTE: the exact tag name for ternary expressions in srcML is unconfirmed --
# if ternaries don't show up in your real output, this is the first thing to check.
BRANCH_TAGS = {
    f"{SRC_NS}if": "if",
    f"{SRC_NS}for": "for",
    f"{SRC_NS}while": "while",
    f"{SRC_NS}do": "do-while",
    f"{SRC_NS}switch": "switch",
    f"{SRC_NS}try": "try",
    f"{SRC_NS}ternary": "ternary",
}


def find_column(fieldnames, candidates):
    for c in candidates:
        if c in fieldnames:
            return c
    return None


def wrap_method_for_parsing(method_code):
    """srcML needs a full compilation unit, so we wrap the bare method in a
    minimal dummy class. This adds exactly 1 line before the method's own
    text starts, which we correct for below when reporting line numbers."""
    return f"public class __Wrapper__ {{\n{method_code}\n}}"


def run_srcml(wrapped_code):
    """Calls the srcml command-line tool. Writes the code to a temp file and
    points srcml at that file -- piping via stdin was confirmed to silently
    fail (srcml received empty input) when tested from Git Bash on Windows.
    Returns (xml_string, error_or_None)."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False, encoding="utf-8") as tmp:
            tmp.write(wrapped_code)
            tmp_path = tmp.name

        result = subprocess.run(
            ["srcml", "--language=Java", "--position", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return None, "srcml command not found -- is it installed and on your PATH?"
    except subprocess.TimeoutExpired:
        return None, "srcml took too long (over 30s) on this input"
    except Exception as e:
        return None, f"unexpected error running srcml: {e}"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    if result.returncode != 0:
        return None, f"srcml exited with an error: {result.stderr[:300]}"
    return result.stdout, None


def parse_position(pos_str):
    """srcML position attributes look like 'line:column'. Returns (line, col)
    as integers, or None if the format doesn't match what's expected."""
    if not pos_str:
        return None
    m = re.match(r"(\d+):(\d+)", pos_str)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def extract_text(wrapped_lines, start_pos, end_pos):
    """Slices the exact original text between two (line, col) positions."""
    start_line, start_col = start_pos
    end_line, end_col = end_pos
    if start_line == end_line:
        return wrapped_lines[start_line - 1][start_col - 1:end_col]
    first_line = wrapped_lines[start_line - 1][start_col - 1:]
    middle_lines = wrapped_lines[start_line:end_line - 1]
    last_line = wrapped_lines[end_line - 1][:end_col]
    return "\n".join([first_line] + middle_lines + [last_line])


def find_innermost_branch(call_start_pos, branches):
    """Given a call's position, finds which branch (if any) it falls inside.
    If nested inside multiple branches (e.g. an if inside a while), returns
    the most specific (smallest-span) one. Returns None if the call isn't
    inside any branch."""
    containing = [
        b for b in branches
        if b["start_pos"] <= call_start_pos <= b["end_pos"]
    ]
    if not containing:
        return None
    # Smallest span = most specific/innermost. Compare by line-span first,
    # then column-span as a tiebreaker.
    def span(b):
        line_span = b["end_pos"][0] - b["start_pos"][0]
        col_span = b["end_pos"][1] - b["start_pos"][1]
        return (line_span, col_span)
    return min(containing, key=span)


def analyze_method(method_code):
    """
    Returns (branches, calls, error_message_or_None).

    branches: list of dicts with line, type, exact_code, start_pos, end_pos
              (positions are raw wrapped-file coordinates, used internally
              for containment matching -- 'line' is already corrected to
              match the original method_code's own line numbering)

    calls: list of dicts with name, line (corrected), branch (the branch
           dict it's inside, or None if unconditional)
    """
    wrapped = wrap_method_for_parsing(method_code)
    wrapped_lines = wrapped.split("\n")

    xml_output, error = run_srcml(wrapped)
    if error:
        return None, None, error

    try:
        root = ET.fromstring(xml_output)
    except ET.ParseError as e:
        return None, None, f"could not parse srcML's XML output: {e}"

    # --- Pass 1: find every branch ---
    branches = []
    for elem in root.iter():
        if elem.tag not in BRANCH_TAGS:
            continue

        start_pos = parse_position(elem.get(f"{POS_NS}start"))
        end_pos = parse_position(elem.get(f"{POS_NS}end"))
        if not start_pos or not end_pos:
            continue

        exact_text = extract_text(wrapped_lines, start_pos, end_pos)

        branches.append({
            "line": start_pos[0] - 1,  # corrected for the wrapper's extra line
            "type": BRANCH_TAGS[elem.tag],
            "exact_code": exact_text,
            "start_pos": start_pos,   # kept raw, for containment matching
            "end_pos": end_pos,       # kept raw, for containment matching
        })

    # --- Pass 2: find every call, and which branch (if any) it's inside ---
    calls = []
    for elem in root.iter(f"{SRC_NS}call"):
        name_elem = elem.find(f"{SRC_NS}name")
        if name_elem is None:
            continue
        full_name = "".join(name_elem.itertext())

        start_pos = parse_position(elem.get(f"{POS_NS}start"))
        if not start_pos:
            continue

        containing_branch = find_innermost_branch(start_pos, branches)

        calls.append({
            "name": full_name,
            "line": start_pos[0] - 1,  # corrected, same as branches
            "branch": containing_branch,
        })

    return branches, calls, None


def safe_filename(test_id):
    return re.sub(r"[^\w#.\-]", "_", test_id) + ".txt"


def write_output(filepath, test_id, branches, calls, error):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Test: {test_id}\n")

        if error:
            f.write(f"STATUS: FAILED -- {error}\n")
            return

        f.write("STATUS: parsed successfully\n")

        unique_call_names = {c["name"] for c in calls}
        f.write(f"Summary: {len(branches)} branch point(s), {len(calls)} method call(s), "
                f"{len(unique_call_names)} unique method(s) called\n\n")

        if not branches:
            f.write("(no branches -- single straight-line execution path)\n\n")

        # Group calls by which branch they belong to (None = unconditional)
        calls_by_branch_id = {}
        unconditional_calls = []
        for c in calls:
            if c["branch"] is None:
                unconditional_calls.append(c)
            else:
                key = id(c["branch"])
                calls_by_branch_id.setdefault(key, []).append(c)

        for b in branches:
            f.write(f"--- Line {b['line']}: {b['type']} ---\n")
            f.write(f"{b['exact_code']}\n")

            branch_calls = calls_by_branch_id.get(id(b), [])
            if branch_calls:
                call_counts = Counter(c["name"] for c in branch_calls)
                call_lines = {}
                for c in branch_calls:
                    call_lines.setdefault(c["name"], []).append(c["line"])
                f.write("  Calls inside this branch:\n")
                for name, count in sorted(call_counts.items(), key=lambda x: -x[1]):
                    lines_str = ", ".join(str(l) for l in call_lines[name])
                    f.write(f"    {name}: called {count}x (line(s): {lines_str})\n")
            f.write("\n")

        if unconditional_calls:
            f.write("Calls NOT inside any branch (always run):\n")
            call_counts = Counter(c["name"] for c in unconditional_calls)
            call_lines = {}
            for c in unconditional_calls:
                call_lines.setdefault(c["name"], []).append(c["line"])
            for name, count in sorted(call_counts.items(), key=lambda x: -x[1]):
                lines_str = ", ".join(str(l) for l in call_lines[name])
                f.write(f"  {name}: called {count}x (line(s): {lines_str})\n")


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 static_branch_analysis_srcml.py <tests_csv> <output_dir>")
        sys.exit(1)

    tests_csv, output_dir = sys.argv[1], sys.argv[2]
    os.makedirs(output_dir, exist_ok=True)

    with open(tests_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        test_col = find_column(reader.fieldnames, ["Test", "test"])
        code_col = find_column(reader.fieldnames, ["test_method_code", "full_code"])
        project_col = find_column(reader.fieldnames, ["project_name", "project"])
        if not test_col or not code_col:
            print(f"ERROR: could not find test/code columns. Found: {reader.fieldnames}")
            sys.exit(1)
        rows = list(reader)

    print(f"Loaded {len(rows)} tests from {tests_csv}")

    ok_count = 0
    fail_count = 0

    for row in rows:
        test_id = row[test_col]
        code = row[code_col]
        project = row[project_col] if project_col else ""

        branches, calls, error = analyze_method(code)

        filename = safe_filename(test_id)
        project_dir = os.path.join(output_dir, project) if project else output_dir
        os.makedirs(project_dir, exist_ok=True)
        filepath = os.path.join(project_dir, filename)

        write_output(filepath, test_id, branches or [], calls or [], error)

        if error:
            fail_count += 1
        else:
            ok_count += 1

    print(f"\nDone. {ok_count} succeeded, {fail_count} failed.")
    print(f"Output written to: {output_dir}")


if __name__ == "__main__":
    main()
