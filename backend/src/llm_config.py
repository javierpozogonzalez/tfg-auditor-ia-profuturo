import os
import json
from typing import Any

import boto3
from dotenv import load_dotenv
from langchain_aws import SagemakerEndpoint
from langchain_aws.llms.sagemaker_endpoint import LLMContentHandler

load_dotenv()


class QwenChatMLContentHandler(LLMContentHandler):
    content_type = "application/json"
    accepts = "application/json"

    def transform_input(self, prompt: str, model_kwargs: dict[str, Any]) -> bytes:
        payload = {
            "inputs": prompt,
            "parameters": model_kwargs or {},
        }
        return json.dumps(payload).encode("utf-8")

    def transform_output(self, output: bytes) -> str:
        data = json.loads(output.read().decode("utf-8"))
        if isinstance(data, list) and data:
            item = data[0]
            if isinstance(item, dict):
                return str(item.get("generated_text", ""))
            return str(item)
        if isinstance(data, dict):
            return str(data.get("generated_text", data.get("output", "")))
        return str(data)


def get_llm():
    region_name = os.getenv("AWS_REGION", "us-east-1")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    max_new_tokens = int(os.getenv("LLM_MAX_NEW_TOKENS", "1024"))

    session = boto3.session.Session(region_name=region_name)
    client = session.client("sagemaker-runtime")

    return SagemakerEndpoint(
        endpoint_name="profuturo-cerebro-qwen-7b-v2",
        client=client,
        content_handler=QwenChatMLContentHandler(),
        model_kwargs={
            "temperature": temperature,
            "max_new_tokens": max_new_tokens,
        },
    )