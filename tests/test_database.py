import psycopg

from src.config import get_settings


def test_test_database_connection():
    settings = get_settings()

    # Confirm that the test database is selected.
    assert "water_rag_test_db" in settings.database_url

    # Connect to the test database.
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.documents')")

            result = cur.fetchone()

    # Confirm that the documents table exists.
    assert result[0] == "documents"
