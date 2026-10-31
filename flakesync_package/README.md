# FlakeSync step 1 on generated tests (concurrentfind + delaylocs)

Runs FlakeSync (https://github.com/UT-SE-Research/FlakeSync) step 1 on generated test files, one test method at a time, for the ReproFlake archives you already use (Zenodo). It uses the helpers of `flaky_check_package` (archive download/extract, Flakym2 -> ~/.m2, Mockito in the module pom, module build, copy test in/out, mockito_fix pom swap).

**What step 1 is, and is not.** `concurrentfind` runs the test under the FlakeSync agent and records which methods ran concurrently. `delaylocs` then delays those methods (100 ms doubling to 12.8 s) in the module's OWN classes and stops at the first delay that makes the test fail. It is not a flakiness detector for TD / OD / ID / NIO. `pass` means "the test passed under the agent", not "the test is not flaky". If nothing in the module's own classes ran concurrently, `delaylocs` has nothing to delay and is skipped.

## What was run with it (Hana's machine, 31 Oct 2026)

| set | folders | files | methods run | concurrentfind pass | delaylocs ran |
|---|---|---|---|---|---|
| `flaky_checked_tests` | 6 | 160 of 161 | 345 of 346 (YARN-9405 not run on purpose) | 345 | 1 (dubbo agent_F_11 row_001, no failing delay up to 12.8 s) |
| `flaky_checked_tests_FC_FCV` | 2 | 21 | 58 of 58 | 58 | 0 |
| `flaky_checked_tests_new10` | 6 | 67 of 80 (13 skipped, see `inputs/BROKEN_DO_NOT_RUN.csv`) | 107 of 128 | 107 | 0 |

510 of 510 methods `pass`. In 509 of 510 rows no method of the module's own classes ran concurrently (`rm_in_module` = 0), so `delaylocs` was skipped. Result files: `flakesync_results/` in https://github.com/QueenNana37/srse-flakiness-research (`checked_full_summary_final.csv`, `checked_more_summary.csv`, `graphic_csv.csv`, `graphic_csv_more.csv`).

## Files

| file | what | md5 |
|---|---|---|
| `flakesync_checked_run.py` | the runner (goes into your `flaky_check_package/` folder) | 888c7880b56d4cfec9da714d0eb77d1c |
| `flakesync_changes_54ebfa3.patch` | changes to FlakeSync 54ebfa3 (see below) | 5c6e48fbf5a6982813da9cf650db422b |
| `make_tests_csv.py` | builds `tests.csv` from `tests_info.csv` (only needed for folders that lack it) | 4d268d49023423dc906a0507f5cca879 |
| `inputs/flaky_checked_tests/` | your first set, as received (6 folders, each with `tests.csv`) | |
| `inputs/flaky_checked_tests_FC_FCV/` | agents FC and FCV, as received | |
| `inputs/flaky_checked_tests_new10/` | the `new10` set; its `tests.csv` files were BUILT by `make_tests_csv.py` with `--assume-mockito-fix false` (you said false for these) | |
| `inputs/BROKEN_DO_NOT_RUN.csv` | your list of 13 `new10` files to skip | 59076127285c6c1214087645f04a40de |
| `MD5SUMS.txt` | md5 of every file in this package | |

Helpers it was tested with: `flaky_check_package.zip` from suzzy777/flaky-ai-gen-tests (commit c8af819, md5 ca0376997121f30cb12b263fa147b070). The dry-run checks below used exactly that file; Hana's own copy was not md5-compared with it. The runner imports `batch_reproflake_chatunitest`, `collect_nonflaky`, `replay_generated`, `flaky_check_basic`, `setup_archives` from that folder and stops with a message if a function it needs is missing.

## Requirements

Linux or WSL (Ubuntu 24.04 tested), Python 3.8+ (3.12 tested), git, curl, Maven (3.9.16 tested), JDK 8 AND JDK 11 (full JDKs with `javac`, in `/usr/lib/jvm` or `JAVA_HOME_8` / `JAVA_HOME_11`). At least 5 GB free (the preflight fails below that); the 16 archives are about 2.4 GB. Not tested: JDK 17 (the runner rejects `java` values other than 8 and 11), macOS, native Windows.

## One-time setup

1. Build FlakeSync with the changes (JDK 8 active):
```
git clone https://github.com/UT-SE-Research/FlakeSync.git ~/flakesync_work/FlakeSync
cd ~/flakesync_work/FlakeSync
git checkout 54ebfa3
git apply --check /path/to/flakesync_changes_54ebfa3.patch      # must print nothing
git apply /path/to/flakesync_changes_54ebfa3.patch
mvn -B clean install -DskipTests
```
The patch has two parts: (a) `SafeClassWriter`, which replaces ASM's `getCommonSuperClass` (it loaded classes with `Class.forName` and caused `LinkageError: duplicate class definition`); (b) two extra lines in `flakesync-core/src/main/resources/blacklist.txt` (`org.apache.camel.util.jndi.JndiContext`, `reactor.`). The blacklist then has 194 entries (192 originally). `org.apache.hadoop` is on the original blacklist, so nothing under Hadoop-family archives (HDFS-, HADOOP-, YARN-, HBASE-) is instrumented.

2. Copy `flakesync_checked_run.py` into your `flaky_check_package/` folder (or pass `--suz-dir /path/to/flaky_check_package`).

3. Check everything (changes nothing). It must end `ALL CHECKS PASSED`:
```
cd flaky_check_package
python3 flakesync_checked_run.py --tests-dir /path/to/inputs/flaky_checked_tests_FC_FCV --work ~/flakesync_work/checked_fc_fcv --preflight
```

## Run

ALWAYS pass `--tests-dir` AND `--work`, and use a NEW `--work` folder for each input set. ONE RUNNER AT A TIME on a machine (the archives are shared). Keep the machine awake; use tmux.
```
python3 flakesync_checked_run.py --tests-dir /path/to/inputs/flaky_checked_tests_FC_FCV --work ~/flakesync_work/checked_fc_fcv --keep-going 2>&1 | tee ~/flakesync_work/fc_fcv.log
```
- `--pilot`: only 1 file per JDK x JUnit combination plus 1 `mockito_fix` file. Use it first on a new set.
- Missing archives are downloaded and extracted automatically (URL from `archives.csv` in the package folder, or from an `archive_url` column in `tests.csv`; only `https://zenodo.org/records/...zip` is accepted).
- Same command again = resume (finished rows are skipped). `--redo` runs rows again.
- `--keep-going`: without it the run stops after 10 unusable rows in a row (`--stop-after N`). `--no-hadoop`: leave out Hadoop-family archives. `--folder TEXT`, `--only TEXT`, `--skip TEXT` (repeatable, substring of `folder file archive methods`), `--java 8|11`, `--junit 4|5`, `--list` (show the plan only).
- `--force-delaylocs` runs `delaylocs` even without a concurrent method in the module. Only for testing the machinery: the result then means nothing.
- Timeouts: `--cf-timeout 20`, `--dl-timeout 45`, `--compile-timeout 60` (minutes).
- Speed: about 30 s per method (batch 2: 165 methods in 82 min of test time). Batch 1 took 3 h 12 min for 345 methods, including one test of about 24 min where `delaylocs` ran.

**Skip a list of known-broken files** (a csv with columns `folder,file_here`, like `inputs/BROKEN_DO_NOT_RUN.csv`). The array below is identical to the 13 `--skip` pairs used for `new10` (checked). Each pair `'<folder> <file>'` removes exactly one file:
```
mapfile -t SK < <(python3 -c "
import csv, sys
for r in csv.DictReader(open(sys.argv[1], newline='', encoding='utf-8')):
    print('--skip'); print(r['folder'] + ' ' + r['file_here'])
" /path/to/inputs/BROKEN_DO_NOT_RUN.csv)
echo "${#SK[@]}"      # 26 for the 13 files
python3 flakesync_checked_run.py --tests-dir /path/to/inputs/flaky_checked_tests_new10 --work ~/flakesync_work/checked_new10 --keep-going "${SK[@]}"
```

## Input format: `<set>/<folder>/tests.csv`

The runner reads every `<set>/<folder>/tests.csv`. One row per test METHOD; rows of one file share `file_here`. The test files sit next to `tests.csv` (`<folder>/row_NNN/<File>.java`).

| column | meaning |
|---|---|
| `project`, `sha` | repo URL and commit (informational, must not be empty) |
| `module` | Maven module in the archive (`.` for a single-module project) |
| `generated_test` | `package.Class#method`. Must match the package and class of the java file |
| `focal_method` | `package.Class#method` of the focal method (used for the blacklist note) |
| `zip` | archive name (the folder in `extracted/`) |
| `java`, `junit` | `8` or `11`; `4` or `5`. Must agree across all rows of one file |
| `mockito_fix` | `true` / `false` (true = run with `replay_generated.py`'s `--mockito-fix` pom) |
| `focal_from_test` | `package.Class#method` of the developer test the focal method was found from (used to locate the module) |
| `file_here` | path of the java file relative to its folder |
| `test_file`, `focal_from_test_type`, `archive_url` | optional (`archive_url` only for archives missing in `archives.csv`) |

The loader checks every row and stops with a list of problems before anything is run. For a folder that has only `tests_info.csv` (like `new10` as received):
```
python3 make_tests_csv.py /path/to/received/flaky_checked_tests_new10 /path/to/NEW/folder --assume-mockito-fix false
```
The target folder must not exist (the script refuses otherwise); the source is only read. Use `--mockito-csv FILE` (columns `zip`, `generated_test`, `mockito_fix`) instead of `--assume-mockito-fix` if you have the real values. On `FC_FCV` it reproduces your `tests.csv` exactly in every column the runner uses (the unused `test_file` column stays empty).

## Output

`<work>/results/summary.csv` (one row per method) and one folder per file: `<work>/results/<folder>__<row>__<Class>/<method>/` with `concurrentfind.log`, `delaylocs.log`, `*-ResultMethods.txt`, `*-Locations.txt`, `*-whitelist.txt`.

- `setup`: `ok`, `failed` (archive/JDK/build problem, see `note`), `would_overwrite` (a file with the name of the generated test already exists in the project; nothing was changed).
- `cf_status`: `pass`, `fail` (test fails under the agent), `error` (for example a LinkageError), `no-tests`, `no-result`, `build-failure`, `timeout`.
- `rm_total`: number of methods in `ResultMethods`. `rm_in_module`: how many of them are in the module's own classes. Only `rm_in_module` > 0 means the test has concurrency that `delaylocs` can delay. `rm_total` = 1 was FlakeSync's own method (`Constants.getConcurrentMethodsFilepath`) in batch 1 (matched by count, not row by row), so do not read it as concurrency.
- `dl_status`: `fail` = FlakeSync found a delay that makes the test fail (the interesting case); `pass` = none up to 12.8 s; `skipped` = no concurrent method in the module's own classes, or `concurrentfind` was not `pass`. `dl_last_delay`, `dl_locations`: delay of the last ladder step and number of delay locations. Read `dl_*` only where `rm_in_module` > 0.
- `focal_blacklisted`: the focal class is under a blacklisted prefix, so nothing of it is instrumented.

## What it changes on disk

- Copies the test file into `<module>/src/test/java/<package>/` for the duration of that file, then removes it and its `.class` files. It refuses to start if a file with that name is already there.
- `mockito_fix=true` rows: swaps the module `pom.xml` for the run and puts the original back (also after Ctrl+C or a crash; a left-over swap is undone at the next start).
- Adds Mockito to a module pom once if it is missing (original kept as `pom.xml.batch_orig`), like your `setup_archives.py`. Copies each archive's `Flakym2/.m2/repository` into `~/.m2` without overwriting. Builds the module once with `mvn install -DskipTests -pl <module> -am` (writes into `~/.m2`).
- Before each test it deletes `<module>/.flakesync/<Class.method>-{ResultMethods,Locations,whitelist}.txt`. The copies of earlier results are in `<work>/results`, so keep a backup of `<work>/results` before you run another set into the same archives.
- FlakeSync itself writes `.flakesync/` and `target/` in the module.

## Known limits

- `delaylocs` only instruments the module's OWN classes (`target/classes`, excluding any path containing `Tests`). Concurrency in another module gives no locations. A folder path containing `Tests` empties the whitelist (the preflight fails on it).
- FlakeSync discards the pom's surefire `<configuration>` (argLine, `--add-opens`, system properties, includes). A test that needs them can fail for reasons that have nothing to do with flakiness.
- FlakeSync catches `Throwable` ("The test did not run") and Maven still says BUILD SUCCESS. The runner reads the log and reports it as `cf_problem`.
- A test that fails in `concurrentfind` is not passed on to `delaylocs` (this is my rule, not FlakeSync's).
- Generated tests in these sets are almost all mock-based and single-threaded, so this step finds little. 1 of 510 had concurrency in the module's own classes.
- Defaults I chose, not taken from FlakeSync or the helpers: the three timeouts, stop after 10 unusable rows, disk check at 5 GB, which rows count as finished (`pass`/`fail`/`error`/`no-tests`/`timeout`; others are retried), module build before the test file is copied in, extra Maven flags (the helpers' `BUILD_SKIPS` minus `-DskipTests`, plus `-Dimpsort.skip=true`).

## What was checked

- On Hana's machine: the files with the md5 values above ran 510 methods, 510 `pass`. A positive control (FlakeSync's own luwak test, JDK 8 / JUnit 4) gave the expected `concurrentfind` method and all 48 expected `delaylocs` locations.
- Not tested: `delaylocs` on a real concurrent case with JDK 11 / JUnit 5.
- Before packaging: the patch applies to a fresh clone of FlakeSync 54ebfa3 and gives the 194-entry blacklist; `--list` reads all three input sets without problems (16 / 5 / 4 archives; 346 / 58 / 128 methods); the skip array above equals the one used for `new10`. The FlakeSync build and the real runs were not repeated for the package.
