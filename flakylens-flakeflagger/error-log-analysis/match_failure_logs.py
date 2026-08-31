"""
Matches FlakeFlagger's official failure-report archives (downloaded from
Zenodo record 5014076) against our 799-test dataset, extracts the real
exception/stack trace for each test, and buckets failures into rough
categories.

SETUP (do this first):
  1. Download failing-test-reports-<project>.tgz for all 21 projects from
     https://zenodo.org/records/5014076
  2. Put all 21 .tgz files in one folder, e.g. ~/Desktop/failure_archives/
  3. Have the official Suzanna CSV on hand too:
     flaky_flakeflagger_with_project_info_with_method_bodies.csv

USAGE:
  python3 match_failure_logs.py \
      --archives-dir ~/Desktop/failure_archives \
      --tests-csv flaky_flakeflagger_with_project_info_with_method_bodies.csv \
      --output flakeflagger_799_with_failures.csv

DESIGN NOTE: this script never extracts archive contents to disk. Some of
these archives unpack into 100,000+ tiny XML files (e.g. apache-hbase alone
is 222k files), which both exhausts disk space and, on Windows, can exceed
the 260-character MAX_PATH limit for deeply nested extracted paths. Instead,
every XML member is read directly out of the open .tgz stream in memory,
parsed, and discarded -- nothing is ever written to disk except the final
output CSV.
"""
import argparse
import csv
import glob
import os
import re
import sys
import tarfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

# Expected project slugs -- used only to sanity-check coverage at the end,
# not to gate processing (an unexpected slug is still processed normally).
EXPECTED_PROJECTS = {
    "spring-projects-spring-boot", "apache-hbase", "Alluxio-alluxio",
    "square-okhttp", "apache-ambari", "hector-client-hector",
    "activiti-activiti", "tootallnate-java-websocket", "apache-httpcore",
    "qos-ch-logback", "wildfly-wildfly", "apache-incubator-dubbo",
    "kevinsawicki-http-request", "wro4j-wro4j", "orbit-orbit",
    "undertow-io-undertow", "doanduyhai-Achilles",
    "elasticjob-elastic-job-lite", "zxing-zxing",
    "jknack-handlebars.java", "joel-costigliola-assertj-core",
}

# =============================================================================
# IMPORTANT / HONESTY NOTE ABOUT CATEGORIZATION:
# The categorize_flakylens() function below is a heuristic Claude wrote.
# It is NOT derived from FlakeFlagger's own labels, not from FlakyLens
# itself, and not verified against any ground truth. It is a best-effort
# attempt to map raw failure text onto FlakyLens's actual 5 flaky categories
# (Async Wait, Concurrency, Time, Unordered Collections, Order Dependent),
# based on how those categories are described in the FlakyLens paper. Treat
# every error_log_guessed_category value as a PROPOSED GUESS with visible reasoning,
# not a fact -- the category_reasoning column states exactly which signal
# fired so it can be audited or thrown out. The ONE rule that is a verified
# check rather than a guess is the Unordered Collections detection: it
# actually compares the sorted characters of the "expected" and "was"
# strings and only fires when they are a true anagram of each other.
#
# The raw exception_type, message, and stack_trace columns are always
# extracted verbatim from the XML -- nothing is invented, cleaned up, or
# reworded in those three columns. Categorization is kept in separate
# columns so the original evidence is never overwritten or lost.
# =============================================================================


def _normalize_for_anagram_check(s):
    """Strip everything except letters/digits and lowercase, for comparing
    if two strings contain the exact same content in a different order."""
    return "".join(ch.lower() for ch in s if ch.isalnum())


def _is_reordered_content(message):
    """
    Checks the common JUnit 'expected:<X> but was:<Y>' pattern. Returns True
    only if X and Y are a genuine anagram of each other (same characters,
    different order) -- this is a real check, not a guess.

    Requires at least MIN_ANAGRAM_LENGTH characters after normalization to
    avoid false positives on short, coincidentally-matching strings (e.g.
    "ab" vs "ba" being unrelated 2-character values rather than a real
    reordered-collection signal).
    """
    MIN_ANAGRAM_LENGTH = 12
    m = re.search(r"expected:\s*<(.*)>\s*but was:\s*<(.*)>", message, re.IGNORECASE | re.DOTALL)
    if not m:
        return False
    expected_norm = _normalize_for_anagram_check(m.group(1))
    actual_norm = _normalize_for_anagram_check(m.group(2))
    if len(expected_norm) < MIN_ANAGRAM_LENGTH or len(actual_norm) < MIN_ANAGRAM_LENGTH:
        return False
    return sorted(expected_norm) == sorted(actual_norm)


