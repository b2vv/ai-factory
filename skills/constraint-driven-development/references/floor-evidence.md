# Evidence for a quality-floor decision

Use the existing task record. Record: constraint and owner; before/after behavior; exact repository/base/HEAD/scope and dirty/untracked hashes; signal location; disposition; raw evidence references; remaining uncertainty.

- `suspected`: a mechanical or reviewer signal awaits analysis. BLOCKED for a claimed clean result.
- `equivalent`: replacement preserves the relevant failure-detection behavior, with concrete before/after evidence. Removing an assertion line alone is not a violation.
- `confirmed_weakening`: evidence shows a capability or threshold reduced. FAIL unless an authorized owner accepted that exact scoped exception with rationale and evidence.
- `accepted_exception`: retain the owner decision, scope and rationale; report PASS_WITH_EXCEPTIONS, not unqualified clean.

A scan with zero regex hits is only a scan result. Explicit inspected-scope coverage is required; missing files, unknown untracked scope, absent commands or unavailable reviewer evidence remain BLOCKED. Never lower a threshold, install a tool, edit ignores or register a hook merely to obtain PASS.

For UI, preserve the existing design-pass and entity-e2e-coverage routes. Entity views, role/permission denial and recovery states need their own observable evidence where applicable. Build success does not establish them.
