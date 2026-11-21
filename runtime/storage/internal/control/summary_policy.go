package control

import "aifactory.local/storage/internal/archive"

// SummaryPolicyAllows checks current authority only. It does not authenticate a
// derivation: the caller must separately verify its envelope and covered sources.
// All records (derived first, then originals) must come from that verified proof.
// This method performs no backend IO and runs under the existing writer fence.
func (t *ArchiveTransaction) SummaryPolicyAllows(a SummaryActivation, records []archive.Record) (bool, error) {
	if err := t.ready(); err != nil {
		return false, err
	}
	current, found := t.d.summaryActivations[summaryScope{t.project, a.Provider}]
	consent := t.d.reg.ConsentEpoch(t.project, a.Provider, "summary")
	state := t.d.archiveStates[t.project]
	if !found || a.Project != t.project || a.Project != current.Project || a.Provider != current.Provider || a.Generation != current.Generation || a.Ordinal != current.Ordinal || !a.At.Equal(current.At) || a.ConsentEpoch != current.ConsentEpoch || a.Generation != state.Generation || !state.MigrationComplete || !consent.Enabled || consent.Epoch != a.ConsentEpoch || a.ConsentEpoch <= consent.RevokedThrough || len(records) < 2 {
		return false, nil
	}
	capture := t.d.reg.ConsentEpoch(t.project, a.Provider, "capture")
	if !capture.Enabled || capture.Epoch <= 0 {
		return false, nil
	}
	for i, r := range records {
		if r.Project != t.project || r.Provider != a.Provider || r.ConsentEpoch <= capture.RevokedThrough || r.ConsentEpoch > capture.Epoch || r.Withdrawn || len(t.d.ret.Serve([]archive.Record{r}, "capture")) != 1 {
			return false, nil
		}
		if i == 0 && r.Type != archive.TypeSummary || i > 0 && r.Type != archive.TypeMessage {
			return false, nil
		}
	}
	return true, nil
}
