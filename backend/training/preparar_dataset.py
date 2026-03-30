import json
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = BASE_DIR / "data" / "datos_profuturo.csv"
OUTPUT_TRAIN = BASE_DIR / "data" / "train.jsonl"


def to_chatml(topic: str, author: str, message: str) -> str:
    system = "Eres un asistente de analitica educativa institucional."
    user = f"Tema: {topic}\nAutor: {author}\nMensaje: {message}"
    assistant = f"Registro recibido. Tema: {topic}. Autor: {author}."
    return (
        f"<|im_start|>system\n{system}<|im_end|>\n"
        f"<|im_start|>user\n{user}<|im_end|>\n"
        f"<|im_start|>assistant\n{assistant}<|im_end|>"
    )


def main() -> None:
    df = pd.read_csv(INPUT_CSV)
    required = ["Mensaje", "Tema", "Autor"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {missing}")

    df = df[required].dropna()
    df["Mensaje"] = df["Mensaje"].astype(str).str.strip()
    df["Tema"] = df["Tema"].astype(str).str.strip()
    df["Autor"] = df["Autor"].astype(str).str.strip()
    df = df[(df["Mensaje"] != "") & (df["Tema"] != "") & (df["Autor"] != "")]

    train_df, _ = train_test_split(df, test_size=0.1, random_state=42, shuffle=True)

    OUTPUT_TRAIN.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_TRAIN.open("w", encoding="utf-8") as f:
        for row in train_df.itertuples(index=False):
            record = {
                "text": to_chatml(row.Tema, row.Autor, row.Mensaje)
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Dataset generado: {OUTPUT_TRAIN}")
    print(f"Registros train: {len(train_df)}")


if __name__ == "__main__":
    main()
