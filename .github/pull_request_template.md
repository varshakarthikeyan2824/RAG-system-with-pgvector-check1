## What and why
<!-- One or two sentences: what changes, and the reason. Link the issue or task if there is one. -->

## How I tested it
<!-- Commands you ran and what you saw. Paste the important lines, not the whole log. -->
- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run pytest -q` (needs the test database: see `scripts/ci_setup_test_db.sh`)
- [ ] Tried the change by hand where it touches behaviour (endpoint, page, container)

## Security and safety
- [ ] No secrets, keys, passwords or real data in the diff (env files stay out; `.example` copies only)
- [ ] New or changed endpoint: login and role checks are in place, and a test proves it
- [ ] New dependency: needed, maintained, and added to the lock file (`uv lock`)
- [ ] User input never reaches SQL text, a shell, a file path or an outbound URL unchecked

## Deployment and rollback
- [ ] Docker or Compose change: image tags and digests are pinned, and I started the stack once
- [ ] Database change: migration included and the schema files still load from empty
- [ ] If this breaks production, the rollback is: <!-- e.g. set the image tag back to the previous release -->

## Notes for the reviewer
<!-- Anything you are unsure about, or want a second opinion on. -->
