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


def generate_response(formatted_prompt: str) -> str:
    """Generate response using LLM"""
    return parser.invoke(llm.invoke(formatted_prompt))
