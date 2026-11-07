/* Deterministic public-function boundary tests, not browser rendering evidence. */
const assert = require('node:assert/strict');
const measureUI = require('../../skills/ui-measurements/scripts/measure-ui.cjs');
const context = { revision: 'r1', state: 'ready', fixture: 'seed1', evidence: 'test:boundary', route: '/fixture', settled: true };
const fit = { id: 'label', kind: 'fit', selector: '#label' };
const config = () => ({ context: { ...context }, checks: [{ ...fit }] });
const invalid = [null, {}, { ...config(), checks: [{ ...fit, axis: 'unknown' }] }, { ...config(), checks: [{ ...fit, axis: 'x', scrollX: { reason: 'table', evidence: 'contract' } }] }, { ...config(), context: { ...context, privateDump: 'must-not-be-copied' } }, { ...config(), checks: [] }, { ...config(), checks: Array(33).fill(fit) },
  { ...config(), tolerance: -1 }, { ...config(), tolerance: Infinity }, { ...config(), tolerance: 3 },
  { ...config(), context: { ...context, revision: '' } },
  { ...config(), checks: [{ ...fit, selector: 'x'.repeat(257) }] },
  { ...config(), checks: [fit, fit] }, { ...config(), checks: [{ ...fit, kind: 'unknown' }] },
  { ...config(), checks: [{ ...fit, kind: 'contrast', minimum: NaN, source: 'agreement' }] },
  { ...config(), checks: [{ ...fit, kind: 'contrast', minimum: 0, source: 'agreement' }] },
  { ...config(), checks: [{ ...fit, kind: 'contrast', minimum: 22, source: 'agreement' }] },
  { ...config(), checks: [{ ...fit, kind: 'contrast', minimum: 4.5, source: '' }] },
  { ...config(), checks: [{ ...fit, scrollX: { reason: '', evidence: 'contract' } }] },
  { ...config(), checks: [{ ...fit, kind: 'text', expected: 42 }] },
  { ...config(), checks: [{ ...fit, kind: 'text', expected: 'x'.repeat(2049) }] }];
invalid.push(
  { ...config(), extra: true }, { ...config(), checks: {} }, { ...config(), checks: [null] },
  { ...config(), context: { ...context, state: 'x'.repeat(513) } },
  { ...config(), context: { ...context, settled: 'yes' } },
  { ...config(), context: { ...context, declaredZoom: 100 } },
  { ...config(), checks: [{ ...fit, id: 'x'.repeat(81) }] },
  { ...config(), checks: [{ ...fit, selector: '' }] },
  { ...config(), checks: [{ ...fit, scrollX: null }] },
  { ...config(), checks: [{ ...fit, axis: 'y', scrollX: { reason: 'table', evidence: 'contract' } }] },
  { ...config(), checks: [{ ...fit, scrollX: { reason: 'table', evidence: '' } }] },
  { ...config(), checks: [{ ...fit, scrollX: { reason: 'table', evidence: 'contract', extra: true } }] },
  { ...config(), checks: [{ ...fit, kind: 'contrast', minimum: '4.5', source: 'agreement' }] },
  { ...config(), checks: [{ ...fit, kind: 'text', expected: '', fixture: null }] },
  { ...config(), checks: [{ ...fit, kind: 'text', expected: '', fixture: { stable: 'yes' } }] },
  { ...config(), checks: [{ ...fit, kind: 'text', expected: '', fixture: { id: 1 } }] },
  { ...config(), checks: [{ ...fit, kind: 'text', expected: '', fixture: { source: 'x'.repeat(513) } }] },
  { ...config(), checks: [{ ...fit, kind: 'text', expected: '', fixture: { extra: true } }] }
);
for (const c of invalid) assert.throws(() => measureUI(c), /^Error: Invalid UI measurement config$/, 'invalid config must fail before browser access');
console.log('PASS bounded fail-closed configuration');
const baseStyle = { display: 'block', visibility: 'visible', opacity: '1', contentVisibility: 'visible', filter: 'none', backdropFilter: 'none', mixBlendMode: 'normal', transform: 'none', perspective: 'none', clipPath: 'none', maskImage: 'none', webkitMaskImage: 'none', backgroundImage: 'none', backgroundBlendMode: 'normal', backgroundClip: 'border-box', color: 'rgb(0, 0, 0)', backgroundColor: 'rgb(255, 255, 255)', textShadow: 'none', boxShadow: 'none', textIndent: '0px', webkitTextFillColor: 'rgb(0, 0, 0)', webkitTextStrokeWidth: '0px', fontSize: '16px', fontWeight: '400', overflowX: 'visible', overflowY: 'visible' };
const node = { namespaceURI: 'http://www.w3.org/1999/xhtml', children: [], textContent: '42', parentElement: null, clientWidth: 60, scrollWidth: 60, clientHeight: 20, scrollHeight: 20, style: { ...baseStyle }, getClientRects: () => [{}], getAnimations: () => [] };
global.window = { location: { pathname: '/fixture' }, innerWidth: 390, innerHeight: 844, devicePixelRatio: 2, visualViewport: { scale: 1 } }; window.top = window;
global.document = { fonts: { status: 'loaded' }, querySelectorAll: () => [node] };
global.getComputedStyle = (n, pseudo) => pseudo ? { ...n.style, backgroundColor: 'rgba(0, 0, 0, 0)', content: 'none' } : n.style;
const one = c => measureUI(c).checks[0];
assert.equal(one(config()).status, 'PASS');
for (const change of [c => { c.context.route = '/other'; }, c => { c.context.settled = false; }]) {
  const c = config(); change(c); assert.equal(one(c).status, 'NOT_TESTED');
}
document.fonts.status = 'loading'; assert.equal(one(config()).status, 'NOT_TESTED'); document.fonts.status = 'loaded';
for (const style of [{ display: 'none' }, { visibility: 'hidden' }, { visibility: 'collapse' }, { opacity: '0' }, { contentVisibility: 'hidden' }, { contentVisibility: 'auto' }]) {
  node.parentElement = { style: { ...baseStyle, ...style }, getAnimations: () => [] };
  assert.equal(one(config()).status, 'NOT_TESTED', 'unrendered ancestor must not pass');
}
node.parentElement = null;
for (const animation of [{ playState: 'running' }, { playState: 'paused' }, { playState: 'idle', pending: true }]) {
  node.getAnimations = () => [animation]; assert.equal(one(config()).status, 'NOT_TESTED');
}
node.getAnimations = () => [];
console.log('PASS runtime route, stable render and visibility boundaries');