def categorize_flakylens(exception_type, message, stack_trace, test_fqn):
    """
    Attempts to map a raw failure onto one of FlakyLens's 5 real categories.
    Returns (category, reasoning) -- reasoning always states exactly which
    signal triggered the decision, so this is auditable rather than a black box.
    """
    exception_type = exception_type or ""
    message = message or ""
    stack_trace = stack_trace or ""
    test_fqn = test_fqn or ""
    combined_lower = f"{exception_type} {message} {stack_trace} {test_fqn}".lower()

    # --- Unordered Collections: VERIFIED via anagram check, not a guess ---
    if _is_reordered_content(message):
        return ("Unordered Collections",
                "verified: 'expected' and 'was' strings contain the exact same "
                "characters in a different order (checked via sorted-character comparison)")

    # --- Async Wait: keywords suggesting an async/callback/future/latch that
    # wasn't waited on long enough ---
    async_signals = ["timeoutexception", "conditiontimeout", "countdownlatch",
                      "completablefuture", "future.get", "async", "callback",
                      "did not complete within", "time limit", "executor"]
    if any(sig in combined_lower for sig in async_signals):
        hit = next(sig for sig in async_signals if sig in combined_lower)
        return ("Async Wait", f"guess: found async-related keyword '{hit}' in exception/message/test name")

    # --- Time: date/clock/calendar related, and NOT already caught by Async Wait above ---
    time_signals = ["currenttimemillis", "calendar", "simpledateformat",
                    "localdatetime", "system.nanotime", "clock.system"]
    if any(sig in combined_lower for sig in time_signals):
        hit = next(sig for sig in time_signals if sig in combined_lower)
        return ("Time", f"guess: found time/clock-related keyword '{hit}' in exception/message/test name")

    # --- Concurrency: race conditions, shared mutable state, thread interference ---
    concurrency_signals = ["concurrentmodificationexception", "interruptedexception",
                            "illegalmonitorstateexception", "deadlock",
                            "wanted but not invoked", "wanted \\d+ time", "race"]
    for sig in concurrency_signals:
        if re.search(sig, combined_lower):
            return ("Concurrency", f"guess: found concurrency-related pattern '{sig}' in exception/message")

    # --- Order Dependent: leftover state from another test, hardest to detect
    # from a single isolated failure log without cross-test context ---
    od_signals = ["already exists", "duplicate key", "duplicate entry",
                  "illegalstateexception", "unique constraint"]
    if any(sig in combined_lower for sig in od_signals):
        hit = next(sig for sig in od_signals if sig in combined_lower)
        return ("Order Dependent",
                f"low-confidence guess: found phrase '{hit}' which can indicate leftover "
                f"state from another test, but this cannot be confirmed without cross-test "
                f"execution context")

    return ("Unclear", f"no rule matched -- raw exception type was '{exception_type}'")


