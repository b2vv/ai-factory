-- Global image binding for derived archive/document indexes. Older images that
-- know only migration 0001 must refuse this schema, including their purge path.
CREATE TABLE derived_index_version (singleton boolean PRIMARY KEY CHECK(singleton), version integer NOT NULL);
INSERT INTO derived_index_version VALUES(true,1);
CREATE TABLE archive_index (
 key_hash text PRIMARY KEY, project_hash text NOT NULL, project text NOT NULL,
 identity text NOT NULL, payload_hash text NOT NULL, terms tsvector NOT NULL);
CREATE INDEX archive_project_key ON archive_index(project_hash,key_hash);
CREATE INDEX archive_terms ON archive_index USING gin(terms);
CREATE TABLE document_index (
 key_hash text PRIMARY KEY, project_hash text NOT NULL, project text NOT NULL,
 identity text NOT NULL, data jsonb NOT NULL);
CREATE INDEX documents_project_key ON document_index(project_hash,key_hash);
