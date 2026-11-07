package archive

import "testing"

func TestQueryUnicodeNormalizationPreservesOriginal(t *testing.T) {
	// Exercise Greek/Latin casefolding and decomposed Unicode normalization.
	original := "Factory \u0399\u0308\u0396\u0391 CAF\u00c9 Stra\u00dfe"
	r := Record{Project: "p", Provider: "synthetic", SourceInstance: "instance", SessionID: "s", MessageID: "m", Text: original}
	for _, q := range []string{"factory", "\u03ca\u03b6\u03b1", "cafe\u0301", "STRASSE"} {
		hits := Query([]Record{r}, q, "synthetic")
		if len(hits) != 1 || hits[0].Text != original || IdentityKey(hits[0].Record) != IdentityKey(r) {
			t.Fatalf("query %q changed or lost original: %+v", q, hits)
		}
	}
	for _, q := range []string{"factory food", ".*", "cafes"} {
		if hits := Query([]Record{r}, q, ""); len(hits) != 0 {
			t.Fatalf("literal substring became tokenized/stemmed/regex for %q", q)
		}
	}
	if hits := Query([]Record{r}, "factory", "SYNTHETIC"); len(hits) != 0 {
		t.Fatal("metadata identity was normalized")
	}
}
