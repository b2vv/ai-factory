# 0.8.0-alpha.1: optional storage alpha

This alpha adds the optional Go storage server, real Mongo/PostgreSQL adapters,
Docker-free operator identity/consent helper, workflow/document operators,
durable ingestion and logical-v1 shared budget ledger. Modules and capture remain
disabled by default. Existing managed-kit/project pins are not moved by this tag.

## Owner-approved publication exception

On 2026-10-31 the owner explicitly accepted publishing this experimental/default-off
candidate to main with an alpha tag after disclosure of the remaining limitations.
This is owner acceptance of a limited alpha, not independent technical approval.
Independent storage review remains **BLOCKED**; no bypass or repeated blocked
security probe was used. Full acceptance is **NOT GREEN**.

Automatic DrainOnce WAL reclamation is **NOT_IMPLEMENTED/BLOCKED**. Its renewed
approval request was rejected before execution; the patch is not included. When
the WAL fills, new intake fails closed. Explicit maintenance methods tested on
synthetic data do not constitute automatic production recovery. This is not yet a
ready continuous conversation archive.

Backups/restore are excluded from this delivery. Existing source and evidence are
retained, but backup-operator and the backup-dependent destructive migration-operator
refuse activation. Forward migrations and newer-schema refusal remain available.
No complete disk/control-state loss recovery is guaranteed.

## Accounting and supported boundaries

The default live cap remains10GiB, WAL256MiB, physical free headroom1GiB. Logical-v1
counts managed representations, declared indexes, control/dedup metadata and staging.
It is not a Mongo/PostgreSQL allocated-page or database-journal quota. The shared
durable ledger serializes server/offline reservations and retains uncertain debt.
Unknown partial writes, damaged ledger state or missing existing accounting refuse
rather than reset or refund. No live-state migration is activated by publication.

Workflow uses an explicit dedicated generated Markdown format and verified
per-project cutover. Arbitrary Markdown-format adapters are not provided. Real
provider fidelity, native non-Linux execution, replica-set/power-loss guarantees,
production sizing and real project capture remain NOT_TESTED. Provider fixtures
are synthetic. No private histories, credentials or real data are part of this tag.

## Evidence and distribution

The unchanged executable payload matches the frozen author-tested ledger candidate:
18 Go race packages and both vet modes; real integration224PASS/2DEFERRED skips;
final changed-scope integration41PASS/1DEFERRED skip; actual process HTTP matrix;
local offline OCI build/save/load/init/health; actual runner with deliberate
FAIL/BLOCKED negative controls; synthetic kit install/upgrade/rollback checks.
Publication packaging is verified separately against its final manifest/checksums.
These are author results, not independent GREEN. The historical whole-kit baseline
is not reclassified as passing or reproduced without its exact retained inputs.

Only canonical export is distributable; the declared research archive remains
preserved and excluded. Immutable licenses/provenance are retained. No registry
image, hosted release, production deploy, global hook or real capture activation is
performed by source publication. Any rollout uses explicit managed-kit/project
adapters and keeps this alpha status and limitations visible.
