package registry

import "fmt"

// TransitionWorkflow holds the same fence as workflow commits while verifyPersist
// verifies the destination and durably records receipt then flip. The callback must
// not reenter this registry. Failure leaves the old in-memory authority unchanged.
func (r *Registry) TransitionWorkflow(actor Principal, project string, from WorkflowOwner, oldEpoch int64, to WorkflowOwner, verifyPersist func() error) (int64, error) {
	if err := requireOperator(actor); err != nil {
		return 0, err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.blocked.Load() {
		return 0, ErrWorkflowFenced
	}
	a, ok := r.authority[project]
	if !ok {
		return 0, ErrUnknownProj
	}
	if a.Owner != from || a.Epoch != oldEpoch {
		return 0, ErrWorkflowFenced
	}
	if from == to || (to != OwnerMarkdown && to != OwnerPostgres) {
		return 0, fmt.Errorf("registry: invalid workflow transition")
	}
	if err := verifyPersist(); err != nil {
		return 0, err
	}
	a.Owner = to
	a.Epoch++
	r.authority[project] = a
	if to == OwnerMarkdown {
		for id, g := range r.grants {
			if g.Projects[project] {
				if g.WorkflowDenied == nil {
					g.WorkflowDenied = map[string]bool{}
				}
				g.WorkflowDenied[project] = true
				r.grants[id] = g
			}
		}
	}
	return a.Epoch, nil
}

// WorkflowGrantsDisabled verifies the project-scoped revocation prerequisite for
// destructive schema maintenance without disabling another project's grant.
func (r *Registry) WorkflowGrantsDisabled(project string) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.blocked.Load() {
		return false
	}
	for _, g := range r.grants {
		if !g.Revoked && g.Projects[project] && (g.Ops[OpWorkflowRead] || g.Ops[OpWorkflowWrite]) && !g.WorkflowDenied[project] {
			return false
		}
	}
	return true
}
