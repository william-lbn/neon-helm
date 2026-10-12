# SQL scripts: deployment and focused reproduction

## Contract and deployment

Unified Helm 0.1.23 selects control source
`3b0eb7c3fec25ab99c879a942ff4dcc7aa4c106c`. Its seven image references are
fixed in `locks/control-plane-3b0eb7c.json`. Script mode needs no extra service,
secret, Worker action or metadata migration. Upgrade the split API and Console
using the ordered stack procedure in [UPGRADE.md](UPGRADE.md), preserving prior
values and business Secret/PVC identities. Writer must remain normally suspended
before the stack maintenance window; wake through Proxy during the UI test.

The [Go/API/UI contract](https://github.com/william-lbn/control-plane/blob/3b0eb7c3fec25ab99c879a942ff4dcc7aa4c106c/docs/SQL-SCRIPTS.md)
defines authorization, native parsing, bounded output and outcome semantics.
The endpoint is `POST /api/v1/projects/{project}/endpoints/{endpoint}/query-script`.
The existing single-statement endpoint and UI default remain compatible.

## Manual UI acceptance

1. Login to Console as an authorized Editor/Admin. Select the retained project,
   Writer, managed database and public role; supply its password for each request.
2. Choose **SQL 脚本 · 逐条结果**. In an operator-owned, unused test table, submit
   CREATE, INSERT containing a quoted semicolon, a dollar-quoted DO body and SELECT
   as one script. Check four native results and actual data through a subsequent
   single SELECT. Keep the exact submitted SQL and outcome outside public Git.
3. Insert a different ID then cause a SQL error in the same implicit transaction.
   Check failed outcome/SQLSTATE and independently verify that row is absent.
4. Explicitly BEGIN/INSERT/COMMIT then cause an error. Independently verify the
   committed row remains; the UI must not claim global rollback.
5. BEGIN/INSERT without COMMIT. Check the open-transaction discard flag and verify
   the row is absent through a new connection.
6. Query 205 rows plus another statement. Check the 200-row display budget,
   truncation indicator and both completed commands. Verify exact bigint and
   non-finite float strings separately.
7. Normally suspend the owned Writer through UI. Retain table data, credentials,
   requests, failures and evidence; verify original Operation success and actual
   VM/Runner absence before the next test.

## Linux automation

Use the protected `sql-script.spec.ts` live workflow with
`NEON_E2E_SQL_SCRIPT_FIXTURE`. The fixture contains `project_id`, `branch_id`,
`writer_id`, `database`, `role`, `password_file`; credentials stay outside Git.
The current bounded suite uses the accepted Owner fixture and preserves its
data. It verifies that its probe table does not exist before first writes.
After failure or unknown outcome, inspect the original state/checkpoints;
do not blindly rerun CREATE/INSERT or make another fixture to hide the failure.

Isolated PostgreSQL tests, public Linux CI and actual UI acceptance passed;
see the [version-specific result](ACCEPTANCE-2026-10-13-SQL-SCRIPTS.md). COPY streaming, transport-loss
fault qualification, history/export, distributed admission and full product
parity are independent gates.
