package control

import (
	"errors"
	"fmt"
	"math"
	"time"
	"unicode/utf8"

	"aifactory.local/storage/internal/registry"
)

// SummaryActivation is a retained no-backfill baseline, never source text.
// Current enabled state and permanent revocations remain registry authority.
type SummaryActivation struct {
	Project      string    `json:"project"`
	Provider     string    `json:"provider"`
	Generation   string    `json:"generation"`
	Ordinal      int64     `json:"ordinal"`
	At           time.Time `json:"at"`
	ConsentEpoch int64     `json:"consent_epoch"`
}
type summaryScope struct{ Project, Provider string }
type summaryConsentMutation struct {
	Epoch      int64              `json:"epoch"`
	Terminal   bool               `json:"terminal,omitempty"`
	Activation *SummaryActivation `json:"activation,omitempty"`
}

const kSummaryConsent mutationKind = "summary_consent_v1"

// A distinct kind makes previous S1 readers refuse instead of replaying the old
// unconditional policy increment with different semantics.
const kSummaryInitialConsent mutationKind = "summary_initial_consent_v2"

var errSummaryConsent = errors.New("control: invalid summary consent or activation")

// ErrSummaryTerminal identifies a retained fail-closed revocation, not transient IO.
var ErrSummaryTerminal = fmt.Errorf("%w: terminal summary revocation requires recovery", ErrBlocked)

// SummaryConsentStep is the counter portion of a consent transition. It grants
// no authority: Durable still validates/persists activation under its own fence.
type SummaryConsentStep struct {
	Epoch int64
	NoOp  bool
}

// PlanSummaryConsent is shared by live writes and replay. Reserve the terminal
// epoch for revocation and accept terminal retries only for a fully revoked state.
func PlanSummaryConsent(c registry.Consent, enabled bool) (SummaryConsentStep, error) {
	if c.Epoch < 0 || c.RevokedThrough < 0 || c.RevokedThrough > c.Epoch || (c.Enabled && (c.Epoch == 0 || c.RevokedThrough >= c.Epoch)) {
		return SummaryConsentStep{}, errSummaryConsent
	}
	if c.Epoch == math.MaxInt64 {
		if !enabled && !c.Enabled && c.RevokedThrough == math.MaxInt64 {
			return SummaryConsentStep{c.Epoch, true}, nil
		}
		return SummaryConsentStep{}, errSummaryConsent
	}
	if enabled && c.Epoch >= math.MaxInt64-1 {
		return SummaryConsentStep{}, errSummaryConsent
	}
	return SummaryConsentStep{Epoch: c.Epoch + 1}, nil
}

func validSummaryID(v string, max int) bool { return v != "" && len(v) <= max && utf8.ValidString(v) }

func (d *Durable) SummaryActivation(project, provider string) (SummaryActivation, bool, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if e := d.ready(); e != nil {
		return SummaryActivation{}, false, e
	}
	a, ok := d.summaryActivations[summaryScope{project, provider}]
	return a, ok, nil
}
func (d *Durable) applySummaryConsent(m mutation) error {
	if m.SummaryConsent == nil || (m.SummaryConsent.Terminal && (m.Enabled || m.SummaryConsent.Activation != nil)) || m.Capability != "summary" || !d.reg.HasProject(m.Project) || !validSummaryID(m.Project, 4096) || !validSummaryID(m.Provider, 256) {
		return errSummaryConsent
	}
	c := d.reg.ConsentEpoch(m.Project, m.Provider, "summary")
	initial := m.Kind == kSummaryInitialConsent
	_, hadActivation := d.summaryActivations[summaryScope{m.Project, m.Provider}]
	if initial && (!m.Enabled || m.SummaryConsent.Terminal || c.Enabled || c.Epoch != 0 || c.RevokedThrough != 0 || hadActivation || m.SummaryConsent.Epoch != 1) {
		return errSummaryConsent
	}
	step, err := PlanSummaryConsent(c, m.Enabled)
	if err != nil || m.SummaryConsent.Epoch != step.Epoch {
		return errSummaryConsent
	}
	if step.NoOp {
		if m.SummaryConsent.Terminal {
			d.block(ErrSummaryTerminal.Error())
			return ErrSummaryTerminal
		}
		if m.SummaryConsent.Activation != nil {
			return errSummaryConsent
		}
		return nil
	}
	a := m.SummaryConsent.Activation
	if m.Enabled {
		state, ok := d.archiveStates[m.Project]
		if !ok || !state.MigrationComplete || state.Pending != nil || state.PolicyRevision == math.MaxUint64 || a == nil || a.Project != m.Project || a.Provider != m.Provider || a.Generation != state.Generation || !validArchiveGeneration(a.Generation) || a.Ordinal != state.CommittedOrdinal || a.Ordinal < 0 || a.ConsentEpoch != m.SummaryConsent.Epoch || a.ConsentEpoch >= math.MaxInt64 || a.At.IsZero() {
			return errSummaryConsent
		}
		if _, e := a.At.UTC().MarshalJSON(); e != nil {
			return errSummaryConsent
		}
	} else if a != nil {
		return errSummaryConsent
	}
	if _, e := d.reg.SetConsent(registry.Principal{Kind: registry.Operator}, m.Project, m.Provider, "summary", m.Enabled); e != nil {
		return e
	}
	if m.Enabled {
		if d.summaryActivations == nil {
			d.summaryActivations = map[summaryScope]SummaryActivation{}
		}
		detached := *a
		detached.At = detached.At.UTC()
		d.summaryActivations[summaryScope{m.Project, m.Provider}] = detached
	}
	// No prior summary authority exists on this explicit first-ever transition.
	// Its baseline excludes history; existing original rows remain valid. V1
	// journal records and every later transition retain their policy increment.
	var policyErr error
	if !initial {
		policyErr = d.advanceArchivePolicy(m.Project)
	}
	if m.SummaryConsent.Terminal {
		d.block(ErrSummaryTerminal.Error())
		return ErrSummaryTerminal
	}
	return policyErr
}

