package backup

import (
	"path/filepath"
	"testing"
)

// privateTempDir returns t.TempDir() with symlinks resolved. OpenRepository
// refuses a directory reached through a symlink, and on macOS the default
// temp root (/var/folders/...) is itself under the /var -> /private/var alias.
func privateTempDir(t *testing.T) string {
	t.Helper()
	dir, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	return dir
}
