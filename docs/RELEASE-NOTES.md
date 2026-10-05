# Neon Helm 0.1.0

Initial independent chart repository. Ten charts unify the Neon data plane,
NeonVM/autoscaling, metadata/Adapter and Go API/Worker/TypeScript Console.
Eight default releases have deterministic deployment order; dynamic Computes
and native branch Data API remain control-product owned. Images and sources are
locked; Secret state is external; PVCs are retained; Linux CI checks rendering,
schemas, ownership safety and packaging. See deployment and upgrade runbooks.

This release is a laboratory candidate. See PRODUCTION-GATES.md for unfinished
features and unqualified HA/DR, fencing, PITR, memory/fractional CPU and TLS.
