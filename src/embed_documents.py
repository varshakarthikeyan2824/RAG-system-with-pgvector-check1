import httpx
import psycopg
from pgvector.psycopg import register_vector
from src.config import get_settings

DATABASE_URL = get_settings().database_url

OLLAMA_URL = get_settings().ollama_embed_url
MODEL = "nomic-embed-text"


def generate_embedding(text):
    response = httpx.post(
        OLLAMA_URL,
        json={"model": MODEL, "input": text},
        timeout=60,
    )
    response.raise_for_status()

    embedding = response.json()["embeddings"][0]

    if len(embedding) != 768:
        raise ValueError("Expected 768-dimensional embedding")

    return embedding


def main():
    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, content
                FROM documents
                WHERE embedding IS NULL
                """
            )
            documents = cur.fetchall()

            print(f"Documents to embed: {len(documents)}")

            for document_id, content in documents:
                embedding = generate_embedding(content)

                cur.execute(
                    """
                    UPDATE documents
                    SET embedding = %s
                    WHERE id = %s
                    """,
                    (embedding, document_id),
                )

            conn.commit()

    print("Embedding generation completed!")


if __name__ == "__main__":
    main()
