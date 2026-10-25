# Python: fixture ownership, ports and async assertions

Select via the [shared index](index.md) for actual Python work. Confirm interpreter,
lockfile, pytest/plugin versions and project configuration. Formatting, linting and
typechecking are separate checks; `ruff format` does not establish `ruff check` or
mypy success. Unknown tooling is reported, not silently installed or marked PASS.

## Review

Keep validation at external boundaries and make failure behavior visible. Protocols
can express consumer-owned collaborator contracts without forcing inheritance;
type annotations alone do not perform runtime validation. Use context managers or
explicit ownership for files, connections and cleanup. Ensure cancellation and
exception paths release resources, not just successful returns.

Review mutable defaults, shared fixture state and implicit environment dependencies.
Do not log arbitrary arguments, keyword arguments, tokens or payloads to improve
debugging; select safe diagnostic fields with the project's redaction policy.

## Test design

- Pick fixture scope according to resource lifetime. Yield/teardown must clean up
  after failure; don't share mutable state across tests merely to reduce startup.
  Parametrize boundary cases with meaningful expected outcomes, including missing,
  malformed and conflicting data, rather than repeating identical happy paths.
- Patch at the namespace where a collaborator is looked up. Use autospec/spec
  where appropriate to expose signature mistakes; a correctly specified mock still
  does not prove real service behavior. Pair fake and actual adapter contract cases
  for touched ports when an isolated integration route exists.
- Async tests assert awaited behavior, cancellation and exceptions, not just mock
  invocation counts. Match async fixtures and markers to the installed
  pytest-asyncio strict/auto mode and version. Do not assume a synchronous fixture
  implicitly owns an event loop or that one mode's decorators work in another.
- Bound waits and concurrency in tests; avoid sleeps as synchronization. Exercise
  timeout/cancellation while work is blocked and check cleanup or explicit abort.
- For wire contracts test actual serialized output, error responses and nullability.
  Generated or mocked consumers must be checked against the same accepted contract.

Frameworks are optional: [FastAPI](frameworks/fastapi.md) for confirmed FastAPI;
[Django](frameworks/django.md) for confirmed Django/DRF. Unknown framework selects
neither. Recipe execution, real databases and application lifespan remain NOT_TESTED
unless the task records their actual authorized runs.
