# FlakyLens on FlakeFlagger data

Runs the FlakyLens pretrained classifier (Rahman, Dutta, Shi — OOPSLA2 2025) on
Suzzana's FlakeFlagger test-code extract to predict a flakiness category for
each test.

## Why a custom script was needed

The FlakyLens artifact (Zenodo doi.org/10.5281/zenodo.15761937) ships scripts
that only evaluate against the paper's own FlakeBench dataset, which already
has ground-truth labels baked into a fixed train/valid/test split per project
group. There's no supported path for scoring arbitrary new, unlabeled code.

`infer_flakeflagger.py` loads one of the four pretrained fold checkpoints
directly (`codebert_model.BERT_Arch` + `microsoft/codebert-base` tokenizer)
and runs plain inference: tokenize each test's `full_code`, forward pass,
argmax over the 6 output classes. No training, no evaluation, no ground
truth required.

## Category mapping

Labels 0-5 match the print order used in the artifact's own `rq1.sh` output
(`Async, Conc, Time, UC, OD, Non-flaky`), which follows sklearn's sorted-label
convention:

| Label | Category |
|---|---|
| 0 | Async Wait |
| 1 | Concurrency |
| 2 | Time |
| 3 | Unordered Collections |
| 4 | Order Dependent |
| 5 | Not Flaky |

## Files

- `infer_flakeflagger.py` — standalone inference script. Run inside the
  FlakyLens Docker container from `/app/src`:
  ```
  python3 infer_flakeflagger.py <input_csv> <output_csv> [fold=1]
  ```
  `input_csv` needs at minimum a `full_code` column. `fold` selects which of
  the 4 pretrained checkpoints to use (`per_project_model_weights_on__dataset_project_group_{fold}.pt`).

- `flakeflagger_reformatted.csv` — Suzzana's
  [chaosapi_method_body_extracted.csv](https://github.com/suzzy777/flakeprobe/blob/main/chaosapi_method_body_extracted.csv)
  (85 rows with `extraction_status == ok`) reformatted to `id, project,
  test_name, full_code`.

- `flakeflagger_consolidated_predictions.csv` — final results. The script was
  run once per fold (1-4) as a robustness check, then predictions were
  combined here: per-fold prediction + confidence, a majority-vote
  `majority_category`, an `unanimous_across_folds` flag, and `avg_confidence`
  across the 4 folds.

## Results summary

All 4 independently-trained fold models agreed on every one of the 85 tests
(100% unanimous). 84/85 predicted **Not Flaky**; 1 predicted **Async Wait**
(`apache-commons-exec` / `testExecuteAsyncWithProcessDestroyer`, which
contains a `Thread.sleep()` waiting on a process destroyer — consistent with
the predicted category).

This is a low positive rate relative to intuition, but it lines up with
FlakeBench's own training distribution (280 flaky / 8,294 non-flaky, ~3.4%
flaky), so the model's prior toward "Not Flaky" by default is expected
behavior rather than a bug in this pipeline.

## Caveat

No ground-truth labels exist for this dataset (confirmed with Suzzana), so
these are FlakyLens's raw predictions, not an accuracy/F1 evaluation.


## Update: full FlakeFlagger run — corrected with Suzanna's official method bodies

**This section supersedes an earlier version of this analysis.** The first
pass extracted test method source code ourselves (811 tests, 23 cloned
repos) and found low recall on known-flaky tests. Suzanna then sent her own
official extraction with real method bodies
(`flaky_flakeflagger_with_project_info_with_method_bodies.csv`, 799 tests).
Diffing our extraction against hers surfaced a real bug: for methods
annotated with something like `@Deployment(resources = { "path.xml" })`, the
annotation's own embedded `{` confused our brace-matching logic and truncated
~13.5% of extracted method bodies right after the annotation, cutting off the
actual method body entirely. All results below use Suzanna's official,
verified 799-test file -> this is the correct, current analysis. The
self-extracted 811-test files and script have been removed from this repo.

### Results: FlakyLens recall on FlakeFlagger's known-flaky tests (799 tests)

Since every one of these 799 tests is confirmed flaky, any "Not Flaky"
prediction is a miss — these are recall numbers:

| Fold | Flaky-catch rate |
|---|---|
| 1 | 24.8% (198/799) |
| 2 | 13.4% (107/799) |
| 3 | 20.7% (165/799) |
| 4 | 25.2% (201/799) |

Combined across all 4 folds:
- Flagged flaky by **at least 1** fold: 25.3% (202/799)
- Flagged flaky by **majority** (2+ of 4): 24.8% (198/799)
- Flagged flaky by **all 4** (unanimous): 13.0% (104/799)

Recall roughly doubled compared to the buggy extraction (which is expected —
truncated method bodies gave the model far less signal to work with). Even
so, FlakyLens still misses roughly 3 in 4 known-flaky FlakeFlagger tests even
counted generously (any single fold flagging it).

### Why this is plausible (not a bug in the inference pipeline)

- **Distribution shift.** FlakyLens is trained entirely on FlakeBench (97
  projects). FlakeFlagger is an older, largely non-overlapping set of OSS
  projects with different coding conventions, frameworks, and Java-version
  idioms. A classifier trained on one project population doesn't
  automatically transfer to another, even for the "same" task.
- **Severe class imbalance in training data.** FlakeBench is ~97%
  non-flaky. FlakyLens's focal loss / class weighting was tuned to that
  specific imbalance and feature distribution — that calibration doesn't
  necessarily carry over to a different distribution, so the decision
  boundary defaults toward "Not Flaky" unless the signal is very strong.
- **Consistent with the paper's own interpretability finding.** The FlakyLens
  paper shows the model leans on surface-level token patterns (`sleep`,
  `wait`, `Duration`, etc.) rather than deep code semantics. If
  FlakeFlagger's real-world flaky tests achieve flakiness through different
  code patterns than FlakeBench's labeled examples, those learned
  token-level heuristics simply may not fire — which also explains why the 4
  independently-trained folds disagree with each other on this new
  distribution.
