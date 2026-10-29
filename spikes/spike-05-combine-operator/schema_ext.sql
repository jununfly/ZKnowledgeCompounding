-- ZKC spike 05: combine-operator extension.
-- Depends on spike-01 base schema + spike-04 extension (transform table).
-- A modeling artifact is a STRUCTURED synthesis product (methodology / mental model /
-- trade-off map) built FROM multiple sources — never free text, always cited.

CREATE TABLE IF NOT EXISTS modeling_artifact (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title         text NOT NULL,
  kind          text NOT NULL CHECK (kind IN ('methodology', 'mental_model', 'tradeoff_map')),
  body          jsonb NOT NULL,                -- full structured artifact (claims/local/global)
  evidence_refs uuid[] NOT NULL,               -- source node ids (provenance, schema-enforced)
  produced_by   uuid REFERENCES transform(id) ON DELETE CASCADE,
  revises       uuid REFERENCES modeling_artifact(id),
  tx_from       timestamptz NOT NULL DEFAULT now(),
  tx_to         timestamptz                    -- NULL = current version (append-only)
);

CREATE INDEX IF NOT EXISTS artifact_produced_idx ON modeling_artifact (produced_by);
CREATE INDEX IF NOT EXISTS artifact_evidence_idx ON modeling_artifact USING gin (evidence_refs);
