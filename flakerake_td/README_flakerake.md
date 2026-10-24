# FlakeRake (TD) check for the generated tests

`flaky_check.py` is `flaky_check_basic.py` plus one more subcommand, `flakerake`. Everything else in the package works as in
`README.md`. `flaky_check_basic.py` itself is unchanged.

## What it checks

TD = timing-dependent flakiness, as in FlakeRake's paper ("Automatically Reproducing Timing-Dependent Flaky Test
Failures"). FlakeRake runs one test method, inserts long sleeps (10 s by default) into the test's threads at points where
threads interact, and uses bisection to find a sleep placement that makes the test fail. A test method that can be made to
fail this way is reported as TD-flaky. The patched FlakeRake copy is in `flakerake/` (see `flakerake/PATCHES.md`).

**Supported: JDK 8, JUnit 4 and JUnit 5 (27 of the 48 methods).** The script picks the runner per row: JUnit 4 rows use
FlakeRake's own `SleepyTestRunner`, JUnit 5 rows use `SleepyJUnit5Runner`, which is new code added in this package (JUnit 4's
runner cannot run Jupiter tests). Same command, same output for both.

| JDK | JUnit 4 | JUnit 5 |
|---|---|---|
| 8 | 16 methods, run | 11 methods (ormlite), run |
| 11 | 18 methods, **not run** (`unsupported_jdk11`) | 3 methods, **not run** (`unsupported_jdk11`) |

JDK 11 is not supported because FlakeRake's agent only works on JDK 8 (`-Xbootclasspath/p:`, ASM 5.0.3). That would need a port
of the agent itself, not a change in this script.

## Per test method, `td` is

