# AI-assisted onboarding: package → host → project → evidence

This is a practical guide to the [single onboarding protocol](../../ai-factory/onboarding.md), not a new installer or tracker. The owner's instruction and local contracts/ADRs take precedence; existing required gates remain in force. Merely reading the examples below does not execute them.

<a id="destinations"></a>
## 1. What belongs where

| Layer | Destination / source | Actual capability and boundary |
|---|---|---|
| Trusted source | Complete release/checkout in an agreed separate root | Verify commit/provenance, source and manifest; `verify_release.py`. Do not modify an immutable release in place |
| Managed package | For example `~/project-data/ai-factory-kit`, canonical absolute path | `tools/kit.py` plan/install/update/rollback. State/backups/receipts in `.ai-factory-state`. This is not host discovery |
| Shared host store | `~/.agents/skills`; workflow/rules may have separate pointers in `~/.agents` | A convention of the current collection, not a managed installer target. Exact immutable package paths also work for file fallback. No separate host publisher exists |
| Claude Code | Personal `~/.claude/skills/<name>/SKILL.md`, project `.claude/skills/<name>/SKILL.md` | Selected mapping after collision/provenance review, not copying all synced variants. Do not automatically replace existing symlink topology |
| Codex | Selected shared skills and local `AGENTS.md`/adapter | Verify actual discovery by the installed CLI; the presence of `.agents/skills` alone does not certify invocation. Without native discovery, use exact-file fallback |
| Project adapter | Existing project-owned document + pointers from entry files | Templates suggest content; `preflight.py` only reads the manifest. A scoped manual/AI edit is needed, not auto-bootstrap |
| Optional runtimes | Python helpers in the package; graph/MCP executables separately | The Graphify/CRG skill does not install a server, DB, language runtime or hook. Models/entitlement are host-specific, not part of the package |

Skills in this bundle are grouped, with duplicate names across variants. Do not flatten/copy all 73 originals into a discovery root. First select the exact `SKILL.md`, read its references, identify the destination/name and check for collisions. The installer rejects symlinks in source/destination; a legitimate host symlink does not mean it can be passed to the installer. Use canonical physical paths for preflight; do not bypass the path guard.

