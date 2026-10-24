#!/usr/bin/env python3
"""Are ChatUniTest's generated tests flaky? Reruns, NonDex, iDFlakies, NIO and FlakeRake (TD) checks.
This is flaky_check_basic.py plus the `flakerake` subcommand; everything else is unchanged.

Input (--tests, default task_csvs/flaky_generated_tests.csv): one row per generated test method,
with project, sha, module, generated_test (Class#method), test_file (the generated .java, relative
to this folder), focal_method, zip, java, junit (4/5), mockito_fix (true = run with
replay_generated.py's --mockito-fix pom) and, at the end, focal_from_test / focal_from_test_type
(the test the focal method was found from). Only the listed test files are copied in; the project
is the extracted archive <zip>/ in one of --archive-dir. Every run is set up exactly like replay_generated.py:
the generated tests are copied into the module's src/test/java for the run, the same pom, JDK and
Maven (without lib/ext) are used, and afterwards the copied tests and their classes are removed and
pom.xml is checked against its hash. The test files of one generation run (out_partN/runs/row_NNN,
which also names the output folders) are done together, each run on its own (two runs have a test
class with the same name).

Subcommands (run them one after another; each one is resumable and has its own --out folder):
  rerun      `mvn test -Dtest=<Class#method>` N times (default 100) for each generated method on its
             own, each run a fresh JVM.
             A method that both passes and fails is NOD-flaky. Surefire's own reruns are off.
  nondex     NonDex (edu.illinois:nondex-maven-plugin) on the generated classes, --nondex-runs seeds.
             Flags tests that fail when unordered Java APIs (HashMap order, etc.) are shuffled.
  idflakies  iDFlakies (edu.illinois.cs:idflakies-maven-plugin) on the WHOLE module test suite with
             the generated tests added, random class+method orders, --rounds rounds. Flags OD/NOD
             tests; existing tests it flags are reported separately (the known flaky test is
             usually one of them, a good sanity check).
  nio        NIO exactly as ReproFlake does it (its nio_statistics_generator.sh): ReproFlake's builds of
             testrunner 1.4-SNAPSHOT + iDFlakies 1.2.0-SNAPSHOT (copied from an archive's Flakym2),
             the plugin added to the module pom for the run, the test as the only line of
             .dtfixingtools/original-order, `mvn testrunner:testplugin` with ReproFlake's flags
             (test run twice in a row in one JVM), --nio-runs iterations. Per iteration, like
             ReproFlake: all results PASS = pass, some PASS = failure (NIO), none = error; and
             not_twice when testrunner ran the test only once (its JUnit 5 executor does not repeat).
                 JUnit 5 files: testrunner 1.4 only repeats JUnit 4 tests (the idempotent option is only in
             its JUnit 4 executor), so they use our own runner instead (nio_method own_junit5_runner):
             a small JUnit Platform launcher program run twice in one JVM per iteration, on the
             module's test classpath (no surefire config such as argLine), same rule and iterations.
  flakerake  TD (timing-dependent) check with FlakeRake (gmu-swe/flakerake, folder flakerake/, a patched copy,
             see flakerake/PATCHES.md). FlakeRake inserts sleeps into the test's threads and looks for
             a placement that makes the test fail. One test method at a time, one FlakeRake run per method,
             each capped at --flakerake-max-hours (default 2). Works on JDK 8 rows, JUnit 4 (FlakeRake's own runner)
             and JUnit 5 (our SleepyJUnit5Runner, see flakerake/PATCHES.md); JDK 11 rows get status
             unsupported_jdk11 and are not run (FlakeRake needs JDK 8). Per method td is
               true          FlakeRake found a sleep placement that makes the test fail (a logged failure)
               false         no thread produced a failure
               timeout       a sleep made the test hang (FlakeRake's SleepyTimeOut(ProbableDeadlock)); not counted
               inconclusive  the test fails without sleeping, the time cap was hit, or the failure could not be logged
               error         FlakeRake wrote no report (see rows/<id>/flakerake/<method>/flakerake.log)
               unsupported_* not run
             Only one check runs at a time (lock file .flaky_check.lock; a second start is refused). Rows whose last
             status is not a result (build_failed, flakerake_error, archive_missing, unsupported_* that are supported now)
             are tried again on the next run; finished methods are kept. A missing archive only skips its rows.
             night_run.py is the one-command way to run it unattended.
  summary    One row per generated test method with the results of all of them.

The tools' own folders (.nondex/, .dtfixingtools/) are moved into the row's output folder after
each run; one that already existed in the module beforehand is left alone.

Outputs (per subcommand --out, default flaky_check_out/<subcommand>):
  rows.csv        one row per generation run (its test files): status and counts
  runs.csv        rerun only: one line per run and method (resume continues after the last run)
  rows/<id>/      logs (rerun keeps only logs of runs where something failed), tool output;
  orders/         idflakies only: <Class#method>.passing.txt / .failing.txt for every flagged test
                  (one Class#method per line, in run order, the flagged test last)
"""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import batch_reproflake_chatunitest as B  # noqa: E402
import collect_nonflaky as C  # noqa: E402
import replay_generated as R  # noqa: E402

HERE = Path(__file__).resolve().parent
NONDEX = "edu.illinois:nondex-maven-plugin:2.1.7"
IDFLAKIES = "edu.illinois.cs:idflakies-maven-plugin:2.0.0"
NIO_FIELDS = ["test", "nio_method", "iterations", "pass", "failure", "error", "not_twice", "nio", "example"]
ROW_FIELDS = ["id", "zip", "module", "java", "focal", "mockito_fix", "test_classes", "build_status",
              "status", "methods", "flaky_generated", "flaky_other", "note", "log"]
RUN_FIELDS = ["id", "run", "test", "outcome"]
FLAKERAKE_FIELDS = ["test", "td", "detail", "minutes"]
SLEEPY_TIMEOUT = "SleepyTimeOut(ProbableDeadlock)"  # FlakeRake's marker for a run that hung
JUNIT5_RUNNER = "edu.gmu.swe.flaky.sleepy.runner.SleepyJUnit5Runner"  # added by us, see flakerake/PATCHES.md
NO_TEST_MARKER = "SLEEPY_JUNIT5_NO_TEST_EXECUTED"  # SleepyJUnit5Runner prints this when it found no test to run
# Row statuses of the flakerake command that are not a result: the row is tried again on the next run (methods that
# already have a result are kept). "unsupported_*" is retried only if the row is supported now (older package versions
# wrote unsupported_junit5 for the JUnit 5 rows; those must not stay skipped).
FLAKERAKE_RETRY = {"build_failed", "build_timeout", "would_overwrite", "flakerake_did_not_run", "flakerake_error",
                   "archive_missing"}
LOCK_FILE = HERE / ".flaky_check.lock"
FLAKERAKE_JARS = [("sleepy-interceptor", "sleepy-interceptor-0.0.4-SNAPSHOT.jar"),
                  ("sleepy-runner", "sleepy-runner-0.0.4-SNAPSHOT.jar")]
SUMMARY_FIELDS = ["project", "sha", "module", "generated_test", "focal_method", "rerun_runs", "rerun_passed", "rerun_failed",
                  "rerun_errors", "rerun_flaky", "nondex_flaky", "idflakies_type", "idflakies_polluter_of", "nio", "nio_method",
                  "flakerake_td", "flakerake_detail", "any_flaky", "focal_from_test", "focal_from_test_type"]
TEST_FLAGS = [s for s in B.BUILD_SKIPS if s != "-DskipTests"] + [
    "-Dmaven.test.failure.ignore=true", "-DfailIfNoTests=false", "-Dsurefire.failIfNoSpecifiedTests=false",
    "-Dsurefire.rerunFailingTestsCount=0"]

