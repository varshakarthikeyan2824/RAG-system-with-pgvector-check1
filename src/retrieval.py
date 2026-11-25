from collections import namedtuple

import httpx
import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from src.config import get_settings

DATABASE_URL = get_settings().database_url

OLLAMA_URL = get_settings().ollama_embed_url
MODEL = "nomic-embed-text"


def generate_query_embedding(question):
    response = httpx.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "input": question,
        },
        timeout=60,
    )
    response.raise_for_status()

    embedding = response.json()["embeddings"][0]

    if len(embedding) != 768:
        raise ValueError("Expected 768-dimensional embedding")

    return embedding


def search_documents(question, tenant_id, user_role, limit=5):
    query_embedding = generate_query_embedding(question)

    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, content, source,
                       embedding <=> %s AS distance
                FROM documents
                WHERE tenant_id = %s
                  AND %s = ANY(allowed_roles)
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (
                    Vector(query_embedding),
                    tenant_id,
                    user_role,
                    Vector(query_embedding),
                    limit,
                ),
            )

            return cur.fetchall()


if __name__ == "__main__":
    results = search_documents(
        question="What is the water tariff per litre in Mumbai?",
        tenant_id="water_company_A",
        user_role="engineer",
        limit=5,
    )

    for result in results:
        print("\nSource:", result[2])
        print("Content:", result[1])
        print("Distance:", result[3])

User = namedtuple("User", ["tenant_id", "role"])


def lookup_user(user_id):
    """Return the user's tenant and role from the database, or None if unknown."""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id, role FROM users WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
    return User(*row) if row else None
