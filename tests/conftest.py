import os
from urllib.parse import urlsplit, urlunsplit

from config import get_settings

# Read the existing database configuration.
settings = get_settings()

# Build a separate URL for the test database.
parts = urlsplit(settings.database_url)

test_database_url = urlunsplit(
    (
        parts.scheme,
        parts.netloc,
        "/water_rag_test_db",
        parts.query,
        parts.fragment,
    )
)

# Make pytest use the test database.
os.environ["DATABASE_URL"] = test_database_url
os.environ["APP_ENV"] = "test"

# Reload settings with the test database URL.
get_settings.cache_clear()
