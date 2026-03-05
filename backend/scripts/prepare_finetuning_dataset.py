import os
import csv
import json
import random

DATA_FILE = "data/datos_profuturo.csv"
OUTPUT_FILE = "data/dataset_profuturo.jsonl"

SYSTEM_PROMPT = "Eres el Auditor IA de ProFuturo. Responde de forma estructurada basandote estrictamente en el contexto proporcionado. No inventes informacion. Si se solicita un informe o PDF, añade obligatoriamente en tu ultima linea [GENERATE_PDF: Titulo]."

PREGUNTAS_QA = [
    "¿Qué dijo {author} en la comunidad {community}?",
    "What did {author} mention about {subject}?",
    "Que disse {author} sobre o tema {subject}?",
    "Qu'a dit {author} dans la communaute {community}?"
]

PREGUNTAS_PDF = [
    "Genera un reporte en PDF sobre la participacion en {community}.",
    "Generate a PDF report summarizing the topic {subject}.",
    "Crie um relatorio em PDF sobre a comunidade {community}.",
    "Generez un rapport PDF sur le sujet {subject}."
]

class FinetuningDatasetGenerator:
    def __init__(self, data_file, output_file):
        self.data_file = data_file
        self.output_file = output_file
        self.records_generated = 0
        
    def read_data(self):
        data = []
        with open(self.data_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append({
                    "author": row.get("autor", "Desconocido"),
                    "community": row.get("comunidad", "General"),
                    "subject": row.get("tema", "Sin tema"),
                    "text": row.get("contenido", ""),
                    "date": row.get("fecha", "")
                })
        return data

    def create_message_format(self, user_prompt, assistant_response, context):
        return {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{user_prompt}\n\nContexto:\n{context}"},
                {"role": "assistant", "content": assistant_response}
            ]
        }

    def generate_dataset(self):
        raw_data = self.read_data()
        examples = []
        
        for row in raw_data:
            if not row["text"].strip():
                continue
                
            context = f"Fecha: {row['date']}\nAutor: {row['author']}\nComunidad: {row['community']}\nTema: {row['subject']}\nMensaje: {row['text']}"
            
            q_qa = random.choice(PREGUNTAS_QA).format(**row)
            resp_qa = f"Basado en los datos recuperados, {row['author']} comento lo siguiente en la comunidad {row['community']} respecto al tema '{row['subject']}':\n\n{row['text']}"
            examples.append(self.create_message_format(q_qa, resp_qa, context))
            
            q_pdf = random.choice(PREGUNTAS_PDF).format(**row)
            safe_title = row['community'].replace(' ', '_')
            resp_pdf = f"Aqui tienes la informacion solicitada sobre {row['community']} y el tema '{row['subject']}':\n\n{row['text']}\n\n[GENERATE_PDF: Reporte_{safe_title}]"
            examples.append(self.create_message_format(q_pdf, resp_pdf, context))
            
            self.records_generated += 2

        random.shuffle(examples)
        return examples

    def save_to_jsonl(self, examples):
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            for example in examples:
                f.write(json.dumps(example, ensure_ascii=False) + "\n")
        print(f"Dataset generado con exito en {self.output_file}")
        print(f"Total de ejemplos de entrenamiento: {self.records_generated}")

    def run(self):
        print("Iniciando generacion de dataset conversacional para Llama 3.2...")
        examples = self.generate_dataset()
        self.save_to_jsonl(examples)

if __name__ == "__main__":
    generator = FinetuningDatasetGenerator(DATA_FILE, OUTPUT_FILE)
    generator.run()