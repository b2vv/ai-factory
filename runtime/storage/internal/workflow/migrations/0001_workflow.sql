-- 0001 workflow structured store (D2: PostgreSQL is the opt-in structured owner; Markdown
-- remains authoritative unless a project is explicitly cut over). One row per task,
-- optimistic-concurrency version column fenced by the application CAS.
CREATE TABLE IF NOT EXISTS workflow_tasks (
    project text   NOT NULL,
    id      text   NOT NULL,
    version bigint NOT NULL,
    fields  jsonb  NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (project, id)
);
