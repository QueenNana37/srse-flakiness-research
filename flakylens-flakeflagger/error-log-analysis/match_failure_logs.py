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

# Coarse category buckets, keyed by substring match against the exception
# class name (case-insensitive). Order matters -- first match wins.
CATEGORY_RULES = [
    ("Timeout / Async Wait", ["timeout", "timeoutexception", "sockettimeout"]),
    ("Connection / Network", ["connectexception", "connection", "sockettimeout",
                              "unknownhostexception", "ioexception", "eofexception"]),
    ("Concurrency", ["interruptedexception", "concurrentmodification",
                     "illegalmonitorstate", "timeoutexception"]),
    ("Null Pointer", ["nullpointerexception"]),
    ("Assertion Failure", ["assertionerror", "comparisonfailure", "assertionfailederror"]),
    ("Ordering / State", ["illegalstateexception", "indexoutofbounds",
                          "concurrentmodificationexception"]),
    ("File / Resource", ["filenotfound", "noSuch file", "resourcenotfound"]),
]


def categorize_exception(exception_type):
    if not exception_type:
        return "Unknown (no exception type captured)"
    lowered = exception_type.lower()
    for category, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw in lowered:
                return category
    return f"Other ({exception_type.rsplit('.', 1)[-1]})"


def build_failure_index(tf):
    """
    Given an OPEN tarfile object, build an index of every XML member whose
    filename matches the 'ClassName#method.xml' convention, WITHOUT
    extracting anything to disk.

    Returns: index[(class_fqn, method_name)] -> list of TarInfo members
    """
    index = defaultdict(list)
    total_xml = 0
    skipped = 0
    for member in tf.getmembers():
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
        index[(class_fqn, method_name)].append(member)
    return index, total_xml, skipped


def parse_failure_from_member(tf, member, method_name):
    """
    Read a tar member's content directly into memory (never touching disk)
    and pull out the <failure>/<error> block for the given method_name.
    Returns a dict, or None if this run's XML didn't show a failure for
    this specific test, or {"parse_error": ...} if the XML was unreadable.
    """
    try:
        fileobj = tf.extractfile(member)
        if fileobj is None:
            return {"parse_error": "member has no extractable content (e.g. a directory or symlink)"}
        content = fileobj.read()
    except Exception as e:
        return {"parse_error": f"could not read member from archive: {e}"}

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        return {"parse_error": f"malformed XML: {e}"}
    except Exception as e:
        return {"parse_error": f"unexpected parse error: {e}"}

    for testcase in root.iter("testcase"):
        if testcase.get("name") != method_name:
            continue
        for tag in ("failure", "error"):
            node = testcase.find(tag)
            if node is not None:
                return {
                    "exception_type": node.get("type", ""),
                    "message": (node.get("message", "") or "")[:500],
                    "stack_trace_snippet": (node.text or "").strip()[:500],
                    "report_type": tag,
                }
    return None  # this specific run's XML didn't show this test failing


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
                    "exception_type": "", "category": "", "message": "",
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
                    "exception_type": "", "category": "", "message": "",
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
                    "exception_type": "", "category": "", "message": "",
                })
                no_archive_count += 1
            continue

        try:
            index, total_xml, skipped = build_failure_index(tf)
            processed_projects.add(project)
            archive_status[project] = f"ok ({total_xml} xml members, {len(index)} unique test keys, {skipped} skipped)"
            print(f"  [{project}] indexed in-memory -- {total_xml} XML members, {len(index)} unique tests, 0 bytes written to disk")

            for row in tests_by_project[project]:
                test_fqn = row.get("Test", "")
                if "#" not in test_fqn:
                    output_rows.append({
                        "project": project, "test": test_fqn,
                        "match_status": "malformed test identifier (no '#')",
                        "exception_type": "", "category": "", "message": "",
                    })
                    continue

                class_fqn, method_name = test_fqn.rsplit("#", 1)
                candidate_members = index.get((class_fqn, method_name), [])

                if not candidate_members:
                    no_match_count += 1
                    output_rows.append({
                        "project": project, "test": test_fqn,
                        "match_status": "no matching failure XML found for this test",
                        "exception_type": "", "category": "", "message": "",
                    })
                    continue

                found = None
                parse_errors = []
                for member in candidate_members:
                    result = parse_failure_from_member(tf, member, method_name)
                    if result is None:
                        continue
                    if "parse_error" in result:
                        parse_errors.append(result["parse_error"])
                        continue
                    found = result
                    break

                if found is None:
                    reason = "; ".join(parse_errors) if parse_errors else \
                        f"{len(candidate_members)} report(s) found but none contained a parsable failure block"
                    output_rows.append({
                        "project": project, "test": test_fqn,
                        "match_status": f"report(s) found but extraction failed: {reason}",
                        "exception_type": "", "category": "", "message": "",
                    })
                    continue

                matched_count += 1
                category = categorize_exception(found["exception_type"])
                category_counter[category] += 1
                output_rows.append({
                    "project": project, "test": test_fqn,
                    "match_status": f"matched ({len(candidate_members)} report(s) available)",
                    "exception_type": found["exception_type"],
                    "category": category,
                    "message": found["message"],
                })
        finally:
            tf.close()  # release the archive handle; nothing to clean up on disk

    # --- Write output ---
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["project", "test", "match_status",
                                                "exception_type", "category", "message"])
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

