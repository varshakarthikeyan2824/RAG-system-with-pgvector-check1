#!/usr/bin/env bash
# Creates the test database the pytest suite expects (water_rag_test_db) and loads the schema.
# Used by the CI workflow and works the same on a laptop.
# Needs the standard libpq variables: PGHOST, PGPORT, PGUSER, PGPASSWORD (the user must be allowed
# to CREATE EXTENSION, i.e. a superuser).
set -euo pipefail
cd "$(dirname "$0")/.."

DB=water_rag_test_db
psql -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE IF EXISTS ${DB}" -c "CREATE DATABASE ${DB}"
psql -v ON_ERROR_STOP=1 -d "${DB}" \
  -c "CREATE EXTENSION IF NOT EXISTS vector" \
  -f schema.sql \
  -f documents.sql \
  -f migrations/001_authentication.sql
echo "test database ${DB} ready"
