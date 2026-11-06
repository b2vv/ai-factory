package archive_test

import (
	"aifactory.local/storage/internal/archive"
	"strings"
	"testing"
	"unicode/utf8"
)

func TestSnippetCentersUnicodeMatchWithoutRewritingSource(t *testing.T) {
	for _, pair := range [][2]string{{"Stra\u00dfe", "STRASSE"}, {"e\u0301cho", "\u00c9CHO"}, {"\U0001f642needle", "NEEDLE"}} {
		text := strings.Repeat("before ", 200) + pair[0] + strings.Repeat(" after", 200)
		s := archive.MakeSnippet(text, pair[1], false)
		if !s.Match || !s.Truncated || !strings.Contains(s.Text, pair[0]) || utf8.RuneCountInString(s.Text) > 240 || !utf8.ValidString(s.Text) {
			t.Fatal(s)
		}
	}
	text := strings.Repeat("before ", 200) + "needle" + strings.Repeat(" after", 200)
	if s := archive.MakeSnippet(text, "missing NEEDLE", true); !s.Match || !strings.Contains(s.Text, "needle") || s.Basis != "query_fragment" {
		t.Fatal(s)
	}
	if s := archive.MakeSnippet(text, "missing NEEDLE", false); s.Match || s.Basis != "prefix_no_literal_match" {
		t.Fatal(s)
	}
	if s := archive.MakeSnippet("original", "", false); s.Text != "original" || s.Match || s.Truncated || s.Basis != "prefix_empty_query" {
		t.Fatal(s)
	}
}
