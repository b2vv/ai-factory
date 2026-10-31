package control

import "aifactory.local/storage/internal/registry"

// WithStableAuthority is an operator-only maintenance boundary. It holds the
// control mutation lock for the callback, which must not call Durable methods.
// Backup/restore callers use current registry/retention data, never backup grants.
func (d *Durable) WithStableAuthority(actor registry.Principal, action func(*registry.Registry) error) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	defer func() { d.externalActive = false }()
	if err := d.ready(); err != nil {
		return err
	}
	if actor.Kind != registry.Operator {
		return registry.ErrNotOperator
	}
	return action(d.reg)
}
