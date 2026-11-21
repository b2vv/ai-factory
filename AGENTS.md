# Candidate repository instructions

Maintain this portable kit only within the user's authorized scope. Read README.md, ai-factory/ai-factory-plan.md, docs/migration-0.4.md and PROVENANCE.md first. Do not install the kit, register hooks/MCP, alter host permissions or roll it out to other repositories implicitly.

Preserve the read-only contract of runtime/onboarding/preflight.py. Fixture success proves only helper behavior, not real agent discovery or model access. Run relevant fixture tests after helper changes. Keep release manifest/checksums consistent with reviewed bytes. Never add credentials, machine-specific absolute paths, project-specific context or third-party content without provenance and license review.

The offline installer is implemented; preserve its explicit paths, default read-only behavior, component allowlist, baseline guards and rollback contract. Never run it against live host or product paths without separate authorization. Do not claim independent review when only author checks exist.