# JUnit 5 NIO fallback (testrunner cannot repeat JUnit 5 tests): runs one test method twice in this
# JVM and prints both outcomes.
NIO_JUNIT5 = r"""
import org.junit.platform.launcher.Launcher;
import org.junit.platform.launcher.LauncherDiscoveryRequest;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;
import org.junit.platform.launcher.listeners.SummaryGeneratingListener;
import org.junit.platform.launcher.listeners.TestExecutionSummary;
import static org.junit.platform.engine.discovery.DiscoverySelectors.selectMethod;

public class FlakyCheckNio5 {
    public static void main(String[] a) throws Exception {
        for (int i = 1; i <= 2; i++) {
            LauncherDiscoveryRequest req = LauncherDiscoveryRequestBuilder.request()
                .selectors(selectMethod(a[0], a[1])).build();
            Launcher launcher = LauncherFactory.create();
            SummaryGeneratingListener listener = new SummaryGeneratingListener();
            launcher.execute(req, listener);
            TestExecutionSummary s = listener.getSummary();
            String why = s.getFailures().isEmpty() ? "" : String.valueOf(s.getFailures().get(0).getException());
            String outcome = s.getTestsStartedCount() == 0 ? "NOTRUN" : s.getTotalFailureCount() > 0 ? "FAIL" : "PASS";
            System.out.println("FLAKYCHECK_NIO " + i + " " + outcome + " " + why.replace('\n', ' '));
        }
        System.exit(0);
    }
}
"""


# NIO as in ReproFlake's nio_statistics_generator.sh (MVNOPTIONS, CHECKSTYLE_OPTS, DETECTOR_OPTS).
TESTRUNNER_PLUGIN = "edu.illinois.cs:testrunner-maven-plugin:1.4-SNAPSHOT"
NIO_ARTIFACTS = ["testrunner/1.4-SNAPSHOT", "testrunner-maven-plugin/1.4-SNAPSHOT", "testrunner-core-plugin/1.4-SNAPSHOT",
                 "testrunner-running/1.4-SNAPSHOT", "testrunner-testing/1.4-SNAPSHOT", "idflakies/1.2.0-SNAPSHOT"]
NIO_MVN_OPTS = [
    "-Ddependency-check.skip=true", "-Dgpg.skip=true", "-DfailIfNoTests=false", "-Dskip.installnodenpm",
    "-Dskip.npm", "-Dskip.yarn", "-Dlicense.skip", "-Dcheckstyle.skip", "-Drat.skip", "-Denforcer.skip",
    "-Danimal.sniffer.skip", "-Dmaven.javadoc.skip", "-Dwarbucks.skip", "-Dmodernizer.skip", "-Dimpsort.skip",
    "-Dmdep.analyze.skip", "-Dpgpverify.skip", "-Dxml.skip", "-Dcobertura.skip=true", "-Dfindbugs.skip=true",
    "-P!checkstyle", "-Dcheckstyle.skipExec=true", "-Dmaven.checkstyle.skip=true", "-DskipCheckstyle=true",
    "-Dcheckstyle.config.location=google_checks.xml", "-Dcheckstyle.failsOnError=false", "-Dspotless.skip=true",
    "-Dskip.format=true"]
NIO_DETECTOR_OPTS = [
    "-Ddt.detector.original_order.all_must_pass=false", "-Ddt.randomize.rounds=0",
    "-Ddt.detector.original_order.retry_count=1", "-Dtestplugin.runner.idempotent.num.runs=2",
    "-Dtestplugin.runner.consec.idempotent=true", "-Ddetector.detector_type=original"]


def load_tests(args):
    """[(id, archive root, g, m, mockito_fix)] per generation run, from the --tests CSV. g/m hold
    what the setup needs, in the names generate/replay use (g["methods"]: the listed methods)."""
    runs = {}
    for r in csv.DictReader(open(args.tests, encoding="utf-8")):
        src = (HERE / r["test_file"]).resolve()
        run_dir = next((q for q in src.parents if q.name.startswith("row_")), src.parent)
        rid = f"{run_dir.parent.parent.name}_{run_dir.name}"  # e.g. out_part1_row_003
        if args.only and not any(x in f"{rid} {r['zip']} {r['generated_test']}" for x in args.only):
            continue
        root = next((d / r["zip"] for d in args.archive_dir if (d / r["zip"]).is_dir()), None)
        if root is None and getattr(args, "command", "") != "flakerake":
            sys.exit(f"{r['zip']} not found in " + ", ".join(map(str, args.archive_dir)))
        # flakerake: a missing archive only skips its rows (status archive_missing), the other rows still run
        if rid not in runs:
            runs[rid] = (rid, root.resolve() if root else None,
                         {"zip": r["zip"], "flaky_test": r["focal_from_test"], "selected_method": r["focal_method"],
                          "chatunitest_mode": r["junit"], "test_files": [], "methods": [], "csv": r},
                         {"project": r["project"], "flaky_commit": r["sha"], "module": r["module"],
                          "java": r["java"], "zip": r["zip"], "flaky_test": r["focal_from_test"]},
                         r["mockito_fix"].strip().lower() == "true")
        g = runs[rid][2]
        if src not in g["test_files"]:
            g["test_files"].append(src)
        g["methods"].append(r["generated_test"])
    return [runs[k] for k in sorted(runs)]


def test_classes(g):
    """[(source file, package, class name)] for the run's listed test files."""
    out = []
    for f in g["test_files"]:
        m = R.PACKAGE.search(f.read_text(encoding="utf-8", errors="replace"))
        out.append((f, m.group(1) if m else "", f.stem))
    return out


class Prepared:
    """The module with the generated tests in place, the pom used for the run, and the env (JDK,
    Maven without lib/ext). Undone on exit; the pom is checked against its hash."""

    def __init__(self, rid, root, g, m, mockito_fix, args):
        self.rid, self.g, self.m, self.fix, self.args = rid, g, m, mockito_fix, args
        self.row_dir = args.out / "rows" / rid
        self.row_dir.mkdir(parents=True, exist_ok=True)
        self.files = test_classes(g)
        self.classes = [name for _, _, name in self.files]
        # Fully qualified, to tell the generated tests apart from the module's own in tool output.
        self.fqcn = [f"{pkg}.{name}" if pkg else name for _, pkg, name in self.files]
        _, self.module_dir, _ = B.locate_test(root, m["module"], g["flaky_test"])
        self.r = dict(m, module=C.norm_module(m["module"]), archive_root=str(root), module_dir=str(self.module_dir))
        self.cwd, self.pl = C.project_root(self.module_dir, self.r["module"])
        self.pom = self.module_dir / "pom.xml"
        self.env = dict(args.env)
        jdk = B.find_jdk(str(m.get("java", "")).strip())
        if jdk:
            self.env["JAVA_HOME"] = jdk
            self.env["PATH"] = str(Path(jdk) / "bin") + os.pathsep + self.env["PATH"]

    def __enter__(self):
        used = self.row_dir / "pom.xml.used"
        if used.is_file() and (self.row_dir / "pom.xml.before").is_file() and self.pom.read_bytes() == used.read_bytes():
            print(f"  restoring {self.pom} left modified by a killed run")
            shutil.copy2(self.row_dir / "pom.xml.before", self.pom)
        used.unlink(missing_ok=True)
        shutil.copy2(self.pom, self.row_dir / "pom.xml.before")
        self.pom_sha = R.sha(self.pom)
        text = R.mockito_fixed(self.pom.read_text(encoding="utf-8"), self.g["chatunitest_mode"]) if self.fix else None
        if self.args.command == "nio" and self.g["chatunitest_mode"] != "5":
            text = with_testrunner(text if text is not None else self.pom.read_text(encoding="utf-8"))
        self.stack = [R.TempPom(self.pom, text, self.row_dir), R.CopiedTests(self.module_dir, self.files, self.row_dir)]
        for s in self.stack:
            s.__enter__()
        return self

    def __exit__(self, *exc):
        for s in reversed(self.stack):
            s.__exit__(*exc)
        if R.sha(self.pom) != self.pom_sha:
            print(f"  WARNING: {self.pom} changed during the run; original copy in {self.row_dir / 'pom.xml.before'}")

    def build(self):
        if self.r["module"] == ".":
            return "not_needed"
        return B.build_module(self.r, self.env, self.args, self.row_dir, "build.log")

    def mvn(self, goals, log, offline=False):
        cmd = ["mvn", "-B", *(["-o"] if offline else []), *self.pl, *goals,
               "-Dmaven.repo.local=" + str(self.args.repo)]
        with log.open("w", encoding="utf-8") as fout:
            fout.write("(cd " + str(self.cwd) + " && " + " ".join(cmd) + ")\n")
            fout.flush()
            try:
                p = subprocess.run(cmd, cwd=self.cwd, env=self.env, stdout=fout, stderr=subprocess.STDOUT,
                                   timeout=self.args.timeout)
            except subprocess.TimeoutExpired:
                fout.write(f"Timed out after {self.args.timeout} seconds.\n")
                return "timeout"
        return p.returncode

    def reports(self):
        tests, _ = C.read_reports(self.module_dir)
        return {t: o for t, o in tests.items() if t.split("#")[0] in self.fqcn}

    def take_tool_dir(self, name, existed):
        """Move the tool's folder (e.g. .nondex) out of the module into the row folder."""
        src = self.module_dir / name
        if existed or not src.exists():
            return None
        dest = self.row_dir / name.lstrip(".")
        shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(src), str(dest))
        return dest


