"""Static regression guards for the semantic-consistency guidance in the design skills (text only).

What they check: section references resolve; the new rules keep their native form and one primary URL; the
design-pass §3 priority line is byte-identical; `style` is never stated to produce PASS in the checked form;
concept fit keeps two separate, exact outcome sets (compatibility and visual fit); required prohibitions
(concept fit is not acceptance, NOT_TESTED is never `fits`, a source read is not a rendered observation) are
present as whole sentences; ui-audit keeps requirement failures in the gate, contrast out of `style` rows, evidence-less
contrast/keyboard claims and missing coverage out of PASS, and proximity alone out of association cues; design-pass runs
the pre-flight on a shown variant and on the result; `compatible` vs `extends concept`; attribution by kit release and helper file hash.

Limits: these are presence and structure checks. They fail when required text is removed or reworded; they do
not detect a new contrary claim phrased elsewhere, and they do not judge what an agent does with the guidance.
Concept fit standing in for acceptance and NOT_TESTED becoming `fits` are covered by the behavioral runs, not
here. Negative controls exist for section references, rule form, the style claim, the outcome sets, the
interface-review prohibitions, the compatible row and attribution.
"""
import hashlib,re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SKILLS=ROOT/'skills'
REF=SKILLS/'ux-review/references/semantic-consistency.md'
RULES=SKILLS/'ux-review/references/rules.md'
CONCEPT=SKILLS/'anti-slop-design/references/concept-fit.md'
REVIEW=SKILLS/'interface-review/SKILL.md'
AUDIT=SKILLS/'interface-review/references/product-audit.md'
CONTRACT=SKILLS/'ui-measurements/references/contract.md'
UIAUDIT=SKILLS/'ui-audit/SKILL.md'
DESIGNPASS=SKILLS/'design-pass/SKILL.md'
# design-pass §3 priority line must stay byte-identical (facade contract unchanged).
PRIORITY_SHA='90aea3d5a32f00b69199653c8fbbc8946aedc5bd36a95c1c91d82daf18468d8b'
NEW_RULES=['Same role, same treatment','Distinguishable roles','Variants follow context','Values through the system','Sizes map to roles','Importance follows weight','Affordance consistency']

def skill_texts():return {str(p.relative_to(ROOT)):p.read_text() for p in SKILLS.rglob('*.md')}
def headings(text):return {m.group(1) for m in re.finditer(r'^#{2,3} (\d+)\.',text,re.M)}
def norm(text):return re.sub(r'\s+',' ',text.replace('**',''))
def sentences(text):return [s for s in re.split(r'(?<=[.;])\s+|\n\s*\n|\n(?=\s*[-|*\d])',text) if s.strip()]
def missing(text,required):
 """Required sentences, compared with whitespace and bold markers normalized; a reworded sentence counts as missing."""
 t=norm(text);return [r for r in required if norm(r) not in t]

# --- Test 15: every section reference resolves -------------------------------------------------
MENTION=re.compile(r'(?:\[(?P<link>semantic-consistency|concept[- ]fit)\]\([^)]*\)|\b(?P<bare>semantic-consistency|concept[- ]fit)\b(?! reference §)|\b(?P<anon>reference)\b)'
  r'\s+§(?P<a>\d+)(?:\s*[–-]\s*§(?P<b>\d+))?(?:\s+and\s+§(?P<c>\d+))?')
def section_reference_violations(files,targets):
 """files: {path: text}; targets: {'semantic-consistency': text, 'concept-fit': text}."""
 out=[]
 heads={k:headings(v) for k,v in targets.items()}
 for path,text in files.items():
  for m in MENTION.finditer(text):
   name=m.group('link') or m.group('bare')
   if name:target='concept-fit' if name.startswith('concept') else 'semantic-consistency'
   else:
    # an anonymous "reference §N" resolves only if its paragraph names exactly one known reference
    para=text[text.rfind('\n\n',0,m.start())+1:text.find('\n\n',m.end()) if text.find('\n\n',m.end())>=0 else len(text)]
    named={'concept-fit' if n.startswith('concept') else n for n in re.findall(r'semantic-consistency|concept[- ]fit',para)}
    if len(named)!=1:out.append((path,m.group(0),'anonymous reference without exactly one named reference'));continue
    target=named.pop()
   for n in filter(None,[m.group('a'),m.group('b'),m.group('c')]):
    if n not in heads[target]:out.append((path,m.group(0),f'{target} has no §{n} heading'))
 return out

