package control

import (
	"aifactory.local/storage/internal/archive"
	"encoding/hex"
	"sort"
	"strings"
)

// SummaryActivations returns detached metadata, not source content or permission.
func (d *Durable) SummaryActivations() ([]SummaryActivation, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if e := d.ready(); e != nil {
		return nil, e
	}
	out := make([]SummaryActivation, 0, len(d.summaryActivations))
	for _, a := range d.summaryActivations {
		out = append(out, a)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Project != out[j].Project {
			return out[i].Project < out[j].Project
		}
		return out[i].Provider < out[j].Provider
	})
	return out, nil
}
func (t *ArchiveTransaction) SummaryActivation(provider string) (SummaryActivation, bool, error) {
	if e := t.ready(); e != nil {
		return SummaryActivation{}, false, e
	}
	a, ok := t.d.summaryActivations[summaryScope{t.project, provider}]
	return a, ok, nil
}

// ReserveSummary is internal derived-source admission. Callers still validate the
// sealed body and every source under this fence immediately before WAL acceptance.
func (t *ArchiveTransaction) ReserveSummary(r archive.Record, epoch int64) (archive.Envelope, error) {
	if e := t.ready(); e != nil {
		return archive.Envelope{}, e
	}
	c := t.d.reg.ConsentEpoch(t.project, r.Provider, "summary")
	capture := t.d.reg.ConsentEpoch(t.project, r.Provider, "capture")
	a, ok := t.d.summaryActivations[summaryScope{t.project, r.Provider}]
	state := t.d.archiveStates[t.project]
	key := strings.TrimPrefix(r.MessageID, archive.SessionExtractMessagePrefix)
	if r.Project != t.project || r.Type != archive.TypeSummary || r.Role != "assistant" || r.Seq != 0 || r.ParentID != "" || r.Edited || r.Withdrawn || key == r.MessageID || len(key) != 64 || !ok || !c.Enabled || epoch != c.Epoch || a.ConsentEpoch != epoch || a.Generation != state.Generation || !capture.Enabled || r.ConsentEpoch <= capture.RevokedThrough || r.ConsentEpoch > capture.Epoch || len(t.d.ret.Serve([]archive.Record{r}, "capture")) != 1 {
		return archive.Envelope{}, errSummaryConsent
	}
	if _, e := hex.DecodeString(key); e != nil {
		return archive.Envelope{}, errSummaryConsent
	}
	return t.reserve(r, nil, false, archive.DerivedSessionExtract)
}
