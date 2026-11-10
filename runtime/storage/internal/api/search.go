package api

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"sort"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/documents"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/retention"
	"aifactory.local/storage/internal/search"
)

func (s *Server) SetSearchStore(store *search.Store) {
	s.searchStore = store
	if store != nil {
		s.searchRequired = true
	}
	s.indexAfter = map[string]*archive.Position{}
}

// IndexOnce rebuilds one bounded slice of one project's derived index. It never
// changes archive commitment or workflow authority. Restart resets only the scan
// position: idempotent upserts rebuild from authoritative Mongo, without WAL
// retention depending on PG availability. Privacy mutations share this fence.
func (s *Server) IndexOnce() (int, error) {
	if s.searchStore == nil || s.ing == nil {
		return 0, nil
	}
	if s.measure == nil {
		return 0, fmt.Errorf("index: capacity metering unavailable")
	}
	base := s.reservationTotal()
	usage, measureErr := s.measure()
	if measureErr != nil {
		s.indexFailed.Store(true)
		return 0, measureErr
	}
	s.mutate.Lock()
	defer s.mutate.Unlock()
	count := 0
	projects := s.ctl.Registry().Projects()
	sort.Strings(projects)
	if len(projects) == 0 {
		return 0, nil
	}
	project := projects[s.indexProject%len(projects)]
	s.indexProject = (s.indexProject + 1) % len(projects)
	e := s.ctl.WithArchiveWriter(s.operatorPrincipal(), project, func(tx *control.ArchiveTransaction) error {
		if tx != nil {
			state, err := tx.State()
			if err != nil {
				return err
			}
			if !state.MigrationComplete {
				return search.ErrCheckpoint
			}
			source, ok := s.ing.Store().(search.MetadataSource)
			if !ok {
				return search.ErrCheckpoint
			}
			count, err = s.searchStore.ProjectArchiveWithGate(tx, source, s.publishEnvelopeGate(tx))
			return err
		}
		window, e := s.ing.Store().Scan(project, s.indexAfter[project])
		if e != nil {
			return e
		}
		for n, r := range window.Records {
			if n == 16 {
				return nil
			}
			if s.publishGate(r) {
				matches, checkErr := s.searchStore.Matches(r)
				if checkErr != nil {
					return checkErr
				}
				if matches && s.ctl.Budget() != nil {
					pending := s.ctl.Budget().Snapshot().Pending
					if len(pending) == 1 && pending[0].Evidence == search.IndexEvidence(r) {
						if e = s.ctl.ReserveIdentifiedExternal(search.IndexEvidence(r), 0); e != nil {
							return e
						}
						if e = s.ctl.FinishExternal(); e != nil {
							return e
						}
					}
				}
				if !matches {
					cost, costErr := s.searchStore.ReservationBytes(r)
					if costErr != nil {
						return costErr
					}
					eff := usage
					delta := s.reservationTotal() - base
					if s.ing != nil {
						delta += s.ing.PendingArchiveBytes()
					}
					eff.LiveBytes += delta
					eff.FreeBytes -= delta
					eff.WALBytes = 0
					if admit := config.NewAccountant(s.cfg).AdmitGrowth(eff, 0, cost); !admit.Allowed {
						return fmt.Errorf("index: %s", admit.Reason)
					}
					// Encoded growth reservation is conservative on ambiguous errors; it is
					// not a proof of the separately open physical DB allocation cap.
					if e = s.ctl.ReserveIdentifiedExternal(search.IndexEvidence(r), cost); e != nil {
						return e
					}
					e = s.searchStore.Put(r)
					if e == nil {
						e = s.ctl.FinishExternal()
					}
				}
			} else {
				e = s.searchStore.Delete(r)
			}
			if e != nil {
				return e
			}
			pos := archive.PositionOf(r)
			s.indexAfter[project] = &pos
			count++
		}
		if !window.More {
			s.indexAfter[project] = nil
		}
		return nil
	})
	s.indexFailed.Store(e != nil)
	return count, e
}
func sourceIdentity(raw, project string) (archive.Record, error) {
	var fields []string
	if e := json.Unmarshal([]byte(raw), &fields); e != nil || len(fields) != 4 || fields[0] != project {
		return archive.Record{}, fmt.Errorf("invalid scoped source identity")
	}
	return archive.Record{Project: fields[0], SourceInstance: fields[1], SessionID: fields[2], MessageID: fields[3]}, nil
}
func (s *Server) handleSearchQuery(w http.ResponseWriter, r *http.Request) {
	if r.URL.Query().Has("sort") || r.URL.Query().Has("since") || r.URL.Query().Has("time_field") {
		s.handleRecentSearch(w, r)
		return
	}
	if r.Method != http.MethodGet {
		writeErr(w, 405, "GET required")
		return
	}
	if s.searchStore == nil || s.ing == nil {
		writeErr(w, 503, "derived archive index is not enabled")
		return
	}
	project, query := r.URL.Query().Get("project"), r.URL.Query().Get("q")
	after, cursorErr := s.indexContinuation(r, project, query, "derived-archive")
	if cursorErr != nil {
		writeErr(w, 400, cursorErr.Error())
		return
	}
	if project == "" || len(query) > 4096 {
		writeErr(w, 400, "project and bounded query required")
		return
	}
	if after != "" {
		if _, e := hex.DecodeString(after); e != nil || len(after) != 64 {
			writeErr(w, 400, "invalid continuation")
			return
		}
	}
	if e := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpSearch); e != nil {
		writeErr(w, 403, e.Error())
		return
	}
	refs, next, e := s.searchStore.Window(project, query, after)
	records := []archive.Record{}
	prepared := map[string]preparedSummary{}
	summarySeen := false
	used := 0
	// Source validation happens before the final authority fence. Never serve the
	// index's text or treat a missing/changed source as authoritative content.
	if e == nil {
		for n, ref := range refs {
			identity, err := sourceIdentity(ref.Identity, project)
			if err != nil {
				e = err
				break
			}
			actual, found, err := s.ing.Store().Lookup(identity)
			if err != nil {
				e = err
				break
			}
			if found && search.RecordHash(actual) == ref.PayloadHash {
				if actual.Type == archive.TypeSummary && summarySeen {
					next = refs[n-1].Key
					break
				}
				raw, err := json.Marshal(actual)
				if err != nil {
					e = err
					break
				}
				if len(raw) > archive.ScanBytes {
					e = archive.ErrRecordTooLarge
					break
				}
				if used+len(raw) > archive.ScanBytes {
					next = refs[n-1].Key
					break
				}
				used += len(raw)
				if actual.Type == archive.TypeSummary {
					summarySeen = true
					proof, err := s.prepareSummary(actual)
					if err != nil {
						e = err
						break
					}
					prepared[archive.IdentityKey(actual)] = proof
				}
				records = append(records, actual)
			}
		}
	}
	s.withArchiveWriter(w, project, func(w http.ResponseWriter, tx *control.ArchiveTransaction) {
		if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpSearch); err != nil {
			writeErr(w, 403, err.Error())
			return
		}
		if e != nil {
			writeErr(w, 503, "search index or authoritative source unavailable")
			return
		}
		visible := []archive.Record{}
		snippets := []snippetReference{}
		for _, record := range records {
			proof := prepared[archive.IdentityKey(record)]
			allowed, err := s.allowPreparedSummary(tx, record, proof)
			if err != nil {
				writeErr(w, 503, "archive authority unavailable")
				return
			}
			if allowed {
				visible = append(visible, record)
				snippets = append(snippets, preparedSnippet(record, proof, query, true))
			}
		}
		token, err := s.nextIndexCursor(project, query, "derived-archive", next)
		if err != nil {
			writeErr(w, 503, "continuation unavailable")
			return
		}
		writeJSON(w, 200, map[string]any{"project": project, "search_mode": "tokenized_simple_nfc_casefold", "hits": visible, "snippets": snippets, "next_cursor": token, "derived": true, "total_exact": false, "consistency": "live_non_snapshot"})
	})
}

