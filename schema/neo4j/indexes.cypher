CREATE INDEX paper_doi IF NOT EXISTS
FOR (p:Paper)
ON (p.doi);

CREATE INDEX method_name IF NOT EXISTS
FOR (m:Method)
ON (m.name);

CREATE INDEX entity_name IF NOT EXISTS
FOR (e:Entity)
ON (e.name);

CREATE INDEX claim_program IF NOT EXISTS
FOR (c:Claim)
ON (c.program_id);

CREATE FULLTEXT INDEX claim_fulltext IF NOT EXISTS
FOR (c:Claim)
ON EACH [c.statement];
