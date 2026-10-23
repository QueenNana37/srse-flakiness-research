# Non-flaky tests and focal methods: ReproFlake group 1

Output of Suzzana Rafi's `nonflaky_focal_group1` package (23 project/commit/module units from ReproFlake's `result_matched.csv`, group 1 of 2), run on 22-23 Oct 2026 (WSL Ubuntu, JDK 8 and 11).

## Files

| File | Rows | Columns |
|---|---|---|
| `nonflaky_list.csv` (step 1) | 27,178 | `project, sha, module, test` |
| `nonflaky_focal_list.csv` (step 2) | 122 | `project, sha, module, test, focal_method` |

- `project`: GitHub URL. `sha`: full commit hash of the flaky commit. `module`: Maven module (`.` = project root).
- `test`: `package.Class#method` as surefire reported it (nested classes keep their `$`).
- `focal_method`: `package.Class#method` of the method under test.
- These are reduced versions of the package's own output. The package's `nonflaky.csv` has the extra columns `zip`, `java`, `url` and the column `commit` (renamed `sha` here).

## Step 1: non-flaky test list (`nonflaky_list.csv`)

`collect_nonflaky.py` downloads each project archive from Zenodo, builds the module, runs its own `mvn test`, and reads the surefire reports. A test is removed if it is listed as flaky in `result_matched_modules.csv` or in IDoFT's `idoft_pr_data.csv` (copy of 2026-10-22), or if it did not pass cleanly (failed, errored, skipped, passed only on a rerun). "Non-flaky" here means "not known to be flaky", not "proven stable".

Of the 23 units, 17 finished with status `ok` and make up this file:

| Project (commit) | Module | Non-flaky tests |
|---|---|---|
| accumulo (a573f96) | core | 545 |
| adyen-java-api-library (6fb5cd0) | . | 290 |
| bookkeeper (34c260b) | bookkeeper-server | 217 |
| byte-buddy (b19eaba) | byte-buddy-dep | 6,922 |
| cloudstack (64262d9) | plugins/network-elements/opendaylight | 21 |
| commons-collections (bc326f8) | . | 7,540 |
| curator (a469dfb) | curator-recipes | 278 |
| dubbo (737f7a7) | dubbo-rpc/dubbo-rpc-api | 81 |
| fastjson (e05e9c5) | . | 4,730 |
| hadoop (10461e0) | .../hadoop-yarn-server-resourcemanager | 2,264 |
| hadoop (4ea60b5) | .../hadoop-mapreduce-client-core | 239 |
| hadoop (d74ec9d) | hadoop-common-project/hadoop-auth | 60 |
| json-schema (81f0b2f) | core | 733 |
| junit-quickcheck (1798a5b) | core | 375 |
| junit-quickcheck (30e31cb) | core | 375 |
| oozie (83f9c9e) | core | 2,152 |
| ratis (52a52ed) | ratis-test | 356 |

The other 6 units are **not** in the file:

| Unit | Status |
|---|---|
| apex-core (a469dfb, engine) | `test_timeout` |
| OpenRefine (3bff27b, main) | `archive_or_module_not_found` |
| okta-hooks-sdk-java (9187787, hooks) | `archive_or_module_not_found` |
| hadoop (2c155af) | `build_failed_archive_m2` |
| hadoop (cae1ed9) | `build_failed_archive_m2` |
| jersey (8105415, media/json-jackson) | `build_failed_archive_m2` |

The causes behind these statuses have not been investigated yet.

## Step 2: focal methods (`nonflaky_focal_list.csv`)

`nonflaky_focal.py` takes up to 20 random non-flaky tests per module (default sample size and seed 1; 17 modules, 340 tests), and finds each test's focal method the same way as for the flaky tests: Jaccard name matching and an LLM (gpt-4o, temperature 0) must both name the same method, then the production-class and overload rules are applied.

Result for the 340 sampled tests:

| Status | Tests |
|---|---|
| auto_resolved | 122 |
| review_jaccard | 81 |
| no_jaccard_candidates | 41 |
| identify_error | 40 |
| disagreed | 34 |
| review_class | 22 |

`nonflaky_focal_list.csv` contains only the 122 `auto_resolved` tests. The full manifest (all 340 rows with status, Jaccard and LLM answers) and `llm_cache.json` were sent separately.

Known limitation: the 40 `identify_error` rows all say "Expected exactly one test method named X; found 0" (commons-collections 17, ratis 10, byte-buddy 7, curator 5, junit-quickcheck 1). For commons-collections the cause is inherited tests: for example `testMapSize` is defined only in the abstract parent `AbstractMapTest.java`, not in the test class that surefire reports. The other projects were not checked.
