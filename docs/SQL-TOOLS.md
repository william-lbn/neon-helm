# SQL plans and CSV/JSON download

## Deploy

Install/upgrade the ordered unified 0.1.24 stack with the preserved values and
business identities described in [UPGRADE.md](UPGRADE.md). Seven control images
are fixed to source `7c0ac720746d04549f231dd71e9589b555c481b0`. No new service,
secret or migration is required. API and Worker stay separate. The existing
PostgreSQL query protocol provides single-statement parsing/authorization/TLS.

## Focused manual UI reproduction

1. Login, select the retained project/Writer/database/public role in SQL Editor.
   Keep the password outside Git and enter it only for each request.
2. In single mode choose **Explain**, enter a safe operator-owned SELECT/INSERT,
   and click **Explain**. Check native JSON plan. For INSERT, independently query
   the unused probe ID: estimating the plan must not insert it.
3. Choose **Analyze** only for SQL you authorize to execute. Confirm the persistent
   write warning and **Analyze** button. Inspect actual timing/plan and independently
   query the resulting data; do not retry a submitted unknown write.
4. After a SELECT, download CSV and JSON in the browser. Check commas/quotes,
   duplicate columns, NULL and nested values. CSV formula-like strings are protected
   and NULL becomes an empty field; JSON retains returned values and positional rows.
5. In script mode query 205 rows. Download its result, verify only 200 retained rows
   and the truncation flag/prompt. Download does not query again or wake Compute.
6. Normally suspend the owned Writer and preserve its data, requests and evidence.

Automated actual browser reproduction: protected Linux `sql-tools.spec.ts`, using
the accepted `NEON_E2E_SQL_SCRIPT_FIXTURE` and Console password file. It continues
from the accepted script fixture without replaying its CREATE/INSERT. A failed
Analyze requires checking the original data/checkpoint before any continuation.

See the [exact source contract](https://github.com/william-lbn/control-plane/blob/7c0ac720746d04549f231dd71e9589b555c481b0/docs/SQL-TOOLS.md).
Actual Linux UI acceptance passed on its first run; see the
[release receipt](ACCEPTANCE-2026-10-13-SQL-TOOLS.md). Full-result export,
XLSX, history/saved queries, graphical plans, official parity, distributed SQL
admission, HA/DR and full-chain trusted TLS remain independent.
