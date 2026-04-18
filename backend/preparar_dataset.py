import pandas as pd
import json

def construir_dataset(csv_in, jsonl_out):
    df = pd.read_csv(csv_in)
    system_prompt = "Eres el Auditor IA de ProFuturo, un asistente experto que ayuda a coordinadores y docentes analizando la información de las comunidades virtuales."
    
    with open(jsonl_out, 'w', encoding='utf-8') as f:
        for _, row in df.iterrows():
            if pd.isna(row['contenido']):
                continue
                
            pregunta = f"¿Qué comentó {row['autor']} en la comunidad '{row['comunidad']}' respecto al tema '{row['tema']}'?"
            respuesta = f"El {row['fecha']}, {row['autor']} aportó lo siguiente: \"{row['contenido']}\". Este mensaje tiene un sentimiento clasificado como {row['sentimiento']}."
            
            record = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": pregunta},
                    {"role": "assistant", "content": respuesta}
                ]
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
            
            pregunta_resumen = f"Haz un resumen del mensaje de {row['autor']} el {row['fecha']}."
            respuesta_resumen = f"En la comunidad '{row['comunidad']}', {row['autor']} habló sobre '{row['tema']}'. Su mensaje principal fue: {row['contenido']}"
            
            record_resumen = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": pregunta_resumen},
                    {"role": "assistant", "content": respuesta_resumen}
                ]
            }
            f.write(json.dumps(record_resumen, ensure_ascii=False) + '\n')

if __name__ == "__main__":
    construir_dataset('data/datos_profuturo.csv', 'dataset_qlora_final.jsonl')