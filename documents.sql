CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    allowed_roles TEXT[] NOT NULL,
    embedding VECTOR(768)
);

CREATE INDEX idx_documents_tenant
ON documents(tenant_id);
