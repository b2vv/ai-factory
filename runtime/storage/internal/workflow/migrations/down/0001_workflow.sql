-- Migration-specific rollback: callable only after the maintenance verifier proves
-- every workflow row is backed up and equal to a current Markdown authority source.
-- Drops derived rows, never an authorized PG-owned source of truth.
DROP TABLE workflow_tasks;
