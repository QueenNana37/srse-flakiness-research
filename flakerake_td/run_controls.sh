#!/bin/bash
# Controls for FlakeRake: three small tests with a known timing race (+ one single-threaded test), as JUnit 4 and as
# JUnit 5. Shows whether FlakeRake, as set up here, finds a failure when there is one. Needs JDK 8 with javac, Maven,
# python3, internet (Maven Central). Takes a while (see README_flakerake.md).
#   bash run_controls.sh junit4      only the JUnit 4 control
#   bash run_controls.sh junit5      only the JUnit 5 control (tests SleepyJUnit5Runner)
#   bash run_controls.sh             both
#   CONTROL_JDK=11 bash run_controls.sh junit4   the same control on JDK 11 (v6): needs JDK 11 with javac as well (JAVA_HOME_11),
#                                    builds and uses the ASM 9 agent (flakerake/asm9/, repository FLAKERAKE_ASM9_REPO, default
#                                    ~/.m2/flakerake-asm9-repository) and compiles the control for Java 11, so that the nest
#                                    attributes of Java 11 class files are in the test too. Without CONTROL_JDK: JDK 8, as before.
# Output: controls_out/<kind>/ (FlakeRake's report + logs) and a table at the end of each run
#         (JDK 11: controls_out/<kind>_jdk11/, the control is copied there and compiled there).
# Exit code: 0 = AS EXPECTED, 3 = ran, but NOT AS EXPECTED, 4 = another check is running (not started), 1 = could not run.
cd "$(dirname "$0")" || exit 1
HERE=$PWD
# Only one check at a time (same lock as flaky_check.py; night_run.py holds it and sets FLAKECHECK_LOCK_HELD=1).
if [ "${FLAKECHECK_LOCK_HELD:-}" != 1 ]; then
  if command -v flock > /dev/null 2>&1; then
    exec 9>> "$HERE/.flaky_check.lock"
    flock -n 9 || { echo "ANOTHER CHECK IS ALREADY RUNNING: $(cat "$HERE/.flaky_check.lock" 2>/dev/null). NOT STARTING."; exit 4; }
    echo "pid $$, started $(date '+%F %T'), run_controls.sh $*" > "$HERE/.flaky_check.lock"
  else
    echo "WARNING: no flock command, cannot lock. Make sure no other check is running."
  fi
fi
kinds=${1:-"junit4 junit5"}
CJDK=${CONTROL_JDK:-8}
case $CJDK in 8|11) ;; *) echo "CONTROL_JDK must be 8 or 11 (not $CJDK)."; exit 1;; esac
JDK8=${JAVA_HOME_8:-}
if [ -z "$JDK8" ]; then   # same search as the rest of the package (batch_reproflake_chatunitest.find_jdk)
  JDK8=$(python3 -c 'import sys; sys.path.insert(0, "."); import batch_reproflake_chatunitest as B; print(B.find_jdk("8") or "")' 2>/dev/null)
fi
if [ -z "$JDK8" ] || [ ! -x "$JDK8/bin/javac" ]; then
  for d in /usr/lib/jvm/java-8-openjdk-amd64 /usr/lib/jvm/java-1.8.0-openjdk-amd64; do
    [ -x "$d/bin/javac" ] && JDK8=$d && break
  done
fi
[ -x "$JDK8/bin/javac" ] || { echo "No JDK 8 with javac found (set JAVA_HOME_8)."; exit 1; }
REPO=${MAVEN_REPO:-$HOME/.m2/repository}
RUNNER_JAR=$REPO/edu/gmu/swe/flaky/sleepy/sleepy-runner/0.0.4-SNAPSHOT/sleepy-runner-0.0.4-SNAPSHOT.jar
export JAVA_HOME=$JDK8 PATH=$JDK8/bin:$PATH

AGENT_REPO=$REPO TESTJDK=$JDK8 SUFFIX="" MVNX=""
if [ "$CJDK" = 8 ]; then
  # Build FlakeRake (same command as flaky_check.py) unless the installed runner jar already has the JUnit 5 runner.
  if ! { [ -f "$RUNNER_JAR" ] && unzip -l "$RUNNER_JAR" 2>/dev/null | grep -q SleepyJUnit5Runner; }; then
    echo "Building FlakeRake (JDK 8) ..."
    mvn -B -q -f "$HERE/flakerake/sleepy-parent/pom.xml" install -DskipTests -Dmaven.repo.local="$REPO" 9>&- || { echo "FlakeRake build failed"; exit 1; }
  fi
else
  # JDK 11 (v6): the ASM 9 agent, built by flakerake/asm9/build_asm9_agent.py (with JDK 8) into its own repository; the tests
  # and the java that runs them are JDK 11, compiled for Java 11 (-Dmaven.compiler.source/target override the control's 1.8).
  AGENT_REPO=${FLAKERAKE_ASM9_REPO:-$HOME/.m2/flakerake-asm9-repository}
  TESTJDK=${JAVA_HOME_11:-}
  if [ -z "$TESTJDK" ]; then
    TESTJDK=$(python3 -c 'import sys; sys.path.insert(0, "."); import batch_reproflake_chatunitest as B; print(B.find_jdk("11") or "")' 2>/dev/null)
  fi
  [ -x "$TESTJDK/bin/javac" ] || { echo "No JDK 11 with javac found (set JAVA_HOME_11)."; exit 1; }
  echo "Building the ASM 9 agent (JDK 8) if needed ..."
  python3 "$HERE/flakerake/asm9/build_asm9_agent.py" --repo "$AGENT_REPO" --jdk "$JDK8" --flakerake-dir "$HERE/flakerake" 9>&- || { echo "ASM 9 agent build failed"; exit 1; }
  SUFFIX=_jdk11 MVNX="-Dmaven.compiler.source=11 -Dmaven.compiler.target=11"
  export JAVA_HOME=$TESTJDK PATH=$TESTJDK/bin:$PATH
