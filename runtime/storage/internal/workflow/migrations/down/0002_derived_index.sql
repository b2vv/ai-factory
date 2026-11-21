-- Only after locked shape and emptiness verification. No CASCADE: unknown
-- dependencies/objects refuse the transaction rather than silently disappearing.
DROP TABLE archive_index;
DROP TABLE document_index;
DROP TABLE derived_index_version;
