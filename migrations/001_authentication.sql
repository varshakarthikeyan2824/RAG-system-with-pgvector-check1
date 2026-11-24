BEGIN;

-- Add password storage to existing users.
ALTER TABLE users
ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- Store hashed session tokens, never raw session tokens.
CREATE TABLE IF NOT EXISTS user_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT token_hash_length
        CHECK (length(token_hash) = 64),
    CONSTRAINT valid_session_expiry
        CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id
ON user_sessions (user_id);

CREATE INDEX IF NOT EXISTS idx_user_sessions_active
ON user_sessions (user_id, expires_at)
WHERE revoked_at IS NULL;

COMMIT;
