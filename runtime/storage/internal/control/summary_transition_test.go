package control_test

import (
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"math"
	"testing"
)

func TestSummaryConsentTransitionNeverWraps(t *testing.T) {
	for _, tc := range []struct {
		name      string
		current   registry.Consent
		enable    bool
		epoch     int64
		noop, bad bool
	}{
		{name: "last enable", current: registry.Consent{Epoch: math.MaxInt64 - 2}, enable: true, epoch: math.MaxInt64 - 1},
		{name: "last revoke", current: registry.Consent{Epoch: math.MaxInt64 - 1, Enabled: true}, epoch: math.MaxInt64},
		{name: "terminal revoke retry", current: registry.Consent{Epoch: math.MaxInt64, RevokedThrough: math.MaxInt64}, epoch: math.MaxInt64, noop: true},
		{name: "reserve revoke epoch", current: registry.Consent{Epoch: math.MaxInt64 - 1}, enable: true, bad: true},
		{name: "terminal enable refused", current: registry.Consent{Epoch: math.MaxInt64, RevokedThrough: math.MaxInt64}, enable: true, bad: true},
		{name: "negative cannot be noop", current: registry.Consent{Epoch: -1, RevokedThrough: math.MaxInt64}, bad: true},
		{name: "unrevoked terminal", current: registry.Consent{Epoch: math.MaxInt64}, bad: true},
		{name: "invalid terminal state", current: registry.Consent{Epoch: math.MaxInt64, Enabled: true}, bad: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			step, e := control.PlanSummaryConsent(tc.current, tc.enable)
			if tc.bad {
				if e == nil {
					t.Fatal("unsafe transition accepted", step)
				}
				return
			}
			if e != nil || step.Epoch != tc.epoch || step.NoOp != tc.noop {
				t.Fatal("wrong transition", step, e)
			}
		})
	}
}

func TestSummaryConsentTransitionRejectsCorruptStates(t *testing.T) {
	for _, c := range []registry.Consent{{Epoch: 1, RevokedThrough: -1}, {Epoch: 1, RevokedThrough: 2}, {Enabled: true}, {Epoch: 2, Enabled: true, RevokedThrough: 2}} {
		for _, enable := range []bool{false, true} {
			if _, e := control.PlanSummaryConsent(c, enable); e == nil {
				t.Fatal("corrupt consent admitted", c)
			}
		}
	}
	if step, e := control.PlanSummaryConsent(registry.Consent{}, true); e != nil || step.Epoch != 1 || step.NoOp {
		t.Fatal("first enable refused", step, e)
	}
	if step, e := control.PlanSummaryConsent(registry.Consent{Epoch: 2, RevokedThrough: 2}, true); e != nil || step.Epoch != 3 || step.NoOp {
		t.Fatal("regrant lost monotone cutoff", step, e)
	}
}
