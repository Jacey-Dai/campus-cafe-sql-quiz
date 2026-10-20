# Campus Café SQL Studio

A 20-point SQL quiz built for Week 7. Students sign in with Supabase Auth, write SQL against a hosted PostgreSQL café dataset, run queries, inspect live result tables, and save their answers.

**Quiz site:** https://campus-cafe-sql-quiz.vercel.app/

**Repository:** https://github.com/Jacey-Dai/campus-cafe-sql-quiz

## Take the quiz

1. Open the quiz site and click **Sign in**.
2. Enter your email address, then open the secure link sent by Supabase. Check spam if needed. Use the same browser/device.
3. Select a question, enter SQL in the editor, and click **Run query** (or Ctrl/Command + Enter).
4. Compare the result table with the **Expected SQL + result** hint. Different SQL that returns the requested values and order is valid.
5. Click **Save answer**. Your five answers persist in PostgreSQL under your verified Supabase user ID and reload on sign-in.

Signed-out visitors can browse the questions and hints. Both Run and Save require sign-in, enforced by server-side verification of the access token with Supabase Auth. Editing browser controls does not bypass authentication.

## Quiz and dataset

All café data is fictional. There are 5 customers, 6 menu items, 6 orders, and 12 order-item rows. Every table is in the `quiz_data` schema:

| Table | Columns |
|---|---|
| customers | id (PK), name |
| menu_items | id (PK), name, category, price |
| orders | id (PK), customer_id (FK), ordered_at |
| order_items | id (PK), order_id (FK), menu_item_id (FK), quantity, unit_price |

| Question | Topic | Points |
|---|---|---|
| Find affordable drinks | SELECT, WHERE, ORDER BY | 4 |
| Count orders by customer | LEFT JOIN, COUNT, GROUP BY | 4 |
| Calculate category revenue | JOIN, SUM, historical sale prices | 4 |
| Spot repeat favorites | GROUP BY, HAVING | 4 |
| Find customers to invite back | NOT EXISTS | 4 |
| **Total** | | **20** |

Each question has one reference query and the exact expected columns and rows in `quiz.py`, also visible in the site. The app displays results rather than assigning an automatic grade. The instructor evaluates result sets, not character-for-character SQL matching.

## How it works

Browser → Supabase Auth for email sign-in → Flask API verifies the bearer token → Psycopg connects over TLS to the Supabase **Session pooler** on port 5432 → PostgreSQL returns real rows.

The new Supabase project is `campus-cafe-sql-quiz`, project reference `rzihuwropluhsqggitam`. The earlier class project is not used. The application uses a Python/Flask server hosted on Vercel. Browser JavaScript uses the version-pinned Supabase SDK from jsDelivr; fonts are loaded from Google Fonts.

### Query protection and extra-credit features

- PostgreSQL AST parsing accepts one SELECT statement and rejects writes, locking, SELECT INTO, access to other schemas, unsafe function calls, and unapproved casts/operators.
- SQL executes in a read-only transaction after switching to `cafe_quiz_reader`, a non-login role with SELECT privileges only on the café tables. The search path is fixed to `pg_catalog, quiz_data`.
- Queries have a 3-second timeout and return at most 200 rows. The parser and role intentionally constrain this to a teaching sandbox rather than general-purpose database administration.
- Application-generated storage queries use Psycopg `%s` parameters for user IDs, question IDs, and SQL answer text. There are no f-string SQL statements. Learner SQL is deliberately executable input, constrained separately by validation and database permissions; it is not treated as a parameterized application query.
- Successful runs and saves create audit rows with the verified user ID, action, question, query, and timestamp. Takers cannot insert, update, or delete audit rows. `manage.py check` checks those privileges.
- Saved answers and audit logs live in `quiz_private`, which is inaccessible to the taker, `anon`, and `authenticated` roles. Row-level security is enabled as defense in depth; the server enforces answer ownership through parameterized user-ID filters.
- The backend currently uses the project-owner database connection to switch roles and perform fixed storage operations. Keep its password server-side; for broader production use, replace it with a narrowly privileged service account and add distributed per-user rate limiting. The database owner can edit logs; the integrity claim applies to the taker role.

## Run locally

Requires Python 3.12 and a Supabase project (or adapt the SQL roles for another hosted Postgres provider).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`: set the project's URL, publishable key, session-pooler hostname, username, and database password. The supplied `.env.example` contains only public project information and a password placeholder. Use `PGPORT=5432`; the connection code explicitly requires `sslmode=require`. Do not use the Direct connection or transaction pooler for this assignment.

```bash
python manage.py setup
python manage.py check
python -m pytest -q
python app.py
```

Open http://127.0.0.1:5050. In Supabase **Authentication → URL Configuration**, allow `http://127.0.0.1:5050/` as a redirect URL. Set the production Site URL and allow the production quiz URL when publishing. Leave email signup enabled for classmates; email confirmation is performed by opening the magic link.

`manage.py setup` creates isolated schemas and roles, loads deterministic sample data, and skips existing primary keys on reruns. It does not overwrite or reset existing answers. Run setup only as the project owner, outside CI.

## GitHub Actions and secrets

The workflow `.github/workflows/database-check.yml` runs on pushes to `main` and manual dispatch. Add **PGPASSWORD** in the repository's **Settings → Secrets and variables → Actions → New repository secret**. Its value is the new project's database password, not a Supabase account login or API key.

The workflow reads `${{ secrets.PGPASSWORD }}` into the environment, checks that it exists, runs authentication/sandbox tests, and compares all five reference queries against the hosted database. It also verifies the taker cannot edit audit logs and checks TLS on the Python-to-pooler connection. The password is never present in the workflow or committed files.

The workflow does not migrate/reset data. A successful run proves the runner used the secret to connect to live PostgreSQL; unit tests alone do not substitute for the live step. See the repository's **Actions** tab for the completed run.

## Deploy on Vercel

Import this repository into a free Hobby project. Flask is automatically detected using `app.py` and `requirements.txt`; `vercel.json` sets a 30-second function limit. Assets are in `public/static` for Vercel's static hosting and are also served locally by Flask.

Add these server environment variables: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`. Use the values from your local `.env`; the password belongs in secret environment storage, never source code. Add the production URL to Supabase's redirect allowlist, redeploy if environment values changed, then test sign-in, Run, Save, refresh, and sign-out.

## Troubleshooting

- **Password authentication failed:** check the project-specific `PGUSER` (`postgres.<project-reference>`) and database password. An old username can route the pooler to the wrong project even when the password is correct.
- **Email link opens localhost:** fix Supabase Site URL and redirect allowlist. Request a new link after changing settings; links expire and are single-use.
- **Email rate limit:** Supabase's built-in email sender has strict limits; wait before retrying or configure your own SMTP for a larger class.
- **Function/operator not supported:** use the reference hints or standard SELECT/JOIN/aggregate syntax. Administrative functions are intentionally unavailable.
- **TLS check:** `conn.pgconn.ssl_in_use` checks the client-to-pooler connection. `pg_stat_ssl` describes the backend-side connection and is not the right check for that hop.

## References

- [Supabase email sign-in](https://supabase.com/docs/guides/auth/auth-email-passwordless)
- [Supabase database connections](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
- [Flask on Vercel](https://vercel.com/docs/frameworks/backend/flask)
