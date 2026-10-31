package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/capture"
	"aifactory.local/storage/internal/registry"
	"bytes"
	"io"
	"net/http"
	"strings"
	"testing"
)

func TestImportSafetyHTTPAllOrNothingAndBodyBound(t *testing.T) {
	store := archive.NewMemStore()
	ts, _, ing, ctl := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if err := ctl.MintProject(op, "p", "p"); err != nil {
		t.Fatal(err)
	}
	if _, err := ctl.SetConsent(op, "p", "claude-code", "capture", true); err != nil {
		t.Fatal(err)
	}
	post := func(body string) (int, string) {
		req, err := http.NewRequest(http.MethodPost, ts.URL+"/v1/capture/claude-code?project=p&source_instance=i", bytes.NewBufferString(body))
		if err != nil {
			t.Fatal(err)
		}
		for k, v := range opHdr() {
			req.Header.Set(k, v)
		}
		res, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer res.Body.Close()
		b, err := io.ReadAll(res.Body)
		if err != nil {
			t.Fatal(err)
		}
		return res.StatusCode, string(b)
	}
	good := `{"type":"user","uuid":"m","sessionId":"s","message":{"role":"user","content":[{"type":"text","text":"password=synthetic-embedded-canary"}]}}`
	for _, body := range []string{good + "\n" + `{"type":"unsupported-canary"}`, good + strings.Repeat(" ", 8<<20)} {
		code, response := post(body)
		if code != 400 {
			t.Fatalf("want400 got%d", code)
		}
		if strings.Contains(response, "canary") {
			t.Fatal("error echoed payload")
		}
		if len(store.All("p")) != 0 || ing.AcceptedBytes() != 0 {
			t.Fatal("partial acceptance of refused batch")
		}
	}
	code, response := post(good)
	if code != 200 || strings.Contains(response, "synthetic-embedded-canary") {
		t.Fatal("sanitized capture failed")
	}
	records := store.All("p")
	if len(records) != 1 || records[0].Text != capture.RedactedText {
		t.Fatal("archive has unsanitized content")
	}
	before := ing.AcceptedBytes()
	code, _ = post(good)
	if code != 200 || ing.AcceptedBytes() != before || len(store.All("p")) != 1 {
		t.Fatal("sanitized retry not idempotent")
	}
}