func (s *Server) SetSearchRequired(required bool) { s.searchRequired = required }

func (s *Server) handleDocumentQuery(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeErr(w, 405, "GET required")
		return
	}
	if s.searchStore == nil {
		writeErr(w, 503, "document index not enabled")
		return
	}
	project := r.URL.Query().Get("project")
	after, cursorErr := s.indexContinuation(r, project, "", "document-metadata")
	if cursorErr != nil {
		writeErr(w, 400, cursorErr.Error())
		return
	}
	if project == "" {
		writeErr(w, 400, "project required")
		return
	}
	if after != "" {
		if _, e := hex.DecodeString(after); e != nil || len(after) != 64 {
			writeErr(w, 400, "invalid continuation")
			return
		}
	}
	if e := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpSearch); e != nil {
		writeErr(w, 403, e.Error())
		return
	}
	refs, next, e := s.searchStore.DocumentWindow(project, after)
	hits := []documents.Entry{}
	stale := false
	if e == nil {
		for _, ref := range refs {
			if err := search.ValidateDocument(ref); err != nil {
				stale = true
				continue
			}
			hits = append(hits, ref.Entry)
		}
	}
	s.withAuthority(w, func(w http.ResponseWriter) {
		if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpSearch); err != nil {
			writeErr(w, 403, err.Error())
			return
		}
		if e != nil {
			writeErr(w, 503, "document index unavailable")
			return
		}
		for _, b := range s.ctl.Retention().Barriers() {
			if b.Project == project && b.Scope == retention.ScopeProject {
				hits = []documents.Entry{}
				break
			}
		}
		token, err := s.nextIndexCursor(project, "", "document-metadata", next)
		if err != nil {
			writeErr(w, 503, "continuation unavailable")
			return
		}
		writeJSON(w, 200, map[string]any{"project": project, "sources": hits, "next_cursor": token, "derived_stale": stale, "search_mode": "document_metadata"})
	})
}

