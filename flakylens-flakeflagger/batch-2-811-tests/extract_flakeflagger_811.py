import csv
import os
import re
import subprocess
from collections import defaultdict

INPUT_CSV = "/mnt/user-data/uploads/flaky_flakeflagger_with_project_info.csv"
REPOS_DIR = "/home/claude/repos"
OUTPUT_CSV = "/home/claude/flakeflagger_811_extracted.csv"

METHOD_PATTERN_TEMPLATE = (
    r'((?:@\w+(?:\([^)]*\))?\s*\n\s*)*'
    r'(?:public|protected|private)?\s*(?:static\s+)?'
    r'(?:void|\w[\w<>\[\],\s]*)\s+{name}\s*\([^)]*\)\s*'
    r'(?:throws\s+[\w,\s]+)?\s*\{{)'
)


def run(cmd, cwd=None, timeout=300):
    try:
        result = subprocess.run(
            cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"


def clone_at_sha(project, url, sha, repos_dir):
    repo_dir = os.path.join(repos_dir, project)
    if os.path.exists(repo_dir) and os.listdir(repo_dir):
        return repo_dir, True, "already cloned"
    os.makedirs(repo_dir, exist_ok=True)

    # Try 1: direct git fetch (works for full 40-char SHAs)
    run("git init -q", cwd=repo_dir)
    run(f"git remote add origin {url}", cwd=repo_dir)
    rc, out, err = run(f"git fetch --depth 1 origin {sha}", cwd=repo_dir, timeout=300)
    if rc == 0:
        rc2, out2, err2 = run("git checkout FETCH_HEAD", cwd=repo_dir, timeout=120)
        if rc2 == 0:
            return repo_dir, True, "cloned (git fetch)"

    # Try 2: codeload tarball (resolves short SHAs without needing GitHub API)
    owner_repo = url.rstrip("/").replace("https://github.com/", "")
    tarball_url = f"https://codeload.github.com/{owner_repo}/tar.gz/{sha}"
    tar_path = os.path.join(repos_dir, f"{project}.tar.gz")
    rc, out, err = run(f'curl -sL -f -o "{tar_path}" "{tarball_url}"', timeout=300)
    if rc != 0 or not os.path.exists(tar_path) or os.path.getsize(tar_path) < 1000:
        return repo_dir, False, f"tarball download failed: {err[:200]}"
    rc, out, err = run(f'tar -xzf "{tar_path}" -C "{repo_dir}" --strip-components=1', timeout=300)
    os.remove(tar_path)
    if rc != 0:
        return repo_dir, False, f"tarball extract failed: {err[:200]}"
    return repo_dir, True, "cloned (tarball)"


def find_java_files(repo_dir, simple_class_name):
    rc, out, err = run(
        f'find . -name "{simple_class_name}.java" -not -path "./.git/*"',
        cwd=repo_dir,
        timeout=30,
    )
    if rc != 0 or not out.strip():
        return []
    return [os.path.join(repo_dir, c) for c in out.strip().split("\n") if c]


def extract_method(filepath, method_name):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return None, f"read error: {e}"

    pattern = re.compile(METHOD_PATTERN_TEMPLATE.format(name=re.escape(method_name)))
    match = pattern.search(content)
    if not match:
        return None, "method signature not found"

    start = match.start()
    try:
        brace_start = content.index("{", match.start())
    except ValueError:
        return None, "no opening brace found"

    depth = 0
    i = brace_start
    while i < len(content):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                return content[start:i + 1], "ok"
        i += 1
    return None, "no matching closing brace"


def main():
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_project = defaultdict(list)
    for r in rows:
        by_project[r["Project"]].append(r)

    os.makedirs(REPOS_DIR, exist_ok=True)
    output_rows = []
    project_status = {}

    for idx, (project, project_rows) in enumerate(by_project.items(), start=1):
        url = project_rows[0]["ProjectURL"]
        sha = project_rows[0]["SHA"]
        print(f"[{idx}/{len(by_project)}] {project} ({len(project_rows)} tests) - cloning...")
        repo_dir, ok, msg = clone_at_sha(project, url, sha, REPOS_DIR)
        project_status[project] = msg
        if not ok:
            print(f"  FAILED: {msg}")
            for r in project_rows:
                output_rows.append({
                    "id": len(output_rows) + 1,
                    "project": project,
                    "test_fqcn": r["Test"],
                    "full_code": "",
                    "extraction_status": f"clone_failed: {msg}",
                })
            continue

        print(f"  {msg}, extracting {len(project_rows)} test methods...")
        ok_count = 0
        for r in project_rows:
            fqcn = r["Test"]
            if "#" not in fqcn:
                output_rows.append({
                    "id": len(output_rows) + 1,
                    "project": project,
                    "test_fqcn": fqcn,
                    "full_code": "",
                    "extraction_status": "malformed test identifier",
                })
                continue
            class_fqn, method_name_raw = fqcn.split("#", 1)
            simple_class_name = class_fqn.rsplit(".", 1)[-1]
            # Strip JUnit5 parameterized-invocation suffixes, e.g. "myTest[0]" -> "myTest"
            method_name = re.sub(r"\[\d+\]\s*$", "", method_name_raw).strip()

            candidate_files = find_java_files(repo_dir, simple_class_name)
            if not candidate_files:
                output_rows.append({
                    "id": len(output_rows) + 1,
                    "project": project,
                    "test_fqcn": fqcn,
                    "full_code": "",
                    "extraction_status": "file not found",
                })
                continue

            code, status = None, "method signature not found"
            for filepath in candidate_files:
                code, status = extract_method(filepath, method_name)
                if code:
                    break
            if code:
                ok_count += 1
            output_rows.append({
                "id": len(output_rows) + 1,
                "project": project,
                "test_fqcn": fqcn,
                "full_code": code or "",
                "extraction_status": status,
            })
        print(f"  extracted {ok_count}/{len(project_rows)} successfully")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "project", "test_fqcn", "full_code", "extraction_status"])
        writer.writeheader()
        writer.writerows(output_rows)

    total_ok = sum(1 for r in output_rows if r["extraction_status"] == "ok")
    print(f"\nDone. {total_ok}/{len(output_rows)} extracted successfully.")
    print(f"Saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
