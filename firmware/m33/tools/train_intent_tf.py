import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight


DEFAULT_INPUT = Path("data/sensor_capture/S01_day2_windows.csv")
DEFAULT_OUTPUT_ROOT = Path("artifacts/intent_model")

METADATA_COLUMNS = {
    "session_id",
    "subject_id",
    "trial_id",
    "trial_index",
    "label",
    "label_trial_index",
    "window_index",
    "window_start_ms",
    "window_end_ms",
    "timestamp",
    "timestamp_iso",
    "rel_ms",
    "channel",
    "can_id",
    "source",
    "raw_hex",
}


@dataclass
class Preprocessor:
    feature_columns: list[str]
    medians: dict[str, float]
    means: dict[str, float]
    stds: dict[str, float]

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        values = df[self.feature_columns].copy()
        for column in self.feature_columns:
            values[column] = pd.to_numeric(values[column], errors="coerce")
            values[column] = values[column].fillna(self.medians[column])
        means = np.array([self.means[column] for column in self.feature_columns], dtype=np.float32)
        stds = np.array([self.stds[column] for column in self.feature_columns], dtype=np.float32)
        return ((values.to_numpy(dtype=np.float32) - means) / stds).astype(np.float32)

    def to_json_dict(self) -> dict:
        return {
            "feature_columns": self.feature_columns,
            "medians": self.medians,
            "means": self.means,
            "stds": self.stds,
        }


def select_feature_columns(df: pd.DataFrame, label_column: str = "label") -> list[str]:
    ignored = set(METADATA_COLUMNS)
    ignored.add(label_column)
    feature_columns: list[str] = []
    for column in df.columns:
        if column in ignored:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        if numeric.notna().sum() == 0:
            continue
        if numeric.nunique(dropna=True) <= 1:
            continue
        feature_columns.append(column)
    if not feature_columns:
        raise ValueError("No usable numeric feature columns were found.")
    return feature_columns


def encode_labels(labels: pd.Series) -> tuple[np.ndarray, list[str]]:
    clean_labels = labels.astype(str)
    class_names = sorted(clean_labels.unique().tolist())
    if len(class_names) < 2:
        raise ValueError("Need at least two labels/classes to train a classifier.")
    label_to_index = {label: index for index, label in enumerate(class_names)}
    encoded = clean_labels.map(label_to_index).to_numpy(dtype=np.int64)
    return encoded, class_names


