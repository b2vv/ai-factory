package main

import (
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestOperatorDeferredAndInvalidExitCodes(t *testing.T) {
	if mode := os.Getenv("FACTORY_SYNTHETIC_OPERATOR_EXIT_CASE"); mode != "" {
		os.Args = []string{"migration-operator"}
		if mode == "deferred" {
			os.Args = append(os.Args, "-to", "0", "-ack-derived-data-removal", "-exclusive-window", "-state", os.Getenv("FACTORY_SYNTHETIC_STATE"))
		} else {
			os.Args = append(os.Args, "-invalid-fixture-option")
		}
		main()
		return
	}
	for _, tc := range []struct {
		mode string
		code int
	}{{"deferred", 2}, {"invalid", 1}} {
		t.Run(tc.mode, func(t *testing.T) {
			state := filepath.Join(t.TempDir(), "must-remain-absent")
			cmd := exec.Command(os.Args[0], "-test.run=^TestOperatorDeferredAndInvalidExitCodes$")
			cmd.Env = append(os.Environ(), "FACTORY_SYNTHETIC_OPERATOR_EXIT_CASE="+tc.mode, "FACTORY_SYNTHETIC_STATE="+state)
			out, err := cmd.CombinedOutput()
			var exit *exec.ExitError
			if !errors.As(err, &exit) || exit.ExitCode() != tc.code {
				t.Fatalf("exit contract: %v %s", err, out)
			}
			if tc.mode == "deferred" && !strings.Contains(string(out), errBackupDeferred.Error()) {
				t.Fatal("unrelated refusal", string(out))
			}
			if _, err := os.Stat(state); !os.IsNotExist(err) {
				t.Fatal("refusal touched state", err)
			}
		})
	}
}
