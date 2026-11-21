// AI Factory optional storage modules — Go modular monolith (API + background worker).
// The hermetic UNIT suite still runs offline against in-memory fakes (no Docker, no
// databases). This candidate additionally provides the REAL MongoDB and PostgreSQL
// backends behind the store interfaces in internal/archive and internal/workflow; they are
// exercised only by the integration/e2e suite against real test databases and are inactive
// unless explicitly enabled. Disabled by default; this module activates nothing on its own.
module aifactory.local/storage

go 1.23

require (
	github.com/jackc/pgx/v5 v5.7.1
	go.mongodb.org/mongo-driver v1.17.1
	golang.org/x/text v0.18.0
)

require (
	github.com/golang/snappy v0.0.4 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	github.com/klauspost/compress v1.13.6 // indirect
	github.com/montanaflynn/stats v0.7.1 // indirect
	github.com/xdg-go/pbkdf2 v1.0.0 // indirect
	github.com/xdg-go/scram v1.1.2 // indirect
	github.com/xdg-go/stringprep v1.0.4 // indirect
	github.com/youmark/pkcs8 v0.0.0-20240726163527-a2c0da244d78 // indirect
	golang.org/x/crypto v0.27.0 // indirect
	golang.org/x/sync v0.8.0 // indirect
)