def split_dataframe(
    df: pd.DataFrame,
    group_column: str = "trial_id",
    val_size: float = 0.15,
    test_size: float = 0.15,
    seed: int = 42,
    label_column: str = "label",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if group_column in df.columns and df[group_column].nunique(dropna=True) >= 3:
        groups = pd.DataFrame({group_column: sorted(df[group_column].dropna().unique())})
        if label_column in df.columns:
            group_labels = (
                df.groupby(group_column)[label_column]
                .agg(lambda values: values.mode().iloc[0] if not values.mode().empty else str(values.iloc[0]))
                .reindex(groups[group_column])
            )
        else:
            group_labels = None

        train_val_groups, test_groups = _train_test_split_safe(
            groups[group_column],
            test_size=test_size,
            seed=seed,
            stratify=group_labels,
        )
        remaining_val_fraction = val_size / max(1.0 - test_size, 1e-9)
        remaining_labels = None
        if group_labels is not None:
            remaining_labels = group_labels.reindex(train_val_groups)
        train_groups, val_groups = _train_test_split_safe(
            pd.Series(train_val_groups),
            test_size=remaining_val_fraction,
            seed=seed + 1,
            stratify=remaining_labels,
        )

        train_df = df[df[group_column].isin(set(train_groups))]
        val_df = df[df[group_column].isin(set(val_groups))]
        test_df = df[df[group_column].isin(set(test_groups))]
    else:
        train_val_df, test_df = _row_split_safe(df, test_size=test_size, seed=seed, label_column=label_column)
        remaining_val_fraction = val_size / max(1.0 - test_size, 1e-9)
        train_df, val_df = _row_split_safe(
            train_val_df,
            test_size=remaining_val_fraction,
            seed=seed + 1,
            label_column=label_column,
        )

    return train_df.copy(), val_df.copy(), test_df.copy()


def fit_preprocessor(train_df: pd.DataFrame, feature_columns: list[str]) -> Preprocessor:
    numeric = train_df[feature_columns].apply(pd.to_numeric, errors="coerce")
    medians = numeric.median(numeric_only=True).fillna(0.0)
    filled = numeric.fillna(medians)
    means = filled.mean()
    stds = filled.std(ddof=0).replace(0.0, 1.0).fillna(1.0)
    return Preprocessor(
        feature_columns=feature_columns,
        medians={column: float(medians[column]) for column in feature_columns},
        means={column: float(means[column]) for column in feature_columns},
        stds={column: float(stds[column]) for column in feature_columns},
    )


def build_model(
    num_features: int,
    num_classes: int,
    hidden_units: list[int],
    dropout: float,
    learning_rate: float,
):
    import tensorflow as tf

    layers = [tf.keras.layers.Input(shape=(num_features,))]
    for units in hidden_units:
        layers.append(tf.keras.layers.Dense(units, activation="relu"))
        if dropout > 0:
            layers.append(tf.keras.layers.Dropout(dropout))
    layers.append(tf.keras.layers.Dense(num_classes, activation="softmax"))

    model = tf.keras.Sequential(layers)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def train(args: argparse.Namespace) -> Path:
    import tensorflow as tf

    start_time = time.time()
    tf.keras.utils.set_random_seed(args.seed)

    input_path = Path(args.input)
    output_dir = Path(args.output_dir) if args.output_dir else make_output_dir(DEFAULT_OUTPUT_ROOT)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path)
    if args.label_column not in df.columns:
        raise ValueError(f"Missing label column: {args.label_column}")
    df = df[df[args.label_column].notna()].reset_index(drop=True)

    feature_columns = select_feature_columns(df, label_column=args.label_column)
    train_df, val_df, test_df = split_dataframe(
        df,
        group_column=args.group_column,
        val_size=args.val_size,
        test_size=args.test_size,
        seed=args.seed,
        label_column=args.label_column,
    )

    _, class_names = encode_labels(df[args.label_column])
    label_to_index = {label: index for index, label in enumerate(class_names)}
    y_train = train_df[args.label_column].astype(str).map(label_to_index).to_numpy(dtype=np.int64)
    y_val = val_df[args.label_column].astype(str).map(label_to_index).to_numpy(dtype=np.int64)
    y_test = test_df[args.label_column].astype(str).map(label_to_index).to_numpy(dtype=np.int64)

    preprocessor = fit_preprocessor(train_df, feature_columns)
    X_train = preprocessor.transform(train_df)
    X_val = preprocessor.transform(val_df)
    X_test = preprocessor.transform(test_df)

    model = build_model(
        num_features=X_train.shape[1],
        num_classes=len(class_names),
        hidden_units=parse_hidden_units(args.hidden_units),
        dropout=args.dropout,
        learning_rate=args.learning_rate,
    )

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=args.patience,
            start_from_epoch=args.min_epochs,
            restore_best_weights=True,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=max(5, args.patience // 4),
            min_lr=1e-6,
        ),
        TimeLimitCallback(max_seconds=args.max_train_seconds),
    ]

    class_weight = None
    if args.class_weight == "balanced":
        weights = compute_class_weight(
            class_weight="balanced",
            classes=np.arange(len(class_names)),
            y=y_train,
        )
        class_weight = {index: float(weight) for index, weight in enumerate(weights)}

    history = model.fit(
        X_train,
        y_train,
        validation_data=(X_val, y_val),
        epochs=args.epochs,
        batch_size=args.batch_size,
        callbacks=callbacks,
        class_weight=class_weight,
        verbose=args.verbose,
    )

    model_path = output_dir / "intent_model.keras"
    model.save(model_path)

    tflite_path = None
    if args.export_tflite:
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        tflite_model = converter.convert()
        tflite_path = output_dir / "intent_model.tflite"
        tflite_path.write_bytes(tflite_model)

    test_loss, test_accuracy = model.evaluate(X_test, y_test, verbose=0)
    probabilities = model.predict(X_test, verbose=0)
    y_pred = probabilities.argmax(axis=1)

    report = classification_report(
        y_test,
        y_pred,
        labels=list(range(len(class_names))),
        target_names=class_names,
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(y_test, y_pred, labels=list(range(len(class_names))))

    pd.DataFrame(history.history).to_csv(output_dir / "history.csv", index_label="epoch")
    pd.DataFrame(matrix, index=class_names, columns=class_names).to_csv(output_dir / "confusion_matrix.csv")

    labels_payload = {
        "class_names": class_names,
        "label_to_index": label_to_index,
        "index_to_label": {str(index): label for index, label in enumerate(class_names)},
    }
    write_json(output_dir / "labels.json", labels_payload)

    preprocess_payload = preprocessor.to_json_dict()
    preprocess_payload.update(
        {
            "label_column": args.label_column,
            "group_column": args.group_column,
            "input_file": str(input_path),
        }
    )
    write_json(output_dir / "preprocess.json", preprocess_payload)

    metrics_payload = {
        "input_file": str(input_path),
        "output_dir": str(output_dir),
        "model_path": str(model_path),
        "tflite_path": str(tflite_path) if tflite_path else None,
        "rows": int(len(df)),
        "train_rows": int(len(train_df)),
        "val_rows": int(len(val_df)),
        "test_rows": int(len(test_df)),
        "feature_count": int(len(feature_columns)),
        "features": feature_columns,
        "class_names": class_names,
        "class_counts": {str(k): int(v) for k, v in df[args.label_column].value_counts().sort_index().items()},
        "epochs_ran": int(len(history.history.get("loss", []))),
        "max_train_seconds": float(args.max_train_seconds),
        "elapsed_seconds": round(time.time() - start_time, 3),
        "test_loss": float(test_loss),
        "test_accuracy": float(test_accuracy),
        "classification_report": report,
        "confusion_matrix": matrix.tolist(),
        "class_weight": class_weight,
        "seed": args.seed,
    }
    write_json(output_dir / "metrics.json", metrics_payload)

    print(f"[train] output_dir={output_dir}")
    print(f"[train] rows train/val/test={len(train_df)}/{len(val_df)}/{len(test_df)}")
    print(f"[train] features={len(feature_columns)} classes={class_names}")
    print(f"[train] epochs_ran={metrics_payload['epochs_ran']} elapsed_s={metrics_payload['elapsed_seconds']}")
    print(f"[train] test_accuracy={test_accuracy:.4f} test_loss={test_loss:.4f}")
    return output_dir


class TimeLimitCallback:
    def __init__(self, max_seconds: float):
        self.max_seconds = max_seconds
        self.started_at = 0.0
        self.model = None
        self.params = {}

    def set_model(self, model):
        self.model = model

    def set_params(self, params):
        self.params = params

    def on_train_begin(self, logs=None):
        self.started_at = time.time()

    def on_train_end(self, logs=None):
        pass

    def on_epoch_begin(self, epoch, logs=None):
        pass

    def on_epoch_end(self, epoch, logs=None):
        if self.max_seconds > 0 and time.time() - self.started_at >= self.max_seconds:
            print(f"\n[train] max_train_seconds reached after epoch {epoch + 1}; stopping.")
            self.model.stop_training = True

    def on_train_batch_begin(self, batch, logs=None):
        pass

    def on_train_batch_end(self, batch, logs=None):
        pass

    def on_test_begin(self, logs=None):
        pass

    def on_test_end(self, logs=None):
        pass

    def on_test_batch_begin(self, batch, logs=None):
        pass

    def on_test_batch_end(self, batch, logs=None):
        pass

    def on_predict_begin(self, logs=None):
        pass

    def on_predict_end(self, logs=None):
        pass

    def on_predict_batch_begin(self, batch, logs=None):
        pass

    def on_predict_batch_end(self, batch, logs=None):
        pass


def _train_test_split_safe(items, test_size: float, seed: int, stratify=None):
    items = pd.Series(list(items)).reset_index(drop=True)
    if len(items) < 2 or test_size <= 0:
        return items.tolist(), []
    test_count = max(1, int(round(len(items) * test_size)))
    if test_count >= len(items):
        test_count = len(items) - 1
    try:
        train_items, test_items = train_test_split(
            items,
            test_size=test_count,
            random_state=seed,
            shuffle=True,
            stratify=stratify if _can_stratify(stratify) else None,
        )
    except ValueError:
        train_items, test_items = train_test_split(
            items,
            test_size=test_count,
            random_state=seed,
            shuffle=True,
            stratify=None,
        )
    return list(train_items), list(test_items)


def _row_split_safe(df: pd.DataFrame, test_size: float, seed: int, label_column: str):
    if len(df) < 2 or test_size <= 0:
        return df.copy(), df.iloc[0:0].copy()
    test_count = max(1, int(round(len(df) * test_size)))
    if test_count >= len(df):
        test_count = len(df) - 1
    stratify = df[label_column] if label_column in df.columns and _can_stratify(df[label_column]) else None
    try:
        return train_test_split(
            df,
            test_size=test_count,
            random_state=seed,
            shuffle=True,
            stratify=stratify,
        )
    except ValueError:
        return train_test_split(df, test_size=test_count, random_state=seed, shuffle=True, stratify=None)


def _can_stratify(values) -> bool:
    if values is None:
        return False
    counts = pd.Series(values).value_counts()
    return len(counts) > 1 and counts.min() >= 2


def parse_hidden_units(value: str) -> list[int]:
    units = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not units or any(unit <= 0 for unit in units):
        raise ValueError("--hidden-units must contain positive integers, for example 128,64,32")
    return units


def make_output_dir(root: Path) -> Path:
    return root / datetime.now().strftime("%Y%m%d-%H%M%S")


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train a TensorFlow intent classifier from windowed EMG/motor CSV data.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Path to the windowed training CSV.")
    parser.add_argument("--output-dir", default=None, help="Directory for model artifacts. Defaults to artifacts/intent_model/<timestamp>.")
    parser.add_argument("--label-column", default="label", help="Target label column.")
    parser.add_argument("--group-column", default="trial_id", help="Group column kept disjoint across train/val/test.")
    parser.add_argument("--val-size", type=float, default=0.15, help="Validation fraction.")
    parser.add_argument("--test-size", type=float, default=0.15, help="Test fraction.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--epochs", type=int, default=2000, help="Maximum training epochs.")
    parser.add_argument("--min-epochs", type=int, default=200, help="Do not early-stop before this epoch.")
    parser.add_argument("--patience", type=int, default=200, help="Early stopping patience after min-epochs.")
    parser.add_argument("--max-train-seconds", type=float, default=7200.0, help="Wall-clock training time limit.")
    parser.add_argument("--batch-size", type=int, default=32, help="Training batch size.")
    parser.add_argument("--hidden-units", default="128,64,32", help="Comma-separated MLP hidden layer sizes.")
    parser.add_argument("--dropout", type=float, default=0.25, help="Dropout ratio.")
    parser.add_argument("--learning-rate", type=float, default=0.001, help="Adam learning rate.")
    parser.add_argument("--class-weight", choices=["balanced", "none"], default="balanced", help="Class weighting strategy.")
    parser.add_argument("--no-tflite", dest="export_tflite", action="store_false", help="Skip TFLite export.")
    parser.add_argument("--verbose", type=int, default=2, choices=[0, 1, 2], help="Keras training verbosity.")
    parser.set_defaults(export_tflite=True)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    train(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