def record(p, mockito_fix):
    return {"id": p.rid, "zip": p.g["zip"], "module": p.m["module"], "java": p.m["java"],
            "focal": p.g["selected_method"], "mockito_fix": str(mockito_fix).lower(),
            "test_classes": ";".join(p.classes), "build_status": "", "status": "", "note": ""}


def generated_name(name, fqcn):
    """Class#method for a test name (Class#method, Class.method or Class.method(...)) if it is one of
    the generated classes, else None."""
    name = re.split(r"[\[(]", name.strip(), 1)[0]
    cls, sep, method = name.partition("#")
    if not sep:
        cls, _, method = name.rpartition(".")
    return f"{cls}#{method}" if cls in fqcn else None


def do_rerun(p, rec, args):
    """Each generated test method on its own (-Dtest=Class#method), --runs times, each run a fresh
    JVM; one runs.csv line per run. Resumes per method after its last recorded run."""
    runs_csv = args.out / "runs.csv"
    done = {}
    if runs_csv.is_file():
        for r in csv.DictReader(open(runs_csv, encoding="utf-8")):
            if r["id"] == p.rid:
                done[r["test"]] = max(done.get(r["test"], 0), int(r["run"]))
    logs = p.row_dir / "rerun_logs"
    logs.mkdir(exist_ok=True)
    new = not runs_csv.is_file()
    first = True
    with runs_csv.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, RUN_FIELDS)
        if new:
            w.writeheader()
        for t in row_methods(args, p.rid):
            cls, _, method = t.partition("#")
            name = cls.rsplit(".", 1)[-1] + "#" + method
            for run in range(done.get(t, 0) + 1, args.runs + 1):
                shutil.rmtree(p.module_dir / "target" / "surefire-reports", ignore_errors=True)
                log = logs / f"{method}_{run:03d}.log"
                # The first run compiles and resolves; later ones only need what is already there.
                code = p.mvn(["test", "-Dtest=" + name, *TEST_FLAGS], log, offline=not first and args.offline)
                first = False
                outcome = p.reports().get(t) or ("timeout" if code == "timeout" else "error")
                w.writerow({"id": p.rid, "run": run, "test": t, "outcome": outcome})
                f.flush()
                if outcome == "passed":
                    log.unlink()  # keep the log only when it did not pass
                print(f"  {name} run {run}/{args.runs}: {outcome}", flush=True)


def rerun_counts(path):
    """{(id, test): [passed, failed, runs, errors]} from runs.csv. errors: Maven itself failed (no
    report), which says nothing about the test, so it is not counted as a failure."""
    counts = {}
    if path.is_file():
        for r in csv.DictReader(open(path, encoding="utf-8")):
            c = counts.setdefault((r["id"], r["test"]), [0, 0, 0, 0])
            c[0] += r["outcome"] == "passed"
            c[1] += r["outcome"] in ("failed", "rerun_passed")
            c[2] += 1
            c[3] += r["outcome"] in ("error", "timeout")
    return counts


def nondex_flagged(log_text):
    """Tests listed under NonDex's final 'Across all seeds:'."""
    out, on = set(), False
    for line in log_text.splitlines():
        if "Across all seeds:" in line:
            on, out = True, set()
            continue
        if on:
            m = re.match(r"\[(?:WARNING|INFO|ERROR)\]\s+(\S+[#.]\S+)\s*$", line)
            if m and not m.group(1).startswith(("-", "*")):
                out.add(m.group(1))
            else:
                on = False
    return out


def do_nondex(p, rec, args):
    existed = (p.module_dir / ".nondex").exists()
    log = p.row_dir / "nondex.log"
    # Not -Dmaven.test.failure.ignore: with it NonDex sees no failures at all ("No Test Failed with
    # this configuration" for a test that failed). The build then fails when NonDex finds something.
    code = p.mvn([NONDEX + ":nondex", "-Dtest=" + ",".join(p.classes), f"-DnondexRuns={args.nondex_runs}",
                  *[f for f in TEST_FLAGS if f != "-Dmaven.test.failure.ignore=true"]], log)
    dest = p.take_tool_dir(".nondex", existed)
    text = log.read_text(encoding="utf-8", errors="replace")
    flagged = nondex_flagged(text)
    gen = sorted({g for g in (generated_name(t, p.fqcn) for t in flagged) if g})
    (p.row_dir / "nondex_flaky.txt").write_text("".join(t + "\n" for t in gen))
    rec.update(log=str(log), flaky_generated=len(gen), flaky_other=len(flagged) - len(gen),
               note=("" if dest else ".nondex existed in the module beforehand, left there; " if existed else ""))
    if code == "timeout":
        rec["status"] = "timeout"
    elif "NonDex SUMMARY" not in text and "Across all seeds" not in text:
        rec["status"] = "compile_failed" if "COMPILATION ERROR" in text else "nondex_did_not_run"
    else:
        rec["status"] = "flaky_found" if gen else "no_flaky_found"


def idflakies_flagged(tool_dir):
    """{test name: type} from .dtfixingtools/detection-results/flaky-lists.json (or list.txt)."""
    res = tool_dir / "detection-results" if tool_dir else None
    out = {}
    if res and (res / "flaky-lists.json").is_file():
        try:
            data = json.loads((res / "flaky-lists.json").read_text())
            for d in data.get("dts", []):
                out[d.get("name", "")] = d.get("type", "")
        except ValueError:
            pass
    if res and not out and (res / "list.txt").is_file():
        out = {line.strip(): "" for line in (res / "list.txt").read_text().splitlines() if line.strip()}
    return out


def idflakies_polluters(tool_dir, fqcn):
    """{flagged test: [generated tests]} for generated tests that ran before it in the order where it
    failed but not in the order where it passed: suspected polluters (iDFlakies' order lists are the
    tests run before the flagged one)."""
    res = tool_dir / "detection-results" / "flaky-lists.json" if tool_dir else None
    out = {}
    if res and res.is_file():
        try:
            dts = json.loads(res.read_text()).get("dts", [])
        except ValueError:
            dts = []
        for d in dts:
            failing = [t for t in (d.get("revealed") or {}).get("order", []) if generated_name(t, fqcn)]
            passing = set((d.get("intended") or {}).get("order", []))
            out[d.get("name", "")] = sorted(generated_name(t, fqcn) for t in failing if t not in passing)
    return out


def flagged_orders(tool_dir):
    """[(test, passing order, failing order)] for every test iDFlakies flagged, all as Class#method,
    each order in run order with the flagged test last (iDFlakies' own lists stop just before it)."""
    res = tool_dir / "detection-results" / "flaky-lists.json" if tool_dir else None
    if not (res and res.is_file()):
        return []
    try:
        dts = json.loads(res.read_text()).get("dts", [])
    except ValueError:
        return []
    def hashed(t):
        # iDFlakies writes Class.method for JUnit 4 and Class#method() for JUnit 5.
        t = re.split(r"[\[(]", t, 1)[0]
        return t if "#" in t else "#".join(t.rsplit(".", 1))
    out = []
    for d in dts:
        name = hashed(d.get("name", ""))
        orders = [[hashed(t) for t in (d.get(k) or {}).get("order", [])] + [name] for k in ("intended", "revealed")]
        out.append((name, *orders))
    return out


def write_orders(args, rows):
    """orders/ in --out: <Class#method>.passing.txt and .failing.txt for every test iDFlakies flagged
    (one test per line, in run order, the flagged test last). A test flagged in the runs of several
    generated files gets -2, -3, ... in that row order; the failing order shows the generated test."""
    dest = args.out / "orders"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    seen = {}
    for rid, root, g, m, fix in rows:
        for test, passing, failing in flagged_orders(args.out / "rows" / rid / "dtfixingtools"):
            seen[test] = seen.get(test, 0) + 1
            name = test + (f"-{seen[test]}" if seen[test] > 1 else "")
            (dest / f"{name}.passing.txt").write_text("\n".join(passing) + "\n")
            (dest / f"{name}.failing.txt").write_text("\n".join(failing) + "\n")


