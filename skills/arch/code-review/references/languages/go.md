# Go: cancellation, bounded work and regressions

Select via the [shared index](index.md) for actual Go work. Confirm toolchain,
module/workspace, build tags and supported target before choosing package-scoped
test, race or fuzz commands. No test-container dependency or runtime is supplied.

## Review ownership and concurrency

Propagate request context to the actual blocking operation, including transport or
storage APIs that support it. A wrapper accepting context while its inner fetch
ignores cancellation is incomplete. Every goroutine needs an owner and termination
condition. Bound fan-out before launching work, not only while collecting results.

Channel sends can block when the consumer exits. Make cancellation and closed-peer
handling explicit on both send and receive paths. Define who closes a channel and
who waits for workers. On sibling failure, cancel or drain according to the contract;
do not leak background work. Graceful shutdown must say which work drains and which
aborts within the deadline. Review shared state for synchronization and ownership.

Interfaces belong at meaningful consumer seams. A fake repository and actual
adapter should meet the same observable contract: absence, ordering, errors,
serialization and persistence constraints as applicable. Do not impose a new
architecture or package tree to obtain an interface.

## Tests that challenge those contracts

- Cancel while a consumer is blocked or has departed; require workers to terminate
  within a bounded deadline. Assert a maximum number of active operations and check
  sibling cancellation on failure. Test graceful drain and forced abort separately.
- Run the project's scoped race checks on a supported toolchain/target when
  available. A race-free run covers observed executions, not all schedules. Record
  unavailable instrumentation as NOT_TESTED rather than ordinary-test equivalence.
- For parsers/transformations, use seed corpus and meaningful invariants for native
  Go fuzzing when supported. Bound duration/memory and retain minimized crashing
  input as a regression. Do not merely assert that random input does not panic if
  the accepted contract also requires validation and output correctness.
- Golden files suit deterministic output. Review the intended diff and compare
  against an independent contract; never regenerate goldens automatically to make
  a failure disappear. Control timestamps and ordering explicitly.
- Table cases cover error identity/wrapping, malformed input, missing/null wire
  fields and actual serialized responses for the touched boundary. Real database
  semantics need the existing isolated integration route, not fake-only success.

No command in this reference was executed against a consumer project. Select
version-compatible commands from the project and attach their real scope/results.
