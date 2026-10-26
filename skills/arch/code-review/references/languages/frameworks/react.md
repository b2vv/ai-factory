# Optional React with TypeScript

Select only when the task actually touches React with TS/TSX, alongside
[TypeScript](../typescript.md). React JS-only does not imply TypeScript and is
outside this reference scope. Confirm React, runner, Testing Library, userEvent,
MSW and query-library versions already in the project before using their APIs.
Do not assume Next.js, React Server Components or a particular state library.

Test interactions through accessible controls and observable results. Use realistic
keyboard/userEvent interactions and awaited assertions rather than forcing internal
state. At the network boundary, use the project's MSW setup if present, fail on
unhandled requests, and reset handlers between tests. Keep query/cache clients
isolated per test with the project's retry policy made explicit; stale cached
success must not conceal a failing request. Test request payloads as well as UI.

For a touched form, exercise server validation, forbidden access and server failure;
inputs should survive recoverable failures and retry should work. Cover duplicate
submission behavior, dependent queries and permission changes where relevant.
Distinguish loading, empty, partial, success, error and permission states using real
domain triggers. Do not manufacture PASS for a state the test cannot render.

Ensure labels and programmatic error associations, useful invalid-field focus,
keyboard navigation, modal focus return and nonduplicated live status. Prefer
existing accessible component primitives. JSDOM/axe checks cannot prove actual
browser contrast, layout, screen-reader behavior or full keyboard usability. Use
the existing Factory UI/viewport evidence route for those observations; no second
viewport checklist is introduced.

Mock network success is not a provider contract test. Pair touched wire expectations
with real provider serialization/consumer contract evidence. Seed a removed error
mapping or incorrectly disabled submit and confirm a relevant test detects it.
For performance work, measure the actual hot interaction/bundle before and after;
do not add memoization or version-specific APIs without a measured reason.

These are obligations, not a bundled harness. Browser, accessibility and runtime
checks stay NOT_TESTED until actual project evidence exists. [Selection](../index.md).
