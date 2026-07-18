import argparse
from pathlib import Path

import pandas as pd


VALID_LABELS = {"rest", "elbow_flex", "elbow_extend", "shoulder_flex"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge and clean intent windows CSV files.")
    parser.add_argument("--input", action="append", required=True, help="Input *_windows.csv file.")
    parser.add_argument("--output", required=True, help="Output cleaned CSV file.")
    parser.add_argument("--bad-trial", action="append", type=int, default=[], help="Trial index to drop.")
    parser.add_argument("--min-sample-count", type=int, default=12)
    parser.add_argument(
        "--merge-elbow-curl",
        action="store_true",
        help="Merge elbow_flex and elbow_extend labels into elbow_curl.",
    )
    args = parser.parse_args()

    bad_trials = set(args.bad_trial)
    frames = []

    for raw_path in args.input:
        path = Path(raw_path)
        df = pd.read_csv(path)
        session = path.stem.replace("_windows", "")
        before = len(df)

        df["source_windows_file"] = path.name
        df["trial_index_from_id"] = pd.to_numeric(
            df["trial_id"].astype(str).str.extract(r"^(\d+)_")[0],
            errors="coerce",
        ).astype("Int64")

        invalid_label = ~df["label"].astype(str).isin(VALID_LABELS)
        short_window = pd.to_numeric(df["sample_count"], errors="coerce").fillna(0) < args.min_sample_count
        bad_trial = df["trial_index_from_id"].isin(bad_trials)
        keep = ~(invalid_label | short_window | bad_trial)

        clean = df.loc[keep].copy()
        if args.merge_elbow_curl:
            clean["label"] = clean["label"].replace(
                {"elbow_flex": "elbow_curl", "elbow_extend": "elbow_curl"}
            )
        clean["trial_id"] = session + "__" + clean["trial_id"].astype(str)
        frames.append(clean)

        print(
            f"[clean] {path.name}: before={before} after={len(clean)} "
            f"invalid_label={int(invalid_label.sum())} "
            f"short_window={int(short_window.sum())} "
            f"bad_trial={int(bad_trial.sum())}"
        )

    combined = pd.concat(frames, ignore_index=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output, index=False)

    print(f"[clean] output={output}")
    print(f"[clean] rows={len(combined)} unique_trials={combined['trial_id'].nunique()}")
    print(f"[clean] labels={combined['label'].value_counts().to_dict()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
