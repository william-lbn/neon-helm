# 0.1.18 — Worker-only Functions Service retirement

This chart patch retains the verified control runtime/source
`07c997b07b9e3e1f60c1ed9ccd34b5cc1cbf1a54` and its existing OCI digest lock.
No Go binary, Neon fork or runtime image change is required.

The real UI stop normally deleted the original Functions VM, then correctly
failed because the independent Worker could not delete its retained Service.
An actual Kubernetes authorization review confirmed Pod listing and VM deletion
were allowed, while Service deletion was denied. The original stop Operation,
Service UID, bootstrap and SQL credentials remain retained.

When Functions is explicitly enabled, the chart now creates a namespace Role
allowing only `delete` on `services`, bound only to the independent Worker.
Functions disabled grants no such role. API/Web receive no Service deletion;
no Secret deletion, Pod mutation, wildcard or cluster grant is added. Kubernetes
RBAC cannot express a dynamic Function name prefix, so the Driver still requires
the saved original UID/resourceVersion before each normal Service deletion.

Upgrade the control-plane release with its complete current values and original
immutable operator Secrets. The previously verified data-plane/runtime images
can remain in place during this chart-only patch. Check real authorization:

```bash
kubectl -n neon auth can-i delete services \
  --as=system:serviceaccount:neon:neon-control-worker  # yes
kubectl -n neon auth can-i delete services \
  --as=system:serviceaccount:neon:neon-control-api     # no
kubectl -n neon auth can-i delete pods \
  --as=system:serviceaccount:neon:neon-control-worker # no
```

Then use Operations to retry the **original failed stop**. Do not issue another
stop or directly delete the Service. After normal retirement completes, the
Functions UI can deploy the retained failed ZIP/environment with no upload and
continue the real guest/SQL acceptance. A committed test-only checkpoint supports
`failed_suspend_operation_id`; runtime source remains unchanged.

Actual Functions invocation acceptance is still pending; a permission fix or
Ready Pod alone does not qualify it. See [the recovery contract](RELEASE-0.1.17.md)
and [production gates](PRODUCTION-GATES.md).
