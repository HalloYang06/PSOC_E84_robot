# EMG Intent Model Training Result - 2026-07-18

## Summary

This document records the training result for the edge-AI EMG intent recognition model used by the rehabilitation assist project. The model classifies three high-level user intents from windowed EMG and motor-state features:

- `rest`: relaxed / no assist intent
- `elbow_curl`: forearm curl intent, merged from the original `elbow_flex` and `elbow_extend` labels
- `shoulder_flex`: upper-arm forward lift intent

The original four-class experiment showed that `elbow_flex` and `elbow_extend` were the main confusion pair. For the current assist-control design, merging them into `elbow_curl` is more robust: the edge-AI model detects the user's movement intent, while the M33 control strategy determines assist direction and magnitude from joint position, velocity, torque estimate, safety limits, and control mode.

## Data Source

Training used the cleaned window-level dataset generated from the 2026-07-14 and 2026-07-18 acquisition sessions:

```text
data/sensor_capture/S01_day4_clean3_20260714_windows.csv
data/sensor_capture/S01_day4_clean4_20260714_windows.csv
```

The generated cleaned dataset is:

```text
data/sensor_capture/S01_day4_20260714_20260718_windows_elbow_curl_cleaned.csv
```

The dataset itself and trained model binaries are not committed to Git because they are generated artifacts.

## Cleaning Rules

The cleaning step used `tools/prepare_clean_intent_windows.py` with these rules:

- Dropped known bad trials: `435`, `492`, `536`, `545`
- Dropped short windows with `sample_count < 12`
- Dropped invalid manual labels such as `11` and `44`
- Merged `elbow_flex` and `elbow_extend` into `elbow_curl`
- Prefixed `trial_id` with the source session name to avoid duplicate trial IDs across sessions

Final cleaned dataset:

| Label | Windows |
|---|---:|
| `elbow_curl` | 8053 |
| `rest` | 2954 |
| `shoulder_flex` | 2414 |
| **Total** | **13421** |

Train / validation / test split:

| Split | Rows |
|---|---:|
| Train | 9347 |
| Validation | 2056 |
| Test | 2018 |

The split is grouped by `trial_id`, so windows from the same trial do not cross train/validation/test boundaries.

## Model Configuration

Training script:

```text
tools/train_intent_tf.py
```

Main configuration:

| Item | Value |
|---|---:|
| Input features | 21 |
| Window length | 300 ms |
| Sliding step | 100 ms |
| Classes | 3 |
| Hidden layers | `128,64,32` |
| Dropout | 0.25 |
| Batch size | 32 |
| Class weighting | balanced |
| Epochs ran | 423 |

Generated training directory:

```text
artifacts/intent_model/S01_day4_20260714_20260718_elbow_curl_cleaned
```

## Float Model Result

Float / default TFLite model test-set result:

| Metric | Result |
|---|---:|
| Test accuracy | 98.81% |
| Macro F1 | 98.51% |
| Weighted F1 | 98.83% |

Per-class result:

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| `elbow_curl` | 100.00% | 98.00% | 98.99% |
| `rest` | 100.00% | 100.00% | 100.00% |
| `shoulder_flex` | 93.30% | 100.00% | 96.53% |

## Full-Int8 Quantization Result

Full-int8 export used:

```text
tools/quantize_intent_tflite_int8.py
```

Quantization settings:

- Representative calibration rows: `512`
- Input dtype: `int8`
- Output dtype: `int8`
- Supported ops: int8 TFLite builtins

Full-int8 model:

```text
intent_model_full_int8.tflite
```

Full-int8 evaluation:

| Metric | Result |
|---|---:|
| Test accuracy | 98.56% |
| Macro F1 | 98.21% |
| Weighted F1 | 98.58% |
| Model size | 22296 bytes |
| Accuracy loss vs float | about 0.25 percentage points |

Per-class result:

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| `elbow_curl` | 100.00% | 97.58% | 98.78% |
| `rest` | 100.00% | 100.00% | 100.00% |
| `shoulder_flex` | 92.01% | 100.00% | 95.84% |

Quantization parameters:

| Tensor | dtype | scale | zero point | shape |
|---|---|---:|---:|---|
| Input | `int8` | 0.058685407 | -47 | `[1, 21]` |
| Output | `int8` | 0.00390625 | -128 | `[1, 3]` |

Observed PC-side TFLite runtime metadata:

```text
ops = FULLY_CONNECTED, FULLY_CONNECTED, FULLY_CONNECTED, FULLY_CONNECTED, SOFTMAX
```

## Deployment Interpretation

The model is intended to run as an edge-AI intent recognizer, not as the final motor authority.

Recommended control responsibility split:

- Edge-AI model: classify high-level intent from EMG and aligned joint state
- M33 control strategy: decide assist direction, velocity/current command, ramping, saturation, and safety gating
- Motor safety layer: enforce current limit, position/velocity limits, fault handling, and rehabilitation mode constraints

This split is important because `elbow_curl` covers both raising and lowering the forearm. Direction should be inferred by the controller from joint trajectory and assist mode rather than forced into the intent classifier.

## Reproduction Commands

Clean and merge the window datasets:

```powershell
C:\Users\ASUS\.conda\envs\edgi-ai\python.exe tools\prepare_clean_intent_windows.py `
  --input data\sensor_capture\S01_day4_clean3_20260714_windows.csv `
  --input data\sensor_capture\S01_day4_clean4_20260714_windows.csv `
  --output data\sensor_capture\S01_day4_20260714_20260718_windows_elbow_curl_cleaned.csv `
  --bad-trial 435 `
  --bad-trial 492 `
  --bad-trial 536 `
  --bad-trial 545 `
  --min-sample-count 12 `
  --merge-elbow-curl
```

Train:

```powershell
C:\Users\ASUS\.conda\envs\edgi-ai\python.exe tools\train_intent_tf.py `
  --input data\sensor_capture\S01_day4_20260714_20260718_windows_elbow_curl_cleaned.csv `
  --output-dir artifacts\intent_model\S01_day4_20260714_20260718_elbow_curl_cleaned `
  --epochs 2000 `
  --min-epochs 200 `
  --patience 200 `
  --max-train-seconds 1800 `
  --batch-size 32 `
  --hidden-units 128,64,32 `
  --dropout 0.25 `
  --learning-rate 0.001 `
  --class-weight balanced
```

Export full-int8:

```powershell
C:\Users\ASUS\.conda\envs\edgi-ai\python.exe tools\quantize_intent_tflite_int8.py `
  --model-dir artifacts\intent_model\S01_day4_20260714_20260718_elbow_curl_cleaned `
  --input data\sensor_capture\S01_day4_20260714_20260718_windows_elbow_curl_cleaned.csv `
  --representative-rows 512
```

Evaluate full-int8:

```powershell
C:\Users\ASUS\.conda\envs\edgi-ai\python.exe tools\eval_tflite_intent.py `
  --model-dir artifacts\intent_model\S01_day4_20260714_20260718_elbow_curl_cleaned `
  --tflite artifacts\intent_model\S01_day4_20260714_20260718_elbow_curl_cleaned\intent_model_full_int8.tflite `
  --input data\sensor_capture\S01_day4_20260714_20260718_windows_elbow_curl_cleaned.csv `
  --name intent_model_full_int8 `
  --batch-size 256
```

## Conclusion

The three-class design is the recommended competition-report version for the current hardware and data condition. It gives high recognition performance after int8 quantization, keeps the embedded model small, and cleanly separates AI intent recognition from deterministic rehabilitation motor control.