def build_failure_content_index(tf, needed_keys):
    """
    Single SEQUENTIAL pass through the tar stream -- reads each member once,
    in the order it physically appears in the archive, and immediately
    parses+discards any XML matching a (class_fqn, method_name) we actually
    need for this project.

    This deliberately avoids the pattern of "build an index of member
    locations, then later call tf.extractfile() on them in arbitrary order" --
    for a gzip-compressed archive, non-sequential extractfile() calls can
    force repeated re-decompression of large portions of the stream, which is
    almost certainly what caused a hang on spring-boot's 713k-member archive.
    A single forward-only pass has no such penalty.

    needed_keys: set of (class_fqn, method_name) tuples this project's test
                 list actually references -- anything else is skipped
                 without even attempting to read its content.

    Returns: index[(class_fqn, method_name)] -> list of parsed result dicts
             (each already a finished {"exception_type":..., ...} or
             {"parse_error":...} dict -- no further archive access needed)
    """
    index = defaultdict(list)
    total_xml = 0
    skipped = 0
    members_scanned = 0
    PROGRESS_INTERVAL = 25000

    for member in tf:  # sequential iteration -- never seeks backward
        members_scanned += 1
        if members_scanned % PROGRESS_INTERVAL == 0:
            print(f"    ... still working, {members_scanned} archive entries scanned so far "
                  f"({total_xml} were XML files, {len(index)} of our tests found so far)")

        if not member.isfile():
            continue
        filename = os.path.basename(member.name)
        if not filename.lower().endswith(".xml"):
            continue
        total_xml += 1

        name_part = filename[:-4]
        if "#" not in name_part:
            skipped += 1
            continue
        class_fqn, method_name = name_part.rsplit("#", 1)

        if (class_fqn, method_name) not in needed_keys:
            continue  # not one of our tests -- skip without reading content

        try:
            fileobj = tf.extractfile(member)  # cheap here: stream is already positioned right at this member
            if fileobj is None:
                index[(class_fqn, method_name)].append({"parse_error": "member has no extractable content"})
                continue
            content = fileobj.read()
        except Exception as e:
            index[(class_fqn, method_name)].append({"parse_error": f"could not read member from archive: {e}"})
            continue

        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            index[(class_fqn, method_name)].append({"parse_error": f"malformed XML: {e}"})
            continue
        except Exception as e:
            index[(class_fqn, method_name)].append({"parse_error": f"unexpected parse error: {e}"})
            continue

        found = None
        for testcase in root.iter("testcase"):
            if testcase.get("name") != method_name:
                continue
            for tag in ("failure", "error"):
                node = testcase.find(tag)
                if node is not None:
                    found = {
                        "exception_type": node.get("type", ""),
                        "message": node.get("message", "") or "",
                        "stack_trace": (node.text or "").strip(),
                        "report_type": tag,
                    }
                    break
            if found:
                break

        if found:
            index[(class_fqn, method_name)].append(found)
        # if not found: this run's XML for this member didn't show a failure
        # for this specific method (rare, but skip silently rather than
        # recording a misleading empty entry)

    return index, total_xml, skipped


