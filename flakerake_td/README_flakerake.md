# FlakeRake (TD) check for the generated tests

`flaky_check.py` is `flaky_check_basic.py` plus one more subcommand, `flakerake`. Everything else in the package works as in
`README.md`. `flaky_check_basic.py` itself is unchanged.

## What it checks

TD = timing-dependent flakiness, as in FlakeRake's paper ("Automatically Reproducing Timing-Dependent Flaky Test
Failures"). FlakeRake runs one test method, inserts long sleeps (10 s by default) into the test's threads at points where
threads interact, and uses bisection to find a sleep placement that makes the test fail. A test method that can be made to
fail this way is reported as TD-flaky. The patched FlakeRake copy is in `flakerake/` (see `flakerake/PATCHES.md`).

**Supported: JDK 8 and JDK 11 (new in v6), JUnit 4 and JUnit 5 (all 48 methods).** The script picks the runner per row: JUnit 4 rows use
FlakeRake's own `SleepyTestRunner`, JUnit 5 rows use `SleepyJUnit5Runner`, which is new code added in this package (JUnit 4's
runner cannot run Jupiter tests). Same command, same output for both.

| JDK | JUnit 4 | JUnit 5 | agent |
|---|---|---|---|
| 8 | 16 methods | 11 methods (ormlite) | upstream's, ASM 5.0.3 (`flakerake/sleepy-parent`), unchanged since v5 |
| 11 | 18 methods: 18 `false` (27 Oct 2026; 7 of them took no nap, see below) | 3 methods: 3 `false` (27 Oct 2026; 2 of them took no nap, see below) | ASM 9.7.1 (`flakerake/asm9/`), built into its own Maven repository |

**Why two agents.** Upstream's agent (ASM 5.0.3, `-Xbootclasspath/p:`) cannot run on JDK 11: the JVM refuses `/p:` (removed in JDK 9), and ASM 5
cannot read Java 11 class files, not even the JDK's own `java.lang.Thread`, which the agent has to rewrite. The agent's transformer
catches the exceptions, so the test still runs and every result would silently be `false`. The JDK 11 rows therefore use an ASM 9 agent
(one changed line and a changed pom, see `flakerake/PATCHES.md`, "ASM 9 agent"); the JDK 8 rows keep the agent that produced the v5
results. JDK 17 and newer are not run (`unsupported_jdk17`, ...): not tried, and the generated tests have no JDK 17 rows.

## Per test method, `td` is

