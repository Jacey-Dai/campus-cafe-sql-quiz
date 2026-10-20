-- Isolated schemas; does not alter existing class tables or authentication settings.
BEGIN;
CREATE SCHEMA IF NOT EXISTS quiz_data;
CREATE SCHEMA IF NOT EXISTS quiz_private;
REVOKE ALL ON SCHEMA quiz_data, quiz_private FROM PUBLIC;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cafe_quiz_reader') THEN
    CREATE ROLE cafe_quiz_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END $$;
GRANT cafe_quiz_reader TO postgres;
GRANT USAGE ON SCHEMA quiz_data TO cafe_quiz_reader;
CREATE TABLE IF NOT EXISTS quiz_data.customers (
 id integer PRIMARY KEY, name text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS quiz_data.menu_items (
 id integer PRIMARY KEY, name text NOT NULL UNIQUE, category text NOT NULL,
 price numeric(8,2) NOT NULL CHECK (price >= 0)
);
CREATE TABLE IF NOT EXISTS quiz_data.orders (
 id integer PRIMARY KEY, customer_id integer NOT NULL REFERENCES quiz_data.customers(id), ordered_at date NOT NULL
);
CREATE TABLE IF NOT EXISTS quiz_data.order_items (
 id integer PRIMARY KEY, order_id integer NOT NULL REFERENCES quiz_data.orders(id),
 menu_item_id integer NOT NULL REFERENCES quiz_data.menu_items(id),
 quantity integer NOT NULL CHECK (quantity > 0), unit_price numeric(8,2) NOT NULL CHECK (unit_price >= 0)
);
INSERT INTO quiz_data.customers VALUES (1,'Alex'),(2,'Blair'),(3,'Casey'),(4,'Drew'),(5,'Emery') ON CONFLICT DO NOTHING;
INSERT INTO quiz_data.menu_items VALUES (1,'Coffee','Drink',3.00),(2,'Tea','Drink',2.50),(3,'Latte','Drink',4.50),(4,'Sandwich','Food',8.00),(5,'Salad','Food',10.00),(6,'Cookie','Food',2.00) ON CONFLICT DO NOTHING;
INSERT INTO quiz_data.orders VALUES (1,1,'2026-10-01'),(2,2,'2026-10-01'),(3,1,'2026-10-02'),(4,3,'2026-10-02'),(5,2,'2026-10-03'),(6,4,'2026-10-03') ON CONFLICT DO NOTHING;
INSERT INTO quiz_data.order_items VALUES
 (1,1,1,2,3.00),(2,1,4,1,8.00),(3,2,2,1,2.50),(4,2,5,1,10.00),
 (5,3,3,1,4.50),(6,3,6,2,2.00),(7,4,4,2,8.00),(8,4,1,1,3.00),
 (9,5,3,1,4.50),(10,5,5,1,10.00),(11,6,1,1,3.00),(12,6,2,1,2.50)
 ON CONFLICT DO NOTHING;
GRANT SELECT ON ALL TABLES IN SCHEMA quiz_data TO cafe_quiz_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA quiz_data FROM PUBLIC, anon, authenticated;
CREATE TABLE IF NOT EXISTS quiz_private.answers (
 user_id uuid NOT NULL, question_id integer NOT NULL CHECK(question_id BETWEEN 1 AND 5),
 query text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id, question_id)
);
CREATE TABLE IF NOT EXISTS quiz_private.audit_log (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, user_id uuid NOT NULL,
 action text NOT NULL CHECK(action IN ('run','save')), question_id integer NOT NULL,
 query text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON SCHEMA quiz_private FROM cafe_quiz_reader, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA quiz_private FROM PUBLIC, cafe_quiz_reader, anon, authenticated;
-- Defense in depth: no direct API access. Only the verified server writes these.
ALTER TABLE quiz_private.answers ENABLE ROW LEVEL SECURITY;
ALTER TABLE quiz_private.audit_log ENABLE ROW LEVEL SECURITY;
COMMIT;
