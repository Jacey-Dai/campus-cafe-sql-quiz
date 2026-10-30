-- Stores usage counters only, without API keys, prompts, or generated content.
CREATE TABLE IF NOT EXISTS quiz_private.rag_requests (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 user_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rag_requests_created_idx ON quiz_private.rag_requests(created_at);
REVOKE ALL ON quiz_private.rag_requests FROM PUBLIC, cafe_quiz_reader, anon, authenticated;
ALTER TABLE quiz_private.rag_requests ENABLE ROW LEVEL SECURITY;
