# Running the stack in Docker (day 18)

Services: `app` (FastAPI RAG), `langgraph` (agent, own FastAPI), `db` (PostgreSQL 17 + pgvector, no published port),
`proxy` (Caddy, HTTPS on 80/443). Ollama stays on the host.

## First run
```bash
cp app.env.example app.env && cp postgres.env.example postgres.env && cp langgraph.env.example langgraph.env
# edit the three files (same DB password in app.env and postgres.env); they are git-ignored
UV_TAG=<release> ./scripts/pin_digests.sh   # once: writes the image digests; check `git diff`
docker compose config --quiet               # prints nothing if valid (without --quiet it prints secrets!)
docker compose up -d --build
docker compose ps                           # wait for "healthy"
curl -k https://localhost/health/ready      # -k: Caddy's local certificate
curl -s http://127.0.0.1:8100/health/ready  # LangGraph (this computer only)
```
Ollama on the host must listen beyond loopback (`OLLAMA_HOST=0.0.0.0:11434`) and be firewalled from outside.
The first start runs `schema.sql`, `documents.sql` and the migration. Loading the CSV data and the embeddings
is the same one-off step as before (point `embed_documents.py` at the database on `127.0.0.1` only if you
temporarily publish the port; the default is to run it inside the network).

## Look before you change
```bash
docker history water-rag:release-a
docker logs -f --tail 100 water-rag-app-1
docker inspect --format '{{.State.Health.Status}}' water-rag-app-1
docker exec -it water-rag-app-1 sh        # `id` should say uid=1000(appuser)
docker stats --no-stream
```

## Update and roll back
```bash
docker build -t water-rag:release-b .      # change the code first
# edit docker-compose.yml: image: water-rag:release-b
docker compose up -d
curl -k https://localhost/health/ready     # smoke test + one real request
# roll back: set the tag to release-a, then
docker compose up -d
```
Keep `release-a` until `release-b` has proved itself. Practise the roll back once.

## Graceful shutdown
`docker compose stop app` sends SIGTERM; uvicorn drains running requests (15 s) and the log shows
"shutting down cleanly". `stop_grace_period: 20s` leaves room before SIGKILL.

## Scan
```bash
docker save water-rag:release-a -o /tmp/water-rag.tar
osv-scanner scan image --archive /tmp/water-rag.tar     # or: osv-scanner scan image water-rag:release-a
```
Record the findings. Usually a newer Python base digest clears most; write down what you accept and why.

## Backup the database
```bash
docker compose exec db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup.sql
```
`docker compose down` keeps volumes; `down -v` deletes your data.

## Known limits
- The LangGraph agent keeps paused approvals in memory: a restart forgets them. It has no login, so it is never routed through Caddy.
- Caddy uses its own local CA until you have a real domain (`SITE_ADDRESS`, remove `tls internal`).

## Scan record (OSV-Scanner, 26 Nov 2026)
Images: `water-rag:release-b`, `langgraph-agent:release-a`. Same base: `python:3.15-slim` (Debian 13), pinned by digest.
Result for both: 18 packages, 79 known vulnerabilities (0 critical, 35 high, 33 medium, 5 low, 6 unknown); 4 fixable.
- No findings in Python dependencies (locked in `uv.lock`); all findings are Debian OS packages in the base image.
- No newer `python:3.15-slim` digest existed at scan time, so nothing to re-pin.
- Most findings have no fix from Debian yet. The packages concerned (perl, tar, util-linux, login/passwd, sqlite3 and others) are not called by the app, and the container runs as a non-root user with no login shell.
- Decision: accepted for the lab. Re-scan and rebuild when a newer base digest is published; fixable items (libzstd, shadow) clear with it.