| td | Meaning |
|---|---|
| `true` | FlakeRake found a sleep placement that makes the test fail (a logged failure). Counted in `any_flaky`. |
| `false` | No thread produced a failure. The `detail` column says how much FlakeRake really did, e.g. `87 interception point(s) in 1 thread(s); in the sleeping runs 40 nap(s), 310 s of sleep inserted`. **A `false` with 0 naps (the detail then says so in capitals) means nothing was slowed, so it says little.** |
| `timeout` | A sleep made the test hang (FlakeRake's `SleepyTimeOut(ProbableDeadlock)`). Not counted in `any_flaky`. |
| `inconclusive` | The test already fails without sleeping, or the time cap was reached, or a failure happened that FlakeRake could not log. |
| `error` | FlakeRake wrote no report, or (JUnit 5) the runner found no test to run, or the java command itself failed (an exit status other than 57; a failing test gives 57), or (v6) the agent could not read the class files of this JDK (its ASM is too old; the detail then quotes the exception); see `rows/<id>/flakerake/<method>/flakerake.log` and `.../sleepy-records/logs/sleepy-script.log`. Tried again on the next run. |
| `unsupported_jdk<N>`, `archive_missing` | Not run (a JDK other than 8 and 11; or the row's archive is not set up, `archive_missing` is tried again on the next run). |

The `true` / `timeout` / `inconclusive` rules are ours (they read FlakeRake's `*_minimal_sleep_report.csv`); FlakeRake itself
only writes the report.

## Requirements (in addition to README.md)

- JDK 8 **with javac** (found in `/usr/lib/jvm`, or set `JAVA_HOME_8`); it also builds both agents
- JDK 11 **with javac** for the JDK 11 rows (`/usr/lib/jvm`, or set `JAVA_HOME_11`)
- `python3` 3.8+, Maven, internet (Maven Central, for building FlakeRake: `asm-all 5.0.3`, `junit 4.13`, and the Maven plugins it needs;
  for the JDK 11 agent also ASM 9.7.1; for JUnit 5 rows also the JUnit Platform launcher, fetched with `dependency:get` if missing)
- Linux (it uses process groups and /proc). The first `flakerake` run builds FlakeRake (`flakerake/sleepy-parent`, `mvn install`) into your local Maven
  repository (`~/.m2/repository`, or `--maven-repo`); log in `<out>/flakerake_build.log`. A runner jar built by the earlier package
  version (without the JUnit 5 runner) is detected and rebuilt. **v6:** the first JDK 11 row builds the ASM 9 agent
  (`flakerake/asm9/build_asm9_agent.py`) into `~/.m2/flakerake-asm9-repository` (`--flakerake-asm9-repo`; a Maven repository of its own,
  because the jar names are the same as the ASM 5 agent's, so the first build downloads the plugins again); log in
  `<out>/flakerake_asm9_build.log`.
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
2. **Preflight:** JDK 8 with javac, JDK 11 with javac if a JDK 11 row needs a result, Maven, 20 GB free, Maven Central reachable, `protoc` for Hadoop rows. A hard problem stops the run before anything starts.
3. **Plan:** a row is *pending* unless it already has a result. Statuses that are not a result (`build_failed`, `flakerake_error`, `would_overwrite`,
   `archive_missing`, and `unsupported_*` on a row that is supported now) are tried again; methods that already have a result are kept.
   Missing archives of pending rows are downloaded and set up (`download_zips.sh`, `setup_archives.py --only <zip>`).
4. **Controls** (below), JUnit 4 then JUnit 5, on JDK 8 for the JDK 8 rows and on JDK 11 for the JDK 11 rows. They are information only: if one is not as expected or cannot run, the main run still goes on
   and the report says **RESULTS NOT VALIDATED** (nobody can act at night, and the results stay on disk either way).
5. **Main run:** `flaky_check.py flakerake` on the pending rows. Ctrl+C is safe; start `night_run.py` again to continue.
6. **Report:** `NIGHT_REPORT.txt` and `flaky_check_out/flakerake_results.csv` (row, zip, java, junit, test, td, detail, minutes), also if the run
   was interrupted or stopped. Logs of every step are in `night_out/`; follow the main run with `tail -f night_out/flakerake_main_*.log`.

Nothing is deleted anywhere. Options: `--skip-controls`, `--redo-controls` (a control result of an earlier run is reused),
`--redo-junit5` (once: the earlier results of the JDK 8 JUnit 5 rows, which came from the argLine bug, are **moved** with their logs to
`flaky_check_out/flakerake_junit5_set_aside_<time>/` and those rows are taken out of `rows.csv` (a copy is kept there), then they are run; JUnit 4 rows are
not touched. A marker file `flaky_check_out/.junit5_results_set_aside` remembers that this was done: if the run is interrupted, start `night_run.py`
again, with or without the flag, and it continues; the new results are never moved. Delete the marker to set aside again), `--flakerake-runs`,
`--flakerake-max-hours`, `--flakerake-sleep-ms`.

## Controls: does FlakeRake find a failure when there is one?

A run that says `false` for every test only means something if FlakeRake can say `true` on this machine at all. `controls/` has
tiny tests with a known timing race, as JUnit 4 and as JUnit 5. The JUnit 4 ones are copied from FlakeRake's own integration
test (`EasySourceTest`); the JUnit 5 file is our port of them. Expected: the single-threaded test shows no TD failure, the two
multi-thread tests do. (This expectation comes from the comments in the upstream test. Observed: `AS EXPECTED` on JDK 8 with JUnit 4 and JUnit 5
(night runs of 24-26 Oct 2026) and on JDK 11 with JUnit 4 and JUnit 5 (night run of 27 Oct 2026).)

```
bash run_controls.sh junit4        # FlakeRake's own runner, as shipped
bash run_controls.sh junit5        # SleepyJUnit5Runner
CONTROL_JDK=11 bash run_controls.sh junit4   # (v6) the same on JDK 11: ASM 9 agent, control compiled for Java 11
CONTROL_JDK=11 bash run_controls.sh junit5
```
The JDK 11 controls are copied to `controls_out/<kind>_jdk11/project/` and compiled there for Java 11 (`-Dmaven.compiler.source/target=11`),
so the Java 11 nest attributes are part of the test. Besides the table they print the class file version of the compiled tests (55 expected)
and how many stack traces the agent printed (0 expected); either one wrong is `NOT AS EXPECTED`.

It prints a table and `AS EXPECTED` / `NOT AS EXPECTED`; the full output is in `controls_out/<kind>/` (`flakerake.log`, `sleepy-records/`; JDK 11: `controls_out/<kind>_jdk11/`).
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

(v6) JDK 11, JUnit 5, scimono (`out_part1_row_003`, one test method) and JDK 11, JUnit 4, crane4j (`out_part1_row_006`); same pattern, after
the JDK 11 controls were `AS EXPECTED`:

```
bash download_zips.sh scimono && python3 setup_archives.py --only scimono
python3 flaky_check.py flakerake --tests task_csvs/flaky_generated_tests.csv --archive-dir extracted \
  --only out_part1_row_003 --flakerake-runs 2 --flakerake-max-hours 0.25 --out flaky_check_out/pilot11/flakerake
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
clock, so the 48 supported methods take at most 144 hours; usually far less (see below).

## Results

`flaky_check_out/flakerake/rows.csv` (one row per test file), `rows/<id>/flakerake.csv` (one row per method: `test, td, detail,
minutes`), and `summary.csv` has two new columns, `flakerake_td` and `flakerake_detail`; `any_flaky` is also `true` when `flakerake_td` is `true`.
`summary` needs all 15 archives set up (or `--only`).

**Stage 1 (package v2, 23-24 Oct 2026): the 16 JDK 8 + JUnit 4 methods, 5 runs, 2 h cap, 10 s sleeps.** 11 `false`,
5 `inconclusive`, 0 `true`. The 5 `inconclusive` are all in the CAMEL file(s): they hit the 2-hour cap (about 119-121 minutes each), so FlakeRake had not
finished, which says nothing about whether the test is flaky. A larger cap (or a smaller sleep) might finish them; that is an open decision.
JDK 8 + JUnit 5 (11 methods, ormlite) was **not** part of stage 1.

**First JUnit 5 run (package v4, night of 24-25 Oct 2026): all 11 ormlite methods `inconclusive` after under a minute each. This is not a result.** Cause: a bug in how
FlakeRake's script reads the module's (empty) `argLine`, which broke the java command (PATCH 8 in `flakerake/PATCHES.md`). Both controls were `AS EXPECTED`. Fixed in v5; the 11 methods
have to be run again (`python3 night_run.py --redo-junit5`, which moves the invalid results aside, nothing is deleted).

**v5 night run (24-26 Oct 2026), JDK 8, 5 runs, 2 h cap, 10 s sleeps; both controls `AS EXPECTED`.** JUnit 4 (16 methods): 11 `false`
(10 with real naps; `testRemoveWithNullKey` had 0 naps, so nothing was slowed and its `false` says nothing), 5 `inconclusive` (the CAMEL rows,
2 h cap). JUnit 5, ormlite (11 methods): 11 `false` (195-495 naps each). No `true`. Of 14,877 naps in the 27 methods only 54 (0.36 %) were in the
project's own code; 20 of the 27 methods had none there; their naps were in Mockito/ByteBuddy, logging, h2, reactor/slf4j. `nap_check.py` and
`nap_where.py` (not part of this package) produced these numbers from `sleepy-records`.

## v6 (JDK 11): what is tested and what is not

Everything below was tested in a sandbox with JDK 8 (1.8.0_432), JDK 11 (11.0.25), JDK 17 (17.0.13) and Maven 3.9.11 **without Maven Central**.
Only fakes stood in for Maven (`mvn`) and for the agent build, so nothing below used a real Maven build of the ASM 9 agent or a real JDK 11 test
method. The real run came afterwards, see "First real JDK 11 run" at the end of this section.

Tested:
- The silent failure that made the port necessary was reproduced, not assumed (details in `flakerake/PATCHES.md`, "ASM 9 agent"): JDK 11 and 17
  refuse `-Xbootclasspath/p:` ("is no longer a supported option"); an agent with ASM API level 5 prints `NestMember requires ASM7` for
  20-21 times (stack traces) in a tiny run on JDK 11 and finds no failure, and nothing else shows a problem. (The real ASM 5.0.3 jar was not available offline, so
  this was shown with ASM 9 set to API level 5, plus the ASM sources; `ClassReader` of 5.0.3 itself was not run.)
- `findFlakySleeps.py` end to end against a fake `mvn` and a fake `java` reporting its version as 1.8.0_432, 11.0.25, 17.0.13, 21.0.5 and unreadable: 8 gets `-Xbootclasspath/p:`, 9 and newer
  get `/a:`, an unreadable version stops the script with a traceback (exit 1, no report -> `td error`, not a result). The four argLine cases of v5 still give a correct command.
- `agent_exceptions()` on real logs from the sandbox runs (old-API agent on JDK 11: 20 and 21 stack traces, "too old" = yes; ASM 9 agent: 0) and on made-up traces
  (`IllegalArgumentException` from `ClassReader.<init>` = too old; an unrelated test exception is not counted; a missing file gives 0).
- `do_flakerake` against a fake `findFlakySleeps.py`, 19 checks, for a JDK 8 and a JDK 11 row: the JDK 8 row gets `MAVEN_REPO` = `--maven-repo`, the JDK 11 row
  gets `--flakerake-asm9-repo`; each gets its own JDK as `JAVA_FLAKY_HOME`/`JAVA_HOME`; an agent that is too old gives `td error`; another agent exception gives the
  result plus a NOTE; exit 2 gives `error`, exit 57 `inconclusive`; no report gives `error`; a missing JDK 11 gives `flakerake_did_not_run` without starting anything.
- `build_asm9_agent.py` with a fake `mvn`: the overlay is applied to a temporary copy (`sleepy-parent/` is not touched), a missing or identical overlay file is refused,
  `~/.m2/repository` is refused, an up-to-date repository is left alone, a repository whose agent has an older ASM is not taken as up to date and is rebuilt, a failed build keeps the build folder and prints its path, a `--jdk` without javac is refused.
- `run_controls.sh`: JDK 8 mode (as in v5, `-Xbootclasspath/p:`) and `CONTROL_JDK=11` with a fake `mvn` and a hand-assembled agent: AS EXPECTED, class file version 55,
  0 agent exceptions. With an agent whose API level is 5 the JDK 11 control is **NOT AS EXPECTED** (95 agent exceptions), so the control does catch a wrong agent.
- `night_run.py` with fakes: the preflight stops without JDK 8 and without JDK 11; the controls for JDK 8 and JDK 11 are asked for; a control that cannot run flags the results
  NOT VALIDATED and the main run still goes; a cached second start does nothing; Ctrl+C (exit 130); `td=error` is listed; `--redo-junit5` (moves only the JDK 8
  JUnit 5 rows, as in v5); `--report-only`.
- `sleepy-parent/` is byte-identical to v5; only `flaky_check.py`, `night_run.py`, `run_controls.sh`, `findFlakySleeps.py` (patch 9), the two READMEs, `PATCHES.md` and the new `asm9/` differ.

**First real JDK 11 run (night run of 27 Oct 2026, WSL Ubuntu 24.04, ASM 9 agent built with Maven by `build_asm9_agent.py`):**
- The JDK 11 controls `junit4_jdk11` and `junit5_jdk11` were AS EXPECTED. The control script also checks class file version 55 and 0 agent exceptions, so the Maven build
  of the agent, including our `module-info.class` filter, worked.
- The 8 JDK 11 rows (21 methods: 18 JUnit 4, 3 JUnit 5) gave 21 `false` and 0 `true`. The main run took 8 h 16 min.
- **Backing of these 21 `false` (the detail column):** 12 methods took 210-978 naps each (rows 017, 032, 055, 059 and part2_043, 16-69 min per method). **9 took no nap and are flagged
  NOTHING WAS SLOWED, so for them the `false` says little:** scimono `out_part1_row_003` and crane4j `out_part1_row_006` (8 methods, 0 interception points) and SCB-2692
  `out_part2_row_016` (8 interception points, 0 naps). None of the 27 JDK 8 methods is flagged. No agent stack trace was found in any `sleepy-script.log`.
- A purely single-threaded test also gives 0 interception points in our sandbox on JDK 8 and JDK 11 (control `testSingleThreadedNoInterception`), so 0 points can simply mean that
  the test touches nothing FlakeRake can slow. That this is the case for the 9 methods was checked on 27 Oct 2026 in the logs of one method of each of the 3 test classes (scimono `out_part1_row_003`, crane4j `out_part1_row_006` `testGetWithArray`, SCB-2692 `out_part2_row_016`): the Java output of the first 6 runs of each (all that was printed) shows `OK`, i.e. the test passed. row_003 and row_006: 0 interception points in 0 threads, and the generated test is plain single-threaded code (reflection on private fields, list/map lookups, no thread, lock or executor; Mockito is only imported: none of the three files contains `mock(`, `when(`, `verify(`, `@RunWith`, `@ExtendWith`, `Thread`, `Executor` or `synchronized`). row_016: 8 interception points, all in JMockit internals (`mockit/internal/...`) on the main thread, and 0 naps; the generated test does not use JMockit, so this is most likely the project's own JMockit setup, and the points were probably reached before the test method started (the Java side records every point, but sleeping only starts when a `test*` or `@Before` method is entered; not verified). The other 6 crane4j methods were not opened one by one.
- All 48 methods (JDK 8 + JDK 11) are in `flakerake_results_27oct.csv`, the report is `NIGHT_REPORT_27oct.txt`: 43 `false` (of which 9 took no nap), 5 `inconclusive` (CAMEL, 2 h cap), 0 `true`.
- Environment: OpenJDK 1.8.0_504, OpenJDK 11.0.32.1, Maven 3.9.16; agent jars in `~/.m2/flakerake-asm9-repository`: sleepy-interceptor sha256 starts a7d00ef6add7, sleepy-runner 5cfc74e59e0e.

**Still open (not done, not decided):** the 5 CAMEL methods that hit the 2 h cap; more known TD tests (the positive control below is one project; `TestYarnNativeServices#testExpressUpgrade` of YARN-9405 is in an archive that is set up here but was not run, the other 24 archives with a known TD test are not set up); JDK 17 and newer (not run).

Chosen by us, not by FlakeRake: ASM 9.7.1; the `module-info` filter; the repository path `~/.m2/flakerake-asm9-repository`; "an agent stack trace that says ASM is too old turns the method
into `error`" (other agent stack traces only add a NOTE); `-Dmaven.compiler.source/target=11` for the JDK 11 controls.

## Known TD check (positive control), 27-28 Oct 2026

**Question.** Can FlakeRake say `true` on real code with a known timing-dependent failure? Without that, a `false` on the generated tests cannot be told apart from "FlakeRake cannot find TD here"
(the controls use tiny tests written for FlakeRake).

**Tests used.** ReproFlake's `test_config.csv` lists 36 tests of type `td`, all on JDK 8, in 26 archives. Only two of those archives are among the 15 of this package: CAMEL-12025
(7 `td` tests, module `components/camel-reactor`, class `ReactorStreamsServiceTest`) and YARN-9405 (1 test, `TestYarnNativeServices#testExpressUpgrade`, not run). The 7 CAMEL-12025 tests were run on JDK 8 with the
JUnit 4 runner. Checked in the archive: the test class imports `org.junit.Test`, and nothing in the module's `src/test` uses `org.junit.jupiter`.

**How (a workaround, not a feature of the package).** `flaky_check.py` runs generated test files and refuses to overwrite a test file that already exists in the module (`would_overwrite`). For an existing test, the CSV row
names the known test in `generated_test` and `focal_from_test`, and `test_file` points to a tiny placeholder class (`public class KnownTdPlaceholderCamel {}`) that the package copies into the module for the run and removes afterwards.
(Checked in a sandbox with a fake archive, also with the archive's real nested layout `CAMEL-12025/CAMEL-12025/Flaky/`: the archive was byte-identical afterwards. The real archive, build and FlakeRake were first used in the pilot below.)
`known_td/setup_known_td.sh` creates the two placeholder files and `known_td/known_td_tests.csv` (8 rows: the 7 CAMEL tests as `known_td_row_900`, the YARN test as `known_td_row_901`).
Chosen by us: the placeholder trick, the row numbers 900 and 901, `junit` = 4, and `project` / `sha`, which are copied from the generated CAMEL-12025 and YARN-9405 rows of `task_csvs/flaky_generated_tests.csv` (FlakeRake only uses them as labels).

```
cd ~/flakecheck/flaky_check_package            # the package folder (where flaky_check.py is)
bash /path/to/known_td/setup_known_td.sh       # creates known_td/ in the package folder
# pilot: one method, 2 runs, 15 minute cap, its own output folder
python3 flaky_check.py flakerake --tests known_td/known_td_tests.csv --archive-dir extracted \
  --out flaky_check_out/known_td_pilot --only ReactorStreamsServiceTest#testFromStreamTimer \
  --flakerake-runs 2 --flakerake-max-hours 0.25 2>&1 | tee known_td_pilot.log
# full run of the 7 CAMEL tests (defaults: 5 runs, 2 h cap, 10 s sleeps), up to 14 hours, inside tmux
python3 flaky_check.py flakerake --tests known_td/known_td_tests.csv --archive-dir extracted \
  --out flaky_check_out/known_td --only known_td_row_900 2>&1 | tee known_td_camel.log
```
`--only` is a substring match (`testTo` would also match `testToFunction`, ...), and a row that is finished is skipped on a second start (`--redo`), which is why the pilot has its own `--out`.

**Results.** Pilot (`testFromStreamTimer`, 2 runs, 15 minute cap): `true` after 16.3 minutes (first failure `AssertionError: expected:<30> but was:<0>`); the failing rows were all for one thread, the slowed lines started with
`org/apache/camel/impl/DefaultInflightRe...` and `reactor/core/publisher/FluxCreate...` / `FluxOnBackpressu...` (cut off in the output we looked at), 4 other threads gave `NoFail` and one more hit the cap. Full run (night of 27-28 Oct 2026):

| method | td | minutes | failing thread analysis rows | failures in the runs without sleeping |
|---|---|---|---|---|
| `testFrom` | true | 118.7 | 76 | 0 |
| `testFromStreamTimer` | true | 120.3 | 76 | 0 |
| `testMultipleSubscriptionsWithTimer` | true | 120.1 | 78 | 0 |
| `testTo` | true | 121.1 | 63 | 0 |
| `testToFunction` | true | 121.1 | 63 | 0 |
| `testToFunctionWithExchange` | true | 120.5 | 63 | 0 |
| `testToWithExchange` | true | 120.3 | 63 | 0 |

7 `true`, 0 `false`; 842 minutes (14.0 hours) in total. The last column is the number of `Unaltered flaky_fail_attempt` lines in each method's `sleepy-script.log`: the test never failed in the runs without sleeping, so the failures came from the slowing.
Each method used about the whole 2 h cap and still ended `true`, because failing rows were found (`classify_flakerake` looks for a failure first). Output: `flaky_check_out/known_td/` and `flaky_check_out/known_td_pilot/` (kept); the summary is `known_td/known_td_results_28oct.txt`.

**What this shows and what it does not.** It shows that on a real project the setup (agent, runner, JDK 8, our Python wiring) can produce `true` for tests that ReproFlake lists as timing-dependent. It does not show a detection rate:
one project, one test class (the 7 tests are methods of one class, so they are not independent), and no information about false positives. We do not know how ReproFlake assigned the `td` label. For comparison: the 5 generated CAMEL-12025 methods hit the same 2 h cap without a failure
(`inconclusive`); that does not say whether they are flaky.

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

- v5: the argLine regex of PATCH 8 on sample `mvn -X` output (the old regex reproduces the garbage seen in the real log, the new one gives an
  empty value; non-empty values come out the same), and the real `setup()` of `findFlakySleeps.py` against a fake `mvn` (empty argLine -> empty,
  `-Xmx256m -Dx=y` -> unchanged), the exit-status guard (exit 2 -> `td error`, exit 57 stays `inconclusive`).
  The whole `findFlakySleeps.py` run end to end against a fake `mvn` and a fake `java` (empty, non-empty, absent and `null` argLine): v5 builds a
  correct java command every time; with the v4 file the same test reproduces the real failure (`sh: Syntax error: "(" unexpected`, `AlreadyFailsStably`).
  `--redo-junit5` as "set aside once" (moves exactly the 6 JUnit 5 rows, keeps the JUnit 4 rows, resumes after an interruption with and without the flag, does not
  move new results, moves nothing if the preflight stops the run). The `false` evidence (`sleep_evidence`) on report files in the format the Java side writes.
  Reading the agent source (`InterceptingMV`): sleeping starts when a method whose name starts with `test` or whose last annotation ends in `Test;`
  / `Before;` is entered, so it starts in all 11 ormlite methods (all are named `test...` and use `@Test`).

**Not tested (needs a machine with Maven Central and JDK 8):**
- a real run of the ormlite tests with the FlakeRake agent and real JUnit Jupiter + Mockito (the JUnit 5 control did run, but its code is tiny);
  after the argLine fix this is the first time the ormlite command line is correct, so the pilot is the real test,
- the Maven build of `sleepy-runner` with the new pom entry and of both control projects,
- JUnit 5 `-Dtest=Class#method` through surefire in `findFlakySleeps.py`'s setup step on the ormlite module,
- whether the controls give the expected result (see above).

- `night_run.py` itself on a real machine (its preflight needs JDK 8, Maven and Maven Central),
- `download_zips.sh` / `setup_archives.py` for the ormlite archive from `night_run.py` (they are the existing scripts, called unchanged).

Chosen by us, not by FlakeRake: control runs = 3 and cap = 30 minutes per method; free disk space limit 20 GB; "control not as expected does not stop the main run"; launcher 1.8.2 as the compile-time version; the `true / false / timeout / inconclusive`
classification; the 2-hour analysis cap and 3-hour wall clock per method.
