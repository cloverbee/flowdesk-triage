"""
build_index.py — Embeds every article in kb/ and loads it into a local
Qdrant collection on disk.

This is what upgrades search_kb (see tools.py) from keyword scoring to
semantic retrieval. Run it once, and again any time kb/ changes — the agent
loop in agent.py never has to know the difference (Day 3, Topic 2).

Qdrant runs here in local/embedded mode (a directory on disk, like SQLite),
and embeddings run through FastEmbed's local ONNX models — no server to
stand up, no API key, though the first run downloads the embedding model
(~130MB) from Hugging Face.

Usage:
    python build_index.py
"""

from pathlib import Path

from qdrant_client import QdrantClient, models

KB_DIR = Path(__file__).parent / "kb"
QDRANT_PATH = Path(__file__).parent / "qdrant_data"
COLLECTION = "flowdesk_kb"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"  # FastEmbed default: small, fast, runs locally


def main() -> None:
    client = QdrantClient(path=str(QDRANT_PATH))

    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(
            size=client.get_embedding_size(EMBED_MODEL),
            distance=models.Distance.COSINE,
        ),
    )

    articles = sorted(KB_DIR.glob("*.md"))
    points = [
        models.PointStruct(
            id=i,
            vector=models.Document(text=path.read_text().strip(), model=EMBED_MODEL),
            payload={"filename": path.name, "text": path.read_text().strip()},
        )
        for i, path in enumerate(articles)
    ]

    client.upsert(collection_name=COLLECTION, points=points)
    print(f"Indexed {len(points)} articles from {KB_DIR}/ into '{COLLECTION}' at {QDRANT_PATH}/")


if __name__ == "__main__":
    main()
