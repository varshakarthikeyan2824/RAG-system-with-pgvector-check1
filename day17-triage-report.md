# Day 17 triage report: RAG system with pgvector

## 1. Summary

Four hardening controls were added and tested (security headers, CORS allowlist, rate limiting, request size limit), together with a production secret check, failed-login logging and a configurable embedding URL. All four scanners finished clean after the changes. Nine new tests were added and the full suite passes (45 tests). A leaked-secret drill was completed in a throwaway repository.

A clean scan means "nothing obvious was found", not "secure". `pip-audit` checks known advisories only, Semgrep CE uses community rules, and gitleaks sees committed history only.

## 2. Controls added

| Control | Result | Evidence |
|---|---|---|
| Security headers | CSP with `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`. HSTS is sent outside development | `curl -i /health`, `test_security_headers_present` |
| CORS allowlist | Empty by default. An unlisted origin gets `400` and no `access-control-allow-origin` header. A listed origin is allowed. `*` is rejected in settings | Preflight curl for both cases, two CORS tests |
| Rate limiting | `/login`: 5 requests per minute. `/ask` and `/knowledge/ask`: 20 per minute. Over the limit returns `429` with `Retry-After` | Curl loop, `test_login_rate_limit_returns_429_with_retry_after` |
| Request size limit | 64 KB cap. `413` when too large, `411` for chunked bodies. Security headers also appear on these error responses | Curl for both cases, two tests |
| Production secret check | The app refuses to start in production if the service key or session key is shorter than 32 characters. Input values are hidden in the error | Weak-key run before and after `hide_input_in_errors` |
| Failed-login logging | One warning per failed login with the user ID and request ID, never the password | `pytest -k login -s` output |
| Lockfile and pinned versions | `uv.lock` committed, 132 pinned lines exported | `pip-audit` run |
| Safe file upload | Not applicable. The app has no upload endpoint, so there was nothing to implement or test. Revisit if document upload is added | Code review |

The tests live in `tests/test_hardening.py`. As a check that they can fail, `nosniff` was removed on purpose and exactly the three tests that check it failed. The line was then restored.

## 3. Scanner results

| Tool | Result | Decision |
|---|---|---|
| `pip-audit` | No known vulnerabilities | None needed. Rerun before each release |
| Bandit | 1 Low finding at first (B105, `webhook_simulator.py:60`), then 0 issues in 899 lines | Ignored as a false positive. `"wrong"` is a test-case label, not a credential. Suppressed with `# nosec B105`, reason on the line above |
| Semgrep CE | 0 findings, 157 rules, 13 of 13 tracked files in `src` | None needed. `tests/` is excluded by default |
| gitleaks | No leaks in 13 commits | None needed. The installed binary is old (only `detect`), so consider updating |

## 4. Manual findings

| # | Finding | Severity | Decision | Status |
|---|---|---|---|---|
| 5 | `.env.example` had `SERVICE_API_KEY=key` | Medium | Fix | Fixed. Placeholder text plus the production startup check |
| 6 | `requires-python >=3.15` and very new dependency versions | Low | Accept and document | Open. One new-version failure was met (`call_next`), so test on the exact Python version that is deployed |
| 7 | Ollama URL hard-coded in two files | Low | Fix | Fixed. `OLLAMA_EMBED_URL` setting with the same default |
| 8 | Failed logins were not logged | Medium | Fix | Fixed |
| 9 | Rate limiter keeps counts in memory and keys on the direct client IP | Medium | Accept for now | Open. Needs Redis for several workers, and the forwarded IP behind a proxy |
| 10 | Retrieved text is placed in the prompt without delimiters | Medium | Fix on day 28 | Open. Prompt-injection risk |
| 11 | `citations` return the full document text | Low to medium | Verify | Open. Check that `templates/partials/answer.html` does not render it unescaped |
| 12 | 500 responses may lack security headers, because the bare `Exception` handler runs outside the middleware | Low | Fix | Open. Apply `SECURITY_HEADERS` in `general_exception_handler` |

## 5. Slopsquatting drill

All 10 suggested packages exist and have long histories (6 to 530 releases, first uploads between 2006 and 2023), checked against the PyPI JSON API. The AI-written reference table contained several wrong dates, so the PyPI values were used instead.

| Package | Releases | First upload | Decision | Reason |
|---|---|---|---|---|
| `fastapi` | 371 | 2018-12-08 | Use | Already in the project |
| `pydantic` | 212 | 2017-05-03 | Use | Already in the project |
| `pgvector` | 27 | 2021-06-12 | Use | Already in the project |
| `sqlalchemy` | 344 | 2006-02-14 | Reject for now | Raw parameterised SQL is already used |
| `langchain` | 530 | 2022-10-25 | Reject | Large dependency tree, retrieval code is small |
| `llama-index` | 506 | 2023-02-16 | Reject | Same reason as `langchain` |
| `sentence-transformers` | 86 | 2019-07-25 | Reject | Pulls in PyTorch, embeddings come from Ollama |
| `PyMuPDF` | 140 | 2017-11-27 | Defer | Only needed for PDF ingestion, AGPL licence needs review |
| `redis` | 171 | 2012-10-08 | Defer | For the rate limiter if several workers are used |
| `ragas` | 90 | 2023-05-14 | Defer | A retrieval evaluation already exists |

Limitation: every name was well known, so this round could not catch a hallucinated package. The real test case from the exercises is `fastapi_jwt_guardrail_kit` (Snippet 4), which was not looked up here.

## 6. Leaked-secret drill

Carried out in a throwaway repository with a fake random token. No real credential was used and the project repository was not touched.

| Step | Result |
|---|---|
| Detect | gitleaks found the token (`github-pat`, `config.env` line 1, commit `d7a792f`) |
| Rotate | Recorded as the first action. A pushed secret is compromised, and removing it from history cannot undo that |
| Remove | `git filter-repo --path config.env --invert-paths`. The file was gone from all history and the commit hashes changed |
| Lesson | gitleaks printed the full secret. Use `--redact` on real repositories |

### Team steps

Replace this list with the steps written during the drill if they differ.

1. Rotate first. Revoke the exposed secret and issue a new one, assuming it was copied.
2. Check the provider's logs for use of the old secret.
3. Rewrite history only if needed, for example when a shared or public repository still contains the secret.
4. Rewrite on a fresh clone with `git filter-repo` and verify with gitleaks.
5. Warn the team, then force-push all branches and tags.
6. Everyone re-clones. Old clones still hold the secret and can bring it back on merge.
7. Prevent a repeat with the gitleaks pre-commit hook and a `.gitignore` entry.

## 7. Not covered in this report

The six spot-the-flaw snippets 