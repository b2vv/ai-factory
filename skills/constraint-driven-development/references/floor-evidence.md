# Evidence for a quality-floor decision

Use the existing task record. Record: constraint and owner; before/after behavior; exact repository/base/HEAD/scope and dirty/untracked hashes; signal location; disposition; raw evidence references; remaining uncertainty.

- `suspected`: a mechanical or reviewer signal awaits analysis. BLOCKED for a claimed clean result.
- `equivalent`: replacement preserves the relevant failure-detection behavior, with concrete before/after evidence. Removing an assertion line alone is not a violation.
- `confirmed_weakening`: evidence shows a capability or threshold reduced. FAIL unless an authorized owner accepted that exact scoped exception with rationale and evidence.
- `accepted_exception`: retain the owner decision, scope and rationale; report PASS_WITH_EXCEPTIONS, not unqualified clean.

A scan with zero regex hits is only a scan result. Explicit inspected-scope coverage is required; missing files, unknown untracked scope, absent commands or unavailable reviewer evidence remain BLOCKED. Never lower a threshold, install a tool, edit ignores or register a hook merely to obtain PASS.

For UI, preserve the existing design-pass and entity-e2e-coverage routes. Entity views, role/permission denial and recovery states need their own observable evidence where applicable. Build success does not establish them.


## Anti-patterns (4-field; shared template + cross-cutting rules in `ai-factory/reference-anti-patterns.md`)

- **Silently lowering the floor.** How-not-to: lowering a threshold, deleting/weakening a test, editing ignores
  or registering a hook merely to obtain PASS. Consequence: the quality floor erodes invisibly. How-to: changing
  a required threshold/test needs an explicit diff, reason and review under the local process; the floor moves
  only by owner decision. Exceptions: none without that explicit, reviewed change. Verify: is there a diff +
  reason + reviewer for the floor change, or did PASS appear by relaxing the check?
- **"Exception" used to dodge evidence.** How-not-to: calling a missing check an "exception" to skip it.
  Consequence: an untested obligation is reported as met. How-to: a missing command, unknown untracked scope or
  unavailable reviewer stays BLOCKED, not N/A. Exceptions: N/A only with an applicability reason. Verify: is the
  deviation a pre-written exception with conditions met, or an invented one (central cross-cutting rule 2)?
