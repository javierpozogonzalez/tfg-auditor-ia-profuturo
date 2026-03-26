import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama

load_dotenv()

def get_llm():
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL_NAME", "profuturo-auditor")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    
    return ChatOllama(
        base_url=base_url,
        model=model,
        temperature=temperature
    )