node.scrollHeight = 200;
assert.equal(one({ ...config(), checks: [{ ...fit, axis: 'x' }] }).status, 'PASS');
assert.equal(one({ ...config(), checks: [{ ...fit, axis: 'y' }] }).status, 'FAIL');
node.scrollHeight = 20;
const t = { ...fit, kind: 'text', expected: '42', fixture: { id: 'seed1', stable: true, source: 'seed:r1' } };
node.textContent = 'x'.repeat(2049);
const large = one({ ...config(), checks: [t] }); assert.equal(large.status, 'NOT_TESTED'); assert.equal(large.actual.value, undefined);
node.textContent = '42';
console.log('PASS explicit axes and bounded text evidence');
const cc = () => ({ ...config(), checks: [{ id: 'contrast', kind: 'contrast', selector: '#label', minimum: 4.5, source: 'agreed normal-text requirement' }] });
for (const change of [
  { opacity: '.5' }, { filter: 'blur(1px)' }, { backdropFilter: 'blur(1px)' }, { mixBlendMode: 'multiply' },
  { transform: 'matrix(1,0,0,1,1,0)' }, { perspective: '1px' }, { clipPath: 'inset(1px)' },
  { maskImage: 'linear-gradient(black,transparent)' }, { webkitMaskImage: 'url(mask)' },
  { backgroundImage: 'linear-gradient(black,white)' }, { backgroundBlendMode: 'multiply' },
  { textShadow: 'black 1px 1px' }, { backgroundClip: 'text' },
  { webkitTextFillColor: 'rgb(255, 0, 0)' }, { webkitTextStrokeWidth: '1px' },
  { color: 'rgba(0, 0, 0, 0.5)', webkitTextFillColor: 'rgba(0, 0, 0, 0.5)' },
  { backgroundColor: 'rgba(255, 255, 255, 0.5)' }, { color: 'color(display-p3 1 0 0)', webkitTextFillColor: 'color(display-p3 1 0 0)' }
]) {
  node.style = { ...baseStyle, ...change }; assert.equal(one(cc()).status, 'NOT_TESTED', 'unsupported paint cannot have a contrast PASS');
}
node.style = { ...baseStyle }; node.parentElement = { style: { ...baseStyle, opacity: '.5' }, getAnimations: () => [] };
assert.equal(one(cc()).status, 'NOT_TESTED'); node.parentElement = null;
for (const [fg, bg, ratio] of [
  ['rgb(0, 0, 0)', 'rgb(255, 255, 255)', 21], ['rgb(255, 255, 255)', 'rgb(0, 0, 0)', 21],
  ['rgb(119, 119, 119)', 'rgb(255, 255, 255)', 4.478089453577214],
  ['rgb(10, 10, 10)', 'rgb(255, 255, 255)', 19.79814571052481],
  ['rgb(255, 0, 0)', 'rgb(255, 255, 255)', 3.9984767707539985],
  ['rgb(0, 255, 0)', 'rgb(255, 255, 255)', 1.3721902770517513],
  ['rgb(0, 0, 255)', 'rgb(255, 255, 255)', 8.592471358428805]
]) {
  node.style = { ...baseStyle, color: fg, webkitTextFillColor: fg, backgroundColor: bg };
  const result = one(cc()); assert.ok(Math.abs(result.actual.ratio - ratio) < 1e-12);
  assert.equal(result.status, ratio >= 4.5 ? 'PASS' : 'FAIL');
}
node.style = { ...baseStyle }; node.children = [{}]; assert.equal(one(cc()).status, 'NOT_TESTED'); node.children = [];
const originalStyle = global.getComputedStyle;
global.getComputedStyle = (n, pseudo) => pseudo ? { ...n.style, backgroundColor: 'rgba(0, 0, 0, 0)', content: ['::before', '::after'].includes(pseudo) ? '"decorative"' : 'none' } : n.style;
assert.equal(one(cc()).status, 'NOT_TESTED'); global.getComputedStyle = originalStyle;
node.namespaceURI = 'http://www.w3.org/2000/svg'; assert.equal(one(cc()).status, 'NOT_TESTED'); node.namespaceURI = 'http://www.w3.org/1999/xhtml';
node.textContent = ''; assert.equal(one(cc()).status, 'NOT_TESTED');
assert.equal(one({ ...config(), checks: [{ ...t, expected: '' }] }).status, 'PASS'); node.textContent = '42';
assert.equal(one({ ...config(), checks: [{ ...t, fixture: { ...t.fixture, stable: false } }] }).status, 'NOT_TESTED');
assert.equal(one({ ...config(), checks: [{ ...t, fixture: { ...t.fixture, id: 'other' } }] }).status, 'NOT_TESTED');
assert.equal(one({ ...config(), checks: [{ ...t, fixture: { ...t.fixture, source: undefined } }] }).status, 'NOT_TESTED');
node.textContent = '43'; assert.equal(one({ ...config(), checks: [t] }).status, 'FAIL'); node.textContent = '42';
for (const nodes of [[], [node, node]]) { document.querySelectorAll = () => nodes; assert.equal(one(config()).status, 'NOT_TESTED'); }
document.querySelectorAll = () => { throw new Error('bad selector'); }; assert.equal(one(config()).status, 'NOT_TESTED'); document.querySelectorAll = () => [node];
node.clientHeight = 0; assert.equal(one(config()).status, 'NOT_TESTED'); node.clientHeight = 20;
node.getClientRects = () => []; assert.equal(one(config()).status, 'NOT_TESTED'); node.getClientRects = () => [{}];
console.log('PASS contrast paint refusals, worked sRGB pairs, fixture scope and target boundaries');

