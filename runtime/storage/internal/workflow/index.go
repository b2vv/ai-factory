package workflow

import (
	"bytes"
	"fmt"

	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
)

// IndexMarkdown refreshes the rebuildable PG projection without transferring
// authority. The operator freezes edits to the dedicated structured document.
// Replace also removes rows deleted from the authoritative document. A failure
// never promotes the possibly stale projection to authority.
func IndexMarkdown(d *control.Durable, store SnapshotStore, actor registry.Principal, project, path, revision string) error {
	return d.WithStableAuthority(actor, func(reg *registry.Registry) error {
		owner, _, ok := reg.WorkflowAuthority(project)
		if !ok {
			return registry.ErrUnknownProj
		}
		if owner != registry.OwnerMarkdown {
			return fmt.Errorf("workflow: indexing requires Markdown authority")
		}
		if !store.Available() {
			return ErrBlockedPGDown
		}
		tasks, e := VerifiedDocument(path, revision)
		if e != nil {
			return e
		}
		cost, e := ReservationBytes(project, tasks)
		if e != nil {
			return e
		}
		if e = d.ReserveExternalBytes(cost); e != nil {
			return e
		}
		if e = store.Replace(project, tasks); e != nil {
			return e
		}
		actual, e := store.Snapshot(project)
		if e != nil {
			return e
		}
		expected, e := canonicalTasks(tasks)
		if e != nil {
			return e
		}
		got, e := canonicalTasks(actual)
		if e != nil {
			return e
		}
		if !bytes.Equal(expected, got) {
			return fmt.Errorf("workflow: index verification failed")
		}
		if _, e = VerifiedDocument(path, revision); e != nil {
			return e
		}
		return d.FinishExternal()
	})
}
