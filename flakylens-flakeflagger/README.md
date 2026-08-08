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
