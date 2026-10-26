# Rust: ownership contracts and invariant tests

Select for actual Rust through the [shared index](index.md). Inspect the toolchain,
edition, enabled features, workspace/package scope and lockfile before proposing a
command. Existing project tools take precedence; no new property-testing, mocking
or async dependency follows automatically from this reference.

## Review

Trace ownership, borrow lifetimes and cleanup across successful, error and
cancellation paths. A clone may be necessary; replacing it with a lifetime trick is
not inherently safer. Distinguish borrowed views from owned data at API boundaries.
Traits should describe consumer needs and observable failure semantics rather than
force a generic abstraction over every function.

Review blocking work inside async code, task ownership, bounded channel capacity,
backpressure and shutdown. Cancellation of a caller may not cancel spawned work;
test the actual runtime's semantics. Bound concurrency and outstanding work, and
make dropped receiver/sender behavior explicit.

Unsafe code needs a precise safety contract: validity, alignment, initialization,
aliasing, lifetime and synchronization obligations plus who establishes them. A raw
pointer does not justify fabricating an arbitrary borrowed lifetime. Prefer an
existing safe API; a test passing is not proof that unsafe code is sound.

## Tests

Use table cases or existing rstest fixtures for observable error and edge behavior.
For a suitable encoder/parser, property tests (for example existing proptest) can
check round trips within the accepted domain, rejection invariants and state-machine
properties. Preserve minimized regressions and deterministic seeds where supported;
arbitrary generation must respect valid preconditions, not assume every byte string
round-trips. Include malformed input separately.

For consequential trait ports, run common contract cases against fake and real
implementations under existing isolated tooling. Existing mockall mocks can expose
interaction failures, but cannot establish real adapter semantics. Use doctests for
public API examples and check applicable features/toolchain. If using `unwrap_err`,
remember the success type needs `Debug`; choose an assertion compatible with the
actual types instead of copying a noncompiling example.

Exercise blocked send/receive, worker failure and shutdown with bounded deadlines.
Record what was run and which features were included. This reference supplies no
verified loom, Miri, trybuild or Rust fuzz harness and makes no such coverage claim.
Those tools require a separate project-specific, available and authorized setup.