fi

export FLAKY_HOME=$HERE/flakerake MAVEN_REPO=$AGENT_REPO JAVA_FLAKY_HOME=$TESTJDK
export FLAKERAKE_SKIP_INSTALL=1 FLAKERAKE_MVN_ARGS="-Dmaven.repo.local=$REPO${MVNX:+ $MVNX}" FLAKY_MVN_INSTALL_OPTS="-B -fn -DskipITs"
unset FLAKERAKE_EXTRA_CP   # the control's pom has the JUnit launcher on its test class path

status=0
for kind in $kinds; do
  rc=0
  dir=$HERE/controls/$kind
  [ -d "$dir" ] || { echo "no such control: $kind"; status=1; continue; }
  out=$HERE/controls_out/$kind$SUFFIX
  mkdir -p "$out"
  if [ "$CJDK" != 8 ]; then   # JDK 11: a fresh copy, so no class files from the JDK 8 control are reused
    rm -rf "$out/project"; cp -r "$dir" "$out/project"; rm -rf "$out/project/target" "$out/project/sleepy-records"
    dir=$out/project
  fi
  runner=()
  [ "$kind" = junit5 ] && runner=(--runner_class edu.gmu.swe.flaky.sleepy.runner.SleepyJUnit5Runner)
  echo "=== control $kind: FlakeRake on 3 tests$([ "$CJDK" != 8 ] && echo " on JDK $CJDK") ($(date +%H:%M)) ==="
  # sleepy-records is FlakeRake's own folder; clear an old one of this control only
  rm -rf "$dir/sleepy-records"
  ( cd "$dir" && python3 "$FLAKY_HOME/shell_scripts/findFlakySleeps.py" --testMethodsFile testmethods.csv \
      --runs 3 --max_hours 0.5 --logging info "${runner[@]}" > "$out/flakerake.log" 2>&1 9>&- )
  rm -rf "$out/sleepy-records"; mv "$dir/sleepy-records" "$out/sleepy-records" 2>/dev/null
  python3 - "$out/sleepy-records/report" "$kind$SUFFIX" "$CJDK" "$dir/target/test-classes" <<'PY'
import csv, glob, sys
rep, kind, cjdk, classes = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
files = glob.glob(rep + "/*minimal_sleep_report.csv")
if not files:
    print("  NO REPORT: FlakeRake did not finish, see flakerake.log in controls_out/%s" % kind); sys.exit(1)
found = {}
for r in csv.DictReader(open(files[0], encoding="utf-8")):
    t = r["TestMethod"].split("#")[1]
    found[t] = found.get(t, False) or "FlakeRakeB64StackTrace=" in r["Failure"]
want = {"testSingleThreadedNoInterception": False, "testMultipleThreadsWithSynchronized": True, "sleepsBeginOfRunThreadMethods": True}
ok = True
print("  %-40s %-14s %-10s %s" % ("test", "TD found", "expected", ""))
for t, exp in want.items():
    got = found.get(t)
    good = got == exp
    ok &= good
    print("  %-40s %-14s %-10s %s" % (t, {True: "yes", False: "no", None: "NOT IN REPORT"}[got], "yes" if exp else "no", "ok" if good else "<-- NOT AS EXPECTED"))
if cjdk != "8":  # JDK 11 (v6) extra checks: Java 11 class files were tested, and the agent did not fail on a class
    majors = set()
    for c in glob.glob(classes + "/**/*.class", recursive=True):
        with open(c, "rb") as fh:
            h = fh.read(8)
        majors.add((h[6] << 8) | h[7])
    print("  class file version of the control's test classes: %s (JDK 11 compiles Java 11 as 55)" % (", ".join(map(str, sorted(majors))) or "none found"))
    if 55 not in majors:
        print("  <-- NOT AS EXPECTED: the control was not compiled for Java 11, so Java 11 class files (nest attributes) were not part of this check")
        ok = False
    n = 0
    try:
        n = open(rep + "/../logs/sleepy-script.log", encoding="utf-8", errors="replace").read().count("SleepyInterceptingAgent$1.transform")
    except OSError:
        pass
    print("  agent exceptions while rewriting classes (sleepy-script.log): %d" % n)
    if n:
        print("  <-- NOT AS EXPECTED: the agent could not rewrite %d class(es), see sleepy-records/logs/sleepy-script.log in controls_out/%s" % (n, kind))
        ok = False
print("  => control %s: %s" % (kind, "AS EXPECTED" if ok else "NOT AS EXPECTED (see controls_out/%s/flakerake.log)" % kind))
sys.exit(0 if ok else 3)
PY
  rc=$?
  [ $rc -gt $status ] && status=$rc
done
exit $status
