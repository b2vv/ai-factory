# Optional Laravel

Select with [PHP](../php.md) only when Laravel is confirmed. This is not a default
for Symfony or plain PHP. Inspect framework, PHP, PHPUnit/Pest and authentication
package versions. Follow the project's application structure and authorization
contract; do not install Sanctum or change guards to match an example.

Trace validated request data through FormRequest or the existing validation route
to a DTO/application boundary where useful. Validate omission/null handling and
output serialization. Review ORM loading at touched collection boundaries for N+1
queries, with representative data and an explicit query budget rather than a
single-record happy path.

Test Policy/authorization decisions for owner, other owner and unauthenticated
callers using the actual guard. If Sanctum bearer tokens are used, test scope and
revocation behavior through that real route; cookie/session and token modes are
not interchangeable. Decide 403/404 behavior according to the accepted contract.

Use existing Http, Queue, Mail and Storage fakes to isolate effects where supported,
then assert meaningful payload, destination, authorization and failure behavior.
A queued/faked dispatch does not prove a worker executed or a real delivery
succeeded. Retain scoped integration coverage for touched database constraints,
transactions and actual external adapters when available.

Exercise failed validation without side effects, cross-owner denial, retry behavior
and rollback. Keep fixtures isolated and tear them down reliably. Traditional
anonymous functions need `use (...)` for required outer locals; arrow functions
capture referenced outer values implicitly on supported PHP versions. Do not copy
an uncaptured-variable example. Composer operations, configuration/cache rebuilds and
database migrations mutate state and are not read-only verification commands.
Use only the task's approved isolated command route. [Selection](../index.md).
