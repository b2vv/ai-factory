-- Opt-in only, after retained control activation and admitted exclusive upgrade.
-- Original index identity/payload hashes and historical rows remain unchanged.
ALTER TABLE archive_index
 ADD COLUMN metadata_hash text,
 ADD COLUMN source_generation text,
 ADD COLUMN source_ordinal bigint,
 ADD COLUMN captured_key text,
 ADD COLUMN source_time_key text,
 ADD CONSTRAINT archive_metadata_shape CHECK (
  (metadata_hash IS NULL AND source_generation IS NULL AND source_ordinal IS NULL AND captured_key IS NULL AND source_time_key IS NULL)
  OR (metadata_hash IS NOT NULL AND length(metadata_hash)=64 AND source_generation IS NOT NULL AND source_generation<>'' AND source_ordinal IS NOT NULL AND source_ordinal>0)),
 ADD CONSTRAINT archive_capture_time_shape CHECK(captured_key IS NULL OR length(captured_key)=30),
 ADD CONSTRAINT archive_source_time_shape CHECK(source_time_key IS NULL OR length(source_time_key)=30);
CREATE UNIQUE INDEX archive_source_ordinal ON archive_index(project_hash,project,source_generation,source_ordinal) WHERE metadata_hash IS NOT NULL;
CREATE INDEX archive_recent_capture ON archive_index(project_hash,source_generation,captured_key DESC,key_hash) WHERE captured_key IS NOT NULL;
CREATE INDEX archive_recent_source ON archive_index(project_hash,source_generation,source_time_key DESC,key_hash) WHERE source_time_key IS NOT NULL;
CREATE TABLE archive_checkpoint (
 project_hash text PRIMARY KEY, project text NOT NULL,
 source_generation text NOT NULL, projection_generation text NOT NULL,
 policy_revision text NOT NULL, ordinal bigint NOT NULL CHECK(ordinal>=0),
 complete boolean NOT NULL,
 CHECK(source_generation<>'' AND projection_generation<>'' AND policy_revision ~ '^[0-9]+$'));
UPDATE derived_index_version SET version=2 WHERE singleton=true;
