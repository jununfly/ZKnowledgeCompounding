#!/bin/sh
# Canonical DB-state dump for app-record --db-dump. Fixed UUID seed => byte-stable.
export PGPASSWORD=zkc
psql -h localhost -p 55433 -U postgres -d zkc_metric_record -tA -F'|' -c \
 "SELECT 'node', id, track, decay_score, (archived_at IS NOT NULL) FROM public.node ORDER BY id;
  SELECT 'edge', src, dst, kind FROM public.edge ORDER BY id;
  SELECT 'claim', id, array_to_string(evidence_refs, ',') FROM public.meta_claim ORDER BY id;
  SELECT 'citation', cited_claim_id FROM public.citation ORDER BY cited_claim_id, id;
  SELECT 'artifact', evidence_refs::text, produced_by FROM public.modeling_artifact ORDER BY id;"
