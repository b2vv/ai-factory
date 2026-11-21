#!/bin/sh
# Reproducible global connection of the installed AI Factory skills to an agent's skill
# discovery directory. The managed kit is the single source of truth: this creates SYMLINKS
# that point at the kit's skill directories, never copies skill bodies, never edits provenance,
# and contains no secrets or machine-specific absolute paths.
#
# SOURCE  = <this repo>/skills  (derived from the script's own location; portable).
# TARGET  = the discovery directory an agent reads, e.g. ~/.claude/skills (which itself may be
#           a symlink to a shared ~/.agents/skills tree). Pass it explicitly or set
#           AF_SKILLS_TARGET; default is the first existing of ~/.claude/skills or ~/.agents/skills.
#
# Safety contract (matches the reviewed connection procedure):
#   - ADDITIVE by default: only skills ABSENT from the target are connected (new symlink).
#   - NEVER overwrites or deletes a local skill. A same-named target that differs in content is
#     reported as CONFLICT and skipped (local customization preserved).
#   - A same-named IDENTICAL target is reported and skipped unless --adopt-identical is given,
#     in which case the original is MOVED ASIDE (reversible) into <target>/.superseded-<ts>/
#     and replaced by a symlink to the kit — never deleted.
#   - Snapshot/vendor trees (synced/, .trash, dot-dirs) and non-skill entries are ignored.
#   - The whole discovery directory symlink is never repointed.
#
# Usage:
#   tools/connect-skills.sh [--adopt-identical] [--dry-run] [TARGET_DIR]
#
set -eu

adopt_identical=0
dry_run=0
target=""
for arg in "$@"; do
  case "$arg" in
    --adopt-identical) adopt_identical=1 ;;
    --dry-run) dry_run=1 ;;
    --*) echo "unknown option: $arg" >&2; exit 2 ;;
    *) target="$arg" ;;
  esac
done

# SOURCE: the kit's skills dir, relative to this script. No hardcoded machine path.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
src=$(CDPATH= cd -- "$script_dir/../skills" && pwd)

# TARGET discovery dir: arg > env > first existing default. Resolve through a dir symlink.
if [ -z "$target" ]; then
  target="${AF_SKILLS_TARGET:-}"
fi
if [ -z "$target" ]; then
  for d in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
    [ -e "$d" ] && { target="$d"; break; }
  done
fi
[ -n "$target" ] || { echo "no TARGET discovery dir found; pass one explicitly" >&2; exit 2; }
# Follow a directory symlink to its real location so we add entries in the real tree.
target=$(CDPATH= cd -- "$target" && pwd -P)

ts=$(date +%Y%m%d-%H%M%S)
hold="$target/.superseded-$ts"
connected=0; skipped_identical=0; conflicts=0; already=0

# Iterate kit skills by their SKILL.md, deriving the skill directory (relative to src).
# Skip snapshot/vendor and dot trees.
find "$src" -name SKILL.md -type f | while IFS= read -r skill_md; do
  rel=${skill_md#"$src"/}            # e.g. arch/code-review/SKILL.md
  rel_dir=${rel%/SKILL.md}           # e.g. arch/code-review
  case "$rel_dir" in
    synced/*|.trash/*|.*/*|.*) continue ;;
  esac
  kit_dir="$src/$rel_dir"
  tgt_dir="$target/$rel_dir"

  if [ -L "$tgt_dir" ]; then
    if [ ! -d "$tgt_dir" ] || [ ! -f "$tgt_dir/SKILL.md" ]; then
      echo "CONFLICT $rel_dir (dangling or missing skill target; preserved)"; conflicts=$((conflicts+1)); continue
    fi
    resolved=$(CDPATH= cd -- "$tgt_dir" && pwd -P)
    expected=$(CDPATH= cd -- "$kit_dir" && pwd -P)
    if [ "$resolved" != "$expected" ]; then
      echo "CONFLICT $rel_dir (symlink targets another location; preserved)"; conflicts=$((conflicts+1)); continue
    fi
    echo "ALREADY  $rel_dir -> $(readlink "$tgt_dir")"; already=$((already+1)); continue
  fi
  if [ ! -e "$tgt_dir" ]; then
    if [ "$dry_run" = 1 ]; then echo "CONNECT  $rel_dir (new)"; else
      mkdir -p "$(dirname -- "$tgt_dir")"; ln -s "$kit_dir" "$tgt_dir"; echo "CONNECT  $rel_dir"
    fi
    connected=$((connected+1)); continue
  fi
  # target exists as a real dir: compare the SKILL.md content
  if [ -f "$tgt_dir/SKILL.md" ] && cmp -s "$tgt_dir/SKILL.md" "$kit_dir/SKILL.md"; then
    if [ "$adopt_identical" = 1 ]; then
      if [ "$dry_run" = 1 ]; then echo "ADOPT    $rel_dir (identical -> kit, move aside)"; else
        mkdir -p "$(dirname -- "$hold/$rel_dir")"; mv "$tgt_dir" "$hold/$rel_dir"; ln -s "$kit_dir" "$tgt_dir"
        echo "ADOPT    $rel_dir (original kept in ${hold##*/})"
      fi
      connected=$((connected+1))
    else
      echo "IDENTICAL $rel_dir (skipped; use --adopt-identical to point at kit)"; skipped_identical=$((skipped_identical+1))
    fi
    continue
  fi
  echo "CONFLICT $rel_dir (target differs; preserved, not overwritten)"; conflicts=$((conflicts+1))
done

echo "---"
echo "source(kit): $src"
echo "target:      $target"
echo "done. (counts above are per-line; run with --dry-run to preview)"
