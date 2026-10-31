// Package maintenance contains explicit offline operator maintenance, never
// automatic startup behavior. No operation grants authority from a backup.
package maintenance

import (
	"aifactory.local/storage/internal/backup"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/workflow"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"time"
)

type Source struct {
	Path     string
	Revision string
}

// RollbackWorkflowV1 verifies the specific table touched by the paired down file.
// The operator must freeze external database/file writers for this maintenance
// window; the control process lock prevents the server from sharing this lineage.
func RollbackWorkflowV1(ctx context.Context, d *control.Durable, p *workflow.PGStore, actor registry.Principal, input io.Reader, sources map[string]Source, acknowledge bool) error {
	if !acknowledge {
		return fmt.Errorf("maintenance: explicit derived-data removal acknowledgement required")
	}
	snap, archiveProofs, e := backup.ReadRollbackSources(input, time.Now())
	if e != nil {
		return e
	}
	saved := map[string]backup.Project{}
	receipts := map[string]control.WorkflowReceipt{}
	for _, item := range snap.Projects {
		if _, ok := saved[item.ID]; ok {
			return fmt.Errorf("maintenance: duplicate backup project")
		}
		saved[item.ID] = item
		if r, ok := d.LastWorkflowReceipt(item.ID); ok {
			receipts[item.ID] = r
		}
	}
	return d.WithStableAuthority(actor, func(reg *registry.Registry) error {
		// Dropping the shared table affects even empty PG-owned projects.
		for _, id := range reg.Projects() {
			owner, _, _ := reg.WorkflowAuthority(id)
			if owner != registry.OwnerMarkdown {
				return fmt.Errorf("maintenance: PG-owned project requires completed cutover before rollback")
			}
		}
		return p.RollbackInitialWithIndex(ctx, func(rows map[string][]workflow.Task) error {
			// Every saved project must match current authority, not stale backup epochs.
			for id, item := range saved {
				owner, epoch, ok := reg.WorkflowAuthority(id)
				if !ok || owner != registry.OwnerMarkdown || owner != item.Owner || epoch != item.Epoch {
					return fmt.Errorf("maintenance: backup authority does not match current lineage")
				}
				source, ok := sources[id]
				if !ok {
					return fmt.Errorf("maintenance: verified Markdown source missing")
				}
				tasks, e := workflow.VerifiedDocument(source.Path, source.Revision)
				if e != nil {
					return e
				}
				expected, e := workflow.Document(tasks)
				if e != nil {
					return e
				}
				stored, e := workflow.Document(rows[id])
				if e != nil {
					return e
				}
				backed, e := workflow.Document(item.Tasks)
				if e != nil {
					return e
				}
				if !bytes.Equal(expected, stored) || !bytes.Equal(stored, backed) {
					return fmt.Errorf("maintenance: source, locked rows and verified backup differ")
				}
				if epoch > 1 {
					receipt, ok := receipts[id]
					if !ok || receipt.To != registry.OwnerMarkdown || receipt.NewEpoch != epoch {
						return fmt.Errorf("maintenance: completed durable cutover receipt missing")
					}
					if !reg.WorkflowGrantsDisabled(id) {
						return fmt.Errorf("maintenance: project workflow grants must be revoked before rollback")
					}

				}
			}
			for id := range rows {
				if _, ok := saved[id]; !ok {
					return fmt.Errorf("maintenance: affected rows absent from backup")
				}
			}
			return nil
		}, func(records []workflow.DerivedIndexRecord, docs []workflow.DerivedDocumentRecord) error {
			for _, r := range records {
				if _, ok := saved[r.Project]; !ok {
					return fmt.Errorf("maintenance: index project absent from verified backup")
				}
				var identity []string
				if json.Unmarshal([]byte(r.Identity), &identity) != nil || len(identity) != 4 || identity[0] != r.Project {
					return fmt.Errorf("maintenance: invalid index identity")
				}
				if archiveProofs[r.Identity] != r.PayloadHash {
					return fmt.Errorf("maintenance: indexed source missing/different in verified backup")
				}
			}
			for _, r := range docs {
				if _, ok := saved[r.Project]; !ok {
					return fmt.Errorf("maintenance: document project absent from verified backup")
				}
				var ref search.DocumentReference
				if e := json.Unmarshal(r.Data, &ref); e != nil {
					return e
				}
				if e := search.ValidateDocument(ref); e != nil {
					return fmt.Errorf("maintenance: current authoritative document ledger unavailable or changed: %w", e)
				}
			}
			return nil
		})
	})
}
func Revision(raw []byte) string { h := sha256.Sum256(raw); return hex.EncodeToString(h[:]) }