node.style = { ...baseStyle }; node.scrollWidth = 61;
assert.equal(one(config()).status, 'PASS');
assert.equal(one({ ...config(), tolerance: 0 }).status, 'FAIL');
node.scrollWidth = 62; assert.equal(one(config()).status, 'FAIL');
assert.equal(one({ ...config(), tolerance: 2 }).status, 'PASS');
node.scrollWidth = 63; assert.equal(one({ ...config(), tolerance: 2 }).status, 'FAIL');
node.scrollWidth = 100; const scroll = { ...fit, scrollX: { reason: 'table', evidence: 'approved:table' } };
assert.equal(one({ ...config(), checks: [scroll] }).status, 'FAIL');
node.style.overflowX = 'auto'; assert.equal(one({ ...config(), checks: [scroll] }).status, 'PASS');
node.scrollHeight = 100; assert.equal(one({ ...config(), checks: [scroll] }).status, 'FAIL');
node.scrollWidth = 60; node.scrollHeight = 20; node.style = { ...baseStyle };
const boundary = cc(); boundary.checks[0].minimum = 21; assert.equal(one(boundary).status, 'PASS');
node.style.backgroundColor = 'rgb(0, 0, 0)'; boundary.checks[0].minimum = 1; assert.equal(one(boundary).status, 'PASS');
node.style = { ...baseStyle, color: 'rgba(0, 0, 0, 1)', webkitTextFillColor: 'rgba(0, 0, 0, 1)' }; assert.equal(one(cc()).status, 'PASS');
node.style = { ...baseStyle, color: 'rgb(999, 0, 0)', webkitTextFillColor: 'rgb(999, 0, 0)' }; assert.equal(one(cc()).status, 'NOT_TESTED'); node.style = { ...baseStyle };
const fontState = document.fonts; delete document.fonts; assert.equal(one(config()).status, 'NOT_TESTED'); document.fonts = fontState;
const animations = node.getAnimations; delete node.getAnimations; assert.equal(one(config()).status, 'NOT_TESTED'); node.getAnimations = animations;
node.clientWidth = 0; assert.equal(one(config()).status, 'NOT_TESTED'); node.clientWidth = 60;
node.scrollWidth = 100;
const mixed = measureUI({ ...config(), checks: [fit, { ...t, id: 'fixture', fixture: undefined }] });
assert.equal(mixed.status, 'FAIL'); assert.equal(mixed.checks[1].status, 'NOT_TESTED'); node.scrollWidth = 60;
assert.equal(measureUI({ ...config(), checks: [{ ...t, fixture: undefined }] }).status, 'NOT_TESTED');
console.log('PASS finite boundaries, intentional-scroll conditions and aggregate honesty');
assert.equal(one({ ...config(), checks: [{ ...fit, axis: 'y' }] }).expected.horizontal, 'not-requested');

