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

## Update: full 811-test FlakeFlagger run

The first analysis (85 tests) used a subset with no ground truth. Suzzana
then confirmed the full FlakeFlagger set is FlakeFlagger's own known-flaky
list — every one of these 811 tests is *supposed* to be flaky. That gives
this batch an implicit ground truth the first batch didn't have.

### Extracting the code

Suzzana's file (`flaky_flakeflagger_with_project_info.csv`) only has
`Project`, `ProjectURL`, `SHA`, and a fully-qualified `Test` identifier
(`package.Class#method`) — no source code. `extract_flakeflagger_811.py`
clones each of the 23 unique (project, commit) pairs, locates the matching
`.java` file by class name, and extracts the target method's body via brace
matching (handles JUnit5 parameterized-test suffixes like `[0]`, `[1]` by
stripping them before searching, since those refer to one underlying method).

**809/811 (99.75%) extracted successfully.** The 2 failures are both cases
where the named class doesn't directly contain the method (likely inherited
from a superclass) — a data-quality note in FlakeFlagger's own list, not an
extraction bug.

### Running inference across all 4 fold checkpoints

Same `infer_flakeflagger.py` script as the 85-test batch, run once per fold
(1-4) on `flakeflagger_811_reformatted.csv`. Consolidated in
`flakeflagger_811_consolidated.csv`.

### Results: FlakyLens has low recall on FlakeFlagger's known-flaky tests

Since every one of these 809 tests is confirmed flaky, any "Not Flaky"
prediction is a miss — these numbers are recall, not just raw counts:

| Fold | Flaky-catch rate |
|---|---|
| 1 | 9.5% (77/809) |
| 2 | 3.2% (26/809) |
| 3 | 8.9% (72/809) |
| 4 | 13.3% (108/809) |

Combined across all 4 folds:
- Flagged flaky by **at least 1** fold: 13.6% (110/809)
- Flagged flaky by **majority** (2+ of 4): 10.6% (86/809)
- Flagged flaky by **all 4** (unanimous): 2.8% (23/809)

The folds also disagree substantially on *which* tests and *which category*
— e.g. rows corresponding to one project (square-okhttp) get called "Async
Wait" by fold 1 but "Order Dependent" by folds 3/4, and are barely flagged at
all by fold 2. This isn't just missed detections; the categorical signal
itself is unstable across independently-trained checkpoints of the same
model.

### Why this is plausible (not a bug)

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
  `wait`, `Duration`, etc.) rather than deep code semantics, and that
  injecting/removing these tokens can flip predictions. If FlakeFlagger's
  real-world flaky tests achieve flakiness through different code patterns
  than FlakeBench's labeled examples, the token-level heuristics the model
  learned simply may not fire — which also explains why different folds
  (each seeing a slightly different slice of FlakeBench during training)
  disagree so much with each other on this new distribution.
