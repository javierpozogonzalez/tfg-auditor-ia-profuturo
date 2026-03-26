import json
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

DATASET_PATH = Path("data/datos_profuturo.csv")
TRAIN_PATH = Path("data/train.jsonl")
VALID_PATH = Path("data/valid.jsonl")


def to_chatml_record(row: dict) -> dict:
    user_content = (
        f"Autor: {row['autor']}\n"
        f"Comunidad: {row['comunidad']}\n"
        f"Tema: {row['tema']}\n"
        f"Contenido: {row['contenido']}\n"
        "Tarea: clasifica el sentimiento del mensaje como positivo, neutral o negativo."
    )
    assistant_content = str(row["sentimiento"]).strip().lower()
    return {
        "messages": [
            {
                "role": "system",
                "content": "Eres un analista de sentimiento para comunidades educativas.",
            },
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]
    }


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    df = pd.read_csv(DATASET_PATH)
    columns = ["autor", "comunidad", "tema", "contenido", "sentimiento"]
    clean = df[columns].dropna().copy()
    clean["sentimiento"] = clean["sentimiento"].astype(str).str.lower().str.strip()
    clean = clean[clean["sentimiento"].isin(["positivo", "neutral", "negativo"])]

    train_df, valid_df = train_test_split(
        clean,
        test_size=0.15,
        random_state=42,
        stratify=clean["sentimiento"],
    )

    train_records = [to_chatml_record(row) for row in train_df.to_dict(orient="records")]
    valid_records = [to_chatml_record(row) for row in valid_df.to_dict(orient="records")]

    write_jsonl(TRAIN_PATH, train_records)
    write_jsonl(VALID_PATH, valid_records)

    print(f"train: {len(train_records)} -> {TRAIN_PATH}")
    print(f"valid: {len(valid_records)} -> {VALID_PATH}")


if __name__ == "__main__":
    main()
