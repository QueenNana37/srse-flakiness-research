#!/usr/bin/env python3
"""night_run.py: one command for an unattended FlakeRake (TD) run.

    python3 night_run.py                  controls, then every FlakeRake row that has no result yet (JDK 8, JUnit 4 + 5)
    python3 night_run.py --report-only    only (re)write NIGHT_REPORT.txt and flaky_check_out/flakerake_results.csv
                                          (safe to run while the night run is going)
    python3 night_run.py --skip-controls  skip the controls   |   --redo-controls  run them again

What it does, in this order (every step is logged in night_out/, the end result is NIGHT_REPORT.txt):
  1. Takes the lock: only one check at a time (a second start is refused, nothing is touched).
  2. Preflight: JDK 8 with javac, Maven, disk space, Maven Central reachable, protoc for Hadoop rows. Hard problems stop
     the run before anything starts.
  3. Plan: which rows still need a result (nothing that already has one is run again), and which archives are missing;
     missing archives of rows that need a run are downloaded and set up (download_zips.sh, setup_archives.py).
  4. Controls (run_controls.sh): tiny tests with a known race, JUnit 4 and JUnit 5. They are only information: if a
     control does not give the expected answer or cannot run, the main run still goes on (nobody can act at night) and
     the report says in capitals that the results are NOT VALIDATED.
  5. Main run: flaky_check.py flakerake on the rows that need a result. Ctrl+C is safe; start again to continue.
  6. Report.
Nothing is deleted anywhere. Leftovers of an interrupted run are moved into the row's output folder."""
import argparse
import csv
import json
import os
import re
import shutil
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import flaky_check as F  # noqa: E402

B = F.B
NIGHT = HERE / "night_out"
CONTROLS_OUT = HERE / "controls_out"
FR_OUT = HERE / "flaky_check_out" / "flakerake"
REPORT = HERE / "NIGHT_REPORT.txt"
RESULTS = HERE / "flaky_check_out" / "flakerake_results.csv"
MIN_FREE_GB = 20
PROTOC_ZIPS = re.compile(r"hadoop|yarn", re.I)


