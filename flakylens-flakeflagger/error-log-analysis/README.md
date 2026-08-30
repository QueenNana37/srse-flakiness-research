# Error log analysis for FlakeFlagger's 799 tests

Figure out why FlakyLens couldn't categorize ~75% of
the FlakeFlagger tests, using the tests' real error logs (not just the code).

Heads up: `flakeflagger_799_with_failures_FINAL.csv` is 3.76 MB, so GitHub
won't preview it in the browser. Click "Raw" or download it instead (the file
should be fine, GitHub just has a size cap on inline previews)

## Where the raw failure data comes from

FlakeFlagger's own original researchers ran these test suites 10,000 times
years ago and archived everything on Zenodo (record 5014076), including a
`failing-test-reports-<project>.tgz` file per project with the actual
exception + stack trace for every failure, as structured XML (surefire
format).

Downloaded all 21 project archives that our 799 tests come from, then wrote
`match_failure_logs.py` script to go through them and pull out the real failure for
each of our specific tests.

## Why the script is built the way it is

First version extracted every archive to disk before reading it. Broke on
the big archives — some of these unpack into 700,000+ tiny XML files
(square-okhttp has over 1 million), which either fills up your hard drive or,
on Windows, hits the 260-character file path limit. Current version never
touches disk -> but instead it reads straight out of the compressed `.tgz` stream, one
file at a time, in the order it naturally appears, and only keeps the ones
that match a test we actually care about. Took about 2 hours to run across
all 21 projects (~2 million archive
entries in Python))

## Running it yourself

```
python match_failure_logs.py \
  --archives-dir <folder with all 21 .tgz files> \
  --tests-csv flaky_flakeflagger_with_project_info_with_method_bodies.csv \
  --output flakeflagger_799_with_failures_FINAL.csv
```

Prints progress every 25,000 archive entries scanned per project, so you can
tell it's alive on the big ones instead of just staring at a frozen terminal.

## What's in the output CSV

| Column | What it is |
|---|---|
| `project` | which repo |
| `test` | full test identifier |
| `match_status` | whether a real failure log was found for this test |
| `exception_type` | **raw**, exactly as it appears in the XML |
| `flakylens_category` | proposed category -- see disclaimer below |
| `category_reasoning` | exactly which rule decided the category, so it's checkable |
| `message` | **raw**, exactly as it appears in the XML |
| `stack_trace` | **raw and full**, exactly as it appears in the XML |

`exception_type`, `message`, and `stack_trace` are never edited or shortened, that's the actual evidence. Categorization is kept in separate columns on
purpose, so if it turns out wrong, nothing real gets lost.

## Important: the categorization is NOT verified

`flakylens_category` is a set of pattern rules I (with Claude) wrote
myself, based on how the FlakyLens paper describes its 5 categories (Async
Wait, Concurrency, Time, Unordered Collections, Order Dependent). This is
**not** checked against any ground truth, and testing it on real spring-boot
failures already caught it giving at least one wrong answer -> eg a Redis
authentication failure got mislabeled "Order Dependent" because the word
"IllegalStateException" happened to show up buried in a wrapped exception
chain that had nothing to do with the real cause.

Full run across all 21 projects: **548 "Unclear," 216 Async Wait, 25 Order
Dependent, 10 Concurrency, 0 Time, 0 Unordered Collections.** The zeroes
aren't a bug - those two rules only fire on very specific, narrow patterns
that just didn't show up in this particular dataset's failure text.

The raw `exception_type` / `message` / `stack_trace` data is solid
either way and doesn't depend on the categorization being right.

## Files

- `match_failure_logs.py` -- the extraction + categorization script
- `flakeflagger_799_with_failures_FINAL.csv` -- full results, all 799 tests
