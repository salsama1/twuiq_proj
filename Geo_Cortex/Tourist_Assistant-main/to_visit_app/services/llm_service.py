from langchain_core.output_parsers import StrOutputParser
from langchain_openai import OpenAI

llm = OpenAI(temperature=0)
parser = StrOutputParser()

def generate_response(formatted_prompt: str) -> str:
    return parser.invoke(llm.invoke(formatted_prompt))
