# 0.1.13: Functions SQL credential and TLS substrate

## Source and release intent

Control source: `d1b12425f0c22c5d56e87847c68697b71ea3c10c`, following
the immutable SQL credential increment `77e12ef82e57c22b588310f62be9bf52e40683c4`.
Use `locks/control-plane-d1b1242.json` for the seven image digests. The own-fork
46-image Neon/autoscaling/PG16 distribution is unchanged.

Migration 022 introduces private Function SQL identity receipts. Passwords,
SCRAM verifiers and connection URLs stay outside metadata. The Worker and API
remain separate; Functions execution remains disabled. This distribution
does not claim complete Neon parity, HA, external fencing or production admission.

## Completed source and supply-chain checks

- Linux dedicated PG16/race/vet/build: 704 pass, 0 fail, 0 skip.
- Dedicated PostgreSQL now explicitly requires SCRAM on host connections;
  actual wrong-password rejection closes the older loopback-trust evidence gap.
- Explicit Function runtime CA/hostname/Writer policy, TLS 1.3, no fallback,
  actual SCRAM/DML, authentication-downgrade and environment-input negatives.
- Real immutable Kubernetes SQL Secret/lost reply/restart/original UID checks
  passed in the preceding four-test backing gate. VM admission was dry-run,
  not customer Function execution.
- [Public control CI 38163791778](https://github.com/william-lbn/control-plane/actions/runs/38163791778)
  succeeded; eight artifacts were actually downloaded and digest checked.
- Seven anonymous Linux OCI source/platform/license verifications and
  twenty-one serial CRI digest inspections across three nodes passed.

Deployment, published Helm and UI results must be recorded after they occur.
The previous 0.1.12 matrix of 134 checks remains historical evidence and cannot
be renamed as a 0.1.13 result. This increment uses focused new-path acceptance;
it does not repeatedly rerun unrelated unchanged product suites.

## Forward migration and recovery

Follow [DEPLOYMENT.md](DEPLOYMENT.md) and the ordered stack tools. Preserve
complete previous values/manifests, metadata backup, Secrets/PVC identities and
old image locks before the maintenance-window apply. Do not down-migrate 022.
Older runtime rollback needs schema compatibility review; never replace the
original SQL Secret or reset a running Function password to make a retry pass.

After apply, verify separate API/Worker readiness and `schema_migrations` max
and count equal 22, with `function_sql_credentials` present. This table's
presence is not proof of Function deployment or invocation. Keep all failed
attempts and their original Job/Pod/Secret identities.

## Next product work

Connect native Function ZIP upload/deployment, private TLS artifact delivery,
original SQL credential/Writer verification, actual microVM readiness,
invocation and React interaction. Only the integrated Driver and real guest
SQL/UI results may enable execution. Real upstream AI credentials remain a
separate operator input. Other production gates remain in
[PRODUCTION-GATES.md](PRODUCTION-GATES.md).
