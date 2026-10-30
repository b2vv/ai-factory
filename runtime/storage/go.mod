// AI Factory optional storage modules — Go modular monolith (API + background worker).
// Stdlib-only so the hermetic test suite runs offline with no module downloads,
// no Docker, and no databases. Real MongoDB/PostgreSQL drivers are introduced later
// behind the store interfaces in internal/archive and internal/workflow; they are not
// required by this suite. Disabled by default; this module activates nothing.
module aifactory.local/storage

go 1.23
