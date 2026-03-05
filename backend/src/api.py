import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.agent import run_agent
from src.tools import (
    generate_report_pdf,
    generate_interaction_graph,
    get_community_stats,
    get_top_topics,
    get_sentiment_distribution
)

load_dotenv()

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app = FastAPI(
    title="ProFuturo AI Analytics API",
    description="Backend API para el dashboard de analisis de foros educativos",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    comunidad: str = "todas"

class ChatResponse(BaseModel):
    response: str
    metadata: dict = {}

class StatsRequest(BaseModel):
    comunidad: str = "todas"

@app.get("/")
async def root():
    return {
        "message": "ProFuturo AI Analytics API",
        "version": "1.0.0",
        "status": "online"
    }

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        response = run_agent(request.message, request.comunidad)
        
        return ChatResponse(
            response=response,
            metadata={
                "comunidad": request.comunidad,
                "timestamp": "2026-02-23T00:00:00Z"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando la consulta: {str(e)}")

@app.post("/api/stats")
async def get_stats(request: StatsRequest):
    try:
        stats = get_community_stats(request.comunidad if request.comunidad != "todas" else None)
        topics = get_top_topics(request.comunidad if request.comunidad != "todas" else None, limit=5)
        sentiments = get_sentiment_distribution(request.comunidad if request.comunidad != "todas" else None)
        
        return {
            "stats": stats,
            "top_topics": topics,
            "sentiments": sentiments
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo estadisticas: {str(e)}")

@app.post("/api/generate-report")
async def generate_report(request: StatsRequest):
    try:
        stats = get_community_stats(request.comunidad if request.comunidad != "todas" else None)
        topics = get_top_topics(request.comunidad if request.comunidad != "todas" else None, limit=5)
        sentiments = get_sentiment_distribution(request.comunidad if request.comunidad != "todas" else None)
        
        report_data = {
            "titulo": f"Reporte de Analisis - {stats['comunidad']}",
            "comunidad": stats['comunidad'],
            "metricas": {
                "Total de Mensajes": stats['total_mensajes'],
                "Total de Autores": stats['total_autores'],
                "Promedio de Respuestas": stats['promedio_respuestas']
            },
            "descripcion": f"Analisis detallado de la actividad en {stats['comunidad']}. "
                          f"Los temas mas discutidos son: {', '.join([t['tema'] for t in topics[:3]])}. "
                          f"El sentimiento predominante es {max(sentiments, key=sentiments.get)} con {sentiments[max(sentiments, key=sentiments.get)]}%.",
            "conclusion": "La comunidad muestra un nivel de engagement positivo con oportunidades de mejora "
                         "en la diversificacion de temas y la participacion de nuevos autores."
        }
        
        file_path = generate_report_pdf(report_data, f"reporte_{request.comunidad}.pdf")
        
        return {
            "success": True,
            "file_path": file_path,
            "message": "Reporte generado exitosamente"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando reporte: {str(e)}")

@app.post("/api/generate-graph")
async def generate_graph(request: StatsRequest):
    try:
        file_path = generate_interaction_graph(
            request.comunidad if request.comunidad != "todas" else None,
            f"grafo_{request.comunidad}.png"
        )
        
        return {
            "success": True,
            "file_path": file_path,
            "message": "Grafo generado exitosamente"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando grafo: {str(e)}")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ProFuturo AI Analytics API"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
