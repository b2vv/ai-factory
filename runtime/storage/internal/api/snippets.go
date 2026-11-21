package api

import "aifactory.local/storage/internal/archive"

type snippetReference struct {
	Identity string `json:"identity"`
	archive.Snippet
}

func sourceSnippets(records []archive.Record, query string, tokenized bool) []snippetReference {
	out := make([]snippetReference, 0, len(records))
	for _, r := range records {
		out = append(out, snippetReference{Identity: archive.IdentityKey(r), Snippet: archive.MakeSnippet(r.Text, query, tokenized)})
	}
	return out
}
