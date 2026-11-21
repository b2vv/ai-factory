# Right-to-left UI review

Use for an in-scope RTL locale or mixed-direction content. Inspect the real route,
locale, state and viewport under the shared viewport contract. Use actual RTL text
from the supported locale, not an English layout with only its alignment reversed.
For a shared component, compare LTR where supported. Skip inapplicable checks;
missing evidence is `NOT_TESTED`, not PASS. This is not a standalone gate.

| Check | Observe on the artifact |
| --- | --- |
| Base direction | In a full RTL document check the root `lang` and `dir="rtl"`; for a mixed-direction region check the intended local direction. Switch locale where supported and inspect the same view and any open menu or dialog. |
| Layout and icons | Compare leading/trailing alignment, padding, navigation and directional icons (back/next, breadcrumbs). Directional affordances should follow the task; do not mirror logos, media controls or other direction-neutral symbols by default. Check for unintended physical `left`/`right` positioning; prefer logical CSS when it expresses the intent. |
| Mixed text and numbers | Render a localized sentence with a user name, Latin identifier, signed amount, and punctuation. Verify that signs, parentheses and separators stay with the correct value and that copy preserves it. Isolate an unknown-direction run with `bdi` or suitable `dir="auto"` markup; use the product's locale formatting instead of rewriting digits indiscriminately. |
| Fields and validation | Type and edit an RTL name, then an email, URL or code if relevant. Check the caret, selection, label and error together. Natural-language input may follow the entered text; known LTR syntax should remain legible without flipping the surrounding form. |
| Interaction and narrow states | Walk the task with keyboard and pointer, including any popovers, tables or pagination. Verify logical focus order, visible focus and expected next/back behavior. At the narrow viewport use a long label or name and check wrapping, clipping and reachable actions. |

Ground language direction and isolation in W3C Internationalization's [structural RTL guidance](https://www.w3.org/International/questions/qa-html-dir) and [inline bidi guidance](https://www.w3.org/International/articles/inline-bidi-markup/). Check icon behavior against the product's design system; it is contextual, not a universal mirroring rule.

Checklist inspiration: Damir Sokolovsky, [Unslop RTL reference](https://github.com/heydamir/unslop/blob/main/skills/unslop/references/rtl.md), CC BY 4.0. This is a rewritten review checklist for AI Factory, not the upstream skill or its scripts.
