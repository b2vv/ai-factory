package api_test

import (
	"aifactory.local/storage/internal/archive"
	"net/url"
	"testing"
)

func TestRecentSinceRejectsUnrepresentableUTC(t *testing.T) {
	ts, _, _, _ := captureServer(t, archive.NewMemStore(), nil)
	for _, since := range []string{"9999-12-31T23:59:59-01:00", "0000-01-01T00:00:00+01:00", "not-time"} {
		code, _ := agentQuery(t, ts.URL, "/v1/search/query?project=p&sort=recent&since="+url.QueryEscape(since), "none", "1", "none")
		if code != 400 {
			t.Fatalf("unrepresentable since %q: %d", since, code)
		}
	}
}
