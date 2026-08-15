from langchain_groq import ChatGroq
from langchain_ollama import OllamaEmbeddings
import concurrent.futures

OLLAMA_BASE_URL = "http://localhost:11434"

def get_extraction_llm():
    """Fast, consistent model for extraction / fact-checking / graph-building.
    Runs on Groq's cloud infrastructure -- no local RAM/CPU load."""
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
    )

def get_synthesis_llm():
    """Model used for the final brief-writing step."""
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.3,
    )

def get_embeddings():
    """Groq doesn't offer embeddings, so this still runs locally via Ollama.
    Only the (lightweight) nomic-embed-text model needs to stay local."""
    return OllamaEmbeddings(model="nomic-embed-text", base_url=OLLAMA_BASE_URL)


def invoke_with_timeout(llm, prompt, timeout_seconds=120):
    """Run llm.invoke in a background thread with a hard timeout."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(llm.invoke, prompt)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"LLM call exceeded {timeout_seconds}s timeout")