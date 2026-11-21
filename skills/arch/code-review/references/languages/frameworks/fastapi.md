# Optional FastAPI

Select with [Python](../python.md) only for confirmed FastAPI. Check the actual
FastAPI, Pydantic, httpx, ASGI test tooling and pytest-asyncio versions; validation
and testing APIs vary. Do not assume Pydantic major versions are interchangeable.

Review separate input/output contracts, omission/nullability, aliases, error shape
and sensitive-field exclusion. Test actual serialized responses, not merely a
model's in-memory attributes. Keep authorization and resource ownership checks at
the appropriate boundary. A pre-insert uniqueness lookup is not concurrency
protection; use database constraints and map conflicts to the accepted response.

Override dependencies only within the test's lifetime and restore them even when
assertions fail. Use the installed dependency injection API correctly, including
required imports such as Depends when writing runnable code. Assert failure paths
and meaningful adapter interactions; a stubbed dependency does not validate the
actual storage/authentication implementation.

An httpx ASGITransport alone does not run application lifespan events. When startup
or shutdown matters, use the project's version-compatible lifespan-aware fixture
and assert resource initialization/cleanup explicitly. State which lifespan events
actually ran; do not label a transport-only test an application lifecycle test.
Match async fixtures/markers to configured strict/auto mode and avoid sharing
mutable application state or incompatible event loops across tests.

Cover invalid input, unauthorized/cross-owner access, conflict, timeout/cancellation
and cleanup. Use the existing isolated real-adapter route for database guarantees;
mock responses establish only the mocked contract. No live server, database,
framework install or model probe is performed by selecting this reference.
[Selection](../index.md).
