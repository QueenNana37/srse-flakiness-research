# Error log analysis for FlakeFlagger's 799 tests

Figure out why FlakyLens couldn't categorize about
75% of the FlakeFlagger tests, using the tests' real error logs instead of
just their code.

Heads up: `flakeflagger_799_with_failures_FINAL.csv` is 3.76 MB, so GitHub
won't preview it in the browser. Click "Raw" or download it instead, the
file is completely fine, GitHub just has a size cap on inline previews.

## Where the raw failure data comes from

FlakeFlagger's own original researchers ran these test suites 10,000 times
years ago and archived everything on Zenodo (record 5014076), including a
`failing-test-reports-<project>.tgz` file per project with the actual
exception + stack trace for every failure, as structured XML.

Downloaded all 21 project archives that our 799 tests come from, then
wrote `match_failure_logs.py` to go through them and pull out the real
failure for each of our specific tests.

## Why the script is built the way it is

First version extracted every archive to disk before reading it. Broke on the big archives — some of these unpack into 700,000+ tiny XML files (square-okhttp has over 1 million), which either fills up your hard drive or, on Windows, hits the 260-character file path limit. Current version never touches disk -> but instead it reads straight out of the compressed .tgz stream, one file at a time, in the order it naturally appears, and only keeps the ones that match a test we actually care about. Took about 2 hours to run across all 21 projects (~2 million archive entries in Python)

## Running it yourself

```
python match_failure_logs.py \
  --archives-dir <folder with all 21 .tgz files> \
  --tests-csv flaky_flakeflagger_with_project_info_with_method_bodies.csv \
  --output flakeflagger_799_with_failures_FINAL.csv
```

Prints progress every 25,000 archive entries scanned per project, so you can
tell it's alive on the big ones instead of just staring at a frozen
terminal.

## What's in the main output CSV

| Column | What it is |
|---|---|
| `project` | which repo |
| `test` | full test identifier |
| `match_status` | whether a real failure log was found for this test |
| `exception_type` | raw (exactly as it appears in the XML) |
| `flakylens_category` | proposed categor (see the disclaimer below) |
| `category_reasoning` | exactly which rule decided the category, so it's checkable |
| `message` | raw (exactly as it appears in the XML) |
| `stack_trace` | raw and full (exactly as it appears in the XML) |

`exception_type`, `message`, and `stack_trace` are never edited or
shortened, that's the actual evidence. Categorization is kept in separate
columns on purpose, so if it turns out wrong, nothing real gets lost.

Note on naming: in the script itself I've since renamed this column to
`error_log_guessed_category`, since `flakylens_category` made it sound like
it came from FlakyLens, and it doesn't (more on that below). The already
generated CSVs still say `flakylens_category` since a full rerun takes 2
hours and wasn't worth it just to fix a label, but everywhere it appears in
this repo, please read it as `error_log_guessed_category` instead.

## Important: FlakyLens never sees this data, and the categorization here is not verified

FlakyLens itself only ever looks at a test's code. It has never seen an
error log or a stack trace, that's just not part of what it does. The
categorization FlakyLens actually produces from code already exists
separately, that's the `majority_category` column over in
`batch-2-799-tests-official/flakeflagger_799_consolidated.csv`.

What's in this folder is something different: I took the real archived
failure text and tried to guess which of FlakyLens's 5 category names it
resembles, so we could compare "what FlakyLens guessed from code" against
"what the real failure actually looks like." Nothing existing does that
mapping, so the rules that decide this are ones I wrote myself with Claude,
based on how the FlakyLens paper describes each category. This is not
checked against any ground truth. Testing it on a real spring-boot failure
already caught it giving a wrong answer: a Redis authentication failure got
labeled "Order Dependent" just because the word "IllegalStateException"
happened to show up buried in a wrapped exception chain that had nothing to
do with the real cause.

Full run across all 21 projects: 548 "Unclear," 216 Async Wait, 25 Order
Dependent, 10 Concurrency, 0 Time, 0 Unordered Collections. The zeros aren't
a bug, those two rules only fire on very specific patterns that just didn't
show up in this dataset's failure text.

Since Suzanna and Shanto haven't confirmed whether this categorization logic
is right, it's currently deprioritized. `flakeflagger_799_raw_errors_ONLY.csv`
is the same data with just the raw evidence columns and no guessed
categories at all, that's the file that's actually been shared as final so far.

## Comparing FlakyLens's real predictions against the real failures

`compare_flakylens_vs_real.py` joins FlakyLens's actual predictions
(from running the real model) against the real error data in this folder,
to answer: when FlakyLens is wrong, what does the real failure suggest it
should have said?

Result, saved in `flakeflagger_flakylens_vs_real_comparison_VERIFY.csv`:

- FlakyLens predicted "Not Flaky" for 619 of the 799 tests, even though
  every one of these 799 is a confirmed flaky test. Those are 619 real
  misses.
- Of those misses, 34.6% show a real error that looks like Async Wait,
  which is by far the clearest pattern in what FlakyLens is missing.
- For the 180 tests FlakyLens did flag as some flaky category, its guessed
  category only matched the real one 2 times out of 180.

## Files

- `match_failure_logs.py`, the extraction and categorization script
- `compare_flakylens_vs_real.py`, compares FlakyLens's real predictions
  against the real error data
- `flakeflagger_799_with_failures_FINAL.csv`, full results for all 799
  tests, includes the unverified category columns
- `flakeflagger_799_with_failures_SUMMARY_part1/2/3.csv`, the same data
  split into 3 files small enough for GitHub to render as a table
- `flakeflagger_799_raw_errors_ONLY.csv`, the version actually sent to
  Suzanna, same data with the unverified category columns removed
- `flakeflagger_flakylens_vs_real_comparison_VERIFY.csv`, the join between
  FlakyLens's real predictions and the real error data
