import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import boto3
import httpx
from botocore.config import Config
from dotenv import load_dotenv
from langchain_core.language_models.llms import LLM
from pydantic import PrivateAttr

load_dotenv()
logger = logging.getLogger(__name__)

AWS_REGION     = os.getenv("AWS_REGION", "eu-west-1")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS  = int(os.getenv("LLM_MAX_TOKENS", "2048"))
LLM_BACKEND     = os.getenv("LLM_BACKEND", "sagemaker").lower()
LLM_LOCAL_URL   = os.getenv("LLM_LOCAL_URL", "http://127.0.0.1:8090")

_CHATML_RE = re.compile(r"<\|im_start\|>(\w+)\n(.*?)<\|im_end\|>", re.DOTALL)


# ── LocalLlamaLLM ─────────────────────────────────────────────────────────────

class LocalLlamaLLM(LLM):
    """Llama.cpp con API compatible OpenAI en http://127.0.0.1:8090."""

    base_url: str = LLM_LOCAL_URL
    temperature: float = LLM_TEMPERATURE
    max_tokens: int = LLM_MAX_TOKENS

    @property
    def _llm_type(self) -> str:
        return "local_llama_cpp"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"base_url": self.base_url, "temperature": self.temperature, "max_tokens": self.max_tokens}

    def _parse_chatml(self, prompt: str) -> List[Dict[str, str]]:
        """Convierte un prompt en formato ChatML a lista de mensajes OpenAI."""
        role_map = {"system": "system", "user": "user", "assistant": "assistant"}
        messages = []
        for role, content in _CHATML_RE.findall(prompt):
            mapped = role_map.get(role)
            if mapped:
                messages.append({"role": mapped, "content": content.strip()})
        return messages

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        messages = self._parse_chatml(prompt)
        if not messages:
            messages = [
                {"role": "system", "content": "Eres el Auditor IA de ProFuturo. Analiza foros educativos."},
                {"role": "user", "content": prompt},
            ]

        payload: Dict[str, Any] = {
            "model": "qwen",
            "messages": messages,
            "temperature": float(kwargs.get("temperature", self.temperature)),
            "max_tokens": int(kwargs.get("max_tokens", self.max_tokens)),
            "stop": stop or ["<|im_end|>", "<|endoftext|>"],
        }

        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(f"{self.base_url}/v1/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.exception("Error invocando llama.cpp local")
            raise RuntimeError(f"Error llamando a llama.cpp en {self.base_url}: {exc}") from exc


# ── QwenTGILLM (SageMaker) ────────────────────────────────────────────────────

class QwenTGILLM(LLM):
    endpoint_name: str
    region_name: str = AWS_REGION
    temperature: float = LLM_TEMPERATURE
    max_new_tokens: int = LLM_MAX_TOKENS

    _client: Any = PrivateAttr(default=None)

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

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "sagemaker-runtime",
                region_name=self.region_name,
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                config=Config(read_timeout=120, connect_timeout=10, retries={"max_attempts": 2}),
            )
        return self._client

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
            response = self._get_client().invoke_endpoint(
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


# ── Factory ───────────────────────────────────────────────────────────────────

def get_profuturo_llm() -> LLM:
    if LLM_BACKEND == "local":
        logger.info("LLM backend: llama.cpp local en %s", LLM_LOCAL_URL)
        return LocalLlamaLLM(
            base_url=LLM_LOCAL_URL,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
        )

    # SageMaker TGI
    endpoint = os.getenv("PROFUTURO_ENDPOINT") or os.getenv("SAGEMAKER_ENDPOINT", "")
    if not endpoint:
        raise RuntimeError("Define PROFUTURO_ENDPOINT o SAGEMAKER_ENDPOINT en el entorno.")
    logger.info("LLM backend: SageMaker TGI endpoint=%s", endpoint)
    return QwenTGILLM(
        endpoint_name=endpoint,
        region_name=AWS_REGION,
        temperature=LLM_TEMPERATURE,
        max_new_tokens=LLM_MAX_TOKENS,
    )
