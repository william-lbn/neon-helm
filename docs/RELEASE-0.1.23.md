# 0.1.23 — Native SQL scripts

Source `3b0eb7c3fec25ab99c879a942ff4dcc7aa4c106c`, OpenAPI 0.16.0 with 99
implemented routes. Public Linux CI `38259279931` passed 740 Go/PostgreSQL
checks with zero failures/skips. Seven public OCI references were anonymously
verified against that source. Neon/Postgres/autoscaling fork and Functions
guest images are unchanged.

The Console adds an explicit script mode with native PostgreSQL parsing,
ordered results, bounded display and truthful transaction outcomes. It does
not split semicolons or retry submitted SQL. Explicit commits before a later
error remain committed; an unclosed transaction is discarded by connection
close. An unknown submitted outcome requires inspection of original data.

See [SQL script deployment and reproduction](SQL-SCRIPTS.md). Actual Linux UI
acceptance passed six checkpoint groups on its first run; see the
[exact receipt](ACCEPTANCE-2026-10-13-SQL-SCRIPTS.md). Previous
Owner and Functions receipts remain version-specific and are not new regression
results. This release does not close HA/DR, distributed fencing, full trusted
TLS, complete catalog or official Console parity gates.