node.style = { ...baseStyle, boxShadow: 'black 0px 0px 100px inset' }; assert.equal(one(cc()).status, 'NOT_TESTED');
node.style = { ...baseStyle, textIndent: '-20px' }; assert.equal(one(cc()).status, 'NOT_TESTED');
node.style = { ...baseStyle, backgroundClip: 'content-box' }; assert.equal(one(cc()).status, 'NOT_TESTED');
node.style = { ...baseStyle }; node.scrollWidth = 100; assert.equal(one(cc()).status, 'NOT_TESTED'); node.scrollWidth = 60;

node.scrollWidth = 100; node.style.overflowX = 'auto';
assert.deepEqual(one({ ...config(), checks: [scroll] }).expected.scrollX, scroll.scrollX);
node.scrollWidth = 60; node.style = { ...baseStyle };

for (const target of ['::first-letter', '::first-line']) {
  global.getComputedStyle = (n, pseudo) => pseudo ? { ...n.style, backgroundColor: 'rgba(0, 0, 0, 0)', content: 'none', ...(pseudo === target ? { color: 'rgb(255, 255, 255)' } : {}) } : n.style;
  assert.equal(one(cc()).status, 'NOT_TESTED');
}
global.getComputedStyle = originalStyle;

node.scrollHeight = 100; assert.equal(one(cc()).status, 'NOT_TESTED'); node.scrollHeight = 20;
const observed = measureUI(config());
assert.deepEqual(observed.context, context); assert.equal(observed.checks.length, 1);
assert.deepEqual(observed.actual, { route: '/fixture', viewport: { width: 390, height: 844, dpr: 2, visualScale: 1 }, frame: 'top' });
assert.equal(observed.checks[0].id, 'label'); assert.equal(observed.checks[0].kind, 'fit'); assert.equal(observed.checks[0].selector, '#label');
assert.deepEqual(observed.checks[0].expected, { horizontal: 'fit', vertical: 'fit', axis: 'both', tolerance: 1, scrollX: null });
assert.deepEqual(observed.checks[0].actual, { clientWidth: 60, scrollWidth: 60, clientHeight: 20, scrollHeight: 20, overflowX: 'visible', overflowY: 'visible' });
const contrastRow = one(cc());
assert.deepEqual(contrastRow.expected, { minimum: 4.5, source: 'agreed normal-text requirement' });
assert.deepEqual(contrastRow.actual.foreground, [0, 0, 0]); assert.deepEqual(contrastRow.actual.background, [255, 255, 255]);
assert.equal(contrastRow.actual.fontSize, '16px'); assert.equal(contrastRow.actual.fontWeight, '400');
assert.deepEqual(one({ ...config(), checks: [t] }).expected, { value: '42', fixture: 'seed1', source: 'seed:r1' });
const unknownFixture = one({ ...config(), checks: [{ ...t, fixture: undefined }] });
assert.deepEqual(unknownFixture.expected, { value: '42', fixture: null, source: null }); assert.equal(unknownFixture.actual, null);
const savedViewport = window.visualViewport; window.visualViewport = undefined;
assert.equal(measureUI(config()).actual.viewport.visualScale, null); window.visualViewport = savedViewport;
for (const [key, value] of Object.entries({ color: 'rgb(255, 255, 255)', backgroundImage: 'linear-gradient(black,white)', textShadow: 'black 1px 1px', boxShadow: 'inset 0 0 10px black', webkitTextFillColor: 'rgb(255, 0, 0)', webkitTextStrokeWidth: '1px', filter: 'blur(1px)', mixBlendMode: 'multiply', opacity: '.5', transform: 'translateX(1px)', clipPath: 'inset(1px)', maskImage: 'url(mask)' })) {
  global.getComputedStyle = (n, pseudo) => pseudo ? { ...n.style, backgroundColor: 'rgba(0, 0, 0, 0)', content: 'none', ...(pseudo === '::first-letter' ? { [key]: value } : {}) } : n.style;
  assert.equal(one(cc()).status, 'NOT_TESTED');
}
for (const backgroundColor of ['rgb(255, 0, 0)', 'rgba(0, 0, 0, 0.5)']) {
  global.getComputedStyle = (n, pseudo) => pseudo ? { ...n.style, backgroundColor: pseudo === '::first-line' ? backgroundColor : 'rgba(0, 0, 0, 0)', content: 'none' } : n.style;
  assert.equal(one(cc()).status, 'NOT_TESTED');
}
global.getComputedStyle = originalStyle;
console.log('PASS evidence serialization and pseudo-text paint boundaries');
node.scrollWidth = 100; node.style.overflowX = 'scroll'; assert.equal(one({ ...config(), checks: [scroll] }).status, 'PASS'); node.scrollWidth = 60; node.style = { ...baseStyle };
window.innerWidth = 0; assert.equal(one(config()).status, 'NOT_TESTED'); window.innerWidth = 390;
for (const [key, value] of Object.entries({ revision: '', state: '', fixture: '', evidence: '', route: '' })) {
  assert.throws(() => measureUI({ ...config(), context: { ...context, [key]: value } }), /Invalid UI measurement config/);
}
for (const c of [
  { ...config(), tolerance: NaN }, { ...config(), checks: [{ ...fit, kind: 'text', expected: '', fixture: [] }] },
  { ...config(), context: { ...context, state: { length: 1 } } },
  { ...config(), checks: [{ ...fit, extra: true }] }
]) assert.throws(() => measureUI(c), /Invalid UI measurement config/);
assert.equal(measureUI({ ...config(), checks: Array.from({ length: 32 }, (_, i) => ({ ...fit, id: 'row' + i })) }).checks.length, 32);
assert.equal(one({ ...config(), checks: [{ ...fit, id: 'x'.repeat(80), selector: 'x'.repeat(256) }] }).status, 'PASS');
assert.equal(one({ ...config(), context: { ...context, state: 'x'.repeat(512), declaredZoom: '100%' } }).status, 'PASS');
for (const fixture of [{}, { stable: true }, { stable: true, id: 'seed1' }, { stable: true, source: 'seed:r1' }]) {
  assert.equal(one({ ...config(), checks: [{ ...t, fixture }] }).reason, 'stable-fixture-not-established');
}
node.textContent = 'x'.repeat(2048);
assert.equal(one({ ...config(), checks: [{ ...t, expected: 'x'.repeat(2048) }] }).status, 'PASS'); node.textContent = '42';
for (const dimension of ['innerWidth', 'innerHeight']) {
  const old = window[dimension];
  for (const value of [0, Infinity, NaN]) { window[dimension] = value; assert.equal(one(config()).reason, 'viewport-unavailable'); }
  window[dimension] = old;
}
assert.equal(one({ ...config(), context: { ...context, route: '/wrong' } }).reason, 'route-mismatch');
assert.equal(one({ ...config(), context: { ...context, settled: false } }).reason, 'state-not-settled');
document.fonts.status = 'loading'; assert.equal(one(config()).reason, 'fonts-not-settled'); document.fonts.status = 'loaded';
node.getAnimations = undefined; assert.equal(one(config()).reason, 'animation-state-unavailable'); node.getAnimations = () => [{ playState: 'running' }];
assert.equal(one(config()).reason, 'active-animation'); node.getAnimations = () => [];
node.clientWidth = 0; assert.equal(one(config()).reason, 'unrendered-target'); node.clientWidth = 60;
node.namespaceURI = 'http://www.w3.org/2000/svg'; assert.equal(one(config()).reason, 'non-html-target'); node.namespaceURI = 'http://www.w3.org/1999/xhtml';
node.children = [{}]; assert.equal(one(cc()).reason, 'unsupported-text-target'); node.children = [];
node.style.opacity = '.5'; assert.equal(one(cc()).reason, 'unsupported-compositing'); node.style = { ...baseStyle };
node.style.backgroundImage = 'linear-gradient(black,white)'; assert.equal(one(cc()).reason, 'unsupported-paint'); node.style = { ...baseStyle };
node.style.backgroundColor = 'rgba(255, 255, 255, 0.5)'; assert.equal(one(cc()).reason, 'non-opaque-or-non-srgb'); node.style = { ...baseStyle };
node.textContent = 'x'.repeat(2049); assert.equal(one({ ...config(), checks: [t] }).reason, 'oversized-text'); node.textContent = '42';
for (const [nodes, reason] of [[[], 'missing-target'], [[node, node], 'ambiguous-target']]) { document.querySelectorAll = () => nodes; assert.equal(one(config()).reason, reason); }
document.querySelectorAll = () => { throw new Error('bad selector'); }; assert.equal(one(config()).reason, 'invalid-selector'); document.querySelectorAll = () => [node];
global.getComputedStyle = (n, pseudo) => pseudo ? { ...n.style, backgroundColor: 'rgba(0, 0, 0, 0)', content: 'none', ...(pseudo === '::first-letter' ? { color: 'rgb(255, 255, 255)' } : {}) } : n.style;
assert.equal(one(cc()).reason, 'unsupported-pseudo-paint'); global.getComputedStyle = originalStyle;
console.log('PASS complete input boundaries and actionable fixed reasons');
node.textContent = ' 42 '; assert.equal(one({ ...config(), checks: [t] }).status, 'FAIL'); node.textContent = '42';
node.style.webkitTextFillColor = undefined; node.style.webkitTextStrokeWidth = undefined; assert.equal(one(cc()).status, 'PASS'); node.style = { ...baseStyle };
assert.equal(one({ ...config(), checks: [{ ...scroll, axis: 'both' }] }).status, 'PASS');

assert.throws(() => measureUI({ ...config(), context: { ...context, state: '   ' } }), /Invalid UI measurement config/);
assert.throws(() => measureUI({ ...config(), checks: [{ ...t, fixture: 42 }] }), /Invalid UI measurement config/);
node.textContent = '   '; assert.equal(one(cc()).status, 'NOT_TESTED');
assert.equal(one({ ...config(), checks: [{ ...t, expected: '   ' }] }).status, 'PASS'); node.textContent = '42';

for (const c of [{ ...config(), context: null }, { ...config(), checks: Array.from({ length: 33 }, (_, i) => ({ ...fit, id: 'row' + i })) }]) assert.throws(() => measureUI(c), /^Error: Invalid UI measurement config$/);
node.scrollWidth = 100; node.style.overflowX = 'auto';
assert.equal(one(config()).status, 'FAIL');
const allowedScroll = one({ ...config(), checks: [scroll] }); assert.equal(allowedScroll.expected.horizontal, 'fit-or-local-scroll'); assert.equal(allowedScroll.expected.vertical, 'fit');
assert.equal(one({ ...config(), checks: [{ ...fit, axis: 'y' }] }).status, 'PASS');
node.scrollWidth = 60; node.style = { ...baseStyle };
