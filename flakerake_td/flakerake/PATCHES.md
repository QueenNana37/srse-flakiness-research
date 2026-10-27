# Changes to FlakeRake in this copy

Source: https://github.com/gmu-swe/flakerake, commit `95c9f2887505cef974438f4155ddef0129c4209e` (22 Jan 2024).
License: MIT, as declared in the root `pom.xml` of that commit (we did not check for a separate LICENSE file).
Only what `flaky_check.py flakerake` needs was copied: `pom.xml`, `sleepy-parent/` (the agent and the JUnit 4 runner)
and from `shell_scripts/`: `findFlakySleeps.py`, `run_experiments.py`, `csv_utils.py`, `maven-repo-fix-settings.xml`,
`__init__.py`. The root `pom.xml` is kept unchanged for completeness but `flaky_check.py` does not build it (it only adds
Sonatype release tooling); it builds `sleepy-parent/pom.xml`.

Compared with upstream, **two files are changed and one is new** (checked byte for byte against the upstream commit: the other 16 copied files are identical):

1. `shell_scripts/findFlakySleeps.py` (patches 1-9 below, all marked `PATCH n` in the file)
2. `sleepy-parent/sleepy-runner/pom.xml` (one dependency added)
3. NEW `sleepy-parent/sleepy-runner/src/main/java/edu/gmu/swe/flaky/sleepy/runner/SleepyJUnit5Runner.java`

Everything else under `sleepy-parent/` is byte-for-byte the upstream file. **v6 adds the folder `asm9/`** (not part of upstream; the ASM 9
agent for JDK 11, see "ASM 9 agent" below) and leaves `sleepy-parent/` exactly as it was in v5, so the JDK 8 agent is unchanged.

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
| 8 | The regex that reads the module's `argLine` from `mvn test -X` is now `DEBUG.*argLine[ \t]+=[ \t]*(.*)` (upstream: `/*DEBUG.*argLine\s+=\s+(.+)`), the value is stripped, and a literal `null` is treated as empty. | **Bug found on the first real JUnit 5 run (ormlite).** When the module's argLine is empty, Maven prints `(f) argLine = ` and nothing else; upstream's `\s+` ran over the line break and `(.+)` captured the NEXT debug line (`[DEBUG]   (s) basedir = ...`), which landed in the java command line (`sh: Syntax error: "(" unexpected`). Every run then "failed without sleeping" and all 11 methods came out `inconclusive`. With a non-empty argLine the result is the same as upstream's. |
| 9 | **(v6)** `-Xbootclasspath/p:` becomes `-Xbootclasspath/a:` when `JAVA_FLAKY_HOME` is JDK 9 or newer (new function `boot_flag()`, which reads `java -version`). JDK 8 keeps `/p:`, exactly as upstream. | `-Xbootclasspath/p` was removed in JDK 9 (JEP 261; Oracle JDK 9 release notes), `/a` still exists (Oracle JDK 11 `java` documentation). Checked on JDK 11.0.25 and 17.0.13 in a sandbox: `java -Xbootclasspath/p:... -version` prints `-Xbootclasspath/p is no longer a supported option.` and `Error: Could not create the Java Virtual Machine.` |

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

- JDK 8 uses upstream's agent (ASM 5.0.3). **JDK 11 uses the ASM 9 agent below.** JDK 17 and newer are not run (the ASM 9 agent
  passed the three control tests on JDK 17 in a sandbox, but nothing more was tried there, and the generated tests have no JDK 17 rows).
- The agent does not instrument classes whose name starts with `org/junit`, so sleeps inside JUnit's own code are not tried
  (also for JUnit 5).
- Upstream strips `@Test(timeout = ...)` (JUnit 4) so that a sleep does not trigger the timeout. There is no equivalent for
  JUnit 5's `@Timeout`: a JUnit 5 test with `@Timeout` can fail because of the inserted sleep, and that is then counted as a
  failure that FlakeRake found.
- The agent starts sleeping when it enters a method whose name starts with `test` (and that has a `V` in its descriptor), or whose
  last annotation ends in `Test;` or `Before;` (`InterceptingMV.onMethodEnter`). That fits JUnit 4 and the `@Test` of JUnit 5. JUnit 5's
  `@BeforeEach` / `@BeforeAll` do not end in `Before;`, so code inside them is **not** slowed (a JUnit 4 `@Before` is). And a JUnit 5 test
  whose name does not start with `test` and whose last annotation is not `@Test` (for example `@Test @DisplayName("x") void shouldX()`)
  would never trigger the sleeping at all and come out as `false`; the `detail` of a `false` result therefore says how many naps were really
  taken. All 11 ormlite methods start with `test` and use `@Test`.
