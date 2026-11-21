# Third-party notices — storage server candidate

Vendored LICENSE/NOTICE files for every module in the storage module's build/test/
delivery graph (captured from the Go module cache; one directory per module).

- `github.com/davecgh/go-spew` — ISC (`LICENSE`)
- `github.com/golang/snappy` — BSD-3-Clause (`LICENSE`)
- `github.com/google/go-cmp` — BSD-3-Clause (`LICENSE`)
- `github.com/jackc/pgpassfile` — MIT (`LICENSE`)
- `github.com/jackc/pgservicefile` — MIT (`LICENSE`)
- `github.com/jackc/pgx/v5` — MIT (`LICENSE`)
- `github.com/jackc/puddle/v2` — MIT (`LICENSE`)
- `github.com/klauspost/compress` — BSD-3-Clause (`LICENSE`)
- `github.com/montanaflynn/stats` — MIT (`LICENSE`)
- `github.com/pmezard/go-difflib` — BSD-3-Clause (`LICENSE`)
- `github.com/stretchr/testify` — MIT (`LICENSE`)
- `github.com/xdg-go/pbkdf2` — Apache-2.0 (`LICENSE`)
- `github.com/xdg-go/scram` — Apache-2.0 (`LICENSE`)
- `github.com/xdg-go/stringprep` — Apache-2.0 (`LICENSE`)
- `github.com/youmark/pkcs8` — MIT (`LICENSE`)
- `go.mongodb.org/mongo-driver` — Apache-2.0 (`LICENSE`)
- `golang.org/x/crypto` — BSD-3-Clause (`LICENSE`)
- `golang.org/x/sync` — BSD-3-Clause (`LICENSE`)
- `golang.org/x/text` — BSD-3-Clause (`LICENSE`)
- `gopkg.in/check.v1` — BSD-3-Clause (`LICENSE`)
- `gopkg.in/yaml.v3` — MIT (`LICENSE`)
- `gopkg.in/yaml.v3` — Apache-2.0 (`NOTICE`)

## Base images (build/test only; NOT redistributed in the FROM-scratch factory image)
- `golang:1.23` — build stage toolchain (Go, BSD-3-Clause).
- `postgres:17.5`, `mongo:7.0.16` — integration/e2e test backends only.
- `scratch` — empty delivery base (no bundled OS userland; only the factory binary).