def say(msg=""):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}" if msg else ""
    print(line, flush=True)
    NIGHT.mkdir(parents=True, exist_ok=True)
    with open(NIGHT / "night_run.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def tail(path, n):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def make_plan(tests):
    """One dict per generation run: state is done / pending / archive_missing / not_supported."""
    ns = argparse.Namespace(tests=tests, only=[], archive_dir=[HERE / "extracted"], command="flakerake")
    prev = {}
    if (FR_OUT / "rows.csv").is_file():
        prev = {r["id"]: r.get("status", "") for r in csv.DictReader(open(FR_OUT / "rows.csv", encoding="utf-8"))}
    plan = []
    for rid, root, g, m, fix in F.load_tests(ns):
        status = prev.get(rid, "")
        reason = F.flakerake_unsupported(g, m)
        if reason:
            state = "not_supported"
        elif status and not F.flakerake_retry(status, g, m):
            state = "done"
        elif root is None:
            state = "archive_missing"
        else:
            state = "pending"
        plan.append({"rid": rid, "zip": g["zip"], "java": m["java"], "junit": g["chatunitest_mode"],
                     "methods": sorted(set(g["methods"])), "status": status, "state": state, "reason": reason})
    return plan


def preflight(plan):
    """([hard problems], [warnings])"""
    stops, warns = [], []
    if sys.version_info < (3, 8):
        stops.append("python3 3.8 or newer is needed")
    if not Path("/proc").is_dir():
        stops.append("Linux (/proc) is needed; this is not Linux")
    jdk8 = B.find_jdk("8")
    if not jdk8 or not (Path(jdk8) / "bin" / "javac").exists():
        stops.append("no JDK 8 with javac found (install openjdk-8-jdk or set JAVA_HOME_8)")
    else:
        say(f"JDK 8: {jdk8}")
    if not shutil.which("mvn"):
        stops.append("mvn (Maven) not found")
    free = shutil.disk_usage(HERE).free / 1e9
    if free < MIN_FREE_GB:
        stops.append(f"only {free:.0f} GB free in {HERE}; need at least {MIN_FREE_GB} GB")
    else:
        say(f"disk: {free:.0f} GB free")
    try:
        urllib.request.urlopen(urllib.request.Request("https://repo.maven.apache.org/maven2/", method="HEAD"), timeout=20)
        say("Maven Central: reachable")
    except Exception as ex:  # a warning only: everything may be in the local repository already
        warns.append(f"Maven Central not reachable from Python ({type(ex).__name__}); runs that need to download will fail")
    for p in plan:
        if p["state"] in ("pending", "archive_missing") and PROTOC_ZIPS.search(p["zip"]):
            protoc = os.environ.get("HADOOP_PROTOC_PATH", "")
            if not protoc or not os.access(protoc, os.X_OK):
                warns.append(f"{p['zip']} (Hadoop) needs protoc in the version of its BUILDING.txt (2.5.0 for YARN-9405) and "
                             "HADOOP_PROTOC_PATH is not set to a working protoc; its build will fail without it")
            break
    return stops, warns


def ensure_archives(plan, env):
    missing = sorted({p["zip"] for p in plan if p["state"] == "archive_missing"})
    for z in missing:
        say(f"archive {z} is missing: downloading and setting it up")
        for name, cmd, limit in (("download", ["bash", "download_zips.sh", z], 4 * 3600),
                                 ("setup", [sys.executable, "setup_archives.py", "--only", z], 6 * 3600)):
            log = NIGHT / f"archive_{z}_{name}.log"
            code = F.run_group(cmd, HERE, env, log, limit)
            say(f"  {name}: exit {code}, log {log}")
            if code != 0:
                for line in tail(log, 8):
                    say("    " + line)
                break


def run_controls(kinds, env, redo):
    out = {}
    for kind in kinds:
        d = CONTROLS_OUT / kind
        d.mkdir(parents=True, exist_ok=True)
        saved = d / "control_result.json"
        if saved.is_file() and not redo:
            out[kind] = json.loads(saved.read_text())
            say(f"control {kind}: earlier result is {out[kind]['verdict']} (--redo-controls runs it again)")
            continue
        log = NIGHT / f"controls_{kind}.log"
        say(f"control {kind}: running (log {log})")
        code = F.run_group(["bash", "run_controls.sh", kind], HERE, env, log, 4 * 3600)
        verdict = {0: "AS EXPECTED", 3: "NOT AS EXPECTED"}.get(code, f"COULD NOT RUN (exit {code})")
        out[kind] = {"code": code, "verdict": verdict, "time": time.strftime("%Y-%m-%d %H:%M")}
        if code in (0, 3):  # a failure to run is not remembered, it is tried again next time
            saved.write_text(json.dumps(out[kind]))
        say(f"control {kind}: {verdict}")
        for line in tail(log, 9):
            say("    " + line)
    return out


def run_main(plan, args, env):
    ids = [p["rid"] for p in plan if p["state"] == "pending"]
    if not ids:
        say("main run: nothing to do (every supported row has a result)")
        return None
    cmd = [sys.executable, "flaky_check.py", "flakerake", "--tests", str(args.tests)]
    for i in ids:
        cmd += ["--only", i]
    cmd += ["--flakerake-runs", str(args.flakerake_runs), "--flakerake-max-hours", str(args.flakerake_max_hours),
            "--flakerake-sleep-ms", str(args.flakerake_sleep_ms)]
    log = NIGHT / f"flakerake_main_{time.strftime('%Y%m%d_%H%M%S')}.log"
    say(f"main run: {len(ids)} row(s): {', '.join(ids)}")
    say(f"  follow it with:  tail -f {log}")
    code = F.run_group(cmd, HERE, env, log, 60 * 3600)
    say(f"main run finished: exit {code}")
    if code != 0:
        for line in tail(log, 15):
            say("    " + line)
    return {"code": code, "log": str(log), "rows": ids}


def collect(plan):
    rows = []
    for p in plan:
        f = FR_OUT / "rows" / p["rid"] / "flakerake.csv"
        if f.is_file():
            for r in csv.DictReader(open(f, encoding="utf-8", newline="")):
                rows.append({"row": p["rid"], "zip": p["zip"], "java": p["java"], "junit": p["junit"],
                             **{k: r.get(k, "") for k in F.FLAKERAKE_FIELDS}})
    return rows


def write_report(args, st):
    """NIGHT_REPORT.txt and flakerake_results.csv from what is on disk, plus what this run recorded in st."""
    try:
        plan = make_plan(args.tests)
    except SystemExit as ex:
        plan = []
        st.setdefault("notes", []).append(f"could not read the plan: {ex}")
    rows = collect(plan)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["row", "zip", "java", "junit", "test", "td", "detail", "minutes"])
        w.writeheader()
        w.writerows(rows)
    L = [f"NIGHT REPORT, written {time.strftime('%Y-%m-%d %H:%M')}", ""]
    ctl = st.get("controls") or {}
    if not ctl:  # not run this time: show the saved results of an earlier run
        for kind in ("junit4", "junit5"):
            saved = CONTROLS_OUT / kind / "control_result.json"
            if saved.is_file():
                ctl[kind] = json.loads(saved.read_text())
    if ctl:
        L.append("Controls (tiny tests with a known race; they show whether FlakeRake can find a failure on this machine):")
        for k, v in ctl.items():
            L.append(f"  {k}: {v['verdict']}")
        if any(v["code"] != 0 for v in ctl.values()):
            L.append("  >>> RESULTS NOT VALIDATED: a control did not give the expected answer or could not run. Do not trust "
                     "'false' results until this is understood (see controls_out/<kind>/ and night_out/controls_<kind>.log).")
        L.append("")
    for n in st.get("notes", []):
        L.append("NOTE: " + n)
    if st.get("notes"):
        L.append("")
    mainrun = st.get("main")
    if mainrun:
        L.append(f"Main run: exit {mainrun['code']}, rows {', '.join(mainrun['rows'])}, log {mainrun['log']}")
        L.append("")
    L.append("Rows (JDK 8 = supported; JDK 11 rows are not run, FlakeRake's agent needs JDK 8):")
    for p in plan:
        tds = Counter(r["td"] for r in rows if r["row"] == p["rid"])
        L.append(f"  {p['rid']:<20} JDK {p['java']:<3} JUnit {p['junit']}  {p['state']:<15} "
                 + (", ".join(f"{k}={v}" for k, v in sorted(tds.items())) or "-"))
    L.append("")
    L.append("td per JUnit version (supported rows):")
    for junit in ("4", "5"):
        c = Counter(r["td"] for r in rows if r["junit"] == junit and r["java"] == "8")
        L.append(f"  JUnit {junit}: " + (", ".join(f"{k}={v}" for k, v in sorted(c.items())) or "no results yet"))
    L.append("")
    problems = [r for r in rows if r["td"] in ("error",)]
    if problems:
        L.append("METHODS WITH td=error (setup problem, not a result; they are tried again on the next run):")
        for r in problems:
            mdir = re.sub(r"[^\w.#-]", "_", r["test"])
            L.append(f"  {r['row']} {r['test']}: {r['detail']}")
            L.append(f"      log: {FR_OUT}/rows/{r['row']}/flakerake/{mdir}/flakerake.log")
        L.append("")
    bad = [p for p in plan if p["state"] == "pending" and p["status"] and p["status"] in F.FLAKERAKE_RETRY]
    if bad:
        L.append("Rows that stopped before FlakeRake ran (status; tried again on the next run):")
        for p in bad:
            L.append(f"  {p['rid']}: {p['status']}")
        L.append("")
    todo = [p["rid"] for p in plan if p["state"] in ("pending", "archive_missing")]
    L.append("Still without a result: " + (", ".join(todo) if todo else "none (all supported rows done)"))
    L.append(f"All results in one file: {RESULTS}")
    text = "\n".join(L) + "\n"
    REPORT.write_text(text, encoding="utf-8")
    return text


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--tests", type=Path, default=HERE / "task_csvs" / "flaky_generated_tests.csv")
    a.add_argument("--report-only", action="store_true")
    a.add_argument("--skip-controls", action="store_true")
    a.add_argument("--redo-controls", action="store_true")
    a.add_argument("--flakerake-runs", type=int, default=5)
    a.add_argument("--flakerake-max-hours", type=float, default=2.0)
    a.add_argument("--flakerake-sleep-ms", type=int, default=10000)
    args = a.parse_args()
    args.tests = args.tests.resolve()
    st = {"notes": []}
    if args.report_only:
        print(write_report(args, st))
        return 0

    lock = F.acquire_run_lock()  # refuses to start (exit) if another check is running; held until this process ends
    os.environ["FLAKECHECK_LOCK_HELD"] = "1"  # our children run under this lock
    env = os.environ.copy()
    jdk8 = B.find_jdk("8")
    if jdk8:
        env.setdefault("JAVA_HOME_8", jdk8)
    code = 0
    try:
        say("=== night run starts ===" + (f" (lock: {lock.name})" if lock else ""))
        plan = make_plan(args.tests)
        stops, warns = preflight(plan)
        for w in warns:
            say("WARNING: " + w)
            st["notes"].append("WARNING: " + w)
        if stops:
            for s_ in stops:
                say("STOP: " + s_)
                st["notes"].append("STOPPED BEFORE STARTING: " + s_)
            return 2
        ensure_archives(plan, env)
        plan = make_plan(args.tests)
        for p in plan:
            say(f"  {p['rid']:<20} JDK {p['java']:<3} JUnit {p['junit']}  {p['state']}"
                + (f" ({p['status']})" if p["status"] else ""))
        missing = [p["rid"] for p in plan if p["state"] == "archive_missing"]
        if missing:
            st["notes"].append("ARCHIVE STILL MISSING, these rows were not run: " + ", ".join(missing)
                               + " (see night_out/archive_*.log)")
        if not args.skip_controls and any(p["state"] == "pending" for p in plan):
            st["controls"] = run_controls(["junit4", "junit5"], env, args.redo_controls)
            bad = [k for k, v in st["controls"].items() if v["code"] != 0]
            if bad:
                # The controls are new and the main run is what the night is for, so it goes on; the report says that
                # its results are not validated. (A broken setup makes the real methods fail fast with td=error.)
                st["notes"].append("CONTROL(S) " + ", ".join(bad) + " did not give the expected answer or could not run. "
                                   "The main run went on anyway, its results are NOT VALIDATED until this is understood.")
                say("WARNING: " + st["notes"][-1])
        st["main"] = run_main(plan, args, env)
        if st["main"] and st["main"]["code"] != 0:
            code = 1
    except KeyboardInterrupt:
        st["notes"].append("INTERRUPTED (Ctrl+C). Start night_run.py again to continue; finished methods are kept.")
        say(st["notes"][-1])
        code = 130
    finally:
        text = write_report(args, st)
        say("=== night run ends ===")
        print()
        print(text)
        print(f"(also in {REPORT})")
    return code


if __name__ == "__main__":
    sys.exit(main())
