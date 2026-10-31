package backup

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func writeExpiryFixture(t *testing.T, dir, name string, created time.Time) {
	t.Helper()
	raw, e := json.Marshal(Snapshot{Version: 1, Created: created, Projects: []Project{}})
	if e != nil {
		t.Fatal(e)
	}
	blob, e := json.Marshal(envelope{SHA256: digest(raw), Payload: raw})
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(dir, name), blob, 0600); e != nil {
		t.Fatal(e)
	}
}
func TestExpiryVerifiedTimestampBoundaryAndBudgetRecovery(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "backups")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	now := time.Now().UTC()
	writeExpiryFixture(t, dir, "old.backup", now.Add(-31*24*time.Hour))
	writeExpiryFixture(t, dir, "boundary.backup", now.Add(-30*24*time.Hour))
	writeExpiryFixture(t, dir, "new.backup", now)
	// A misleading recent mtime cannot preserve an expired backup; old mtimes do
	// not authorize deleting a current backup.
	os.Chtimes(filepath.Join(dir, "old.backup"), now, now)
	os.Chtimes(filepath.Join(dir, "new.backup"), now.Add(-90*24*time.Hour), now.Add(-90*24*time.Hour))
	if e := os.WriteFile(filepath.Join(dir, "unrecognized"), []byte("preserve"), 0600); e != nil {
		t.Fatal(e)
	}
	r, e := OpenRepository(dir, 1<<20, 0)
	if e != nil {
		t.Fatal(e)
	}
	defer r.Close()
	before, e := r.usage()
	if e != nil {
		t.Fatal(e)
	}
	result, e := r.Expire(now)
	if e != nil {
		t.Fatal(e)
	}
	if len(result.Removed) != 1 || result.Removed[0] != "old.backup" || len(result.Retained) != 2 {
		t.Fatal(result)
	}
	after, e := r.usage()
	if e != nil || after >= before {
		t.Fatal("budget not freed", before, after, e)
	}
	if raw, e := os.ReadFile(filepath.Join(dir, "unrecognized")); e != nil || string(raw) != "preserve" {
		t.Fatal("unknown file changed", e)
	}
	result, e = r.Expire(now)
	if e != nil || len(result.Removed) != 0 {
		t.Fatal("repeat", result, e)
	}
}
func TestExpiryCorruptionFutureAndSymlinkRefuseBeforeDeletion(t *testing.T) {
	for _, fault := range []string{"corrupt", "future", "symlink"} {
		t.Run(fault, func(t *testing.T) {
			dir := filepath.Join(t.TempDir(), "backups")
			os.Mkdir(dir, 0700)
			now := time.Now().UTC()
			writeExpiryFixture(t, dir, "a-old.backup", now.Add(-31*24*time.Hour))
			switch fault {
			case "corrupt":
				os.WriteFile(filepath.Join(dir, "z-bad.backup"), []byte("invalid"), 0600)
			case "future":
				writeExpiryFixture(t, dir, "z-bad.backup", now.Add(time.Hour))
			case "symlink":
				os.Symlink("a-old.backup", filepath.Join(dir, "z-bad.backup"))
			}
			r, e := OpenRepository(dir, 1<<20, 0)
			if e != nil {
				t.Fatal(e)
			}
			defer r.Close()
			result, e := r.Expire(now)
			if e == nil || len(result.Removed) != 0 {
				t.Fatal("unsafe partial expiry", result, e)
			}
			if _, e = os.Stat(filepath.Join(dir, "a-old.backup")); e != nil {
				t.Fatal("deleted before complete validation", e)
			}
		})
	}
}
