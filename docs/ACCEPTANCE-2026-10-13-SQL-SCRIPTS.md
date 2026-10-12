# SQL scripts: actual Linux UI acceptance

## Result and immutable release

**First live pass for the bounded preview slice.** Runtime and test source
`3b0eb7c3fec25ab99c879a942ff4dcc7aa4c106c`, OpenAPI 0.16.0 / 99 routes,
unified Helm 0.1.23. Public Linux CI `38259279931` passed 740 Go/PostgreSQL
checks, zero failures/skips. Seven anonymous OCI/source checks and 21 serial
three-node imports passed. Ten-chart checks and eight-stage deployment passed,
preserving full values and business Secret/PVC identities. No Neon/Postgres/
autoscaling fork or fixed Functions guest image was changed.

Chromium Job `publication-ui-20261012214018` completed on 2026-10-13 05:40:50
Asia/Shanghai (2026-10-12 21:40:50 UTC). Six checkpoint groups passed using the
existing Owner project/branch/Writer/database/public role. Previous Owner and
Functions fixture creation and lifecycle suites were not replayed.

## Actual results

- UI submitted one CREATE/INSERT/DO/SELECT script, parsed quoted semicolons and
  dollar-quoted bodies, and displayed four native results and actual data.
- Implicit transaction error returned failure/SQLSTATE; a new single-query
  connection verified the inserted row had rolled back.
- Earlier explicit COMMIT remained visible after a later error. The UI did not
  claim that the complete script rolled back.
- Unclosed BEGIN/INSERT was reported/discarded; a new connection verified its
  row was absent.
- Display retained 200 rows while both commands completed. Bigint outside
  JavaScript exact range and non-finite floats displayed as exact strings.
- Original Writer was normally suspended through UI and Operation completed.
  Collector observations contained no managed Compute VM or Runner Pod.

Owned `public.script_ui_probe` and committed rows 1/3 remain in
`owner_transfer_v1`; rows 2/99 are absent. Passwords remain outside Git.
Job/source archive identities, results and private records are preserved.

## Reproduction and remaining gates

See [deployment and focused reproduction](SQL-SCRIPTS.md) and the
[exact contract](https://github.com/william-lbn/control-plane/blob/3b0eb7c3fec25ab99c879a942ff4dcc7aa4c106c/docs/SQL-SCRIPTS.md).
Use an unused operator-owned table for fresh manual testing. Do not replay the
retained probe writes; inspect original data after an unknown outcome.

COPY streaming, transport-loss/COPY fault injection, distributed SQL admission,
history/export, full trusted TLS and HA/DR remain independent. Earlier Function/
Owner receipts retain their version scopes. This is not full production or
official SQL Editor qualification.
