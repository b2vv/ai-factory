# Optional Django / DRF

Select with [Python](../python.md) only for confirmed Django/DRF work. Confirm
framework, runner, database and factory-library versions. Retain the existing app
layout and model authority; this reference introduces no migrations or services.

Exercise serializer/model validation, actual rendered response shape, permissions
and database constraints at the touched boundary. Application-level checks do not
replace unique constraints when concurrent writes are possible. Scope fixtures and
factories to the invariants being tested; avoid factories that silently make every
case authorized or valid.

Measure queries on representative collections. Use select_related/prefetch_related
according to relationship cardinality and actual access, then verify response
correctness and a justified query budget. Don't infer N+1 absence from a one-row
fixture. Test cross-owner/tenant access, missing objects, pagination under the
accepted ordering and invalid input, including failure without unintended writes.

Use the existing isolated database test route. Transaction-wrapped unit tests may
mask real commit behavior; select a transaction-capable test mode when exercising
locking or on-commit behavior and record which database actually ran. A substitute
database does not establish production locking semantics.

If touched work includes Celery, treat it as project-specific integration, not an
included worker runtime. select_for_update requires an appropriate transaction on
a backend that supports its intended semantics. A lock around a row does not make
an external charge idempotent. Define a stable idempotency key or equivalent
external deduplication contract and recovery after a crash between remote success
and local commit. Test retries and reconciliation; eager/faked tasks do not prove
broker, worker or transaction timing. Never log raw task args/kwargs that may carry
secrets or personal data. [Selection](../index.md).
