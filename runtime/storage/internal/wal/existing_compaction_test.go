package wal

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func TestExistingOpenResumesEveryCompactionRenameBoundary(t *testing.T) {
	for _, empty := range []bool{false, true} {
		for boundary := 0; boundary <= len(journalFiles); boundary++ {
			t.Run(fmt.Sprintf("empty_%v_boundary_%d", empty, boundary), func(t *testing.T) {
				dir := t.TempDir()
				acceptN(t, dir, 3)
				original := installGeneration
				installGeneration = func(d string) error {
					for _, name := range journalFiles[:boundary] {
						if err := os.Rename(filepath.Join(d, compactStaging, name), filepath.Join(d, name)); err != nil {
							return err
						}
					}
					return errFault
				}
				_, err := Compact(dir, func(k string, _ []byte) bool { return !empty && k == "k2" })
				installGeneration = original
				if err == nil {
					t.Fatal("fault not injected")
				}
				w, err := OpenExisting(dir)
				if err != nil {
					t.Fatal(err)
				}
				w.Close()
				got := acceptedKeys(t, dir)
				if empty {
					if len(got) != 0 {
						t.Fatal(got)
					}
				} else if len(got) != 1 || got["k2"] != "payload-2" {
					t.Fatal(got)
				}
			})
		}
	}
}
func TestExistingOpenPreservesMissingBothTransitionEvidence(t *testing.T) {
	for _, missing := range journalFiles {
		t.Run(missing, func(t *testing.T) {
			dir := t.TempDir()
			acceptN(t, dir, 3)
			original := installGeneration
			installGeneration = func(string) error { return errFault }
			_, err := Compact(dir, func(k string, _ []byte) bool { return k == "k1" })
			installGeneration = original
			if err == nil {
				t.Fatal("fault not injected")
			}
			sentinel, err := os.ReadFile(filepath.Join(dir, compactSentinel))
			if err != nil {
				t.Fatal(err)
			}
			for _, path := range []string{filepath.Join(dir, missing), filepath.Join(dir, compactStaging, missing)} {
				if err := os.Remove(path); err != nil {
					t.Fatal(err)
				}
			}
			if w, err := OpenExisting(dir); err == nil {
				w.Close()
				t.Fatal("missing both accepted")
			}
			after, err := os.ReadFile(filepath.Join(dir, compactSentinel))
			if err != nil || !bytes.Equal(sentinel, after) {
				t.Fatal("sentinel destroyed", err)
			}
			for _, name := range journalFiles {
				if name != missing {
					if _, err := os.Stat(filepath.Join(dir, compactStaging, name)); err != nil {
						t.Fatal("staged evidence destroyed", name, err)
					}
				}
			}
		})
	}
}
func TestExistingOpenChecksLiveBeforeAbortedStagingCleanup(t *testing.T) {
	for _, missing := range []bool{false, true} {
		t.Run(fmt.Sprint(missing), func(t *testing.T) {
			dir := t.TempDir()
			acceptN(t, dir, 2)
			staging := filepath.Join(dir, compactStaging)
			if err := os.Mkdir(staging, 0700); err != nil {
				t.Fatal(err)
			}
			for _, name := range journalFiles {
				raw, err := os.ReadFile(filepath.Join(dir, name))
				if err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(filepath.Join(staging, name), raw, 0600); err != nil {
					t.Fatal(err)
				}
			}
			if missing {
				if err := os.Remove(filepath.Join(dir, "data")); err != nil {
					t.Fatal(err)
				}
			}
			w, err := OpenExisting(dir)
			if missing {
				if err == nil {
					w.Close()
					t.Fatal("aborted stage substituted for missing live")
				}
				if _, err := os.Stat(filepath.Join(staging, "data")); err != nil {
					t.Fatal("aborted evidence destroyed", err)
				}
			} else {
				if err != nil {
					t.Fatal(err)
				}
				w.Close()
				if len(acceptedKeys(t, dir)) != 2 {
					t.Fatal("original changed")
				}
			}
		})
	}
}

func TestExistingOpenRejectsNonregularEvidenceBeforeCleanup(t *testing.T) {
	for _, name := range []string{compactSentinel, compactStaging, "data", "accepts"} {
		for _, kind := range []string{"directory", "symlink"} {
			t.Run(name+kind, func(t *testing.T) {
				dir := t.TempDir()
				acceptN(t, dir, 1)
				path := filepath.Join(dir, name)
				if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
					t.Fatal(err)
				}
				if kind == "directory" {
					if name == compactStaging {
						if err := os.WriteFile(path, []byte("not a directory"), 0600); err != nil {
							t.Fatal(err)
						}
					} else {
						if err := os.Mkdir(path, 0700); err != nil {
							t.Fatal(err)
						}
					}
				} else {
					target := filepath.Join(t.TempDir(), "target")
					if err := os.WriteFile(target, []byte("evidence"), 0600); err != nil {
						t.Fatal(err)
					}
					if err := os.Symlink(target, path); err != nil {
						t.Fatal(err)
					}
				}
				if w, err := OpenExisting(dir); err == nil {
					w.Close()
					t.Fatal("nonregular evidence accepted")
				}
				if _, err := os.Lstat(path); err != nil {
					t.Fatal("evidence removed", err)
				}
			})
		}
	}
}
func TestExistingOpenPreservesInvalidSentinelWhenLiveMissing(t *testing.T) {
	dir := t.TempDir()
	acceptN(t, dir, 1)
	if err := os.Mkdir(filepath.Join(dir, compactStaging), 0700); err != nil {
		t.Fatal(err)
	}
	sentinel := filepath.Join(dir, compactSentinel)
	if err := os.WriteFile(sentinel, []byte("incomplete"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(filepath.Join(dir, "data")); err != nil {
		t.Fatal(err)
	}
	if w, err := OpenExisting(dir); err == nil {
		w.Close()
		t.Fatal("invalid transition accepted")
	}
	if b, err := os.ReadFile(sentinel); err != nil || string(b) != "incomplete" {
		t.Fatal("sentinel destroyed", err)
	}
	if _, err := os.Stat(filepath.Join(dir, compactStaging)); err != nil {
		t.Fatal("stage destroyed", err)
	}
}
