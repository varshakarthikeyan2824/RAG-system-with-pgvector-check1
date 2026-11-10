TRUNCATE documents RESTART IDENTITY;

-- Outage reports
INSERT INTO documents
(content, source, tenant_id, allowed_roles)
SELECT
    'Outage: ' || name ||
    '. Status: ' || status ||
    '. Category: ' || category ||
    '. Created at: ' || created_at,
    'outage_reports:' || id,
    'water_company_A',
    ARRAY['admin', 'engineer', 'customer']
FROM outage_reports;

-- Affected areas
INSERT INTO documents
(content, source, tenant_id, allowed_roles)
SELECT
    'Affected area: ' || a.label ||
    '. Amount: ' || a.amount ||
    '. Related outage: ' || o.name ||
    '. Outage status: ' || o.status,
    'areas:' || a.id,
    'water_company_A',
    ARRAY['admin', 'engineer', 'customer']
FROM areas a
JOIN outage_reports o ON a.parent_id = o.id;

-- Crew events
INSERT INTO documents
(content, source, tenant_id, allowed_roles)
SELECT
    'Crew event: ' || c.event ||
    '. Happened at: ' || c.happened_at ||
    '. Area: ' || a.label ||
    '. Related outage: ' || o.name,
    'crews:' || c.id,
    'water_company_A',
    ARRAY['admin', 'engineer']
FROM crews c
JOIN areas a ON c.parent_id = a.id
JOIN outage_reports o ON a.parent_id = o.id;