// Raw key hashes can reveal a guessed withheld identity. Bind encrypted cursors
// to project, query and endpoint; never expose the internal index keyset position.
func (s *Server) indexContinuation(r *http.Request, project, query, kind string) (string, error) {
	if r.URL.Query().Get("after") != "" {
		return "", fmt.Errorf("use an authenticated cursor")
	}
	raw := r.URL.Query().Get("cursor")
	if raw == "" {
		return "", nil
	}
	c, e := s.decodeCursor(raw)
	if e != nil || c.Time != nil || c.Project != project || c.Query != query || c.Provider != kind || len(c.IndexAfter) != 64 {
		return "", fmt.Errorf("invalid scoped cursor")
	}
	if _, e = hex.DecodeString(c.IndexAfter); e != nil {
		return "", fmt.Errorf("invalid cursor position")
	}
	return c.IndexAfter, nil
}
func (s *Server) nextIndexCursor(project, query, kind, next string) (string, error) {
	if next == "" {
		return "", nil
	}
	return s.encodeCursor(pageCursor{Project: project, Query: query, Provider: kind, IndexAfter: next})
}

// RecoverIndex reconciles persisted index requests before startup can create an
// unrelated marker intent. It does not start a new rebuild or scan.
func (s *Server) RecoverIndex() error {
	return s.recoverIndexContext(context.Background())
}
func (s *Server) recoverIndexContext(ctx context.Context) error {
	s.mutate.Lock()
	defer s.mutate.Unlock()
	for _, project := range s.ctl.Registry().Projects() {
		if err := ctx.Err(); err != nil {
			return err
		}
		if err := s.ctl.WithArchiveWriter(s.operatorPrincipal(), project, func(tx *control.ArchiveTransaction) error {
			if tx == nil {
				return nil
			}
			op, err := tx.RecoveryProjection()
			if err != nil || op == nil {
				return err
			}
			if s.searchStore == nil || s.ing == nil {
				return search.ErrCheckpoint
			}
			source, ok := s.ing.Store().(search.MetadataSource)
			if !ok {
				return search.ErrCheckpoint
			}
			return s.searchStore.RecoverProjectionWithGate(tx, source, s.publishEnvelopeGateContext(ctx, tx))
		}); err != nil {
			return err
		}
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if ledger := s.ctl.Budget(); ledger != nil {
		pending := ledger.Snapshot().Pending
		if len(pending) == 1 && pending[0].Evidence.Kind == "archive-index-v2" {
			return s.ctl.RecoverUnreservedArchiveIntent(s.operatorPrincipal())
		}
	}
	return nil
}
