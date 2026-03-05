import pandas as pd
import re
from html import unescape
from datetime import datetime

def clean_html(text):
    if pd.isna(text):
        return ""
    
    text = str(text)
    text = re.sub(r'<img[^>]*>', '', text)
    text = re.sub(r'<iframe[^>]*>.*?</iframe>', '', text, flags=re.DOTALL)
    text = re.sub(r'data:image/[^"]*', '', text)
    text = re.sub(r'@@PLUGINFILE@@/[^"]*', '', text)
    text = re.sub(r'<div[^>]*>', '', text)
    text = re.sub(r'</div>', '', text)
    text = re.sub(r'<p[^>]*>', '', text)
    text = re.sub(r'</p>', ' ', text)
    text = re.sub(r'<br\s*/?>', ' ', text)
    text = re.sub(r'<strong>', '', text)
    text = re.sub(r'</strong>', '', text)
    text = re.sub(r'<em>', '', text)
    text = re.sub(r'</em>', '', text)
    text = re.sub(r'<span[^>]*>', '', text)
    text = re.sub(r'</span>', '', text)
    text = re.sub(r'<a [^>]*>', '', text)
    text = re.sub(r'</a>', '', text)
    text = re.sub(r'<ul>', '', text)
    text = re.sub(r'</ul>', '', text)
    text = re.sub(r'<ol>', '', text)
    text = re.sub(r'</ol>', '', text)
    text = re.sub(r'<li>', '- ', text)
    text = re.sub(r'</li>', ' ', text)
    text = re.sub(r'<h[1-6][^>]*>', '', text)
    text = re.sub(r'</h[1-6]>', ' ', text)
    text = re.sub(r'<[^>]+>', '', text)
    
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    text = text.replace('"', '')
    text = text.replace('\n', ' ')
    text = text.replace('\r', ' ')
    
    return text

def clean_emoji(text):
    emoji_pattern = re.compile(
        "["
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF"
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text)

def normalize_date(date_str):
    try:
        dt = pd.to_datetime(date_str)
        return dt.strftime('%Y-%m-%d')
    except:
        return date_str

def analyze_sentiment(text):
    if pd.isna(text) or text == "":
        return "neutral"
    
    text_lower = text.lower()
    
    positive_words = [
        'gracias', 'excelente', 'bueno', 'alegr', 'feliz', 'genial', 'maravilloso',
        'encantad', 'éxito', 'inspirador', 'posit', 'mejor', 'satisfacci', 'logr',
        'increible', 'fantástico', 'amor', 'entusiasm', 'emocionad', 'chévere',
        'bienvenid', 'enriquecedor', 'gratificante', 'esperanza'
    ]
    
    negative_words = [
        'dificil', 'problema', 'mal', 'triste', 'preocup', 'error', 'fallo',
        'negativ', 'peor', 'desafortunad', 'lament', 'confus', 'frustra'
    ]
    
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    if positive_count > negative_count:
        return "positivo"
    elif negative_count > positive_count:
        return "negativo"
    else:
        return "neutral"

def extract_tema(topic):
    topic = str(topic)
    topic = clean_emoji(topic)
    topic = clean_html(topic)
    topic = topic.strip()
    
    if len(topic) > 100:
        topic = topic[:100] + "..."
    
    return topic

def normalize_community_name(community):
    community = str(community)
    
    if "Coaches Plataforma Offline" in community:
        return "ProFuturo Conecta: Coaches Plataforma Offline"
    elif "Líderes Innovadores" in community or "Lideres Innovadores" in community:
        return "Red de Líderes Innovadores"
    elif "Pruebas TED" in community or "PTED" in community:
        return "Comunidad Pruebas TED"
    else:
        return community

def clean_csv():
    print("Leyendo archivo CSV original...")
    df = pd.read_csv('data/datos_profuturo.csv')
    
    print(f"Total de mensajes: {len(df)}")
    
    print("Limpiando datos...")
    
    df_clean = pd.DataFrame()
    
    df_clean['tema'] = df['topic'].apply(extract_tema)
    df_clean['autor'] = df['author'].apply(lambda x: clean_html(str(x)))
    df_clean['contenido'] = df['msg'].apply(clean_html)
    df_clean['comunidad'] = df['community'].apply(normalize_community_name)
    df_clean['fecha'] = df['fecha'].apply(normalize_date)
    
    print("Eliminando mensajes vacíos...")
    df_clean = df_clean[df_clean['contenido'].str.len() > 10]
    
    print("Eliminando duplicados...")
    df_clean = df_clean.drop_duplicates(subset=['contenido', 'autor'], keep='first')
    
    print("Analizando sentimientos...")
    df_clean['sentimiento'] = df_clean['contenido'].apply(analyze_sentiment)
    
    print("Asignando mensaje_id...")
    df_clean['mensaje_id'] = range(1, len(df_clean) + 1)
    
    print("Limitando a 222 mensajes más representativos...")
    df_final = df_clean.head(222)
    
    columnas_finales = ['mensaje_id', 'autor', 'comunidad', 'tema', 'contenido', 'fecha', 'sentimiento']
    df_final = df_final[columnas_finales]
    
    print("Guardando archivo limpio...")
    df_final.to_csv('data/datos_profuturo.csv', index=False, encoding='utf-8')
    
    print("\n=== ESTADÍSTICAS ===")
    print(f"Total mensajes procesados: {len(df)}")
    print(f"Total mensajes válidos: {len(df_clean)}")
    print(f"Total mensajes finales: {len(df_final)}")
    print(f"\nDistribución por comunidad:")
    print(df_final['comunidad'].value_counts())
    print(f"\nDistribución por sentimiento:")
    print(df_final['sentimiento'].value_counts())
    print(f"\nRango de fechas: {df_final['fecha'].min()} a {df_final['fecha'].max()}")
    print("\nArchivo limpio guardado en: data/datos_profuturo.csv")

if __name__ == "__main__":
    clean_csv()
