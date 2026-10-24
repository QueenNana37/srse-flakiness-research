#!/bin/bash
# Controls for FlakeRake: three small tests with a known timing race (+ one single-threaded test), as JUnit 4 and as
# JUnit 5. Shows whether FlakeRake, as set up here, finds a failure when there is one. Needs JDK 8 with javac, Maven,
# python3, internet (Maven Central). Takes a while (see README_flakerake.md).
#   bash run_controls.sh junit4      only the JUnit 4 control
#   bash run_controls.sh junit5      only the JUnit 5 control (tests SleepyJUnit5Runner)
#   bash run_controls.sh             both
# Output: controls_out/<kind>/ (FlakeRake's report + logs) and a table at the end of each run.
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

# Build FlakeRake (same command as flaky_check.py) unless the installed runner jar already has the JUnit 5 runner.
if ! { [ -f "$RUNNER_JAR" ] && unzip -l "$RUNNER_JAR" 2>/dev/null | grep -q SleepyJUnit5Runner; }; then
  echo "Building FlakeRake (JDK 8) ..."
  mvn -B -q -f "$HERE/flakerake/sleepy-parent/pom.xml" install -DskipTests -Dmaven.repo.local="$REPO" 9>&- || { echo "FlakeRake build failed"; exit 1; }
fi

export FLAKY_HOME=$HERE/flakerake MAVEN_REPO=$REPO JAVA_FLAKY_HOME=$JDK8
export FLAKERAKE_SKIP_INSTALL=1 FLAKERAKE_MVN_ARGS="-Dmaven.repo.local=$REPO" FLAKY_MVN_INSTALL_OPTS="-B -fn -DskipITs"
unset FLAKERAKE_EXTRA_CP   # the control's pom has the JUnit launcher on its test class path

status=0
for kind in $kinds; do
  rc=0
  dir=$HERE/controls/$kind
  [ -d "$dir" ] || { echo "no such control: $kind"; status=1; continue; }
  out=$HERE/controls_out/$kind
  mkdir -p "$out"
  runner=()
  [ "$kind" = junit5 ] && runner=(--runner_class edu.gmu.swe.flaky.sleepy.runner.SleepyJUnit5Runner)
  echo "=== control $kind: FlakeRake on 3 tests ($(date +%H:%M)) ==="
  # sleepy-records is FlakeRake's own folder; clear an old one of this control only
  rm -rf "$dir/sleepy-records"
  ( cd "$dir" && python3 "$FLAKY_HOME/shell_scripts/findFlakySleeps.py" --testMethodsFile testmethods.csv \
      --runs 3 --max_hours 0.5 --logging info "${runner[@]}" > "$out/flakerake.log" 2>&1 9>&- )
  rm -rf "$out/sleepy-records"; mv "$dir/sleepy-records" "$out/sleepy-records" 2>/dev/null
  python3 - "$out/sleepy-records/report" "$kind" <<'PY'
import csv, glob, sys
rep, kind = sys.argv[1], sys.argv[2]
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
print("  => control %s: %s" % (kind, "AS EXPECTED" if ok else "NOT AS EXPECTED (see controls_out/%s/flakerake.log)" % kind))
sys.exit(0 if ok else 3)
PY
  rc=$?
  [ $rc -gt $status ] && status=$rc
done
exit $status