- The paper's evaluation ran on Ubuntu 20 with Oracle Java 1.8.0_301. It does not say anything about JUnit versions; JUnit 5
  support here is ours and has not been checked by the FlakeRake authors.

## ASM 9 agent (v6, JDK 11): `asm9/`

**Why.** The agent rewrites classes with ASM 5.0.3. On JDK 11 that fails, and silently: the agent's class transformer catches every
exception, prints the stack trace and leaves the class as it was, so the test still runs and FlakeRake reports `NoFail` for every
thread. Two facts cause it (the second one was seen in a sandbox run, see below):

- Java 11 class files carry nest attributes (JEP 181, class file version 55). ASM reads them only with an API level of 7 or higher
  (ASM's `ClassVisitor.visitNestHost` / `visitNestMember` throw `UnsupportedOperationException: ... requires ASM7` otherwise);
  ASM 5 also throws `IllegalArgumentException` from `ClassReader` for class file versions it does not know (sources: ASM 7.1 and
  9.0 source, a Spigot BuildTools stack trace, an OpenJDK core-libs-dev mail; **not tested on ASM 5.0.3 itself**, its jar was not
  available offline).
- On JDK 11 the classes the agent must rewrite in the JDK itself (`java.lang.Thread`, `java.util.concurrent.ForkJoinTask`,
  `java.util.concurrent.FutureTask`) are version 55 with nest attributes (checked with `javap` on JDK 8, 11, 17). So even a project
  compiled for Java 8 loses all thread tracking on JDK 11 with the ASM 5 agent.

**What.** `asm9/overlay/` holds the two files that differ from `sleepy-parent/sleepy-interceptor/`:

| File | Change |
|---|---|
| `pom.xml` | `org.ow2.asm:asm-all:5.0.3` replaced by `asm`, `asm-commons`, `asm-tree` **9.7.1** (the version is our choice: it is the one that was tested; the ASM site lists support for class files up to Java 24). `module-info.class` of the ASM jars is filtered out of the shaded jar (our addition so that the shade plugin does not have to process a Java 9 class file; untested, because Maven Central was not reachable in the sandbox). The relocation `org.objectweb.asm` -> `agent.org.objectweb.asm` is upstream's. |
| `src/main/java/.../SleepyInterceptingAgent.java` | one line: `new InterceptingCV(ASM5, cw)` -> `new InterceptingCV(ASM9, cw)`. This API level reaches all method visitors, they get it from `InterceptingCV`. |

`asm9/build_asm9_agent.py` copies `sleepy-parent/` to a temporary folder, puts the two files over it and runs the same Maven command as
for the JDK 8 agent (`mvn -B -f sleepy-parent/pom.xml install -DskipTests -Dmaven.repo.local=<repo>`, built with JDK 8) into **its own
Maven repository** (default `~/.m2/flakerake-asm9-repository`, `--flakerake-asm9-repo`). The jar names are the same as the ASM 5 agent's, which
is why the two must not share a repository; `findFlakySleeps.py` reads the jars through the environment variable `MAVEN_REPO` (two places,
checked), which `flaky_check.py` sets per row: `--maven-repo` for JDK 8 rows, `--flakerake-asm9-repo` for JDK 11 rows. The script refuses
`~/.m2/repository` as the repository, and it checks the result: both jars present, SleepyJUnit5Runner in the runner jar, and the shaded
`Opcodes` class has an `ASM9` constant (ASM 5.0.3's does not).

**Guard against the silent failure.** After each method, `flaky_check.py` reads `sleepy-records/logs/sleepy-script.log`, where the agent's
stack traces end up, and counts those that come from the agent's transformer. If one says that ASM is too old for a class
(`... requires ASM7`, or an `IllegalArgumentException` from `ClassReader.<init>`) the method gets `td = error` instead of a result. Any
other agent stack trace is only added to the `detail` as a NOTE. `run_controls.sh` on JDK 11 fails the control if the agent printed any.

**What was tested (sandbox, JDK 8/11/17, no real Maven build):** the ASM 9 agent, built with javac and a small relocation program instead of
Maven, passed the three control tests on JDK 8, 11 and 17 through the real `findFlakySleeps.py`. On JDK 11 with a test compiled for
Java 11: failure found (`expected:<2> but was:<1>`), 29 interception points; the same agent with the API level set to ASM5: 0
interception points for the Java 11 test and `NoFail`; with a Java 8 test: `NoFail` and 20 stack traces `NestMember requires ASM7`
in `sleepy-script.log`. One run each, `--runs 2`; FlakeRake's exploration is not deterministic (5 vs 6 failures found on different JDKs).
**Not tested:** the Maven build of the ASM 9 agent (first real build is on the machine that runs this), Mockito/ByteBuddy and the JUnit 5
runner on JDK 11 (no such jars in the sandbox), and any of the 21 real JDK 11 test methods.