// Caller holds d.mu. Replay does not require a live ledger: it validates retained
// transitions, while live admission separately refuses any unresolved intent.
func (d *Durable) setSummaryConsent(project, provider string, enabled bool) (int64, error) {
	if !d.reg.HasProject(project) || !validSummaryID(project, 4096) || !validSummaryID(provider, 256) {
		return 0, errSummaryConsent
	}
	c := d.reg.ConsentEpoch(project, provider, "summary")
	step, err := PlanSummaryConsent(c, enabled)
	if err != nil {
		if c.Epoch < 0 || c.Epoch == math.MaxInt64 {
			d.block("summary consent counter invalid/exhausted; explicit recovery required")
		}
		return 0, err
	}
	if step.NoOp {
		return step.Epoch, nil
	}
	m := mutation{Kind: kSummaryConsent, Project: project, Provider: provider, Capability: "summary", Enabled: enabled, SummaryConsent: &summaryConsentMutation{Epoch: step.Epoch}}
	if enabled {
		if !c.Enabled && c.Epoch == 0 && c.RevokedThrough == 0 {
			if _, exists := d.summaryActivations[summaryScope{project, provider}]; exists {
				return 0, errSummaryConsent
			}
			m.Kind = kSummaryInitialConsent
		}
		state, ok := d.archiveStates[project]
		if !ok || !state.MigrationComplete || state.Pending != nil || state.PolicyRevision == math.MaxUint64 || d.budget == nil || len(d.budget.Snapshot().Pending) != 0 {
			return 0, errSummaryConsent
		}
		now := time.Now().UTC()
		m.SummaryConsent.Activation = &SummaryActivation{Project: project, Provider: provider, Generation: state.Generation, Ordinal: state.CommittedOrdinal, At: now, ConsentEpoch: c.Epoch + 1}
		if e := d.persist(m); e != nil {
			return 0, e
		}
		if e := d.applySummaryConsent(m); e != nil {
			d.block("summary granting witness requires recovery")
			return 0, e
		}
		return m.SummaryConsent.Epoch, nil
	}
	if state, ok := d.archiveStates[project]; ok && state.PolicyRevision == math.MaxUint64 {
		m.SummaryConsent.Terminal = true
	}
	// Revoke first, and attempt its retained witness even when advancing policy
	// enters terminal exhaustion. Such an outcome remains BLOCKED/unacknowledged.
	applyErr := d.applySummaryConsent(m)
	persistErr := d.persist(m)
	if applyErr != nil {
		return m.SummaryConsent.Epoch, applyErr
	}
	return m.SummaryConsent.Epoch, persistErr
}

// Legacy revokes remain monotone-safe, but must never use unchecked increment.
func (d *Durable) applyLegacySummaryConsent(m mutation) error {
	if m.Enabled {
		return errSummaryConsent
	}
	c := d.reg.ConsentEpoch(m.Project, m.Provider, "summary")
	step, err := PlanSummaryConsent(c, false)
	if err != nil {
		return err
	}
	if step.NoOp {
		return nil
	}
	m.Kind = kSummaryConsent
	m.SummaryConsent = &summaryConsentMutation{Epoch: step.Epoch}
	return d.applySummaryConsent(m)
}
