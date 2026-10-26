# TypeScript: boundary types and observable tests

**Historical-rule warning:** Factory's inherited
`rules/typescript-pocock-idioms.md` contains an older forced-interface house rule.
Its historical policy is retained in an English adaptation, not universal current authority. Current
Cassiopeia rules use a hybrid policy: types for unions, derived/function shapes;
interfaces where extension or declaration merging is intended. Follow the actual
accepted project convention and record conflicts. This reference does not repair
the old file; reading that file directly still exposes the stale note.

Select for confirmed TS/TSX work through the [shared index](index.md). Inspect the
actual TypeScript version, compiler options, module boundaries and test runner.
Do not impose Cassiopeia's MVC directories, service classes, barrel policy, naming,
schema library, lint presets or dependency versions on another project.

## Review the touched contract

- Treat external data as unknown until runtime validation/narrowing establishes
  its shape. `satisfies` can check an expression while preserving inference on
  supported compiler versions; it does not validate network or persisted data.
  Assertions and double casts cannot substitute for boundary validation.
- Model mutually exclusive states with discriminants and review exhaustive
  handling. Prefer literal unions for new compatible APIs when project rules
  agree; do not silently replace public enums or change serialized values.
- Use precise callable types and inspect callback variance under the actual
  compiler configuration. Avoid broadly erasing parameters/results. A narrowly
  justified generic `any` exception needs evidence about the constraint it solves,
  not a blanket lint disable. Unknown input and a generic constraint differ.
- Derive deliberately coupled types from one authoritative contract. Keep unrelated
  concepts independent. Use `readonly` to express permitted operations, while
  remembering it does not deep-freeze runtime objects. Type-only imports must
  match actual module/compiler behavior.
- Distinguish identifiers where accidental mixing is consequential. Construct and
  validate them at trusted boundaries; do not mandate branding every ID or add
  a project-wide helper. Public return annotations and type/interface choices
  should express the accepted local API contract.
- Make failure behavior explicit: exceptions or result unions according to the
  existing contract. Do not force Cassiopeia-specific result names or no-throw
  policy across all projects. Preserve the existing architectural boundaries.

## Tests that expose mistakes

At critical public seams, include compile-time negative cases for incompatible
identifiers, impossible state combinations or invalid callback arguments using the
project's existing type-test mechanism. Verify that a deliberately wrong type is
rejected. Scope these checks to consequential contracts, not exhaustive assertions
about every type. Record compiler/version and whether those checks actually ran.

Runtime tests should exercise malformed input, missing/null fields, unknown enum
values and explicit failure results. Test actual provider serialization against
the accepted schema and consumer expectations when that boundary is touched;
mock-only agreement is insufficient. Cover identifiers beyond JavaScript's safe
integer range according to the wire contract, without silently rounding them.

Use typed builders or the existing partial-fixture helper without hiding the field
under test behind `as unknown as`. A fixture must preserve the relevant invariants;
do not add shoehorn, Zod or ts-reset as a prerequisite. Compare generated consumer
fixtures only if the project already has a pinned, authorized generation route.
For TS React interaction work, explicitly select [React](frameworks/react.md).

Source intent comes first from Cassiopeia's current public agent style sections
20–45 and critical-boundary testing guidance; ECC contract/testing content is
supplementary. Exact source hashes and retained project-specific choices are
recorded in the origins manifest. These are review obligations, not executed tests.
