# SQL plans and downloads: actual Linux UI acceptance

**First live pass for this preview slice.** Runtime/test source
`7c0ac720746d04549f231dd71e9589b555c481b0`, OpenAPI 0.16.0 / 99 routes,
unified Helm 0.1.24. Public Linux CI `38312642166` passed 740 Go/PostgreSQL
checks with zero failures/skips. Frontend Linux tests passed 19 checks and
TypeScript/Vite build. Seven anonymous OCI/source verifications, 21 serial
node imports, ten-chart QA and eight-stage deployment passed. Full old values
and business Secret/PVC identities were preserved; no fork/guest image changed.

Chromium Job `publication-ui-20261012215748` completed on 2026-10-13 05:58:21
Asia/Shanghai (2026-10-12 21:58:21 UTC). Five checkpoint groups passed from the
accepted script fixture without replaying its original CREATE/INSERT.

- Explain returned the actual PostgreSQL INSERT plan; a new connection verified
  ID 4 was absent before Analyze.
- The explicit Analyze warning/button led to real PostgreSQL execution/timing.
  A new connection verified ID 4 with `analyze-write` persisted.
- Actual Chromium CSV/JSON downloads preserved duplicate columns, quotes, NULL
  and raw JSON values; CSV formula-like text was protected.
- Script download contained exactly 200 retained rows and truthful truncation
  metadata/prompt, without a second data query for download.
- Owned Writer normally suspended through UI and its original Operation succeeded.
  Collector observations contained no managed Compute VM or Runner Pod.

Original `owner_transfer_v1`, passwords and script probe data remain; the new
Analyze row is retained. Requests, source archive identity, downloaded files,
result and private records remain in evidence. See [deployment/reproduction](SQL-TOOLS.md)
and the [exact source contract](https://github.com/william-lbn/control-plane/blob/7c0ac720746d04549f231dd71e9589b555c481b0/docs/SQL-TOOLS.md).

This closes plans and bounded CSV/JSON download, not query history/saving, XLSX,
graphical plans, Time Travel UI, AI SQL, full-result export, distributed admission,
HA/DR or full trusted TLS. Earlier Function/Owner/script receipts retain their
own runtime versions rather than becoming repeated full regression results.
