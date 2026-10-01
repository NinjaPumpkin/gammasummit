-- 0001_app_meta.sql — scaffold metadata table (card E1.1).
--
-- Expand-only by law (docs/build/code-structure-and-release.md §4): forward
-- migrations, never alter/drop in place while serving. app_meta carries the
-- schema_version marker used by T2 rollup tables and general deployment
-- metadata. Real T0/T1/T2 tiering DDL lands in later migration cards.

CREATE TABLE app_meta (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO app_meta (key, value) VALUES ('schema_version', '1');
