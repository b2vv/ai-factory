# Runtime helpers

- `onboarding/preflight.py`: one shared read-only inventory implementation.
- `review/review_package.py`: portable Git reads disable fsmonitor/hooks.
- `session-size/session_guard.py`: portable CLI requires an explicit absolute `--store`.
- `legacy/review/review_package.py`: retained original Git invocation policy.
- `legacy/session-size/session_guard.py`: retained original default home-store contract.

Legacy modules are explicit compatibility variants, not aliases for portable modules. Their behavior and tests are preserved; selecting a file is not authorization to run it or register callbacks. No live hook migration occurs. Existing releases keep their own immutable paths. Use an exact runtime path and report it; never select a helper by basename alone.
