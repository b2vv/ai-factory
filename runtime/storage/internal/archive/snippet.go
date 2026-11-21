package archive

import (
	"golang.org/x/text/unicode/norm"
	"strings"
	"unicode/utf8"
)

type Snippet struct {
	Text      string `json:"text"`
	Match     bool   `json:"match"`
	Truncated bool   `json:"truncated"`
	Basis     string `json:"basis"`
}

// MakeSnippet returns original source runes, never index text or normalized
// replacement text. Match locates a literal query (or one token-query fragment),
// not a claim that every token is visible inside the bounded excerpt.
func MakeSnippet(text, query string, tokenized bool) Snippet {
	needles := []string{query}
	basis := "literal_match"
	if tokenized {
		needles = strings.Fields(query)
		basis = "query_fragment"
	}
	normalized := normalizedQueryText(text)
	at := -1
	for _, needle := range needles {
		needle = normalizedQueryText(needle)
		if needle == "" {
			continue
		}
		position := strings.Index(normalized, needle)
		if position >= 0 && (at < 0 || position < at) {
			at = position
		}
	}
	center := 0
	if at >= 0 {
		var iter norm.Iter
		iter.InitString(norm.NFC, text)
		normalizedOffset := 0
		for !iter.Done() {
			originalOffset := iter.Pos()
			segment := iter.Next()
			size := len(normalizedQueryText(string(segment)))
			if at < normalizedOffset+size {
				center = utf8.RuneCountInString(text[:originalOffset])
				break
			}
			normalizedOffset += size
		}
	} else {
		basis = "prefix_no_literal_match"
		if query == "" {
			basis = "prefix_empty_query"
		}
	}
	runes := []rune(text)
	start := center - 120
	if start < 0 {
		start = 0
	}
	end := start + 240
	if end > len(runes) {
		end = len(runes)
	}
	return Snippet{Text: string(runes[start:end]), Match: at >= 0, Truncated: start > 0 || end < len(runes), Basis: basis}
}
