package capture

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestKnownCredentialsWithholdWholeText(t *testing.T) {
	for _, text := range []string{
		`before password="synthetic-canary" after`,
		`{"nested":{"client_secret":{"value":"synthetic-canary"}}}`,
		"Authorization: Bearer synthetic-canary",
		"Cookie: session=synthetic-canary",
		"connect postgres://user:synthetic-canary@local/db",
		"-----BEGIN OPENSSH PRIVATE KEY-----\nsynthetic-canary\n-----END OPENSSH PRIVATE KEY-----",
		"sk-proj-0123456789abcdefghijklmnop",
		"ghp_" + "0123456789abcdefghijklmnop",
		"AKIA" + "ABCDEFGHIJKLMNOP",
		"eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c3ludGhldGlj",
		"DATABASE_PASSWORD=synthetic-canary",
	} {
		got, red := SanitizeText(text)
		if !red || got != RedactedText {
			t.Fatalf("pattern not withheld (input omitted)")
		}
		again, _ := SanitizeText(got)
		if again != got {
			t.Fatal("not idempotent")
		}
	}
	safe := "Discuss password rotation without including a value."
	if got, red := SanitizeText(safe); red || got != safe {
		t.Fatal("ordinary prose changed")
	}
}

func TestClaudeUnsupportedBatchHasNoPartialRecordsOrInputInErrors(t *testing.T) {
	valid := `{"type":"user","uuid":"u","sessionId":"s","message":{"role":"user","content":[{"type":"text","text":"ok"}]}}`
	for _, bad := range []string{
		`{"type":"future-secret-canary"}`,
		`{"type":"user","uuid":"u","sessionId":"s","message":{"role":"user","content":"secret-canary"}}`,
		`{"type":"user","message":{"role":"user","content":[{"type":"text","text":"secret-canary"}]}}`,
		`{"type":"user","uuid":"u","sessionId":"s","message":{"role":"assistant","content":[{"type":"text","text":"secret-canary"}]}}`,
		`{"type":"user","uuid":"u","sessionId":"s","message":{"role":"user","content":[{"type":"future-secret-canary"}]}}`,
		`{"type":"user","uuid":"u","sessionId":"s","message":{"role":"user","content":null}}`,
	} {
		recs, red, err := AdaptClaudeCodeJSONL([]byte(valid+"\n"+bad), "p", "i")
		if err == nil || recs != nil || red != nil {
			t.Fatal("unsupported batch did not fail atomically")
		}
		if strings.Contains(err.Error(), "secret-canary") {
			t.Fatal("error echoed input")
		}
	}
}

func TestClaudeCredentialsAcrossBlocksAreWithheld(t *testing.T) {
	line := map[string]any{"type": "user", "uuid": "u", "sessionId": "s", "message": map[string]any{"role": "user", "content": []map[string]string{{"type": "text", "text": "password:"}, {"type": "text", "text": "synthetic-canary"}}}}
	b, _ := json.Marshal(line)
	recs, red, err := AdaptClaudeCodeJSONL(b, "p", "i")
	if err != nil || len(recs) != 1 || recs[0].Text != RedactedText || len(red) != 1 {
		t.Fatal("joined text was not sanitized")
	}
}