def find_archive_path(archives_dir, project):
    """Find the archive for a project, tolerating case differences."""
    exact = os.path.join(archives_dir, f"failing-test-reports-{project}.tgz")
    if os.path.exists(exact):
        return exact
    candidates = glob.glob(os.path.join(archives_dir, "failing-test-reports-*.tgz"))
    target_lower = f"failing-test-reports-{project}.tgz".lower()
    for c in candidates:
        if os.path.basename(c).lower() == target_lower:
            return c
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives-dir", required=True,
                         help="Folder containing the downloaded failing-test-reports-*.tgz files")
    parser.add_argument("--tests-csv", required=True,
                         help="Suzanna's official CSV (needs 'Test' and 'project_name' columns)")
    parser.add_argument("--output", default="flakeflagger_799_with_failures.csv")
    args = parser.parse_args()

    if not os.path.isdir(args.archives_dir):
        print(f"ERROR: archives dir not found: {args.archives_dir}")
        sys.exit(1)
    if not os.path.exists(args.tests_csv):
        print(f"ERROR: tests CSV not found: {args.tests_csv}")
        sys.exit(1)

    # --- Load the 799-test list ---
    with open(args.tests_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "Test" not in reader.fieldnames or "project_name" not in reader.fieldnames:
            print(f"ERROR: expected columns 'Test' and 'project_name', found: {reader.fieldnames}")
            sys.exit(1)
        test_rows = list(reader)
    print(f"Loaded {len(test_rows)} tests from {args.tests_csv}")

    tests_by_project = defaultdict(list)
    for row in test_rows:
        tests_by_project[row["project_name"]].append(row)
    projects_needed = sorted(tests_by_project.keys())
    print(f"{len(projects_needed)} unique projects referenced in the test list")

    output_rows = []
    category_counter = Counter()
    no_archive_count = 0
    no_match_count = 0
    matched_count = 0
    archive_status = {}
    processed_projects = set()

    for project in projects_needed:
        archive_path = find_archive_path(args.archives_dir, project)
        if archive_path is None:
            archive_status[project] = "archive not downloaded"
            print(f"  [{project}] SKIPPED -- archive not found, expected: failing-test-reports-{project}.tgz")
            for row in tests_by_project[project]:
                output_rows.append({
                    "project": project, "test": row.get("Test", ""),
                    "match_status": f"no archive available ({archive_status[project]})",
                    "exception_type": "", "error_log_guessed_category": "", "category_reasoning": "", "message": "", "stack_trace": "",
                })
                no_archive_count += 1
            continue

        try:
            tf = tarfile.open(archive_path, "r:gz")
        except tarfile.ReadError as e:
            archive_status[project] = f"corrupt or unreadable archive: {e}"
            print(f"  [{project}] EXTRACTION FAILED: {archive_status[project]}")
            for row in tests_by_project[project]:
                output_rows.append({
                    "project": project, "test": row.get("Test", ""),
                    "match_status": f"archive present but unreadable ({archive_status[project]})",
                    "exception_type": "", "error_log_guessed_category": "", "category_reasoning": "", "message": "", "stack_trace": "",
                })
                no_archive_count += 1
            continue
        except Exception as e:
            archive_status[project] = f"unexpected error opening archive: {e}"
            print(f"  [{project}] EXTRACTION FAILED: {archive_status[project]}")
            for row in tests_by_project[project]:
                output_rows.append({
                    "project": project, "test": row.get("Test", ""),
                    "match_status": f"archive present but unreadable ({archive_status[project]})",
                    "exception_type": "", "error_log_guessed_category": "", "category_reasoning": "", "message": "", "stack_trace": "",
                })
                no_archive_count += 1
            continue

        try:
            # Only look for tests this project's CSV rows actually reference --
            # lets the single pass skip reading content for irrelevant XML entries.
            needed_keys = set()
            for row in tests_by_project[project]:
                t = row.get("Test", "")
                if "#" in t:
                    c, m = t.rsplit("#", 1)
                    needed_keys.add((c, m))

            index, total_xml, skipped = build_failure_content_index(tf, needed_keys)
            processed_projects.add(project)
            archive_status[project] = f"ok ({total_xml} xml members scanned, {len(index)} of our tests found, {skipped} skipped)"
            print(f"  [{project}] single sequential pass complete -- {total_xml} XML members scanned, "
                  f"{len(index)} of our tests found, 0 bytes written to disk")

            for row in tests_by_project[project]:
                test_fqn = row.get("Test", "")
                if "#" not in test_fqn:
                    output_rows.append({
                        "project": project, "test": test_fqn,
                        "match_status": "malformed test identifier (no '#')",
                        "exception_type": "", "error_log_guessed_category": "", "category_reasoning": "", "message": "", "stack_trace": "",
                    })
                    continue

                class_fqn, method_name = test_fqn.rsplit("#", 1)
                candidate_results = index.get((class_fqn, method_name), [])

                if not candidate_results:
                    no_match_count += 1
                    output_rows.append({
                        "project": project, "test": test_fqn,
                        "match_status": "no matching failure XML found for this test",
                        "exception_type": "", "error_log_guessed_category": "", "category_reasoning": "", "message": "", "stack_trace": "",
                    })
                    continue

                found = None
                parse_errors = []
                for result in candidate_results:
                    if "parse_error" in result:
                        parse_errors.append(result["parse_error"])
                        continue
                    found = result
                    break

                if found is None:
                    reason = "; ".join(parse_errors) if parse_errors else \
                        f"{len(candidate_results)} report(s) found but none contained a parsable failure block"
                    output_rows.append({
                        "project": project, "test": test_fqn,
                        "match_status": f"report(s) found but extraction failed: {reason}",
                        "exception_type": "", "error_log_guessed_category": "", "category_reasoning": "", "message": "", "stack_trace": "",
                    })
                    continue

                matched_count += 1
                category, reasoning = categorize_flakylens(
                    found["exception_type"], found["message"], found["stack_trace"], test_fqn
                )
                category_counter[category] += 1
                output_rows.append({
                    "project": project, "test": test_fqn,
                    "match_status": f"matched ({len(candidate_results)} report(s) available)",
                    "exception_type": found["exception_type"],
                    "error_log_guessed_category": category,
                    "category_reasoning": reasoning,
                    "message": found["message"],
                    "stack_trace": found["stack_trace"],
                })
        finally:
            tf.close()  # release the archive handle; nothing to clean up on disk

    # --- Write output ---
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["project", "test", "match_status",
                                                "exception_type", "error_log_guessed_category",
                                                "category_reasoning", "message", "stack_trace"])
        writer.writeheader()
        writer.writerows(output_rows)

    # --- Summary ---
    print()
    print("=" * 60)
    print(f"Total tests processed: {len(test_rows)}")
    print(f"  Matched with a real failure/exception: {matched_count}")
    print(f"  No archive available for that project: {no_archive_count}")
    print(f"  Archive present but no matching test found: {no_match_count}")
    print()
    missing_projects = EXPECTED_PROJECTS - processed_projects
    if missing_projects:
        print(f"Projects with NO usable archive ({len(missing_projects)}): {sorted(missing_projects)}")
    print()
    print("Category breakdown among matched failures:")
    for cat, count in category_counter.most_common():
        print(f"  {cat:30s} {count}")
    print()
    print(f"Full results written to: {args.output}")


if __name__ == "__main__":
    main()

