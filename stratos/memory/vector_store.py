import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from stratos.config import settings

class QdrantStore:
    def __init__(self):
        if settings.qdrant_api_key:
            self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        else:
            self.client = QdrantClient(url=settings.qdrant_url)
            
        self.collection_name = "competitor_signals"
        self._create_collection_if_not_exists()

    def _create_collection_if_not_exists(self):
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
                )
                print(f"Created {self.collection_name} collection")
            else:
                print(f"Collection {self.collection_name} already exists")
        except Exception as e:
            print(f"Error checking/creating collection: {e}")

    def upsert_signal(self, signal_id: str, vector: list[float], payload: dict):
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=signal_id,
                        vector=vector,
                        payload=payload
                    )
                ]
            )
            return True
        except Exception as e:
            print(f"Error upserting signal: {e}")
            return False

    def search_similar(self, vector: list[float], competitor_id: str, top_k: int = 3) -> list[dict]:
        try:
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="competitor_id",
                            match=MatchValue(value=competitor_id),
                        )
                    ]
                ),
                score_threshold=0.98,
                limit=top_k
            )
            return [{"score": r.score, "payload": r.payload} for r in results.points]
        except Exception as e:
            print(f"Error searching similar signals: {e}")
            return []

if __name__ == "__main__":
    try:
        store = QdrantStore()
        print("Qdrant connection successful")
        info = store.client.get_collection(collection_name=store.collection_name)
        print(f"Collection info: {info}")
    except Exception as e:
        print(f"Qdrant test failed: {e}")
