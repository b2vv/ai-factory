package maintenance

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
)

func migrationHash(s string) string { h := sha256.Sum256([]byte(s)); return hex.EncodeToString(h[:]) }

// PrepareArchiveSchema is explicit offline maintenance after the control
// downgrade witness. Ready schemas are inspected without taking an unrelated
// intent, so interrupted source/index operations can resume safely.
func PrepareArchiveSchema(ctx context.Context, d *control.Durable, actor registry.Principal, project string, source *archive.MongoStore, pg *workflow.PGStore) error {
	if source == nil {
		return control.ErrBlocked
	}
	evidence := budget.Evidence{Kind: "archive-schema-v2", KeyHash: migrationHash(project), PayloadHash: migrationHash(fmt.Sprintf("metadata-v2:pg=%t", pg != nil))}
	return d.WithArchiveWriter(actor, project, func(tx *control.ArchiveTransaction) error {
		if tx == nil || d.Budget() == nil {
			return control.ErrBlocked
		}
		ready := func() (bool, error) {
			mongoReady, err := source.MetadataSchemaReady()
			if err != nil {
				return false, err
			}
			pgReady := true
			if pg != nil {
				pgReady, err = pg.ArchiveMetadataReady(ctx)
				if err != nil {
					return false, err
				}
			}
			return mongoReady && pgReady, nil
		}
		established, err := ready()
		if err != nil {
			return err
		}
		pending := d.Budget().Snapshot().Pending
		if established && (len(pending) == 0 || len(pending) == 1 && pending[0].Evidence != evidence) {
			return nil
		}
		cost := archive.SchemaLogicalBytes()
		if pg != nil {
			cost += workflow.SchemaLogicalBytes()
		}
		if err := d.ReserveIdentifiedExternal(evidence, cost); err != nil {
			return err
		}
		if err := source.EnsureMetadataSchema(); err != nil {
			return err
		}
		if pg != nil {
			if err := pg.UpgradeArchiveMetadata(ctx); err != nil {
				return err
			}
		}
		established, err = ready()
		if err != nil {
			return err
		}
		if !established {
			return control.ErrBlocked
		}
		return d.FinishExternal()
	})
}
