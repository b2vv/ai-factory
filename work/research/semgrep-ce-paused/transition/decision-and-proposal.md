# Official-image / CE-use transition — 2026-10-22

Owner decision Sentinel_0a4f9e3cf8b48191937347d67c060d1d supersedes CE-only image composition with CE-only execution. Custom build is PAUSED/SUPERSEDED for this integration, not successful or deleted. All candidates, tests, run-v2–v6 and reviews stay in place; preservation-index.json binds84 existing evidence references and identifies preserved roots. Tar-parser work remains STOPPED; libarchive audit cancelled. No prior artifact is rewritten by this addendum.

Storage: task and task-2 are outside a Git working tree (git rev-parse returned128); these research/build artifacts are LOCAL ONLY, not a proven remote backup. A future exact Git checkpoint must select authored recipes/tests/docs and evidence indexes explicitly, review third-party/source/log contents and size first; never git add -A or silently commit acquired archives, image blobs, DBs or all logs. No staging/commit/push now. Existing scanner-only publication a99fbd709a04cfd2a406fc6691ab76344cd855d8 is independently recorded; preserving this work does not merge it or activate Cargo.

## Workflow checkpoint

Route: existing-session planning/resume, task-local only. Applied AGENTS.md, README, ai-factory/ai-factory-plan.md and pre-code-checkpoint.md, PROVENANCE, docs/migration-0.4.md and existing docs/portable/change-protocol.md. Parent owns delivery/reviewer coordination. Canonical HEAD observed36b1a2f565457687682388832287f3ae1526d343, tracked status clean at read time; this is not writer-exclusivity proof. No canonical writes. Before implementation recheck exact base/diff, writer slot and affected plan review. Current proposal is AUTHOR_CHECKED, independent review pending; runtime NOT_RUN. Changed acceptance requires affected review, not retrospective reuse of CE-build ACCEPT.

## Exact candidate and terms

Semgrep1.181.0, linux/amd64:
`docker.io/semgrep/semgrep@sha256:c47e426f7f0cfa19af6d7877560d0a7135f683b8090ad0efc97c4ec7810dc435`.
Saved raw index81474464c1f07483ba0682a44787fd93c91397419762a04abe2bafaae396304b and2760-byte platform manifest rehashed successfully; index descriptor says linux/amd64. This revalidates prior2026-10-20 acquisition, not a fresh tag or latest-release claim. Config02f02a7c0dbcc7f723274d32682920bb81a86f99563fc41d7278122d8fd58cb9 is7839bytes;13 layer descriptors total427,947,231 compressed bytes (~408.12MiB), not unpacked size/network quota. No image pulled.

Public release source is72d3525fe7e02f486428386078f192f8c4756804. Existing image provenance refers to a proprietary revision; authenticated mapping to this CE commit and Semgrep signature verification remain unestablished. Preserve this supply-chain limitation; changing execution mode does not solve it.

Official public sources checked2026-10-22:
- https://docs.semgrep.dev/deployment/oss-deployment recommends semgrep scan and semgrep/semgrep Docker for CE. It requires own/open-source rules for strictly open-source use.
- https://docs.semgrep.dev/cli-reference defines --oss-only as OSS-engine selection, even with Pro toggle; it can still run Pro rules. Therefore rule licensing remains separate.
- https://docs.semgrep.dev/licensing assigns LGPL2.1 to CE, different terms to proprietary extensions and Semgrep-maintained rules.
- https://semgrep.dev/legal/terms/ (page dated2026-08-20), definitions exclude OSS engine from proprietary Software; §2.2 points to LGPL2.1 for OSS engine.

These support the documented local CE-use route. They do not establish that the mixed image is entirely LGPL, supply exact-image notices, or grant redistribution rights for all bundled components. Proposal: local internal use only; do not redistribute/repackage the image. Inspect delivered notices/component metadata during separately approved acquisition before adoption. No claim of illegality or blanket rights clearance. Existing baseline rules are two original eval rules only; no full security coverage claim and no automatic Semgrep Registry rules acquisition.

## Minimal wiring

compose-command-proposal.diff adds only --oss-only after scan; it is not applied. Keep local /rules, metrics off, version check off, --disable-nosem, --no-git-ignore and existing JSON report classifier. Do not add --error: current classifier expects exit0 plus JSON results/errors and distinguishes FINDINGS/CLEAN/ERROR itself. No ci/login/Pro/registry-auto/cloud command.

Proposed effective argv:
`semgrep scan --oss-only --disable-nosem --config /rules --metrics off --disable-version-check --no-git-ignore --json --output /reports/semgrep.json /src`

Existing product-neutral profile remains: pull never, network none, rootfs RO, cap-drop ALL, no-new-privileges, bounded noexec/nosuid tmpfs, staged hash-allowlisted source/rules RO and separate reports RW. No source mount of whole home/project, Docker socket, credentials, token, env_file or host env inheritance; inspect resolved paths, actual mounts/argv/env and image config. HOME=/tmp. No SEMGREP_APP_TOKEN. No telemetry/network success claim merely from flags: network none is enforcement of network isolation, not proof of zero attempted telemetry.

Future code delta: one Compose flag + focused argv/CE rejection tests, then exact engine manifest/provenance evidence and derived checksums only after review. Keep engine pins pending now; no fabricated ACCEPT status. Canonical rules-directory/hash staging/tmpfs protections and Cargo adapter ownership/attestation boundaries remain. Cargo activation and real target selection are separate; P6/revoke remain outside generic portability.

## Three next steps, no custom-build detour

1. Review this small policy/wiring proposal and exact image-use evidence. Prepare the one-flag/test delta in an isolated current-base snapshot; establish writer window only for canonical apply. Owner transition decision already supplied; no redundant policy question.
2. Obtain one explicit acquisition/runtime grant: pull only exact amd64 digest from Docker Hub public registry/auth/CDN, no source transmitted, anonymous access only; inspect actual config/User/Entrypoint/Env/Volumes/platform and delivered notices before run. Descriptor total428MB is a baseline, not hard traffic bound. Propose acquisition cap600MiB,10min and task storage ceiling2GiB with10GiB host reserve (soft/unpacked unknown: stop if exceeded). Use standard Docker, no new framework. Exact config user/path compatibility unresolved: do not invent UID or relax protections. Then bounded offline --version/--help and tiny CE fixtures (2CPU/2GiB/128PIDs,10min aggregate, reports<=16MiB), no product mounts. Stop on protection/config/rights-evidence mismatch; no automatic fallback to custom build or elevated privileges.
3. Accept only observed CE positive/clean/error, valid/malformed local rules, actual mount/argv/env and no credential/no Courses access evidence. Independently review exact results before accepting pin and release metadata. Trivy amd64 candidate/Factory-owned versioned DB+separate network updater and Yarn prod/dev/transitive acceptance remain separate outstanding scanner prerequisites. Do not hold Semgrep fixture result out as complete scanner release or Cargo activation.

No downloads, pulls, container execution, DB changes, product scans, repository changes or publication in this phase. Smallest next action: independent proposal review then bounded official-image acquisition/CE-fixture package; preserve prior work locally and offer a separately scoped durable checkpoint.