# --- Test 15: new rules in native form, one primary URL -----------------------------------------
def rule_blocks(text):return [b.split('\n\n')[0] for b in re.split(r'\n(?=\[)',text)]   # a rule ends at its blank line
def rule_form_violations(rules_text):
 out=[]
 blocks=rule_blocks(rules_text)
 for name in NEW_RULES:
  found=[b for b in blocks if b.startswith('[consistency] '+name)]
  if len(found)!=1:out.append((name,f'{len(found)} blocks'));continue
  if '→ violation:' not in found[0]:out.append((name,'no → violation:'))
  if len(re.findall(r'https://\S+',found[0]))!=1:out.append((name,'not exactly one URL'))
 wcag=[b for b in blocks if b.startswith('[wcag] 1.4.1 ')]
 if len(wcag)!=1:out.append(('[wcag] 1.4.1',f'{len(wcag)} blocks'))
 else:
  urls=re.findall(r'https://\S+',wcag[0])
  if '→ violation:' not in wcag[0]:out.append(('[wcag] 1.4.1','no → violation:'))
  if len(urls)!=1 or not urls[0].startswith('https://www.w3.org/WAI/WCAG22/Understanding/use-of-color'):out.append(('[wcag] 1.4.1','primary URL must be the single W3C Understanding 1.4.1 link'))
 names=re.findall(r'^\[consistency\] ([^—\n]+?) —',rules_text,re.M)
 if len(names)!=len(set(names)):out.append(('[consistency]','duplicate rule name'))
 return out

# --- Test 16 and later owner distinctions: required prohibitions stay present -------------------
CONCEPT_PROHIBITIONS=['Concept-fit verdicts are design-quality results, not acceptance: open mandatory acceptance criteria or required evidence do not become PASS by being listed as decisions (semantic-consistency §5, gating decisions).',
 '| `NOT_TESTED` | not shown, or no evidence record | never reported as `fits` |',
 'Proceed rule. Implementation may start only when compatibility is `compatible` (or an approved `extends concept`) and visual fit is `fits` — or visual fit is `NOT_TESTED` and the acceptance criteria and risk of the change allow that (a small local change; recorded as `NOT_TESTED`, never as `fits`).',
 'Visual fit `fits` never repairs a compatibility `conflicts`; `compatible` never stands in for a visual fit that the acceptance criteria require.']
REVIEW_PROHIBITIONS=['An open gating decision blocks PASS (the affected check stays BLOCKED / NOT_TESTED); open stylistic decisions do not.',
 'Moving an open acceptance criterion or required evidence into the decisions section does not make it pass.']
SOURCE_PROHIBITIONS=["Reading source (including a fixture's code) proves what exists or is absent in the code read: definitions, usages, inline overrides.",
 'It does not stand in for observing the rendered state; a check that needs the rendered result stays NOT_TESTED, and a finding resting on source alone says `source only`.',
 'A claim of absence or non-use (a token no sampled screen uses, a control not found) is scoped to the screens and files actually read and is reported as such, not as a product defect.']
UIAUDIT_PROHIBITIONS=['An entry that fails an applicable accessibility, keyboard or functional requirement (an in-scope WCAG criterion, a broken task step, an unreachable control) stays in the report and is passed to the interface-review gate whatever the answer; record the answer beside it, and only a dated limitation the owner explicitly accepts, with its impact, changes its gate status.',
 '`style` rows are observed values, not a verdict; they do not establish contrast.',
 "For contrast use the ui-measurements `contrast` kind with a declared threshold and its source; where it returns `NOT_TESTED` (unsupported paint, opacity, background outside the text box), the entry says `NOT_TESTED` and is never reported as fine.",
 'A contrast or keyboard statement without that evidence (helper rows for contrast, actual navigation for keyboard) is reported as `NOT_TESTED` with what was observed, never as a violation or a pass; a ratio calculated by hand from source colours is not evidence.',
 'Being on the same screen, or near something, is not by itself a cue.',
 'Missing coverage is listed as `not looked` or `NOT_TESTED` and never counts as fine or as a pass.']
DESIGNPASS_PREFLIGHT=['Its §3 pre-flight runs at two points with different objects: on a variant shown for visual fit before implementation (step 4, per concept fit), and on the implemented result in the §5 final pass.',
 'a pre-flight on a variant before implementation (§2 step 4) does not replace it.']
ATTRIBUTION={'contract':['- Version: results are attributed by kit release and helper file hash (the helper reports no version of its own).'],
 'audit':['1. Scope and run identity: build/commit, accounts/fixtures, sampled routes × keys, reader kit release and helper file hash, earlier records consulted (or "none readable").']}
CONCEPT_OUTCOMES=[['compatible','extends concept','conflicts','NOT_TESTED'],['fits','conflicts','NOT_TESTED']]
def outcome_tables(concept_text):
 """Concept-fit §3 tables in order, each as the backticked verdicts of its first column (headers and labels ignored)."""
 sec=re.split(r'\n## ',concept_text.split('\n## 3.',1)[1],maxsplit=1)[0]
 tables,cur=[],[]
 for line in sec.splitlines()+['']:
  if line.startswith('|'):cur.append(line);continue
  if cur:tables.append(cur);cur=[]
 return [[m.group(1) for m in map(lambda l:re.match(r'^\| `([^`]+)` \|',l),t) if m] for t in tables]
STYLE_PASS_OK=r'\b(?:never|not|no)\W{0,3}PASS\b|excluded'
def style_pass_violations(files):
 """A sentence naming `style` and PASS must negate PASS directly or say the rows are excluded."""
 return [(path,s.strip()[:120]) for path,text in files.items() for s in sentences(text) if '`style`' in s and re.search(r'\bPASS\b',s) and not re.search(STYLE_PASS_OK,s)]
