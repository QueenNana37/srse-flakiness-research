"""
Static analysis of test methods: for each test, find every branch point
(if/else, loops, switch, try/catch) WITHOUT compiling or running anything.

Uses javalang, a pure-Python Java parser. This only looks INSIDE the test
method itself (it does not follow calls into other methods/classes).

for each test,it writes a separate output file listing:
  - every line number in the method
  - what kind of statement is on that line (plain, or a branch point)
  - for branch points, what the possible outcomes are

USAGE:
  python3 static_branch_analysis.py <tests_csv> <output_dir>

tests_csv needs 'Test' (or 'test') and 'test_method_code' (or 'full_code')
columns -- works directly with Suzanna's official CSV or our reformatted one.
"""
import csv
import os
import re
import sys

import javalang


def find_column(fieldnames, candidates):
    for c in candidates:
        if c in fieldnames:
            return c
    return None


def wrap_method_for_parsing(method_code):
    """
    javalang.parse.parse() needs a full compilation unit (a whole .java file),
    not a bare method. Wrapping the method in a minimal dummy class lets us
    parse it without needing the real surrounding class, imports, or project.
    """
    return f"public class __Wrapper__ {{\n{method_code}\n}}"


def analyze_method(method_code):
    """
    Parses one test method's source and walks its AST looking for branch
    points. Returns (branch_info_list, error_message_or_None).

    branch_info_list is a list of dicts, one per branch point found:
      {"line": int, "type": "if"/"for"/"while"/"switch"/"try"/"ternary",
       "possible_outcomes": [...]}
    """
    wrapped = wrap_method_for_parsing(method_code)
    try:
        tree = javalang.parse.parse(wrapped)
    except (javalang.parser.JavaSyntaxError, javalang.tokenizer.LexerError) as e:
        return None, f"could not parse: {e}"
    except Exception as e:
        return None, f"unexpected parse error: {e}"

    branches = []

    for path, node in tree.filter(javalang.tree.IfStatement):
        line = node.position.line if node.position else None
        outcomes = ["then-branch executes"]
        if node.else_statement is not None:
            outcomes.append("else-branch executes")
        else:
            outcomes.append("if-condition false, nothing in this if executes")
        branches.append({"line": line, "type": "if", "possible_outcomes": outcomes})

    for path, node in tree.filter(javalang.tree.ForStatement):
        line = node.position.line if node.position else None
        branches.append({"line": line, "type": "for",
                          "possible_outcomes": ["loop body runs 0 times", "loop body runs 1+ times"]})

    for path, node in tree.filter(javalang.tree.WhileStatement):
        line = node.position.line if node.position else None
        branches.append({"line": line, "type": "while",
                          "possible_outcomes": ["loop body runs 0 times", "loop body runs 1+ times"]})

    for path, node in tree.filter(javalang.tree.DoStatement):
        line = node.position.line if node.position else None
        branches.append({"line": line, "type": "do-while",
                          "possible_outcomes": ["loop body runs at least once (always)"]})

    for path, node in tree.filter(javalang.tree.SwitchStatement):
        line = node.position.line if node.position else None
        case_labels = []
        for case in node.cases:
            if case.case:
                case_labels.append(str(case.case))
            else:
                case_labels.append("default")
        branches.append({"line": line, "type": "switch",
                          "possible_outcomes": [f"case: {c}" for c in case_labels]})

    for path, node in tree.filter(javalang.tree.TryStatement):
        line = node.position.line if node.position else None
        outcomes = ["try-block completes normally"]
        for catch in (node.catches or []):
            caught_types = "/".join(t for t in catch.parameter.types) if catch.parameter else "?"
            outcomes.append(f"catch triggered: {caught_types}")
        if node.finally_block:
            outcomes.append("finally-block always runs")
        branches.append({"line": line, "type": "try", "possible_outcomes": outcomes})

    for path, node in tree.filter(javalang.tree.TernaryExpression):
        line = node.position.line if node.position else None
        branches.append({"line": line, "type": "ternary",
                          "possible_outcomes": ["true-expression used", "false-expression used"]})

    return branches, None


def safe_filename(test_id):
    """Turns 'org.foo.Test#method' into a safe filename."""
    return re.sub(r"[^\w#.\-]", "_", test_id) + ".txt"


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 static_branch_analysis.py <tests_csv> <output_dir>")
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
        if not project_col:
            print(f"WARNING: no project column found -- all files will go in one flat folder")
        rows = list(reader)

    print(f"Loaded {len(rows)} tests from {tests_csv}")
    print(f"Using '{test_col}' as test identifier, '{code_col}' as source code"
          + (f", '{project_col}' as project" if project_col else ""))

    ok_count = 0
    fail_count = 0

    for row in rows:
        test_id = row[test_col]
        code = row[code_col]
        project = row[project_col] if project_col else ""

        branches, error = analyze_method(code)
        filename = safe_filename(test_id)

        # Put each test's file inside a subfolder named after its project
        project_dir = os.path.join(output_dir, project) if project else output_dir
        os.makedirs(project_dir, exist_ok=True)
        filepath = os.path.join(project_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Test: {test_id}\n")
            if error:
                f.write(f"STATUS: FAILED TO PARSE -- {error}\n")
                fail_count += 1
            else:
                f.write(f"STATUS: parsed successfully\n")
                f.write(f"Branch points found: {len(branches)}\n\n")
                if not branches:
                    f.write("(no branches -- this test has a single straight-line execution path)\n")
                for b in branches:
                    f.write(f"Line {b['line']}: {b['type']} statement\n")
                    for outcome in b["possible_outcomes"]:
                        f.write(f"    -> {outcome}\n")
                ok_count += 1

    print()
    print(f"Done. {ok_count} parsed successfully, {fail_count} failed to parse.")
    print(f"One file per test written to: {output_dir}")


if __name__ == "__main__":
    main()
