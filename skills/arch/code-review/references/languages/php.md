# PHP: explicit boundaries and isolated tests

Select for actual PHP work through the [shared index](index.md). Confirm PHP,
Composer lockfile, PHPUnit or Pest version and the existing test configuration.
Composer install/update, application boot, cache and database commands can mutate
state; selecting this reference does not authorize them. No framework is inferred.

## Review

Use DTOs or value objects where a real boundary needs validated data or invariants;
do not create wrappers for every value. Review nullability, scalar coercion and
exception behavior against the actual PHP version and project policy. Constructor
injection should make necessary collaborators visible. Keep ORM records, SDK
objects and transport details from leaking into domain behavior unless the accepted
architecture intentionally owns that coupling. Preserve the project's layout.

An interface or fake is useful when it represents a consequential port. Its
contract must describe failure, ordering, absence and transaction expectations;
do not make mock call order the sole specification. Validate serialized output
and error shape at the actual HTTP or message boundary where applicable.

## Testing obligations

- Unit cases: valid and invalid DTO construction, optional/null fields, invariant
  violations, exception/result behavior and collaborator failure. Assert observable
  results or effects, not only that a method was called.
- Integration cases: the real adapter shares contract cases with its fake; verify
  persistence constraints, serialization and rollback behavior in the existing
  isolated fixture route. Do not claim fake-only tests exercise the database.
- Fixture lifetime: reset mutable state and use teardown for resources even after
  an assertion fails. Separate tests that need framework boot from pure unit cases.
  Avoid dependence on wall-clock time, network availability or test ordering.
- When changing a public signature or field, seed a mismatch and verify the relevant
  consumer/adapter test detects it. Record the supported runner version and command
  actually used; PHPUnit and Pest APIs are not interchangeable across all versions.

Select [Laravel](frameworks/laravel.md) only for confirmed Laravel work. Symfony and
plain PHP retain their own project references. This is authored guidance, with no
bundled PHPUnit/Pest installation, compiled recipe or framework activation.
