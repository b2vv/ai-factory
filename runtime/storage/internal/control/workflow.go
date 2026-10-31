package control

import (
	"aifactory.local/storage/internal/registry"
	"encoding/hex"
	"fmt"
)

// WorkflowReceipt is persisted before the flip in the single control WAL.
// A prepared receipt alone never changes authority during replay.
type WorkflowReceipt struct {
	Project        string
	From           registry.WorkflowOwner
	To             registry.WorkflowOwner
	OldEpoch       int64
	NewEpoch       int64
	SourceRevision string
	ExportHash     string
}

func validWorkflowReceipt(r *WorkflowReceipt) bool {
	if r == nil || r.Project == "" || r.SourceRevision == "" || r.OldEpoch < 1 || r.NewEpoch != r.OldEpoch+1 || r.From == r.To {
		return false
	}
	if (r.From != registry.OwnerMarkdown && r.From != registry.OwnerPostgres) || (r.To != registry.OwnerMarkdown && r.To != registry.OwnerPostgres) {
		return false
	}
	b, e := hex.DecodeString(r.ExportHash)
	return e == nil && len(b) == 32
}
func (d *Durable) applyWorkflowPrepare(r *WorkflowReceipt) error {
	if !validWorkflowReceipt(r) {
		return fmt.Errorf("control: invalid workflow receipt")
	}
	owner, epoch, ok := d.reg.WorkflowAuthority(r.Project)
	if !ok || owner != r.From || epoch != r.OldEpoch {
		return registry.ErrWorkflowFenced
	}
	if d.workflowPrepared == nil {
		d.workflowPrepared = map[string]WorkflowReceipt{}
	}
	d.workflowPrepared[r.Project] = *r
	return nil
}
func (d *Durable) applyWorkflowFlip(actor registry.Principal, r *WorkflowReceipt) error {
	if !validWorkflowReceipt(r) {
		return fmt.Errorf("control: invalid workflow flip")
	}
	prepared, ok := d.workflowPrepared[r.Project]
	if !ok || prepared != *r {
		return fmt.Errorf("control: flip without matching durable receipt")
	}
	_, err := d.reg.TransitionWorkflow(actor, r.Project, r.From, r.OldEpoch, r.To, func() error { return nil })
	if err == nil {
		delete(d.workflowPrepared, r.Project)
		if d.workflowCompleted == nil {
			d.workflowCompleted = map[string]WorkflowReceipt{}
		}
		d.workflowCompleted[r.Project] = *r
	}
	return err
}

// CutoverWorkflow serializes control mutations and workflow commits. verify runs
// under the authority fence and must verify actual destination bytes against source
// revision; it must not call control or registry methods. No grant/authority changes
// occur if verification fails. A persistence error is an ambiguous outcome, requiring
// recovery before serving. Runtime callers must gate all access on Blocked.
func (d *Durable) CutoverWorkflow(actor registry.Principal, project string, from registry.WorkflowOwner, oldEpoch int64, to registry.WorkflowOwner, verify func() (sourceRevision, exportHash string, err error)) (WorkflowReceipt, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	defer func() { d.externalActive = false }()
	var receipt WorkflowReceipt
	if err := d.ready(); err != nil {
		return receipt, err
	}
	if actor.Kind != registry.Operator {
		return receipt, registry.ErrNotOperator
	}
	if verify == nil {
		return receipt, fmt.Errorf("control: workflow verification required")
	}
	_, err := d.reg.TransitionWorkflow(actor, project, from, oldEpoch, to, func() error {
		rev, hash, e := verify()
		if e != nil {
			return e
		}
		if e = d.FinishExternal(); e != nil {
			return e
		}
		receipt = WorkflowReceipt{Project: project, From: from, To: to, OldEpoch: oldEpoch, NewEpoch: oldEpoch + 1, SourceRevision: rev, ExportHash: hash}
		if !validWorkflowReceipt(&receipt) {
			return fmt.Errorf("control: invalid verified workflow receipt")
		}
		if e = d.persist(mutation{Kind: kWorkflowPrepare, Workflow: &receipt}); e != nil {
			return e
		}
		if d.workflowPrepared == nil {
			d.workflowPrepared = map[string]WorkflowReceipt{}
		}
		d.workflowPrepared[project] = receipt
		if e = d.persist(mutation{Kind: kWorkflowFlip, Workflow: &receipt}); e != nil {
			return e
		}
		delete(d.workflowPrepared, project)
		return nil
	})
	if err == nil {
		if d.workflowCompleted == nil {
			d.workflowCompleted = map[string]WorkflowReceipt{}
		}
		d.workflowCompleted[project] = receipt
	}
	return receipt, err
}

// LastWorkflowReceipt returns a copy of the last completed durable transition.
// Callers must recheck its NewEpoch under a stable authority fence before acting.
func (d *Durable) LastWorkflowReceipt(project string) (WorkflowReceipt, bool) {
	d.mu.Lock()
	defer d.mu.Unlock()
	r, ok := d.workflowCompleted[project]
	return r, ok
}