def do_idflakies(p, rec, args):
    existed = (p.module_dir / ".dtfixingtools").exists()
    log = p.row_dir / "idflakies.log"
    code = p.mvn(["test-compile", IDFLAKIES + ":detect", "-Ddetector.detector_type=random-class-method",
                  f"-Ddt.randomize.rounds={args.rounds}", "-Ddt.detector.original_order.all_must_pass=false",
                  *[s for s in B.BUILD_SKIPS if s != "-DskipTests"]], log)
    dest = p.take_tool_dir(".dtfixingtools", existed)
    if existed:
        rec["note"] = ".dtfixingtools existed in the module beforehand, left there and read from there; "
        dest = p.module_dir / ".dtfixingtools"
    flagged = idflakies_flagged(dest)
    gen = {g: typ for g, typ in ((generated_name(t, p.fqcn), typ) for t, typ in flagged.items()) if g}
    polluters = idflakies_polluters(dest, p.fqcn)
    with (p.row_dir / "idflakies_flaky.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["test", "type", "generated", "suspected_generated_polluters"])
        for t, typ in sorted(flagged.items()):
            w.writerow([t, typ, str(generated_name(t, p.fqcn) is not None).lower(), ";".join(polluters.get(t, []))])
    polluted = sum(1 for t, ps in polluters.items() if ps and not generated_name(t, p.fqcn))
    rec.update(log=str(log), flaky_generated=len(gen), flaky_other=len(flagged) - len(gen))
    if polluted:
        rec["note"] = rec.get("note", "") + f"{polluted} existing test(s) fail only after a generated test (suspected polluter); "
    text = log.read_text(encoding="utf-8", errors="replace")
    if code == "timeout":
        rec["status"] = "timeout"
    elif dest is None or not (dest / "detection-results").is_dir():
        rec["status"] = "compile_failed" if "COMPILATION ERROR" in text else "idflakies_did_not_run"
    else:
        rec["status"] = "flaky_found" if gen else ("polluter_found" if polluted else "no_flaky_found")


def row_methods(args, rid):
    """The generated test methods (Class#method) listed for this run in the --tests CSV."""
    return sorted(set(args.methods.get(rid, [])))


def with_testrunner(text):
    """The pom with ReproFlake's testrunner plugin (iDFlakies DetectorPlugin) in <build><plugins>,
    as in the poms of ReproFlake's NIO archives; unchanged if it already has one."""
    if "<artifactId>testrunner-maven-plugin</artifactId>" in text:
        return text
    import xml.etree.ElementTree as ET
    root = ET.fromstring(text.encode("utf-8"))
    ns = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
    if ns:
        ET.register_namespace("", ns)
    q = lambda tag: f"{{{ns}}}{tag}" if ns else tag

    def child(parent, tag, value=None):
        e = ET.SubElement(parent, q(tag))
        if value is not None:
            e.text = value
        return e
    build = root.find(q("build"))
    if build is None:
        build = child(root, "build")
    plugins = build.find(q("plugins"))
    if plugins is None:
        plugins = child(build, "plugins")
    plugin = child(plugins, "plugin")
    group, artifact, version = TESTRUNNER_PLUGIN.split(":")
    child(plugin, "groupId", group), child(plugin, "artifactId", artifact), child(plugin, "version", version)
    dep = child(child(plugin, "dependencies"), "dependency")
    child(dep, "groupId", "edu.illinois.cs"), child(dep, "artifactId", "idflakies"), child(dep, "version", "1.2.0-SNAPSHOT")
    child(child(plugin, "configuration"), "className", "edu.illinois.cs.dt.tools.detection.DetectorPlugin")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def ensure_testrunner(args):
    """ReproFlake's testrunner/iDFlakies builds in --maven-repo: copied (never overwriting) from the
    first archive whose Flakym2 has them (ReproFlake installed them there for its NIO runs)."""
    cs = Path("edu/illinois/cs")
    if all((args.repo / cs / a).is_dir() for a in NIO_ARTIFACTS):
        return
    for d in args.archive_dir:
        for m2 in sorted(d.glob("*/*/Flakym2/.m2/repository")) + sorted(d.glob("*/Flakym2/.m2/repository")):
            if all((m2 / cs / a).is_dir() for a in NIO_ARTIFACTS):
                for a in NIO_ARTIFACTS:
                    for f in (m2 / cs / a).iterdir():
                        dest = args.repo / cs / a / f.name
                        if f.is_file() and not dest.exists():
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(f, dest)
                print(f"  testrunner/iDFlakies copied from {m2}", flush=True)
                return
    raise RuntimeError("no archive Flakym2 with ReproFlake's testrunner 1.4-SNAPSHOT / iDFlakies 1.2.0-SNAPSHOT")


def nio_status(dt):
    """(pass | failure | error, results in run order, result file) from testrunner's result JSON,
    ReproFlake's rule: all PASS = pass, some PASS = failure, no PASS (or no result) = error."""
    results_dir = next((d for d in (dt / "test-runs" / "results", dt / "results") if d.is_dir()), None)
    files = sorted(results_dir.iterdir()) if results_dir else []
    if not files:
        return "error", "no testrunner result", None
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
    except ValueError:
        return "error", "unreadable testrunner result", files[0]
    res = data.get("results") or {}
    order = [t for t in (data.get("testOrder") or []) if t in res] or list(res)  # run order
    vals = [((res[t] or {}).get("result") or "").upper().replace("SUCCESS", "PASS") for t in order]
    status = "pass" if vals and all(v == "PASS" for v in vals) else ("failure" if "PASS" in vals else "error")
    if len(vals) < 2:
        # Not run twice (testrunner 1.4 does the repeat only for JUnit 4): no NIO check at all, so
        # not a pass, whatever ReproFlake's rule would say.
        status = "not_twice"
    return status, ";".join(vals), files[0]


def nio_runner(p, junit, args):
    """Directory with the compiled runner class. Compiled with JDK 8's javac for Java 8 (JDK 11
    here has no javac), so it runs on any of the JDKs."""
    jdk8 = B.find_jdk("8")
    if not jdk8 or not (Path(jdk8) / "bin" / "javac").exists():
        raise RuntimeError("needs a JDK 8 with javac to compile the small NIO runner")
    name = f"FlakyCheckNio{junit}"
    d = p.row_dir / "nio_runner"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir()
    (d / (name + ".java")).write_text(NIO_JUNIT5)
    out = subprocess.run([str(Path(jdk8) / "bin" / "javac"), "-source", "8", "-target", "8", "-nowarn",
                          "-cp", p.classpath, "-d", str(d), str(d / (name + ".java"))],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if out.returncode != 0:
        raise RuntimeError("could not compile the NIO runner: " + out.stdout[-500:])
    return d, name


def junit_launcher(p, cp, args):
    """Jars the JUnit Platform needs that the module's test classpath lacks: the launcher (surefire
    brings its own), and the engines if the pom only gives them to the surefire plugin (ormlite).
    Versions follow the module's junit-jupiter-api (5.x.y -> platform 1.x.y); fetched with
    dependency:get if they are not in the local repo yet."""
    def version(prefix):
        found = [re.search(prefix + r"-([\w.\-]+)\.jar$", e) for e in cp]
        return next((m.group(1) for m in found if m), None)
    jupiter = version("junit-jupiter-api")
    platform = version("junit-platform-engine") or version("junit-platform-commons") or (
        "1." + jupiter.split(".", 1)[1] if jupiter and jupiter.startswith("5.") else None)
    if not platform:
        raise RuntimeError("no JUnit Platform on the test classpath")
    want = [("org.junit.platform", "junit-platform-launcher", platform)]
    if not version("junit-platform-engine"):
        want.append(("org.junit.platform", "junit-platform-engine", platform))
    if jupiter and not version("junit-jupiter-engine"):
        want.append(("org.junit.jupiter", "junit-jupiter-engine", jupiter))
    jars = []
    for group, artifact, ver in want:
        if version(artifact):
            continue
        jar = args.repo / group.replace(".", "/") / artifact / ver / f"{artifact}-{ver}.jar"
        if not jar.is_file():
            p.mvn(["org.apache.maven.plugins:maven-dependency-plugin:3.6.1:get", "-Dtransitive=false",
                   f"-Dartifact={group}:{artifact}:{ver}"], p.row_dir / f"nio_get_{artifact}.log")
        if not jar.is_file():
            raise RuntimeError(f"could not get {group}:{artifact}:{ver}")
        jars.append(str(jar))
    return jars


def own_junit5_iterations(p, args):
    """JUnit 5 NIO with our own runner: {test: [status,results per iteration]} (same rule as
    nio_status), or raises RuntimeError if the classpath or runner cannot be set up."""
    cp_file = p.row_dir / "test_classpath.txt"
    code = p.mvn(["test-compile", "org.apache.maven.plugins:maven-dependency-plugin:3.6.1:build-classpath",
                  "-Dmdep.includeScope=test", "-Dmdep.outputFile=" + str(cp_file),
                  *[s for s in B.BUILD_SKIPS if s != "-DskipTests"]], p.row_dir / "nio_classpath.log")
    if code != 0 or not cp_file.is_file():
        raise RuntimeError(f"test classpath failed, see {p.row_dir / 'nio_classpath.log'}")
    cp = [str(p.module_dir / "target" / "test-classes"), str(p.module_dir / "target" / "classes")]
    cp += [e for e in cp_file.read_text().strip().split(os.pathsep) if e]
    cp += junit_launcher(p, cp, args)
    p.classpath = os.pathsep.join(cp)
    runner_dir, runner = nio_runner(p, "5", args)
    java = str(Path(p.env["JAVA_HOME"]) / "bin" / "java") if p.env.get("JAVA_HOME") else "java"
    out = {}
    for t in row_methods(args, p.rid):
        tdir = p.row_dir / "nio_runs" / t
        tdir.mkdir(parents=True, exist_ok=True)
        done_file = tdir / "statuses.txt"
        done = done_file.read_text().splitlines() if done_file.is_file() else []
        cls, _, method = t.partition("#")
        for i in range(len(done), args.nio_runs):
            try:
                text = subprocess.run([java, "-cp", os.pathsep.join([str(runner_dir), p.classpath]), runner, cls, method],
                                      cwd=p.module_dir, env=p.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, timeout=args.timeout).stdout
            except subprocess.TimeoutExpired:
                text = "FLAKYCHECK_NIO 1 TIMEOUT"
            got = dict(re.findall(r"^FLAKYCHECK_NIO (\d) (\w+)", text, re.M))
            vals = [got.get("1", "ERROR"), got.get("2", "ERROR")]
            status = "pass" if vals == ["PASS", "PASS"] else ("failure" if "PASS" in vals else "error")
            if status != "pass":
                (tdir / f"run_{i:03d}.log").write_text(text)
            with done_file.open("a") as f:
                f.write(f"{status},{';'.join(vals)}\n")
            done.append(f"{status},{';'.join(vals)}")
        out[t] = done
    return out


def do_nio(p, rec, args):
    if p.g["chatunitest_mode"] == "5":
        try:
            runs = own_junit5_iterations(p, args)
        except RuntimeError as ex:
            rec.update(status="nio_setup_failed", note=str(ex)[:300])
            return
        nio_summarize(p, rec, runs, "own_junit5_runner")
        return
    try:
        ensure_testrunner(args)
    except RuntimeError as ex:
        rec.update(status="nio_setup_failed", note=str(ex)[:300])
        return
    dt = p.module_dir / ".dtfixingtools"
    if dt.exists():
        rec.update(status="skipped_dtfixingtools_exists", note=f"{dt} already exists; testrunner would use it")
        return
    log = p.row_dir / "nio_compile.log"
    # ReproFlake runs `mvn clean install -DskipTests -pl <module> -am` first; the build is done, this
    # compiles the copied generated tests.
    if p.mvn(["test-compile", *NIO_MVN_OPTS, *[s for s in B.BUILD_SKIPS if s != "-DskipTests"]], log) != 0:
        rec.update(status="compile_failed", log=str(log))
        return
    junit5 = p.g["chatunitest_mode"] == "5"
    force4 = "false" if junit5 else "true"
    results = {}
    try:
        for t in row_methods(args, p.rid):
            tdir = p.row_dir / "nio_runs" / t
            tdir.mkdir(parents=True, exist_ok=True)
            done_file = tdir / "statuses.txt"  # one line per finished iteration: status,results
            done = done_file.read_text().splitlines() if done_file.is_file() else []
            for i in range(len(done), 0 if done and done[-1].startswith("not_twice") else args.nio_runs):
                dt.mkdir(exist_ok=True)
                # Class.method like ReproFlake (JUnit 4); testrunner's JUnit 5 executor needs Class#method.
                (dt / "original-order").write_text((t if junit5 else t.replace("#", ".")) + "\n")
                run_log = tdir / f"run_{i:03d}.log"
                p.mvn([TESTRUNNER_PLUGIN + ":testplugin", *NIO_MVN_OPTS, *NIO_DETECTOR_OPTS,
                       f"-Ddt.detector.forceJUnit4={force4}"], run_log)
                status, vals, result_file = nio_status(dt)
                if result_file:
                    shutil.copy2(result_file, tdir / f"run_{i:03d}.json")
                shutil.rmtree(dt, ignore_errors=True)
                # testrunner writes failing-test-output-* into the directory Maven runs in.
                for out in [*p.cwd.glob("failing-test-output-*"), *p.module_dir.glob("failing-test-output-*")]:
                    shutil.move(str(out), str(tdir / f"run_{i:03d}.{out.name}"))
                if status == "pass":
                    run_log.unlink()  # keep the Maven log only when it did not pass
                with done_file.open("a") as f:
                    f.write(f"{status},{vals}\n")
                done.append(f"{status},{vals}")
                if status == "not_twice":
                    break  # testrunner cannot repeat this test; more iterations would not either
            results[t] = done
    finally:
        shutil.rmtree(dt, ignore_errors=True)
    nio_summarize(p, rec, results, "testrunner")


def nio_summarize(p, rec, runs, method):
    """nio.csv and the row record from {test: [status,results per iteration]}."""
    results = []
    for t, done in runs.items():
        counts = {k: sum(1 for d in done if d.split(",", 1)[0] == k) for k in ("pass", "failure", "error", "not_twice")}
        example = next((d.split(",", 1)[1] for d in done if not d.startswith("pass")), "")
        nio = "true" if counts["failure"] else ("false" if counts["pass"] else "inconclusive")
        results.append({"test": t, "nio_method": method, "iterations": len(done), **counts, "nio": nio, "example": example})
        print(f"  {t}: pass {counts['pass']}, failure {counts['failure']}, error {counts['error']}, "
              f"not run twice {counts['not_twice']} ({method})" + (" -> NIO" if nio == "true" else ""), flush=True)
    B.csv_write(p.row_dir / "nio.csv", results, NIO_FIELDS)
    gen = [r for r in results if r["nio"] == "true"]
    rec.update(log=str(p.row_dir / "nio.csv"), methods=len(results), flaky_generated=len(gen),
               note=rec.get("note", "") + ("" if method == "testrunner" else f"NIO with {method}; "),
               status="flaky_found" if gen else ("inconclusive" if any(r["nio"] == "inconclusive" for r in results)
                                                  else "no_flaky_found"))


def acquire_run_lock():
    """Only one check (or the controls / night_run.py) at a time: they share the project folders, the Maven
    repository and the FlakeRake build, and two at once corrupt each other. An exclusive lock on LOCK_FILE; it is
    released when this process ends, however it ends. night_run.py holds it for its children (FLAKECHECK_LOCK_HELD=1)."""
    if os.environ.get("FLAKECHECK_LOCK_HELD") == "1":
        return None
    import fcntl
    f = open(LOCK_FILE, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.seek(0)
        sys.exit("ANOTHER CHECK IS ALREADY RUNNING (flaky_check.py, run_controls.sh or night_run.py): " + f.read().strip()
                 + f"\nNOT STARTING. Wait for it or stop it first (lock file {LOCK_FILE}).")
    except OSError as ex:  # a file system without locks: go on, but say so
        print(f"WARNING: could not lock {LOCK_FILE} ({ex}); make sure no other check is running.", flush=True)
        return f
    f.seek(0)
    f.truncate()
    f.write(f"pid {os.getpid()}, started {time.strftime('%Y-%m-%d %H:%M:%S')}, {' '.join(sys.argv)}\n")
    f.flush()
    return f  # the caller keeps it open


_J5_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?org\.junit\.jupiter\.", re.M)
_J4_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?org\.junit\.(?!jupiter|platform|vintage)", re.M)


def detect_junit(files):
    """"4", "5", "both" or "" from the imports of the generated test files: what the tests are really written in,
    to compare with the junit column of the CSV (the runner must match the test, not the column)."""
    four = five = False
    for f in files:
        text = Path(f).read_text(encoding="utf-8", errors="replace")
        five = five or bool(_J5_IMPORT.search(text))
        four = four or bool(_J4_IMPORT.search(text))
    return "both" if four and five else "5" if five else "4" if four else ""


def flakerake_retry(status, g, m):
    """True if the earlier status of a row is not a result and the row should be tried again."""
    if status in FLAKERAKE_RETRY:
        return True
    return status.startswith("unsupported") and not flakerake_unsupported(g, m)


def flakerake_unsupported(g, m):
    """Why FlakeRake cannot run on this generation run, or "" if it can. FlakeRake's agent needs JDK 8
    (-Xbootclasspath/p, ASM 5). JUnit 4 and JUnit 5 both work (JUnit 5 through SleepyJUnit5Runner)."""
    java = str(m.get("java", "")).strip()
    if java != "8":
        return f"unsupported_jdk{java}"
    return ""


def classify_flakerake(report, code=0):
    """(td, detail) from FlakeRake's <input>_minimal_sleep_report.csv: one row per thread (and failure)
    it analysed, Failure = NoFail, an exception line + FlakeRakeB64StackTrace=..., or a marker."""
    if not report.is_file():
        return "error", f"no report (findFlakySleeps exit {code})"
    rows = list(csv.DictReader(open(report, encoding="utf-8", newline="")))
    if not rows:
        return "error", "empty report"
    failures = [(r.get("Failure") or "") for r in rows]
    real = [f for f in failures if "FlakeRakeB64StackTrace=" in f]
    if real:
        line = real[0].split("FlakeRakeB64StackTrace=")[0].strip().replace("\n", " ")[:200]
        return "true", f"{len(real)} failing thread analysis row(s); first: {line}"
    if SLEEPY_TIMEOUT in failures:
        return "timeout", "a sleep made the test hang (ProbableDeadlock), no failure reproduced"
    if any(r.get("Thread") == "AlreadyFailsStably" or r.get("SleepyLines") == "AlreadyFailsStably" for r in rows):
        return "inconclusive", "the test fails even without sleeping"
    if any(f.startswith("TestMethodAnalysisExceeded") for f in failures):
        return "inconclusive", "analysis time cap reached before a failure was found"
    if any(f == "FAILURE_THAT_COULD_NOT_BE_LOGGED" for f in failures):
        return "inconclusive", "a failure happened but FlakeRake could not log it"
    if all(f == "NoFail" for f in failures):
        return "false", ""
    return "inconclusive", "unrecognised failure value: " + failures[0][:100]


def descendants(pid):
    """PIDs of all children, grandchildren, ... of pid (read from /proc, Linux). They are found through
    their parent PID, so also those that started their own session or process group."""
    kids = {}
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                with open(f"/proc/{d}/stat") as f:
                    ppid = int(f.read().rsplit(")", 1)[1].split()[1])
                kids.setdefault(ppid, []).append(int(d))
            except (OSError, ValueError, IndexError):
                pass
    out, stack = [], [pid]
    while stack:
        for c in kids.get(stack.pop(), []):
            out.append(c)
            stack.append(c)
    return out


def kill_tree(pid):
    """SIGKILL pid, everything below it, and its process group. Only this process tree is touched."""
    for p in [*descendants(pid), pid]:
        try:
            os.kill(p, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_group(cmd, cwd, env, log, timeout):
    """Run cmd (a list) in its own session, output to log. Returns the exit code, or "timeout".
    On a timeout or an interrupt (Ctrl+C) the whole process tree below it is killed, including the Java
    processes FlakeRake starts in sessions of their own; afterwards leftovers in its process group are
    killed. Never other Java processes."""
    with log.open("w", encoding="utf-8") as fout:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=fout, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(proc.pid)
            proc.wait()
            fout.write(f"\nTimed out after {timeout} seconds.\n")
            code = "timeout"
        except BaseException:  # Ctrl+C etc.: do not leave the run behind
            kill_tree(proc.pid)
            proc.wait()
            raise
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)  # leftovers of the finished run, in its own group
            except (ProcessLookupError, PermissionError):
                pass
    return code


def has_junit5_runner(runner_jar):
    """True if the installed sleepy-runner jar contains SleepyJUnit5Runner (an older v2 build does not)."""
    import zipfile
    try:
        with zipfile.ZipFile(runner_jar) as z:
            return "edu/gmu/swe/flaky/sleepy/runner/SleepyJUnit5Runner.class" in z.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def ensure_flakerake(args):
    """Build and install the patched FlakeRake (flakerake/, JDK 8) into --maven-repo, unless the two jars
    are there and newer than every source file."""
    fr = args.flakerake_dir
    if not (fr / "sleepy-parent" / "pom.xml").is_file():
        sys.exit(f"FlakeRake folder not found: {fr} (flakerake/ from the package)")
    base = args.repo / "edu" / "gmu" / "swe" / "flaky" / "sleepy"
    jars = [base / a / "0.0.4-SNAPSHOT" / j for a, j in FLAKERAKE_JARS]
    sources = [f for f in (fr / "sleepy-parent").rglob("*") if f.is_file() and "target" not in f.parts]
    newest = max(f.stat().st_mtime for f in sources)
    if all(j.is_file() and j.stat().st_mtime >= newest for j in jars) and has_junit5_runner(jars[1]):
        return
    jdk8 = B.find_jdk("8")
    if not jdk8 or not (Path(jdk8) / "bin" / "javac").exists():
        sys.exit("FlakeRake needs a JDK 8 with javac (set JAVA_HOME_8)")
    env = dict(args.env)
    env["JAVA_HOME"] = jdk8
    env["PATH"] = str(Path(jdk8) / "bin") + os.pathsep + env["PATH"]
    log = args.out / "flakerake_build.log"
    # sleepy-parent/pom.xml only (the agent and the runner). The root pom of the FlakeRake repo is not built: it
    # only adds Sonatype release tooling (nexus-staging plugin, snapshot repository) that is not needed.
    cmd = ["mvn", "-B", "-f", str(fr / "sleepy-parent" / "pom.xml"), "install", "-DskipTests",
           "-Dmaven.repo.local=" + str(args.repo)]
    print("Building FlakeRake: " + " ".join(cmd), flush=True)
    code = run_group(cmd, fr, env, log, 3600)
    if code != 0 or not all(j.is_file() for j in jars):
        sys.exit(f"FlakeRake build failed (exit {code}), see {log}")


def write_flakerake_rows(path, rows):
    B.csv_write(path, rows, FLAKERAKE_FIELDS)


def flakerake_unsupported_row(args, rid, g, m, fix, reason, detail="FlakeRake not run"):
    """The row record for a generation run FlakeRake is not run on, plus its flakerake.csv."""
    row_dir = args.out / "rows" / rid
    row_dir.mkdir(parents=True, exist_ok=True)
    tests = row_methods(args, rid)
    write_flakerake_rows(row_dir / "flakerake.csv",
                         [{"test": t, "td": reason, "detail": detail, "minutes": ""} for t in tests])
    return {"id": rid, "zip": g["zip"], "module": m["module"], "java": m["java"], "focal": g["selected_method"],
            "mockito_fix": str(fix).lower(), "test_classes": ";".join(f.stem for f in g["test_files"]),
            "build_status": "", "status": reason, "methods": len(tests), "note": detail}


def flakerake_junit5_classpath(p, args):
    """Jars SleepyJUnit5Runner needs on top of FlakeRake's class path: the JUnit Platform launcher (surefire brings
    its own, the module's test class path usually lacks it) and, when the module's pom only gives the engines to
    surefire (ormlite), the engines. Same logic as the nio check (junit_launcher) on the module's test class path.
    Raises RuntimeError if it cannot be worked out."""
    cp_file = p.row_dir / "flakerake_test_classpath.txt"
    log = p.row_dir / "flakerake_classpath.log"
    code = p.mvn(["test-compile", "org.apache.maven.plugins:maven-dependency-plugin:3.6.1:build-classpath",
                  "-Dmdep.includeScope=test", "-Dmdep.outputFile=" + str(cp_file),
                  *[s for s in B.BUILD_SKIPS if s != "-DskipTests"]], log)
    if code != 0 or not cp_file.is_file():
        raise RuntimeError(f"test classpath failed, see {log}")
    cp = [e for e in cp_file.read_text().strip().split(os.pathsep) if e]
    return junit_launcher(p, cp, args)


def no_test_executed(*logs):
    """True if one of the logs holds the marker SleepyJUnit5Runner prints when the Launcher found no test to run."""
    for f in logs:
        try:
            if NO_TEST_MARKER in Path(f).read_text(errors="replace"):
                return True
        except OSError:
            pass
    return False


def do_flakerake(p, rec, args):
    jdk8 = p.env.get("JAVA_HOME")
    if not jdk8 or not (Path(jdk8) / "bin" / "java").exists():
        rec.update(status="flakerake_did_not_run", note="no JDK 8 found (set JAVA_HOME_8)")
        return
    sleepy = p.module_dir / "sleepy-records"
    input_csv = p.module_dir / "flakerake_input.csv"
    for leftover in (sleepy, input_csv):
        if leftover.exists():
            # Left behind by an interrupted run (this process holds the lock, so nothing else is running). Moved, not
            # deleted, so nothing is lost; the earlier package version stopped here with would_overwrite.
            stash = p.row_dir / ("leftover_" + time.strftime("%Y%m%d_%H%M%S"))
            stash.mkdir(parents=True, exist_ok=True)
            shutil.move(str(leftover), str(stash / leftover.name))
            print(f"  moved {leftover.name}, left in the module by an earlier interrupted run, to {stash}", flush=True)
    env = dict(p.env)
    env.update({
        "FLAKY_HOME": str(args.flakerake_dir), "MAVEN_REPO": str(args.repo),
        "JAVA_FLAKY_HOME": jdk8, "JAVA_HOME": jdk8,
        "FLAKERAKE_SKIP_INSTALL": "1",  # the module was already built by p.build()
        "FLAKERAKE_MVN_ARGS": "-Dmaven.repo.local=" + str(args.repo),
        "FLAKY_MVN_INSTALL_OPTS": " ".join(["-B", "-fn", "-DskipITs", *B.BUILD_SKIPS]),
    })
    junit5 = p.g["chatunitest_mode"] == "5"
    seen = detect_junit(p.g["test_files"])
    if seen == "both":
        print("  WARNING: the test files import both JUnit 4 and JUnit 5; using the junit column "
              f"({p.g['chatunitest_mode']}). The runner has to match the tests, check the result.", flush=True)
    elif seen and (seen == "5") != junit5:
        print(f"  WARNING: the junit column says {p.g['chatunitest_mode']} but the test files use JUnit {seen}; "
              f"using the runner for JUnit {seen}.", flush=True)
        junit5 = seen == "5"
    runner_args = []
    if junit5:
        try:
            env["FLAKERAKE_EXTRA_CP"] = os.pathsep.join(flakerake_junit5_classpath(p, args))
        except RuntimeError as ex:
            rec.update(status="flakerake_did_not_run", note=str(ex)[:300])
            return
        runner_args = ["--runner_class", JUNIT5_RUNNER]
    script = args.flakerake_dir / "shell_scripts" / "findFlakySleeps.py"
    out_dir = p.row_dir / "flakerake"
    results = []
    for t in row_methods(args, p.rid):
        mdir = out_dir / re.sub(r"[^\w.#-]", "_", t)
        mdir.mkdir(parents=True, exist_ok=True)
        done = mdir / "result.json"
        if done.is_file() and not args.redo:
            res = json.loads(done.read_text())
            if res["td"] != "error":  # a setup error is tried again; real results are kept (--redo to redo)
                print(f"  {t}: td {res['td']} (done earlier)", flush=True)
                results.append({"test": t, **res})
                continue
        with input_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Project_Git_URL", "Git_SHA", "TestMethod"])
            w.writerow([p.m["project"], p.m["flaky_commit"], t])
        begin = time.time()
        dest = mdir / "sleepy-records"
        try:
            code = run_group([sys.executable, str(script), "--testMethodsFile", input_csv.name,
                              "--runs", str(args.flakerake_runs), "--max_hours", str(args.flakerake_max_hours),
                              "--sleep_time_ms", str(args.flakerake_sleep_ms), "--logging", "info", *runner_args],
                             p.module_dir, env, mdir / "flakerake.log", int((args.flakerake_max_hours + 1) * 3600))
        finally:
            # Also on Ctrl+C or any error: leave no flakerake_input.csv / sleepy-records in the module (they would
            # make the next run stop with would_overwrite). An interrupted method has no result.json, so it is redone.
            input_csv.unlink(missing_ok=True)
            shutil.rmtree(dest, ignore_errors=True)
            if sleepy.exists():
                shutil.move(str(sleepy), str(dest))
        if junit5 and no_test_executed(mdir / "flakerake.log", dest / "logs" / "sleepy-script.log"):
            td, detail = "error", "JUnit 5 runner found no test to run (" + NO_TEST_MARKER + "), see flakerake.log"
        elif code == "timeout":
            td, detail = "inconclusive", "FlakeRake did not finish within the wall-clock limit"
        else:
            td, detail = classify_flakerake(dest / "report" / (input_csv.name + "_minimal_sleep_report.csv"), code)
        res = {"td": td, "detail": detail, "minutes": round((time.time() - begin) / 60, 1)}
        done.write_text(json.dumps(res))
        results.append({"test": t, **res})
        print(f"  {t}: td {td} ({res['minutes']} min){': ' + detail if detail else ''}", flush=True)
    write_flakerake_rows(p.row_dir / "flakerake.csv", results)
    tds = [r["td"] for r in results]
    rec.update(log=str(p.row_dir / "flakerake.csv"), methods=len(results), flaky_generated=tds.count("true"),
               status="flaky_found" if "true" in tds else
               ("flakerake_error" if "error" in tds else
                ("inconclusive" if any(x in ("inconclusive", "timeout") for x in tds) else "no_flaky_found")))


def summary(args):
    base = args.out
    counts = rerun_counts(base / "rerun" / "runs.csv")
    out = []
    for rid, root, g, m, fix in load_tests(args):
        files = test_classes(g)
        fqcn = [f"{pkg}.{name}" if pkg else name for _, pkg, name in files]
        nd_file = base / "nondex" / "rows" / rid / "nondex_flaky.txt"
        nd = set(nd_file.read_text().split()) if nd_file.is_file() else None
        idf, polluter_of = {}, {}
        idf_file = base / "idflakies" / "rows" / rid / "idflakies_flaky.csv"
        if idf_file.is_file():
            for r in csv.DictReader(open(idf_file, encoding="utf-8")):
                name = generated_name(r["test"], fqcn)
                if name:
                    idf[name] = r["type"] or "flaky"
                else:
                    for gt in filter(None, (r.get("suspected_generated_polluters") or "").split(";")):
                        polluter_of[gt] = polluter_of.get(gt, 0) + 1
        nio_file = base / "nio" / "rows" / rid / "nio.csv"
        nio_rows = {r["test"]: r for r in csv.DictReader(open(nio_file, encoding="utf-8"))} if nio_file.is_file() else None
        nio = {t: r["nio"] for t, r in nio_rows.items()} if nio_rows is not None else None
        fr_file = base / "flakerake" / "rows" / rid / "flakerake.csv"
        fr_rows = {r["test"]: r for r in csv.DictReader(open(fr_file, encoding="utf-8"))} if fr_file.is_file() else None
        for t in row_methods(args, rid):
            c = counts.get((rid, t), [0, 0, 0, 0])
            errors = c[3]
            row = {"project": m["project"], "sha": m["flaky_commit"], "module": m["module"], "generated_test": t,
                   "focal_method": g["selected_method"], "focal_from_test": g["csv"]["focal_from_test"],
                   "focal_from_test_type": g["csv"].get("focal_from_test_type", ""),
                   "rerun_runs": c[2] or "", "rerun_passed": c[0] if c[2] else "", "rerun_failed": c[1] if c[2] else "",
                   "rerun_errors": errors or "",
                   "rerun_flaky": (str(c[0] > 0 and c[1] > 0).lower() if c[2] else ""),
                   "nondex_flaky": "" if nd is None else str(t in nd).lower(),
                   "idflakies_type": "" if not idf_file.is_file() else idf.get(t, "-"),
                   "idflakies_polluter_of": "" if not idf_file.is_file() else polluter_of.get(t, 0),
                   "nio": "" if nio is None else nio.get(t, ""),
                   "nio_method": "" if nio_rows is None else (nio_rows.get(t) or {}).get("nio_method", ""),
                   "flakerake_td": "" if fr_rows is None else (fr_rows.get(t) or {}).get("td", ""),
                   "flakerake_detail": "" if fr_rows is None else (fr_rows.get(t) or {}).get("detail", "")}
            row["any_flaky"] = str(row["rerun_flaky"] == "true" or row["nondex_flaky"] == "true"
                                   or row["idflakies_type"] not in ("", "-") or row["nio"] == "true"
                                   or row["flakerake_td"] == "true"
                                   or bool(row["idflakies_polluter_of"])).lower()
            out.append(row)
    B.csv_write(base / "summary.csv", out, SUMMARY_FIELDS)
    flaky = [r for r in out if r["any_flaky"] == "true"]
    print(f"{len(out)} generated test methods, {len(flaky)} flagged flaky by at least one tool -> {base / 'summary.csv'}")
    for r in flaky:
        print(f"  {r['generated_test']}: rerun {r['rerun_failed']}/{r['rerun_runs']} failed, nondex {r['nondex_flaky']}, "
              f"idflakies {r['idflakies_type']} (polluter of {r['idflakies_polluter_of'] or 0}) , nio {r['nio']}, "
              f"flakerake td {r['flakerake_td'] or '-'}")


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("command", choices=["rerun", "nondex", "idflakies", "nio", "flakerake", "summary"])
    a.add_argument("--out", type=Path, help="Default flaky_check_out/<command> (summary: flaky_check_out)")
    a.add_argument("--tests", type=Path, default=HERE / "task_csvs" / "flaky_generated_tests.csv",
                   help="CSV with the generated tests to check (default task_csvs/flaky_generated_tests.csv)")
    a.add_argument("--archive-dir", type=Path, action="append",
                   help="Folder with extracted <zip>/ archives (repeatable; default extracted/, made by setup_archives.py)")
    a.add_argument("--maven-repo", dest="repo", type=Path, default=Path.home() / ".m2" / "repository")
    a.add_argument("--runs", type=int, default=100, help="rerun: runs per test method (default 100)")
    a.add_argument("--offline", action="store_true", help="rerun: mvn -o after the first run (faster)")
    a.add_argument("--nondex-runs", type=int, default=10, help="nondex: seeds (default 10)")
    a.add_argument("--nio-runs", type=int, default=100,
                   help="nio: iterations per test method, each running it twice in one JVM (default 100)")
    a.add_argument("--rounds", type=int, default=10, help="idflakies: shuffled rounds (default 10)")
    a.add_argument("--flakerake-dir", type=Path, default=HERE / "flakerake",
                   help="flakerake: the patched FlakeRake folder (default flakerake/ next to this script)")
    a.add_argument("--flakerake-runs", type=int, default=5,
                   help="flakerake: tries to make a failure stable, FlakeRake's own default (5)")
    a.add_argument("--flakerake-max-hours", type=float, default=2.0,
                   help="flakerake: most hours of analysis per test method (default 2; upstream FlakeRake uses 24)")
    a.add_argument("--flakerake-sleep-ms", type=int, default=10000,
                   help="flakerake: sleep time in ms at the chosen lines, FlakeRake's own default (10000)")
    a.add_argument("--timeout", type=int, default=6 * 3600, help="Seconds per Maven call (default 6h)")
    a.add_argument("--only", action="append", default=[], help="Only runs whose id, zip or generated test contains this text")
    a.add_argument("--redo", action="store_true", help="nondex/idflakies/nio/flakerake: redo rows (flakerake: methods) that have a result")
    args = a.parse_args()
    args.tests = args.tests.resolve()
    args.archive_dir = [d.resolve() for d in (args.archive_dir or [HERE / "extracted"])]
    args.methods = {rid: g["methods"] for rid, _, g, _, _ in load_tests(args)}
    args.repo = args.repo.resolve()
    args.flakerake_dir = args.flakerake_dir.resolve()
    args.out = (args.out or HERE / "flaky_check_out" / ("" if args.command == "summary" else args.command)).resolve()
    if args.command == "summary":
        return summary(args)
    lock = acquire_run_lock()  # noqa: F841  (kept open until this process ends)
    args.out.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    mvn_bin = C.maven_without_extensions(args.out)
    if mvn_bin:
        env["PATH"] = str(mvn_bin) + os.pathsep + env["PATH"]
        env.pop("M2_HOME", None)
        env.pop("MAVEN_HOME", None)
    args.env = env

    rows = load_tests(args)
    prev = {}
    if (args.out / "rows.csv").is_file():
        prev = {r["id"]: r for r in csv.DictReader(open(args.out / "rows.csv", encoding="utf-8"))}
    print(f"{len(rows)} generation runs, {sum(len(r[2]['methods']) for r in rows)} test methods "
          f"from {args.tests.name} ({args.command})")
    flakerake_ready = False
    for i, (rid, root, g, m, fix) in enumerate(rows, 1):
        if args.command != "rerun" and rid in prev and prev[rid]["status"] and not args.redo:
            if args.command == "flakerake" and flakerake_retry(prev[rid]["status"], g, m):
                print(f"[{i}/{len(rows)}] {rid}: earlier status {prev[rid]['status']} is not a result, trying again", flush=True)
            else:
                print(f"[{i}/{len(rows)}] {rid}: done ({prev[rid]['status']}), skipping (--redo to rerun)")
                continue
        if args.command == "flakerake":
            reason = flakerake_unsupported(g, m)
            if reason:
                print(f"[{i}/{len(rows)}] {rid} {g['zip']} (JDK {m['java']}, JUnit {g['chatunitest_mode']}): {reason}", flush=True)
                prev[rid] = flakerake_unsupported_row(args, rid, g, m, fix, reason)
                B.csv_write(args.out / "rows.csv", sorted(prev.values(), key=lambda x: x["id"]), ROW_FIELDS)
                continue
            if root is None:
                print(f"[{i}/{len(rows)}] {rid} {g['zip']}: ARCHIVE NOT FOUND, row skipped (download_zips.sh + "
                      f"setup_archives.py --only {g['zip']}); run again afterwards", flush=True)
                prev[rid] = flakerake_unsupported_row(args, rid, g, m, fix, "archive_missing",
                                                      f"archive {g['zip']} not found")
                B.csv_write(args.out / "rows.csv", sorted(prev.values(), key=lambda x: x["id"]), ROW_FIELDS)
                continue
            if not flakerake_ready:
                ensure_flakerake(args)
                flakerake_ready = True
        print(f"[{i}/{len(rows)}] {rid} {g['zip']} {g['selected_method']} (JDK {m['java']}"
              + (", mockito fix" if fix else "") + ")", flush=True)
        p = Prepared(rid, root, g, m, fix, args)
        rec = record(p, fix)
        try:
            with p:
                rec["build_status"] = p.build()
                if rec["build_status"] in ("build_failed", "build_timeout"):
                    rec["status"] = rec["build_status"]
                else:
                    {"rerun": do_rerun, "nondex": do_nondex, "idflakies": do_idflakies, "nio": do_nio,
                     "flakerake": do_flakerake}[args.command](p, rec, args)
        except FileExistsError as ex:
            rec.update(status="would_overwrite", note=str(ex)[:300])
        if args.command == "rerun" and not rec["status"]:
            c = {t: v for (r_id, t), v in rerun_counts(args.out / "runs.csv").items() if r_id == rid}
            flaky = [t for t, v in c.items() if v[0] and v[1]]
            rec.update(methods=len(c), flaky_generated=len(flaky),
                       status="flaky_found" if flaky else ("always_failed" if c and all(not v[0] for v in c.values())
                                                           else "no_flaky_found"))
        print(f"  => {rec['status']}" + (f": {rec.get('flaky_generated')} generated test(s) flaky"
                                         if rec.get("flaky_generated") else ""), flush=True)
        prev[rid] = rec
        B.csv_write(args.out / "rows.csv", sorted(prev.values(), key=lambda x: x["id"]), ROW_FIELDS)
        if args.command == "idflakies":
            write_orders(args, rows)


if __name__ == "__main__":
    main()