def concept_outcome_violations(concept_text):
 """`compatible` must be conditioned on the already-accepted norm; `extends concept` must cover a norm change."""
 rows={m.group(1):m.group(2) for m in re.finditer(r'^\| `(compatible|extends concept)` \| ([^|]+)\|',concept_text,re.M)}
 out=[]
 if 'compatible' not in rows or not re.search(r'norm already accepted for this role and context',rows['compatible']):out.append('compatible row lacks the accepted-norm condition')
 if 'extends concept' not in rows or not re.search(r'changes the accepted norm',rows['extends concept']):out.append('extends concept row lacks the norm-change case')
 if 'compatible' in rows and re.search(r'changes the accepted norm',rows['compatible']):out.append('compatible row admits a norm change')
 return out

class DesignSemanticsText(unittest.TestCase):
 def setUp(self):
  self.files=skill_texts();self.targets={'semantic-consistency':REF.read_text(),'concept-fit':CONCEPT.read_text()}
 # Test 15
 def test_section_references_resolve(self):
  self.assertEqual(section_reference_violations(self.files,self.targets),[])
 def test_section_reference_guard_catches_broken_forms(self):
  bad={'x.md':'See [semantic-consistency](a.md) §9.\n\nAlso semantic-consistency §1–§9.\n\nThen reference §2 here.'}
  self.assertEqual(len(section_reference_violations(bad,self.targets)),3)
 def test_new_rules_use_native_form_once_with_one_primary_url(self):
  self.assertEqual(rule_form_violations(RULES.read_text()),[])
 def test_rule_form_guard_catches_extra_url(self):
  text=RULES.read_text()
  wcag=next(b for b in rule_blocks(text) if b.startswith('[wcag] 1.4.1 '))
  self.assertTrue(rule_form_violations(text.replace(wcag,wcag+' https://example.org/second')))
 # Test 16
 def test_design_pass_priority_line_is_unchanged(self):
  dp=(SKILLS/'design-pass/SKILL.md').read_text()
  line=next(l for l in dp.splitlines() if l.startswith('The explicit user request defines the goal.'))
  self.assertEqual(hashlib.sha256(line.encode()).hexdigest(),PRIORITY_SHA)
 def test_style_rows_never_claimed_to_pass(self):
  self.assertEqual(style_pass_violations(self.files),[])
  self.assertTrue(style_pass_violations({'x.md':'A `style` row that is not blocked counts toward PASS.'}))
 def test_concept_fit_keeps_two_exact_outcome_sets(self):
  text=CONCEPT.read_text()
  self.assertEqual(outcome_tables(text),CONCEPT_OUTCOMES)
  merged=re.sub(r'(\| `NOT_TESTED` \| no card[^\n]*\n)(?:.*\n)*?\|---\|---\|---\|\n',r'\1',text,count=1)   # second table's rows joined to the first
  self.assertNotEqual(merged,text)
  self.assertNotEqual(outcome_tables(merged),CONCEPT_OUTCOMES)
 def test_required_prohibitions_present(self):
  self.assertEqual(missing(CONCEPT.read_text(),CONCEPT_PROHIBITIONS),[])
  self.assertEqual(missing(REVIEW.read_text(),REVIEW_PROHIBITIONS),[])
  self.assertEqual(missing(REF.read_text(),SOURCE_PROHIBITIONS),[])
 def test_ui_audit_and_preflight_rules_present(self):
  self.assertEqual(missing(UIAUDIT.read_text(),UIAUDIT_PROHIBITIONS),[])
  self.assertEqual(missing(DESIGNPASS.read_text(),DESIGNPASS_PREFLIGHT),[])
  self.assertTrue(missing(UIAUDIT.read_text().replace('stays in the report','is dropped from the report'),UIAUDIT_PROHIBITIONS))
  self.assertTrue(missing(UIAUDIT.read_text().replace('is not by itself a cue','is a cue'),UIAUDIT_PROHIBITIONS))
  self.assertTrue(missing(DESIGNPASS.read_text().replace('does not replace it','replaces it'),DESIGNPASS_PREFLIGHT))
 def test_required_prohibition_guard_catches_a_dropped_negation(self):
  self.assertTrue(missing(REVIEW.read_text().replace('does not make it pass','makes it pass'),REVIEW_PROHIBITIONS))
 # later owner distinctions and attribution
 def test_compatible_and_extends_concept_keep_the_accepted_norm_distinction(self):
  text=CONCEPT.read_text()
  self.assertEqual(concept_outcome_violations(text),[])
  self.assertTrue(concept_outcome_violations(text.replace('under the norm already accepted for this role and context','under any norm')))
 def test_attribution_stays_required(self):
  self.assertEqual(missing(CONTRACT.read_text(),ATTRIBUTION['contract']),[])
  self.assertEqual(missing(AUDIT.read_text(),ATTRIBUTION['audit']),[])
  self.assertTrue(missing(CONTRACT.read_text().replace('results are attributed by','results may be attributed by'),ATTRIBUTION['contract']))
if __name__=='__main__':unittest.main(verbosity=2)
