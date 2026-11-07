# Read-only archive search client

Optional `search-client` source component. This does not install a route, create a
grant, change capture, or prove native agent invocation. Python standard library;
no storage/operator/capture component is required by the client itself.

## Configuration and access

Only adjacent `search-routes.json` maps an alias to a project, expected search
principal, explicit credential format and loopback port. The example is deliberately
non-runnable. Local configuration and credentials must stay outside this portable
source/package. After explicit installation, create the configuration through the
normal authorized setup process, using only an existing verified search-only grant.
A JSON file shape or a historical principal name does not prove current rights.

Each route has `project_id`, `principal_id`, `port`, and `credential_format`:

- `json`: exactly one `credential_file` pointing to JSON with `principal_id`,
  positive int64 `epoch` and `secret`. Principal must match the route.
- `split`: exactly `secret_file` and `epoch_file`; the expected principal is in the
  route. Both files must already belong to that same verified search binding.
  Each accepts at most one trailing LF or CRLF. Other whitespace is rejected.
  Epoch is ASCII decimal digits, value 1..9223372036854775807. Secret is 16..4096
  printable non-space ASCII characters. JSON secrets use the same value limits.

No format/path fallback, copying of secrets, key creation or retry after denial
exists. Split files are read separately, not as an atomic rotation snapshot. A
concurrent rotation may cause a denied request; stop and re-establish the binding
through its authorized setup, never try another credential automatically.

Configuration must be an owned regular file, not writable by group/others.
Secrets and JSON credentials must additionally have no group/other permissions
(0600 or 0400). A split epoch is public grant-version metadata: it may be readable
by group/others (0644), but must remain owned and not writable by them.
All configured path components are opened without following symlinks. Paths must
be absolute and canonical, without `..`. JSON/split shapes cannot be mixed.

The client is an ordinary same-user process, not a privileged broker or independent
server authentication. It assumes the intended service owns its configured loopback
port. Credential access denied by the harness remains denied: stop that action and
resolve the supported approval/setup path. Never substitute a capture, operator or
foreign-project key. This helper is not a way to disguise a denied operation.

## Command and result contract

After explicit installation and verified binding only:

    python3 -I /absolute/installed/client/archive_search.py courses 'staff tidy'

An optional `--cursor` resumes the same project/query. No URL, method, credential
path, header, proxy or environment-variable override is accepted. HTTP is only to
the configured `127.0.0.1` port and `/v1/search/query`; redirects and proxy variables
are not used. A loopback address assumes the intended local service owns that port;
it is not independent server authentication.

`X-Principal-Id`, `X-Grant-Epoch`, and `X-Secret` are built in process memory. Secrets
are not passed in subprocess arguments, URLs, logs or reports. The client creates
no subprocess and writes no credential copy. It rejects a known credential echoed
verbatim in a successful response; it is not a general archive-content secret scanner.

Queries are transmitted unchanged using URL encoding. PostgreSQL `simple` parsing
ANDs query lexemes. Quotation marks are not a phrase operator. ASCII hyphen compounds,
numeric negative-looking lexemes and Unicode dashes differ. Do not silently turn
hyphens into spaces or claim that all multiword queries fail.

Output is one strict JSON object:

- Exit 0 / `status=exhausted`: terminal cursor reached in this live traversal.
- Exit 2 / `status=incomplete`: page, network-time or byte budget reached.
- Exit 1 / `status=error`: denied/unavailable route, credential mismatch, HTTP error,
  network failure, malformed response, cursor cycle or other explicit refusal.
- `hits` and `snippets` contain only validated, completed pages; `returned_count`
  counts returned hit occurrences, not an exact global total or unique-message count.
- `pages` counts completed pages. `next_cursor` points after the last completed page
  (or is the caller's validated starting cursor when none completed). It can be reused
  with the same project/query. A failing/oversized page is not silently skipped.
- `traversal_complete` never means complete capture, current indexing or a snapshot.
  `capture_completeness` and `index_freshness` remain `unknown`; `total_exact=false`.

The network traversal budget is 20 pages / 15 seconds, with at most 4 seconds for
one request, 16 MiB per page and 32 MiB across response bodies. These are transport
budgets, not a whole-process memory/CPU guarantee. File lookup, parsing and output
are bounded separately by input sizes; there is no background daemon or retry loop.
Empty intermediate pages are followed. 401/403 and redirects are not retried.

Strict UTF-8 JSON is required. Duplicate keys, NaN/Infinity, overflowed floating
numbers, unpaired surrogates, raw control characters and malformed/truncated HTTP
framing fail closed. No `strict=False`, `unicode_escape` or manual unescaping exists.
Standard escaped newlines round-trip as ordinary text. HTTP errors are reported
without echoing response bodies or low-level exception details.

## Verification and boundaries

Run `python3 -B -m unittest discover -s runtime/storage/deploy/search-client -p
 test_archive_search.py -v` from the source root (join the displayed command onto
one line), or use `python3 -B -m unittest -v test_archive_search` in this directory.
The aggregate fixture runner includes this suite when the component is present.
Tests use temporary synthetic private files and ephemeral loopback servers, never
production credentials, the storage databases or port 8780.

Wire validation requires string Provider, SourceInstance, SessionID, MessageID,
ParentID and Text for every project-scoped hit. Empty legacy strings are allowed;
they do not imply provenance or parent completeness. Snippets must reference a hit's
four-part identity and supply text/basis strings and match/truncated booleans.
Unknown optional server fields remain data, not instructions or authority.

Fixture success proves helper behavior only. Package integrity, installation,
current search-only authorization, live own-project HTTP search and native agent
invocation are separate gates. No credentials, host routes, server changes, hook
trust or rollout are enabled by shipping this component. No exact global total,
complete historical absence, freshness or complete capture is inferred from a
terminal cursor or a zero-hit result.
