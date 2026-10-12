# 0.1.24 — SQL plans and result downloads

Source `7c0ac720746d04549f231dd71e9589b555c481b0`, OpenAPI 0.16.0 / 99 routes.
This Console increment uses the existing single-query and script APIs. Explain
returns actual PostgreSQL JSON plans; Analyze explicitly runs the statement and
can commit writes. CSV/JSON download uses the current bounded browser result,
preserving truncation metadata and guarding common spreadsheet formulas.

Linux frontend quality passed 19 tests and TypeScript/Vite build. Public Linux
CI `38312642166` and seven anonymous OCI source checks passed. Actual live UI
acceptance passed five checkpoint groups on its first run; see the
[exact receipt](ACCEPTANCE-2026-10-13-SQL-TOOLS.md). Source, images and ten charts
are fixed by `locks/control-plane-7c0ac72.json` and the stack contract. No fork or
Functions guest image changed.

See the [source execution/export contract](https://github.com/william-lbn/control-plane/blob/7c0ac720746d04549f231dd71e9589b555c481b0/docs/SQL-TOOLS.md)
and [Linux focused reproduction](SQL-TOOLS.md). Query history/saving, XLSX,
graphical plans, Time Travel UI and AI SQL are separate next gates. Existing
0.1.23 script and earlier Owner/Functions receipts retain their own versions.