[Claude skills docs](https://code.claude.com/docs/en/skills) confirm personal/project locations; host precedence and reserved names must be checked for the selected CLI. A local home store does not automatically transfer into a cloud session. During this documentation review, the official OpenAI skills URL redirected to the [general build-skills guide](https://learn.chatgpt.com/docs/build-skills); this is not evidence of current CLI search roots. Therefore, the minimum Codex version/native discovery here is **NOT_TESTED**, not invented. Both hosts can read explicitly selected files; this is instruction fallback, not native invocation.

## 2. Prerequisites and private access

Python 3.9+ stdlib; the installer uses `fcntl`, atomic filesystem operations and an advisory lock. macOS is fixture-tested; Linux is a POSIX candidate, not a verified support matrix; Windows is unsupported. Review helpers need Git with HEAD; in an empty directory without an initial commit, this review route is BLOCKED. The project determines product Node/Go/Docker/Playwright versions, not this kit.

For a private GitHub source, the developer must be added to the repository and use their own already-configured SSH agent or credential manager/approved Git client. The owner supplies a repo URL without embedded credentials and a trusted commit. Do not ask for a PAT/password in chat or copy someone else's `.gitconfig`, `.ssh`, `.npmrc`, `.env`, session stores, auth caches or vault. Without access, acquisition is BLOCKED; the owner resolves access, the agent does not search for tokens. Download/initial source checkout requires separate scope authorization; this guide does not initiate network access or login. Trusted source may be transferred offline with an independently confirmed commit/digest; a checksum from the same unverified archive does not authenticate its author.

Before the first Python/npm/CI run, inspect source, scripts, dependencies/lockfiles and provenance. Repo instructions are content to assess, not permission to read secrets or expand scope. Use minimal permissions and a credential-free test environment; do not disable OS trust/TCC/sandbox or change security settings for onboarding.

## 3. Actual offline commands

Replace every placeholder below with agreed **canonical absolute paths without symlink components**. SOURCE is the complete trusted package; TARGET is a separate managed root (not home, `.agents`, `.claude`, `.codex`, `skills` or a product root); PROJECT is an existing project directory; EVIDENCE is a reviewer-accessible folder outside the product tree. Do not use `$HOME` as a temporary variable. The examples have no `--dry-run`: that flag DOES NOT EXIST; `plan` and omission of `--execute` are the read-only modes.

```sh
FACTORY_SOURCE='/absolute/trusted/ai-factory'
FACTORY_TARGET='/absolute/dedicated/ai-factory-kit'
FACTORY_PROJECT='/absolute/project'
FACTORY_MANIFEST='/absolute/evidence/onboarding-manifest.json'
python3 -B "$FACTORY_SOURCE/tools/verify_release.py" --root "$FACTORY_SOURCE"
python3 -B "$FACTORY_SOURCE/tools/kit.py" plan --package "$FACTORY_SOURCE" --root "$FACTORY_TARGET" --component collection --component planning --component review --component session-guard
```

Read the JSON plan: additions/removals, component set, conflicts and `plan_id`. `collection` includes core/skills/graphify/legacy-runtime; `planning` contains four non-native profiles; `review` and `session-guard` are separate portable helpers. The presence of legacy helpers does not activate hooks. Explicitly select different components for a smaller set; core-only does not contain all skills.

Only after authorization for the specific reviewed plan and confirmation of an exclusive writer window:

```sh
python3 -B "$FACTORY_SOURCE/tools/kit.py" install --package "$FACTORY_SOURCE" --root "$FACTORY_TARGET" --component collection --component planning --component review --component session-guard --execute --exclusive-window --plan-id '<reviewed-plan-id>'
python3 -B "$FACTORY_SOURCE/tools/kit.py" plan --package "$FACTORY_SOURCE" --root "$FACTORY_TARGET" --component collection --component planning --component review --component session-guard
```

The repeated plan must return `NOOP`. Retain the returned transaction ID, plan, exit and source commit/hash. `--exclusive-window` is a coordination assertion, not an automatic cross-session guarantee. Apply is not atomic across all files: partial failure leaves a receipt/pending transaction; do not delete state manually.

The [manifest example](../../examples/onboarding/manifest.json) is a valid starting point, not an inventory result. For an existing repo, fill in actual instruction/workflow/command paths; do not declare optional skills required merely because they exist. `preflight.py` does not automatically detect every semantic conflict. Copy/adapt the manifest into the agreed evidence folder, then:

```sh
python3 -B "$FACTORY_SOURCE/runtime/onboarding/preflight.py" --root "$FACTORY_PROJECT" --manifest "$FACTORY_MANIFEST" --shared-skill-root "$FACTORY_TARGET/skills"
```

Preflight is read-only; JSON `configured=false` and `behavior_tested=false` are expected. A successful exit means inventory completed, not that the project is ready; inspect item-level BLOCKED/UNKNOWN. An empty project naturally has missing instructions, not PASS. Supply physical repo-relative paths for symlinked entrypoint inventory after checking their semantics.

<a id="existing-project"></a>
## 4. Existing project — copy-ready AI prompt

Replace the angle-bracket fields. The prompt starts safe planning; it does not grant blanket apply/install permission:

```text
Connect AI Factory to the existing <PROJECT_ROOT> without changing the stack, architecture or product.
Trusted complete source: <FACTORY_SOURCE + COMMIT/DIGEST>; managed destination: <FACTORY_TARGET>;
evidence root: <EVIDENCE>; current reviewer: <REFERENCE or UNRESOLVED>.
Read README, docs/guides/ai-assisted-onboarding.md and ai-factory/onboarding.md.
Start read-only: source/provenance/scripts, AGENTS/CLAUDE, local skills, tasks/ADRs/gates,
HEAD/index/dirty ownership and actual host versions/discovery. Do not read secrets/session logs.
Verify the release; create a kit plan (do not invent --dry-run), manifest/preflight and minimal adapter diff.
Show exact targets, selected components/skill mappings, side effects, conflicts, backups,
checks and rollback. Preserve existing global skills/symlinks. There is no native publisher here:
selected host mapping only as a separate reviewed diff; exact-file fallback is acceptable.
After explicit permission, apply only the agreed package plan/adapter delta; do not install/run runtime tools,
graph DB, hooks/MCP/models/permissions, dependencies or product tests.
Task branch in the main repo only with an agreed writer and WIP; foreign/unknown WIP → STOP,
no stash/reset/commit and no worktree/clone fallback. Keep the current reviewer; no duplication/contact without permission.
Check hashes/links, repeat NOOP; native invocation only through a separately authorized harmless probe.
Return applied/blocked/not-tested, raw commands/exits/snapshot and review handoff, not a fake PASS.
```

<a id="empty-project"></a>
## 5. Empty project — copy-ready AI prompt

The kit has no `bootstrap` CLI, project generator or automatic stack selection. The repo-bootstrap skill exists as instructions, not as an installed app scaffolder. Define the product goal, language/stack, test runner, delivery target and required constraints before a skeleton. The minimum first-stage result is project instructions, an adapter and one task/acceptance record; do not copy someone else's FSD/MVC/Go architecture. `git init`, initial commit, package-manager install and scaffold execution are separately approved actions, not onboarding side effects. Mark missing HEAD as BLOCKED only for dependent Git-review helpers.

```text
Prepare an AI Factory workflow for the empty <PROJECT_ROOT>.
Trusted source <FACTORY_SOURCE + COMMIT/DIGEST>, managed root <FACTORY_TARGET>, evidence <EVIDENCE>.
First verify that the directory is actually empty/who owns WIP, and read the onboarding guide.
Product goal: <GOAL>; already agreed stack/constraints: <VALUES or UNKNOWN>.
Do not select a framework or hosting by default. Clarify only decisions blocking scope/acceptance.
Create a read-only package plan + empty-project preflight; propose minimal AGENTS/CLAUDE pointers,
project adapter, task/acceptance record and suitable tests/QA; do not create a second tracker.
Show exact diff/commands/backups/rollback; after separate apply permission, write only these docs
and the agreed package plan. Do not run scaffold/install/devserver or perform git init/commit/push
without the corresponding instruction. Task branch/one writer; no HEAD → explicit review-helper BLOCKED.
Keep the existing reviewer or mark UNRESOLVED. Do not call missing tests/CLI discovery PASS.
After applying, check files/links/NOOP; the first small product slice and runtime proof are a
separate lifecycle with code review and final evidence, not part of docs bootstrap.
```

<a id="new-machine"></a>
## 6. New developer / machine — copy-ready AI prompt

The developer needs their own private-source access, installed Python/Git and the selected AI host. A missing prerequisite means BLOCKED with a concrete next step, not a hidden package download. Start with the same pin the team approved; do not use floating `latest`. Do not transfer the previous developer's home paths. License exclusions/provenance remain in force; access to a private repo does not grant redistribution rights for restricted skills.

```text
Prepare a plan to move AI Factory to this machine for <DEVELOPER/TEAM>.
OS/host: <OS + Codex/Claude CLI>; trusted private source/commit: <SOURCE>; dedicated managed
root: <TARGET>; project: <PROJECT>; evidence: <EVIDENCE>; reviewer: <REFERENCE or UNRESOLVED>.
First inspect Python/Git/host versions, platform limits and existing ~/.agents/skills,
~/.claude/skills mappings read-only, without reading credentials. The developer configures auth using their own
approved client; do not ask for tokens in chat or copy someone else's home/settings/session stores.
If source is unavailable, acquisition is BLOCKED; do not initiate network/auth without permission.
After source inspection/commit/hash verification, create a kit plan for the dedicated root and inventory
the project adapter. Do not install directly into ~/.agents: there is no native host publisher; propose
selected skill mapping or exact-file fallback, show collisions and backup/restore boundaries.
After permission, apply only the reviewed plan/diff, check repeat NOOP and retain the transaction.
Do not change system permissions, hooks/MCP/models or install graph/scanners/marketplace/SaaS.
Mark Linux NOT_TESTED and Windows UNSUPPORTED for the kit; do not promise parity without separate proof.
Record per-host detected/configured/discovered/invoked separately. The first task branch in the main repo requires
a designated writer and no foreign/unknown WIP; no automatic per-task clone/worktree.
Return evidence + handoff to the existing reviewer; installation ≠ product/runtime/workflow acceptance.
```

## 7. Update, backups, rollback and uninstall boundaries

For a new trusted release, first use a new SOURCE + the complete desired component set in `plan`. Omitting a component during update means deleting its managed files, not “leave it as it was.” Preserve the current source and `.ai-factory-state`; an unmanaged-file collision or someone else's edit means BLOCKED, with no force/adopt/reset.

```sh
python3 -B "$FACTORY_SOURCE/tools/kit.py" update --package "$FACTORY_SOURCE" --root "$FACTORY_TARGET" --component collection --component planning --component review --component session-guard
python3 -B "$FACTORY_SOURCE/tools/kit.py" update --package "$FACTORY_SOURCE" --root "$FACTORY_TARGET" --component collection --component planning --component review --component session-guard --execute --exclusive-window --plan-id '<new-reviewed-plan-id>'
python3 -B "$FACTORY_SOURCE/tools/kit.py" rollback --root "$FACTORY_TARGET" --transaction '<transaction-id>'
python3 -B "$FACTORY_SOURCE/tools/kit.py" rollback --root "$FACTORY_TARGET" --transaction '<transaction-id>' --execute --exclusive-window --plan-id '<rollback-plan-id>'
```

Rollback checks the latest/pending receipt and applied hashes, restoring only its own bytes, not others' edits. For an initial install, it may remove owned files, but not others' files/directories. There is no separate `uninstall` command. Removing an optional component is a reviewed update; fully clearing state, host links, adapters, hooks or caches is not covered by package rollback. Do not recommend `rm -rf ~/.agents` or deleting the callback store. A separate exact ownership inventory/permission is required; preserve artifacts until then.

## 8. How to verify readiness

Use one existing task record: source/commit/digest, selected components, exact source→destination mapping, baseline/applied hashes, branch/base/writer, plan/receipt IDs, commands/exits/artifacts/snapshot, limitations. Each host's state is DETECTED → CONFIGURED → DISCOVERED → INVOKED with separate evidence; reading a file is not invocation. Checks use PASS/FAIL/BLOCKED/NOT_TESTED/N/A with a reason. Fixtures establish helper behavior, not native agent behavior. An uninstalled optional graph means explicit file fallback; a required unavailable tool blocks only its dependent scope.

The current [lifecycle](../../ai-factory/feature-lifecycle.md): proportional grilling → scoped impact/checkpoint → required bound critique/defense → implementation → observable verification → independent final review → durable handoff. An aggregate build or merge does not replace acceptance rows. One task branch/one writer; the independent reviewer receives a snapshot and is not duplicated. Separate delivery state from verdict: `prepared` / `sent` / `acknowledged` / `verdict_received` under the [single contract](../../ai-factory/review-handoff.md#delivery-state); ACK is not PASS, and `AWAITING_DELIVERY` is only a historical name for the waiting reason. Do not wait for an incidental owner reminder: the author prepares the final package and uses the already-authorized reviewer route; with manual relay, explicitly name its next action. `sent` or exit 0 is not a received ACCEPTED verdict. With outstanding required proofs, the report remains VERIFICATION_INCOMPLETE/REVIEW_PENDING even if the product is merged.

Safe verification of the trusted package itself (disposable fixtures only, not user projects):

```sh
python3 -B "$FACTORY_SOURCE/tools/verify_release.py" --root "$FACTORY_SOURCE"
python3 -B "$FACTORY_SOURCE/tools/run_tests.py" --previous-release '/absolute/trusted/previous-release'
```

Without `--previous-release`, the specific migration fixture is skipped, not PASS. Retain output/exit. Portable support requires separate OS/CLI proof; this run is not installs/graphs/models/browser QA.

<a id="security-proposed"></a>
## 9. Security adoption — PROPOSED, not installed

Dangerous code may execute **before the scanner**: dependency lifecycle scripts, explicitly invoked npm test/run, CI Actions or instructions from another repository. First review provenance/source, the lockfile, exact vetted tool/action versions/digests, permissions and a secretless test environment; then separately authorize execution. Install-script policy must name permitted lifecycle scripts and the reason; default inspection may use `--ignore-scripts`, but this is **not a sandbox** and does not block explicitly invoked `npm test`/`npm run`. Sources: [npm ci](https://docs.npmjs.com/cli/commands/npm-ci/), [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use). Review Actions as code with runner access; pin verified immutable revisions and minimal token permissions, with no automated settings changes by this guide.

| Candidate from earlier research | Status / boundary before adoption |
|---|---|
| Semgrep Community Edition / custom rules | PROPOSED. The engine and registry rules have different terms. Check the [rules license](https://semgrep.dev/legal/rules-license/) before redistribution; do not vendor others' registry rules into Factory. Custom rules/permitted references are a separate reviewed scope |
| Trivy | PROPOSED. The [official supply-chain advisory March 2026](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23) demonstrates the need to check provenance and a specific vetted version/digest; it does not establish current unsafety or compromise of this user. Do not arbitrarily pin `latest` or an old “safe” version |

This shortlist is not exhaustive security coverage. Tool installation, database download/update, network mode, findings policy and permissions remain unspecified until a separate proposal. Nothing is installed, no registry/marketplace is connected; no additional SaaS required. Zero scanner findings do not prove the absence of vulnerabilities; first-party scripts, actions, secrets handling and dependency provenance also require review. The research below refines the proposal; any rollout requires a separate bounded instruction in the current task record.

### Risk-triggered gates in the current lifecycle

This is a proposal for the next bounded adoption, not an automatically enabled policy. In the existing task/acceptance record, write only applicable trigger → expected behavior → actual check/artifact → owner → status. No corresponding feature means N/A with a reason; missing required evidence means NOT_TESTED/BLOCKED. No new tracker or identical heavy checklist for every repo is needed.

| Trigger | What to include in scoped acceptance and evidence |
|---|---|
| Any new execution source | Before running dependency/test scripts, CI Actions, hooks/MCP, inspect source, provenance, permissions and data egress. Instructions from a repository, retrieved content or tool output do not grant new permissions. Test without production secrets; agree on actual side effects rather than trusting a scanner's name. [Secure Coding with AI](https://cheatsheetseries.owasp.org/cheatsheets/Secure_Coding_with_AI_Cheat_Sheet.html), [Prompt Injection](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) |
| Identity, role, tenant or shared cache | Check the real API/resource: anonymous, another user/tenant, revoked role, disabled account, expired session, switch/logout and a repeated cached request. Hidden UI is not authorization. Cache keys/invalidation must preserve tenant/user boundaries; if SSR/hydration exists, check HTML/serialized state for private fields. [Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [Web Cache Security](https://cheatsheetseries.owasp.org/cheatsheets/Web_Cache_Security_Cheat_Sheet.html) |
| Cookie/session/cross-origin mutation | Record actual Set-Cookie attributes and logout/expiry behavior through the real proxy path. Check CSRF for state-changing requests, credentialed CORS and origin policy, not just configuration lines. CORS does not replace authorization or CSRF protection. [Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) |
| Server fetch by URL | Only when a feature accepts/derives a destination: check scheme/host/IP, redirect destination and repeated DNS resolution/rebinding, time/size limits and network egress. Use controlled fixtures without probing others' or internal production endpoints. [SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) |
| Upload/archive/download | Server-side total bytes, decompressed size/count, type/content/name validation, storage/processing boundary and download authorization; do not rely on client MIME/extension. Check with small bounded fixtures. [File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) |
| Incoming webhook | Verify the provider signature under its contract before business effects, replay/delivery ID and idempotency for redelivery, invalid/missing signature and duplicate event. HTTP 2xx alone does not prove correct handling. [GitHub webhook practices](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks) |
| Resource/cost amplification | Define request bytes, batch/array/page limits, queues/concurrency/timeouts and downstream cost budget for the feature. For Go, `ParseMultipartForm(maxMemory)` limits memory file parts and writes the rest to disk; this is NOT a total upload cap. A separate total-body limit is required, for example reviewed `MaxBytesReader` placement. No production load testing. [OWASP API4](https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/), [Go net/http](https://pkg.go.dev/net/http) |
| Errors/logs/traces and incident recovery | Verify redaction of credentials, session IDs and sensitive payloads in actual error/log/trace outputs; define the owner for patch, revoke and rollback, and evidence access/retention boundaries. Supply sanitized artifacts without secrets for review. [Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) |

### The scanner gate needs its own verification

Before adoption in a CI/local gate, three harmless fixtures are required: a known positive detection with the expected policy failure, a clean case with PASS, and a tool/config/DB error with ERROR/BLOCKED, not “clean.” Record version/digest, rule-set/version/license, DB timestamp, target snapshot, enabled scanners, coverage/exclusions, output format, findings policy and commands/exits. Verify that the wrapper/CI itself preserves and interprets findings; exit 0 alone is not PASS. [Trivy default exit](https://www.trivy.dev/docs/dev/guide/configuration/others/) can be 0 even with findings. For Go only as a stack-specific candidate: [govulncheck](https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck) also has output modes with success exit despite findings and documented static-analysis limits. This is not permission to install/run another scanner.

### Final evidence and boundaries of completion claims

Verify the actual built artifact/handler/runtime on the final snapshot; a copied-handler harness may establish narrow logic but does not replace the real production route. Required CSP/browser interaction, throw path, SSR cancellation/abort, auth/proxy/cache boundaries need separate observable acceptance rows with raw sanitized evidence. Unit/build/merge do not close unverified runtime rows. After a delta, identify invalidated checks and hand the final snapshot to the current independent reviewer; `prepared`/`sent`/`acknowledged` is not `verdict_received`/ACCEPTED. Missing required rows leave VERIFICATION_INCOMPLETE even after merge.

Adoption sequence: agree on only applicable gates and their owner in the current plan → verify scanner provenance/policy/fixtures in a separate bounded scope → obtain actual runtime evidence for the first small slice → independent final-delta verdict. This document does not authorize destructive DAST, new permissions, paid tools, network integrations or rollout.

Review-only adoption proposal: [thin security adapter](../../adapters/security/review.md), [pinned upstream sources](../../provenance/security-sources.json), [declarative scanner profile](../../examples/security/scanner-profile.json). These references do not imply installation, native invocation or a working security gate.
