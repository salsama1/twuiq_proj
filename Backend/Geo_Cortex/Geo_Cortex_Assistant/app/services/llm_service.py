from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from langchain_core.output_parsers import StrOutputParser
import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama

load_dotenv()

# Initialize local Ollama LLM
# Make sure Ollama is running: `ollama serve`
llm = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "llama3.1"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0")),
)
parser = StrOutputParser()

_EXEC = ThreadPoolExecutor(max_workers=1)


def generate_response(formatted_prompt: str) -> str:
    """Generate response using LLM"""
    if os.getenv("LLM_DISABLED", "").strip().lower() in {"1", "true", "yes"}:
        return "LLM is disabled (LLM_DISABLED=true)."

    timeout_s = float(os.getenv("LLM_TIMEOUT_SEC", "20"))

    def _call() -> str:
        return parser.invoke(llm.invoke(formatted_prompt))

    fut = _EXEC.submit(_call)
    try:
        return fut.result(timeout=timeout_s)
    except FuturesTimeoutError:
        return (
            "LLM call timed out. If you want fully-offline answers, set LLM_DISABLED=true, "
            "or increase LLM_TIMEOUT_SEC, and make sure Ollama is running."
        )
    except Exception as e:
        return f"LLM error: {e}"
