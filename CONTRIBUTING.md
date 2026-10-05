# Contributing

Use issues for reproducible defects and pull requests for reviewed changes.
Run all quality gates on Linux (`npm ci`, `npm run check`, `npm test`,
`npm run helm`, `npm run package`). Include source commits, immutable image
digests, affected API/config contracts, migration/recovery steps and test proof.
Keep changes backward-compatible or version the migration explicitly.

Every chart default must have a matching values schema and explanatory comment.
Do not change Stateful/PVC selectors, namespaces or storage identities silently.
Do not mark a capability available based on template rendering. Respect the
qualification matrix and update docs whenever behavior changes.

Never commit `.local`, credentials, kubeconfig, database dumps, protected live
values, private test fixtures or Python verification scripts. Runtime Python
compatibility code is explicitly whitelisted; migrating it is separate work.
Sign off commits (`git commit -s`) to certify the right to contribute under
Apache-2.0. CI changes require pinned action commits and least privilege.