| td | Meaning |
|---|---|
| `true` | FlakeRake found a sleep placement that makes the test fail (a logged failure). Counted in `any_flaky`. |
| `false` | No thread produced a failure. |
| `timeout` | A sleep made the test hang (FlakeRake's `SleepyTimeOut(ProbableDeadlock)`). Not counted in `any_flaky`. |
| `inconclusive` | The test already fails without sleeping, or the time cap was reached, or a failure happened that FlakeRake could not log. |
| `error` | FlakeRake wrote no report, or (JUnit 5) the runner found no test to run; see `rows/<id>/flakerake/<method>/flakerake.log`. Tried again on the next run. |
| `unsupported_jdk11`, `archive_missing` | Not run (JDK 11; or the row's archive is not set up, `archive_missing` is tried again on the next run). |

The `true` / `timeout` / `inconclusive` rules are ours (they read FlakeRake's `*_minimal_sleep_report.csv`); FlakeRake itself
only writes the report.

## Requirements (in addition to README.md)

- JDK 8 **with javac** (found in `/usr/lib/jvm`, or set `JAVA_HOME_8`)
- `python3` 3.8+, Maven, internet (Maven Central, for building FlakeRake: `asm-all 5.0.3`, `junit 4.13`, and the Maven plugins it needs;
  for JUnit 5 rows also the JUnit Platform launcher, fetched with `dependency:get` if missing)
- Linux (it uses process groups and /proc). The first `flakerake` run builds FlakeRake (`flakerake/sleepy-parent`, `mvn install`) into your local Maven
  repository (`~/.m2/repository`, or `--maven-repo`); log in `<out>/flakerake_build.log`. A runner jar built by the earlier package
  version (without the JUnit 5 runner) is detected and rebuilt.
- **`protoc` for the Hadoop archives.** Hadoop/YARN modules need the Protocol Buffers compiler in the version their
  `BUILDING.txt` names; for the YARN-9405 snapshot that is **2.5.0**. Without it the build stops at hadoop-common with a protoc error and the
  row gets `build_failed`. The official binary is on Maven Central (`com.google.protobuf:protoc:2.5.0`, classifier `linux-x86_64`);
  point `HADOOP_PROTOC_PATH` at it. Other Hadoop units from other commits may need another version (check that commit's `BUILDING.txt`).
  This package does not install protoc for you.

## Setup

If `python3 setup_archives.py` has trouble downloading (it uses Python's urllib), download the zips with curl first. It resumes
and checks sizes. `bash download_zips.sh marineapi` for one archive (the name only has to contain the text), `bash download_zips.sh` for all 15. Then:

```
python3 setup_archives.py --only marineapi     # one archive (without --only: all 15)
```

## Unattended run: `night_run.py`

One command that does everything below in the right order and checks itself, for a run nobody watches:

```
python3 night_run.py                   # inside tmux: controls, then every row that has no result yet
python3 night_run.py --report-only     # rewrite NIGHT_REPORT.txt now (safe while it runs)
```

1. **Lock:** only one check at a time (`.flaky_check.lock`). A second start (`night_run.py`, `flaky_check.py`, `run_controls.sh`) is refused
   with the message of who holds the lock; nothing is touched. (This replaces "run one check at a time" as a rule you have to remember.)
2. **Preflight:** JDK 8 with javac, Maven, 20 GB free, Maven Central reachable, `protoc` for Hadoop rows. A hard problem stops the run before anything starts.
3. **Plan:** a row is *pending* unless it already has a result. Statuses that are not a result (`build_failed`, `flakerake_error`, `would_overwrite`,
   `archive_missing`, and `unsupported_*` on a row that is supported now) are tried again; methods that already have a result are kept.
   Missing archives of pending rows are downloaded and set up (`download_zips.sh`, `setup_archives.py --only <zip>`).
4. **Controls** (below), JUnit 4 then JUnit 5. They are information only: if one is not as expected or cannot run, the main run still goes on
   and the report says **RESULTS NOT VALIDATED** (nobody can act at night, and the results stay on disk either way).
5. **Main run:** `flaky_check.py flakerake` on the pending rows. Ctrl+C is safe; start `night_run.py` again to continue.
6. **Report:** `NIGHT_REPORT.txt` and `flaky_check_out/flakerake_results.csv` (row, zip, java, junit, test, td, detail, minutes), also if the run
   was interrupted or stopped. Logs of every step are in `night_out/`; follow the main run with `tail -f night_out/flakerake_main_*.log`.

Nothing is deleted anywhere. Options: `--skip-controls`, `--redo-controls` (a control result of an earlier run is reused), `--flakerake-runs`,
`--flakerake-max-hours`, `--flakerake-sleep-ms`.

## Controls: does FlakeRake find a failure when there is one?

A run that says `false` for every test only means something if FlakeRake can say `true` on this machine at all. `controls/` has
tiny tests with a known timing race, as JUnit 4 and as JUnit 5. The JUnit 4 ones are copied from FlakeRake's own integration
test (`EasySourceTest`); the JUnit 5 file is our port of them. Expected: the single-threaded test shows no TD failure, the two
multi-thread tests do. (This expectation comes from the comments in the upstream test; **we have not observed it yet**, that is
what this run is for.)

```
bash run_controls.sh junit4        # FlakeRake's own runner, as shipped
bash run_controls.sh junit5        # SleepyJUnit5Runner
```

It prints a table and `AS EXPECTED` / `NOT AS EXPECTED`; the full output is in `controls_out/<kind>/` (`flakerake.log`, `sleepy-records/`).
Exit code: 0 = as expected, 3 = ran but not as expected, 4 = another check holds the lock (not started), 1 = could not run.
Uses 3 runs and a 30-minute cap per test method (our values, not FlakeRake's defaults). It takes the same lock as `flaky_check.py`.

## Pilot (one test file)

JUnit 4, marineapi:

```
python3 flaky_check.py flakerake --tests task_csvs/flaky_generated_tests.csv --archive-dir extracted \
  --only out_part2_row_045 --flakerake-runs 2 --flakerake-max-hours 0.25 --out flaky_check_out/pilot/flakerake
```

JUnit 5, ormlite (2 test methods; set the archive up first with `bash download_zips.sh ormlite` and
`python3 setup_archives.py --only ormlite`):

```
python3 flaky_check.py flakerake --tests task_csvs/flaky_generated_tests.csv --archive-dir extracted \
  --only out_part1_row_046 --flakerake-runs 2 --flakerake-max-hours 0.25 --out flaky_check_out/pilot5/flakerake
```

Look for `=> ...` at the end of the row. `no_flaky_found`, `flaky_found` or `inconclusive` all mean FlakeRake ran; `flakerake_did_not_run`,
`flakerake_error`, `would_overwrite` or a build error mean a setup problem. A JUnit 5 method with `td error` and the text
`SLEEPY_JUNIT5_NO_TEST_EXECUTED` means the runner started but the JUnit Platform ran no test (wrong class/method name, no engine on the class path, or the test was skipped):
that is a setup problem, not a result. Logs: `<out>/rows/<id>/flakerake/<method>/flakerake.log` and the FlakeRake reports in `.../sleepy-records/report/`.
Delete the pilot folders afterwards.

## Full run

Run one check at a time (they share the project folders), inside tmux or with `setsid nohup`:

```
python3 flaky_check.py flakerake --tests task_csvs/flaky_generated_tests.csv --archive-dir extracted 2>&1 | tee flaky_flakerake.log
python3 flaky_check.py summary   --tests task_csvs/flaky_generated_tests.csv --archive-dir extracted
```

Resumable: finished methods are skipped (`--redo` redoes them). **Ctrl+C is safe:** the method in progress is stopped, its leftovers
(`flakerake_input.csv`, `sleepy-records` in the module) are removed or moved into the method's output folder, and the method is
redone on the next run. Leftovers from an older interrupted run are moved (not deleted) to `rows/<id>/leftover_<time>/` and the run goes on.
(In the earlier package version they made the next run stop with `would_overwrite`.)

The runner is chosen per row from the `junit` column, and checked against the imports of the generated test files; if they disagree the
runner for the version the test is really written in is used, with a WARNING. (For all 23 test files of the current CSV they agree.)

Options: `--flakerake-max-hours` (default 2, upstream 24), `--flakerake-runs` (default 5, FlakeRake's own), `--flakerake-sleep-ms` (default 10000, FlakeRake's own).
Time: FlakeRake needs minutes to hours per test method. Each method is limited to 2 hours of analysis and to 3 hours wall
clock, so the 27 supported methods take at most 81 hours; usually far less (see below).

## Results

`flaky_check_out/flakerake/rows.csv` (one row per test file), `rows/<id>/flakerake.csv` (one row per method: `test, td, detail,
minutes`), and `summary.csv` has two new columns, `flakerake_td` and `flakerake_detail`; `any_flaky` is also `true` when `flakerake_td` is `true`.
`summary` needs all 15 archives set up (or `--only`).

**Stage 1 (package v2, 23-24 Oct 2026): the 16 JDK 8 + JUnit 4 methods, 5 runs, 2 h cap, 10 s sleeps.** 11 `false`,
5 `inconclusive`, 0 `true`. The 5 `inconclusive` are all in the CAMEL file(s): they hit the 2-hour cap (about 119-121 minutes each), so FlakeRake had not
finished, which says nothing about whether the test is flaky. A larger cap (or a smaller sleep) might finish them; that is an open decision.
JDK 8 + JUnit 5 (11 methods, ormlite) was **not** part of stage 1.

## What is tested and what is not (package v3)

Tested without the real tools (in a sandbox with JDK 21 and no access to Maven Central):
- `SleepyJUnit5Runner` compiles (`javac --release 8`, against `junit-platform-launcher` 1.8.2 and ASM) and, run against a fake JUnit Platform engine,
  gives exit 0 for a passing test, 1337 plus a `failure.log` with the stack trace for a failing one, and 1337 plus the `SLEEPY_JUNIT5_NO_TEST_EXECUTED` marker for a missing or skipped test.
- The Python wiring (`do_flakerake`) against a fake `findFlakySleeps.py`: JUnit 4 rows are unchanged (no `--runner_class`, no extra class path);
  JUnit 5 rows pass `--runner_class` and `FLAKERAKE_EXTRA_CP`; the no-test marker gives `td error`; Ctrl+C leaves nothing behind.
- The table of `run_controls.sh` on fake reports. The shell script and the control projects pass a syntax check (`bash -n`, `javac` against stand-in libraries).

- v4: the lock (all three entry points refuse a second start, and release it when the holder ends), the retry of old statuses
  (`unsupported_junit5`, `build_failed` rows are tried again; the same scenario with the v3 file skips the 6 JUnit 5 rows), a missing archive
  (row `archive_missing`, the run goes on), and `night_run.py` with the steps replaced by fakes (archive download/setup, controls cached and
  not cached, control not as expected, control cannot run, Ctrl+C, a method with `td=error`, `--report-only`).

**Not tested (needs a machine with Maven Central and JDK 8):**
- a real run with the FlakeRake agent and real JUnit Jupiter (does the agent insert sleeps in Jupiter's threads the way it does for JUnit 4?),
- the Maven build of `sleepy-runner` with the new pom entry and of both control projects,
- JUnit 5 `-Dtest=Class#method` through surefire in `findFlakySleeps.py`'s setup step on the ormlite module,
- whether the controls give the expected result (see above).

- `night_run.py` itself on a real machine (its preflight needs JDK 8, Maven and Maven Central),
- `download_zips.sh` / `setup_archives.py` for the ormlite archive from `night_run.py` (they are the existing scripts, called unchanged).

Chosen by us, not by FlakeRake: control runs = 3 and cap = 30 minutes per method; free disk space limit 20 GB; "control not as expected does not stop the main run"; launcher 1.8.2 as the compile-time version; the `true / false / timeout / inconclusive`
classification; the 2-hour analysis cap and 3-hour wall clock per method.
