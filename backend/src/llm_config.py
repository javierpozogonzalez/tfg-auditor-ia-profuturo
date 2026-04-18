import json
import logging
import os
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from dotenv import load_dotenv
from langchain_core.language_models.llms import LLM

load_dotenv()
logger = logging.getLogger(__name__)

AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "512"))


class QwenTGILLM(LLM):
    endpoint_name: str
    region_name: str = AWS_REGION
    temperature: float = LLM_TEMPERATURE
    max_new_tokens: int = LLM_MAX_TOKENS

    @property
    def _llm_type(self) -> str:
        return "qwen_tgi_sagemaker"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "endpoint_name": self.endpoint_name,
            "region_name": self.region_name,
            "temperature": self.temperature,
            "max_new_tokens": self.max_new_tokens,
        }

    def _build_client(self):
        return boto3.client(
            "sagemaker-runtime",
            region_name=self.region_name,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            config=Config(read_timeout=120, connect_timeout=10, retries={"max_attempts": 2}),
        )

    def _ensure_chatml(self, prompt: str) -> str:
        stripped = prompt.lstrip()
        if stripped.startswith("<|im_start|>"):
            return prompt

        return (
            "<|im_start|>system\n"
            "Eres el Auditor IA de ProFuturo. Analiza foros educativos con precision institucional.\n"
            "<|im_end|>\n"
            f"<|im_start|>user\n{prompt}\n<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        payload = {
            "inputs": self._ensure_chatml(prompt),
            "parameters": {
                "max_new_tokens": int(kwargs.get("max_new_tokens", self.max_new_tokens)),
                "temperature": float(kwargs.get("temperature", self.temperature)),
                "do_sample": float(kwargs.get("temperature", self.temperature)) > 0,
                "stop": stop or kwargs.get("stop") or ["<|im_end|>", "<|endoftext|>"],
                "return_full_text": False,
                "repetition_penalty": float(kwargs.get("repetition_penalty", 1.1)),
            },
        }

        try:
            client = self._build_client()
            response = client.invoke_endpoint(
                EndpointName=self.endpoint_name,
                ContentType="application/json",
                Accept="application/json",
                Body=json.dumps(payload),
            )
            raw = response["Body"].read().decode("utf-8")
            result = json.loads(raw)

            if isinstance(result, list) and result:
                text = str(result[0].get("generated_text", ""))
            elif isinstance(result, dict):
                if "generated_text" in result:
                    text = str(result["generated_text"])
                elif "output" in result:
                    text = str(result["output"])
                elif "outputs" in result and isinstance(result["outputs"], list) and result["outputs"]:
                    text = str(result["outputs"][0])
                else:
                    text = str(result)
            else:
                text = str(result)

            return text.replace("<|im_start|>assistant\n", "").replace("<|im_end|>", "").strip()
        except Exception as exc:
            logger.exception("Error invocando endpoint SageMaker TGI")
            raise RuntimeError(f"Error raised by inference endpoint: {exc}") from exc


def get_profuturo_llm() -> QwenTGILLM:
    endpoint = os.getenv("PROFUTURO_ENDPOINT") or os.getenv("SAGEMAKER_ENDPOINT", "")
    if not endpoint:
        raise RuntimeError("Define PROFUTURO_ENDPOINT o SAGEMAKER_ENDPOINT en el entorno.")

    return QwenTGILLM(
        endpoint_name=endpoint,
        region_name=AWS_REGION,
        temperature=LLM_TEMPERATURE,
        max_new_tokens=LLM_MAX_TOKENS,
    )


def get_llm() -> QwenTGILLM:
    return get_profuturo_llm()