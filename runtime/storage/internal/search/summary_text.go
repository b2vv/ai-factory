package search

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/summary"
	"fmt"
	"strings"
)

func tokenBoundaries(text string) string { return strings.ReplaceAll(text, "\x00", " ") }

// ProjectionText is rebuildable term input, never a new source payload. Marked
// summaries index literal excerpt text rather than their proof wrapper. NUL is a
// token boundary because PostgreSQL text cannot carry it. This structural helper
// does not establish current consent or covered-source facts; the gate does that.
func ProjectionText(e archive.Envelope) (string, error) {
	if len(e.Record.Text) > MaxTextBytes {
		return "", fmt.Errorf("search: input exceeds bounded record limit")
	}
	if e.Metadata.DerivedKind == "" {
		return tokenBoundaries(e.Record.Text), nil
	}
	stored, err := summary.DecodeStored(e)
	if err != nil {
		return "", err
	}
	parts := make([]string, 0, len(stored.Document.Excerpts))
	for _, excerpt := range stored.Document.Excerpts {
		parts = append(parts, excerpt.Text)
	}
	return tokenBoundaries(strings.Join(parts, "\n")), nil
}
