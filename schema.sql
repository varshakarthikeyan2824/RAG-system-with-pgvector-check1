CREATE TABLE outage_reports (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    category TEXT NOT NULL,
    created_at DATE
);

CREATE TABLE areas (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL REFERENCES outage_reports(id),
    label TEXT,
    amount NUMERIC(10,2)
);

CREATE TABLE crews (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL REFERENCES areas(id),
    event TEXT,
    happened_at DATE
);

CREATE TABLE users (
    user_id   TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    role      TEXT NOT NULL CHECK (role IN ('admin', 'engineer', 'customer'))
);

INSERT INTO users VALUES
  ('u_cust', 'water_company_A', 'customer'),
  ('u_eng',  'water_company_A', 'engineer');

CREATE INDEX idx_areas_parent ON areas(parent_id);
CREATE INDEX idx_crews_parent ON crews(parent_id);
CREATE INDEX idx_outage_status ON outage_reports(status);
