# 0.7.0-rc.7: ephemeral hook lifecycle fix

Base: 0.7.0-rc.6. This patch candidate changes the optional session-guard-docker
component, not consumer pins, model settings or hook registration.

An interrupted Docker create can finish after a single removal attempt has
already returned not-found. A stateful fault fixture reproduces this race.
The dispatcher now retries within its original cleanup reserve, verifies an
invocation label, and removes the verified ID. Missing validators cannot consume
the whole reserve before worker cleanup. Parser cancellation forwarding and
temporary projection cleanup are included. Hook names identify host and role with
a short random suffix; grouping metadata uses the ai-factory project.

The new shared helper is included in the component manifest and clean-install
regression. Existing image pins, non-root execution, network isolation, filesystem
restrictions, identity binding and fail-open optional monitoring are retained.
Independent shell review and synthetic fixtures are separate evidence from native
agent delivery and Docker Desktop presentation. Unavailable-daemon cleanup may
remain UNRESOLVED after nine seconds; no unconditional zero-residual guarantee is
made. Historical tests and acceptance apply only to their original snapshots.

No consumer repinning, automatic installation, stable promotion or publication is
implied by this candidate. Host overlay activation requires its own byte checks
and rollback baseline. The source and installed profiles are tested separately.
