// Package logical defines the versioned logical-v1 billing representations.
// These are not PostgreSQL/Mongo allocator sizes or filesystem allocation quotas.
package logical

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
)

func size(v any) int64 {
	b, e := json.Marshal(v)
	if e != nil {
		panic("logical-v1 scalar representation failed")
	}
	return int64(len(b))
}
func Workflow(project, id string, version int64, fields map[string]string) int64 {
	row := struct {
		Project string
		Task    struct {
			ID      string
			Version int64
			Fields  map[string]string
		}
	}{Project: project}
	row.Task.ID = id
	row.Task.Version = version
	row.Task.Fields = fields
	return size(row) + size([]string{project, id})
}
func Canonical(raw []byte) (json.RawMessage, error) {
	var v any
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	if e := d.Decode(&v); e != nil {
		return nil, e
	}
	var extra any
	if e := d.Decode(&extra); e != io.EOF {
		return nil, fmt.Errorf("logical-v1: trailing JSON")
	}
	b, e := json.Marshal(v)
	return b, e
}
func ArchiveIndex(key, projectHash, project, identity, payload, terms string, lexemes []string) int64 {
	row := struct{ Key, ProjectHash, Project, Identity, PayloadHash, Terms string }{key, projectHash, project, identity, payload, terms}
	total := size(row) + size(key) + size([]string{projectHash, key})
	// One logical posting per lexeme; positions/weights live in the complete row
	// term-vector representation and are not silently omitted from the inventory.
	for _, word := range lexemes {
		total += size([]string{word, key})
	}
	return total
}
func DocumentIndex(key, projectHash, project, identity string, data []byte) (int64, error) {
	canonical, e := Canonical(data)
	if e != nil {
		return 0, e
	}
	row := struct {
		Key, ProjectHash, Project, Identity string
		Data                                json.RawMessage
	}{key, projectHash, project, identity, canonical}
	return size(row) + size(key) + size([]string{projectHash, key}), nil
}
func Add(total, value, limit int64) (int64, error) {
	if value < 0 || total < 0 || total > limit || value > limit-total {
		return 0, fmt.Errorf("logical-v1: inventory exceeds bounded cap")
	}
	return total + value, nil
}

// ArchiveMetadata extends the unchanged v1 projection representation. It bills
// the metadata fields and every declared ordinal/time index entry plus row key.
func ArchiveMetadata(key, projectHash, project, generation, metadataHash string, ordinal int64, captured, event *string) int64 {
	row := struct {
		MetadataHash, SourceGeneration string
		SourceOrdinal                  int64
		CapturedKey, SourceTimeKey     *string
	}{metadataHash, generation, ordinal, captured, event}
	total := size(row) + size([]any{projectHash, project, generation, ordinal, key})
	for _, v := range []*string{captured, event} {
		if v != nil {
			total += size([]string{projectHash, generation, *v, key})
		}
	}
	return total
}
func ArchiveCheckpoint(projectHash, project, sourceGeneration, projectionGeneration, policy string, ordinal int64, complete bool) int64 {
	row := struct {
		ProjectHash, Project, SourceGeneration, ProjectionGeneration, PolicyRevision string
		Ordinal                                                                      int64
		Complete                                                                     bool
	}{projectHash, project, sourceGeneration, projectionGeneration, policy, ordinal, complete}
	return size(row) + size(projectHash)
}
