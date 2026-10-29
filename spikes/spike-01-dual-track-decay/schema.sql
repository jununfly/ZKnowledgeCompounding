-- ZKC spike 01: dual-track schema + decay
-- Target: PostgreSQL 16 + pgvector (production-shaped). Validated against pgvector/pgvector:pg16.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE track_kind AS ENUM ('static', 'dynamic', 'unrouted');
CREATE TYPE context_scope AS ENUM ('self_loop', 'higher_dim');

-- Node: dual-track + bitemporal (static) + decay (dynamic)
CREATE TABLE node (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  track              track_kind NOT NULL DEFAULT 'unrouted',
  routing_confidence real,                  -- NULL when unrouted / abstained
  title              text NOT NULL,
  content            text,
  -- bitemporal: serves the STATIC track (fact evolution + provenance)
  valid_from         timestamptz,
  valid_to           timestamptz,
  tx_from            timestamptz NOT NULL DEFAULT now(),
  tx_to              timestamptz,
  -- decay: serves the DYNAMIC track (rot / attention cost)
  decay_score        real NOT NULL DEFAULT 0 CHECK (decay_score BETWEEN 0 AND 1),
  review_interval    interval,              -- planned re-evaluation cadence
  last_reviewed_at   timestamptz,
  -- scheduling
  attention_signal   real NOT NULL DEFAULT 0,
  created_at         timestamptz NOT NULL DEFAULT now(),
  embedding          vector(1024)
);

-- Meta-cognition claim (distillation output; MUST carry provenance)
CREATE TABLE meta_claim (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  statement     text NOT NULL,
  level         text,
  confidence    real,
  evidence_refs uuid[] NOT NULL,            -- source node ids
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- Edges: distillation provenance + meta-cognition-driven reverse links
CREATE TABLE edge (
  id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  src    uuid NOT NULL REFERENCES node(id) ON DELETE CASCADE,
  dst    uuid NOT NULL REFERENCES node(id) ON DELETE CASCADE,
  kind   text NOT NULL,                     -- derived_from | reverse_link
  weight real,
  CHECK (src <> dst)
);

-- Context topology: self-closed-loop vs shared higher-dimensional context
CREATE TABLE context (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope        context_scope NOT NULL,
  label        text,
  member_nodes uuid[] NOT NULL DEFAULT '{}'
);

CREATE INDEX node_track_decay_idx  ON node (track, decay_score DESC);
CREATE INDEX node_attention_idx    ON node (attention_signal DESC);
CREATE INDEX edge_src_idx          ON edge (src);
CREATE INDEX edge_dst_idx          ON edge (dst);
CREATE INDEX claim_evidence_idx    ON meta_claim USING gin (evidence_refs);
