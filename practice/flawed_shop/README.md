# Shop service (day 19 practice app)

Small service for orders, used to practise scanning, triage and fixing. See `TRIAGE.md`.

Run the tests: `LLM_API_KEY=x python -m pytest -q` (or copy `.env.example` to `.env` and export it).
Settings come from the environment: `LLM_API_KEY`, `ALLOWED_FETCH_HOSTS`. No credentials belong in this file.

## Endpoints
`/login` (returns a session token), then send `Authorization: Bearer <token>` to
`/search`, `/orders/{id}`, `/fetch`, `/ask`; `/admin/users` and `/import` need an admin account.
