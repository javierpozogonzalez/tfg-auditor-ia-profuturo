import os
from dotenv import load_dotenv
from langchain_aws import ChatBedrock
# from langchain_community.chat_models import ChatOllama

load_dotenv()

def get_llm():
    # Uso actual: API de Amazon Bedrock (Claude 4.5)
    return ChatBedrock(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0", 
        model_kwargs={"temperature": 0.0},
        region_name=os.getenv("REGION_BEDROCK"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("AWS_SECRET_KEY")
    )

    # FUTURO: Modelo propio (profuturo-ia) alojado en maquina virtual de AWS
    # Descomentar este bloque y comentar el de arriba cuando exista la instancia EC2
    # model_name = os.getenv("LLM_MODEL", "profuturo-ia")
    # base_url = os.getenv("OLLAMA_AWS_HOST", "http://IP_DE_MAQUINA_AWS:11434")
    # 
    # return ChatOllama(
    #     base_url=base_url,
    #     model=model_name,
    #     temperature=0.0
    # )