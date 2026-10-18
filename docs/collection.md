> Retained documentation from release 626fd68. Historical layout/status statements below are preserved for provenance; current paths and commands are in the root README and migration guide.

# Full internal skill collection and AI Factory plan

The full inherited plan is [agents/ai-factory/ai-factory-plan.md](../ai-factory/ai-factory-plan.md), with all authored subfiles, roadmap history, status, evidence, rules, templates and original helpers. It is the full source plan; root docs/tools are separate portable wrappers, not a replacement. Historical measurements and machine-specific integration claims are not acceptance on a new host.

## Exact requested boundary

All 84 definitions physically within `~/.agents/skills` are accounted for: all 62 primary and 22 synced. 73 are copied with complete in-bundle references/scripts/assets; 11 have explicit outside-Service copy restrictions in their local licenses and are inventory-only. No bundle was excluded merely because historical authorship or a license was unknown. Existing Apache/MIT/font notices in included bundles are retained unchanged.

The eleven restricted definitions are snapshot-01 built-in-browser, chrome-browser, computer-use, docx, pdf, pptx, xlsx; and snapshot-02 docx, pdf, pptx, xlsx. Their terms explicitly prohibit extraction/retention outside Services and copying other than authorized temporary copies. Obtain them via the provider Services under applicable entitlement. Their content is not in this payload.

External symlink targets, genericui bundles, project-local skills, Codex system/plugin content and their inventories are outside the clarified scope. Former external aliases are recorded only as excluded links. Internal aliases map to included physical sources without recursion. The earlier broader commit remains in Git history; this correction uses a normal forward commit, not a history rewrite.

## Layout and discovery

`collection/agents/skills/<group>/<name>` preserves nested primary paths. `collection/agents/skills/synced/snapshot-01|02/<name>` preserves independent variants with opaque machine identifiers normalized. Never flatten same-name variants silently. The manifest maps sources, aliases, destinations, source/payload hashes, original modes and exact transformations.

Plan an inert source install into a dedicated directory:

```sh
python3 -B tools/kit.py --package "$PWD" --root /absolute/dedicated/toolkit --component collection
```

Then use the explicit plan/apply/rollback protocol in `docs/portability-design.md` after reviewing the plan. No host registration, global writes, hook activation or source script execution occurs. Exact-file invocation means opening the selected installed `SKILL.md`. Native Codex/Claude discovery is NOT_TESTED; setting up host aliases is separate authorized work. Source modes are recorded; staged files remain non-executable (0644) until deliberately invoked with an inspected interpreter.

## Preservation, privacy and dependencies

Source files are byte-identical except recorded portable links and home/machine/network-coordinate normalization. `.gitattributes` disables Git line-ending conversion so committed bytes match checksums, including fonts and legal notices. No original sources were modified. Full authored roadmap history is included; raw sessions/handoffs, caches, env/auth/keys, host metadata, graph data and private product artifacts are not.

The manifest checks every source Markdown link: included targets resolve; placeholders and external project/tool/historical references are explicitly recorded. `wayfinder`'s literal `link` and `google-workspace`'s `its link` are template placeholders, not missing dependency files. Runtime CLIs/MCP tools and project standards are not bundled or installed. Cross-project references in the original plan retain their meaning but do not authorize copying those repositories.

Independent review and native runtime acceptance remain pending. Product rollout remains STOPPED.

## Explicit b2b exclusion

No physical internal bundle has a directory or declared skill name starting `b2b` (case-insensitive). Six external alias skill names match: `b2b-grill-me`, `b2b-handoff`, `b2b-mode-careful`, `b2b-mode-ralph`, `b2b-save-idea`, `b2b-work`. They are excluded, not dereferenced or installed. Any inherited reference to these skills is an unavailable external dependency in this package; invoking it requires an independently supplied source and authorization. No substitute is invented.
