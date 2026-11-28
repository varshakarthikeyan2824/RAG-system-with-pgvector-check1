# Triage report: flawed shop app

Scanned with Bandit 1.x, pip-audit and gitleaks 8.28.0 (Semgrep CE and OSV-Scanner run in CI and on a developer machine).
Each exploit below was reproduced on the original code first, then turned into a test that now passes.

## What the scanners found, and what they missed
| Tool | Result on the original |
|---|---|
| Bandit | 8 findings: MD5 x3 (High), SQL string building (Medium), pickle (Medium + Low), hardcoded strings x2 (Low) |
| pip-audit | `requests 2.19.1`: 10 known vulnerabilities (fixes in 2.20.0 to 2.33.0). The package is not used by the code |
| gitleaks | No leaks found. The default rules do not recognise the fake `sk_live_...` string or `admin-token-123`, so "clean" is not "safe" |
| Not flagged by anything | Missing login on `/admin/users` and `/orders`, SSRF in `/fetch`, forgeable token, wildcard CORS, `debug=True` |

Lesson: Bandit rated pickle only Medium, but it is remote code execution. Severity labels are a starting point, not the ranking. Logic flaws (access control, SSRF) need review and tests.

## Top 5, in the order fixed
| # | Flaw | Impact (reproduced) | Fix | Test |
|---|---|---|---|---|
| 1 | `pickle.loads` on request data (`/import`) | Server ran code chosen by the caller | Typed JSON model, admin only | `test_import_*` |
| 2 | SQL injection (`/search`) | One request returned every password hash | Bound parameter | `test_search_is_not_injectable` |
| 3 | No login or ownership checks (`/admin/users`, `/orders/{id}`), token = base64(name), hash returned | Anyone read all users and any order; anyone could forge an admin token | Random session tokens, admin-only route, owner-only orders, no hash in output | `test_admin_users_*`, `test_orders_*`, `test_token_*` |
| 4 | Secrets in code and README; API key sent inside the request body | Key readable by anyone with the repo or the log | Read from environment, fail if missing, key sent in a header, README cleaned, `.env.example` added | `test_no_secret_values_*`, `test_llm_key_*` |
| 5 | SSRF (`/fetch`) | Caller could make the server request internal addresses | Host allow-list, https only, public addresses only, no redirects, 5 s timeout | `test_fetch_*` |

Also changed on the way: the login log no longer prints the password; `/search`, `/fetch` and `/ask` now need a login; `/ask` has a timeout and a clean 502.

## Still open (next in line)
1. MD5 password hashing (Bandit High x3): move to a slow salted hash (scrypt or argon2) and re-hash on login.
2. `requests 2.19.1`: unused, so removed from `requirements.txt` (clears all 10 advisories). Pin the rest with a lock file.
3. `debug=True` and wildcard CORS: set debug from an environment flag and list real origins.
4. Sessions are in memory (lost on restart); no login rate limit.
5. Original Dockerfile and Compose file: `python:latest`, runs as root, `--reload`, `COPY . .` (would copy `.env`), `postgres:latest` with the password `postgres` and port 5432 published. Rebuild them the way the Day 18 files do.
6. SSRF residual risk: the host name is resolved twice (our check, then httpx), so DNS rebinding is not fully closed. Pin the resolved address if this endpoint is kept.

## Left as false positive
Bandit B105 on `"token": None` in `/login`: a null value, not a password.
