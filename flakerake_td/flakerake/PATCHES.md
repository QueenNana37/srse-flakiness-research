# Changes to FlakeRake in this copy

Source: https://github.com/gmu-swe/flakerake, commit `95c9f2887505cef974438f4155ddef0129c4209e` (22 Jan 2024).
License: MIT, as declared in the root `pom.xml` of that commit (we did not check for a separate LICENSE file).
Only what `flaky_check.py flakerake` needs was copied: `pom.xml`, `sleepy-parent/` (the agent and the JUnit 4 runner)
and from `shell_scripts/`: `findFlakySleeps.py`, `run_experiments.py`, `csv_utils.py`, `maven-repo-fix-settings.xml`,
`__init__.py`. The root `pom.xml` is kept unchanged for completeness but `flaky_check.py` does not build it (it only adds
Sonatype release tooling); it builds `sleepy-parent/pom.xml`.

Compared with upstream, **three files are changed and one is new**:

1. `shell_scripts/findFlakySleeps.py` (patches 1-7 below, all marked `PATCH n` in the file)
2. `sleepy-parent/sleepy-runner/pom.xml` (one dependency added)
3. NEW `sleepy-parent/sleepy-runner/src/main/java/edu/gmu/swe/flaky/sleepy/runner/SleepyJUnit5Runner.java`

Everything else is byte-for-byte the upstream file.

## findFlakySleeps.py

| # | Change | Why |
|---|---|---|
| 1 | The `pkill --parent 1 java` and `killall -9 java` after every run are gone. New `run_group()` runs each test run in its own process group and kills only that group on a timeout and afterwards. | Upstream kills every Java process of the user, including unrelated Maven or test runs. |
| 2 | New option `--max_hours` (default 24 = upstream's fixed value) replaces the hard-coded 24-hour analysis cap per test method. | `flaky_check.py` passes 2. |
| 3 | The two `mvn` calls in `setup()` append the environment variable `FLAKERAKE_MVN_ARGS` (we set `-Dmaven.repo.local=<repo>`). | So FlakeRake uses the same local Maven repository as the other checks. |
| 4 | New option `--runner_class` (default upstream's `SleepyTestRunner`, JUnit 4). | Lets the JUnit 5 runner be selected without touching the script again. |
| 5 | `logging.warn` -> `logging.warning`. | `logging.warn` is removed in Python 3.13. |
| 6 | `do_mvn_install()` does nothing when `FLAKERAKE_SKIP_INSTALL=1`. | `flaky_check.py` has already built the module's dependencies; upstream would `mvn install` the whole project again. |
| 7 | If the environment variable `FLAKERAKE_EXTRA_CP` is set, its value is appended to the class path the runner is started with (`clazz_path`). | The JUnit 5 runner needs `junit-platform-launcher` (and the engine) on the class path; the module's own test class path often lacks the launcher. `flaky_check.py` sets it for JUnit 5 rows only. |

## SleepyJUnit5Runner (new Java file) and the runner pom

Upstream's only runner, `SleepyTestRunner`, uses JUnit 4's `JUnitCore`, which cannot run a JUnit 5 (Jupiter) test.
`SleepyJUnit5Runner` does the same job through the JUnit Platform Launcher (`selectMethod(class, method)`):

- same arguments, same files, same exit codes (0 = pass, 1337 = fail) as `SleepyTestRunner`, so `findFlakySleeps.py`
  needs no other change; a failing run writes `./sleepy-records/internal/failure.log` like the original;
- **difference:** JUnit 4 reports an unknown test name as a failure. The Launcher just finds nothing and reports success. A run
  in which no test was started (wrong name, test disabled, skipped, aborted) would then count as "no failure" for ever, a silent
  false negative. Here it is written to `failure.log` as `java.lang.IllegalStateException: SLEEPY_JUNIT5_NO_TEST_EXECUTED for
  <Class#method> (started=.., skipped=.., found=..)` and exits 1337. `flaky_check.py` turns that into `td = error`.
- `sleepy-runner/pom.xml`: `org.junit.platform:junit-platform-launcher:1.8.2`, scope `provided`. Only so the class compiles;
  it is not packaged, the real launcher comes from the module's own dependencies or from `FLAKERAKE_EXTRA_CP`.
  (1.8.2 is the version we compiled against; `flaky_check.py` picks the launcher version for the run from the module's own
  Jupiter/Platform version.)

## Known limits (upstream FlakeRake or our runner, not fixed here)

- FlakeRake needs JDK 8 (`-Xbootclasspath/p:`, ASM 5.0.3). JDK 11 rows are not run.
- The agent does not instrument classes whose name starts with `org/junit`, so sleeps inside JUnit's own code are not tried
  (also for JUnit 5).
- Upstream strips `@Test(timeout = ...)` (JUnit 4) so that a sleep does not trigger the timeout. There is no equivalent for
  JUnit 5's `@Timeout`: a JUnit 5 test with `@Timeout` can fail because of the inserted sleep, and that is then counted as a
  failure that FlakeRake found.
- The paper's evaluation ran on Ubuntu 20 with Oracle Java 1.8.0_301. It does not say anything about JUnit versions; JUnit 5
  support here is ours and has not been checked by the FlakeRake authors.
