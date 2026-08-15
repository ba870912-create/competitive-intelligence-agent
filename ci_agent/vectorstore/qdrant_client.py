from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from ci_agent.llm.ollama_client import get_embeddings
import uuid

embedder = get_embeddings()          # nomic-embed-text via Ollama
EMBED_DIM = 768                       # nomic-embed-text output size

class VectorStore:
    def __init__(self):
        self.client = QdrantClient(url="http://localhost:6333")
        if not self.client.collection_exists("announcements"):
            self.client.create_collection(
                collection_name="announcements",
                vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            )

    def upsert_claim(self, claim):
        vector = embedder.embed_query(claim.text)
        self.client.upsert(
            collection_name="announcements",
            points=[PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"competitor": claim.competitor, "text": claim.text,
                         "source_url": claim.source_url, "date": str(claim.observed_on)},
            )],
        )

    def semantic_search(self, query: str, top_k: int = 8):
        vector = embedder.embed_query(query)
        result = self.client.query_points(
            collection_name="announcements",
            query=vector,
            limit=top_k,
        )
        return result.points