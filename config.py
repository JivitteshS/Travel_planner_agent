import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_openai import AzureChatOpenAI

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATION_STACK_API_KEY = os.getenv("AVIATION_STACK_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")

# ------------------------
# LangSmith observability
# ------------------------
# Accepts either the LANGSMITH_* or the legacy LANGCHAIN_* env var names.
# Tracing is only switched on when an API key is actually present, so a
# machine without LangSmith configured just runs untraced instead of erroring.
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
LANGSMITH_PROJECT = (
    os.getenv("LANGSMITH_PROJECT")
    or os.getenv("LANGCHAIN_PROJECT")
    or "travel-planner-agent"
)
LANGSMITH_ENDPOINT = os.getenv("LANGSMITH_ENDPOINT") or os.getenv("LANGCHAIN_ENDPOINT")
LANGSMITH_TRACING_ENABLED = bool(LANGSMITH_API_KEY) and os.getenv(
    "LANGSMITH_TRACING", os.getenv("LANGCHAIN_TRACING_V2", "true")
).lower() not in ("false", "0", "")

if LANGSMITH_TRACING_ENABLED:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGSMITH_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT
    os.environ["LANGSMITH_PROJECT"] = LANGSMITH_PROJECT
    if LANGSMITH_ENDPOINT:
        os.environ["LANGCHAIN_ENDPOINT"] = LANGSMITH_ENDPOINT
        os.environ["LANGSMITH_ENDPOINT"] = LANGSMITH_ENDPOINT
else:
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"


def get_llm():
    return ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))

# def get_llm():
#     return AzureChatOpenAI(
#         azure_endpoint=AZURE_OPENAI_ENDPOINT,
#         azure_deployment=AZURE_OPENAI_DEPLOYMENT_NAME,
#         api_key=AZURE_OPENAI_API_KEY,
#         api_version=AZURE_OPENAI_API_VERSION,
#     )