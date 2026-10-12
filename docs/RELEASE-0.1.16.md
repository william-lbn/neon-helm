# 0.1.16 — Native Functions Proxy trust compatibility

## Summary

This candidate locks control-plane commit
`21eafbc53010e29dd4af1c4038dcbf88f17ad895` and public Linux CI run
`38207036604`. All seven control-plane OCI images are independently checked on
Linux for anonymous access, platform, source revision and license labels.
The own-fork Neon/Postgres/autoscaling image set and fixed Functions guest image
remain unchanged. This release does not patch those forks.

## Corrected failure and recovery contract

The original Functions deployment failed before a guest was created because
the control-plane SQL connector rejected a configured CA whose KeyUsage
extension was absent. The Proxy's public certificate was inspected without
emitting its private key. The fix follows RFC 5280 and Go's x509 signing rules:
an absent extension is allowed; an explicit non-signing usage is rejected.
Hostname verification, explicit roots, TLS 1.3 and SCRAM remain required.

Focused Linux verification passed 41 Functions SQL checks, including a real
TLS handshake using a CA without KeyUsage and negative non-signing CA cases.
A separate read-only live diagnosis confirmed the original Proxy connection,
database, non-superuser CREATEROLE provisioner and empty self-grant setting.
The original failed Operation, code digest, environment and credential identity
are retained. The browser test retries that exact Operation from the real
Operations UI, without creating a new project, definition or bundle.

## Deployment and qualification

Use the existing immutable operator configuration/issuer Secrets from the
Functions preview setup; do not regenerate keys during an upgrade. Normally
suspend the completed test Compute from the UI before the stack upgrade, retain
data and test evidence, then let the subsequent real SQL connection wake it.
The Linux chart gate checks enabled Functions mounts and private artifact TLS
service in addition to all ten charts and negative configuration tests.

**Live Functions UI acceptance is pending.** It must independently prove original
deployment recovery, guest publication, real Proxy SQL read/write, other-schema
denial, safe HTML/error presentation, manual stop, configuration-only redeployment,
owned-role NOLOGIN on deletion, retained data and Compute zero. This candidate
must not be described as official feature parity or production-qualified before
those receipts exist. Public streaming ingress, automatic Functions idle/wake,
backend cloning, HA/DR, external fencing and complete transport trust remain
separate gates.
