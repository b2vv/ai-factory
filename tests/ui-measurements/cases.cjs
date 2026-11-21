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

/* style kind: deterministic boundaries with stubbed DOM (not browser rendering evidence). */
(() => {
const LIMIT = 1048576;
const bytes = v => new TextEncoder().encode(v).length;
const context = { revision: 'r1', state: 'ready', fixture: 'seed1', evidence: 'test:style', route: '/fixture', settled: true };
const style = (over = {}) => ({ id: 's', kind: 'style', selector: '.t', properties: ['padding-top'], ...over });
const cfg = (...checks) => ({ context: { ...context }, checks });
const styleArray = r => bytes(JSON.stringify(r.checks.filter(c => c.kind === 'style')));

// 1. Invalid configuration throws before any page read (recording proxies + control).
const reads = [];
const recorder = name => new Proxy(function () {}, { get(_, k) { reads.push(name + '.' + String(k)); return undefined; }, apply() { reads.push(name + '()'); return undefined; } });
global.window = recorder('window'); global.document = recorder('document'); global.getComputedStyle = recorder('getComputedStyle');
const invalid = [style({ properties: ['padding'] }), style({ properties: ['unknown-prop'] }), style({ properties: ['color', 'color'] }),
  style({ properties: Array(17).fill(0).map((_, i) => ['color', 'opacity', 'display', 'position', 'width', 'height', 'min-width', 'min-height', 'row-gap', 'column-gap', 'font-size', 'font-weight', 'font-style', 'line-height', 'letter-spacing', 'text-transform', 'background-color'][i]) }),
  style({ properties: [] }), style({ properties: 'color' }), style({ properties: [1] }), style({ limit: 0 }), style({ limit: 51 }), style({ limit: 1.5 }), style({ limit: '2' }),
  style({ extra: true }), style({ properties: ['background-image'] }), style({ properties: ['--token'] })];
for (const c of invalid) { reads.length = 0; assert.throws(() => measureUI(cfg(c)), /^Error: Invalid UI measurement config$/); assert.deepEqual(reads, [], 'no page reads before throw'); }
for (const ctx of [{ colorScheme: 1 }, { colorScheme: '' }, { colorScheme: 'x'.repeat(513) }]) {
  reads.length = 0; assert.throws(() => measureUI({ context: { ...context, ...ctx }, checks: [style()] }), /Invalid UI measurement config/); assert.deepEqual(reads, []);
}
reads.length = 0; try { measureUI(cfg(style())); } catch (_) {} assert.ok(reads.length > 0, 'control: the recorder detects page reads');
console.log('PASS style config fails closed before page reads (with recorder control)');

// Stub DOM.
const HTML = 'http://www.w3.org/1999/xhtml';
const base = { display: 'block', visibility: 'visible', opacity: '1', contentVisibility: 'visible' };
let values = {};
function el(over = {}) {
  const inline = over.inline || [];
  return { namespaceURI: HTML, localName: 'div', parentElement: null, clientWidth: 10, clientHeight: 10, shadowRoot: null,
    getClientRects: () => [{}], getAnimations: () => [], getBoundingClientRect: () => ({ width: 112.4, height: 63.6 }),
    getAttribute: k => (k === 'role' ? over.role ?? null : null), cs: { ...base, ...(over.cs || {}) },
    style: { length: inline.length, item: i => inline[i] }, ...over };
}
let nodes = [];
global.window = { location: { pathname: '/fixture' }, innerWidth: 390, innerHeight: 844, devicePixelRatio: 1, visualViewport: { scale: 1 },
  matchMedia: q => ({ matches: q === '(prefers-color-scheme: light)' }) };
window.top = window;
global.document = { fonts: { status: 'loaded' }, adoptedStyleSheets: [],
  querySelectorAll: sel => sel === '*' ? nodes : sel === 'iframe, frame' || sel === 'canvas' ? [] : sel === '((' ? (() => { throw new Error('bad'); })() : nodes };
global.getComputedStyle = n => ({ ...n.cs, getPropertyValue: p => (p in (n.values || values) ? (n.values || values)[p] : '') });
values = { 'padding-top': '9px', 'line-height': 'normal', 'font-family': '"Inter Display", system-ui, sans-serif', 'box-shadow': 'rgba(0, 0, 0, 0.2) 0px 1px 2px 0px, rgb(0, 0, 0) 0px 0px 0px 1px' };

// 2. Exact values, derived fields, privacy-shaped output.
nodes = [el({ role: 'group', inline: ['padding-top', 'padding-left'] })];
let r = measureUI({ context: { ...context, colorScheme: 'dark' }, checks: [style({ properties: ['padding-top', 'line-height', 'font-family', 'box-shadow'] })] });
let row = r.checks[0];
assert.equal(row.status, 'OBSERVED'); assert.equal(row.reason, undefined); assert.equal(r.status, 'OBSERVED'); assert.equal(r.styleStatus, 'OBSERVED');
assert.deepEqual(row.elements[0], { index: 0, tag: 'div', ariaRole: 'group', box: { width: 112, height: 64 },
  values: { 'padding-top': '9px', 'line-height': 'normal' }, derived: { 'font-family-first': 'Inter Display', 'box-shadow-layers': 2 },
  inlineProperties: ['padding-top', 'padding-left'], oversized: [] });
assert.deepEqual(row.untraversed, { openShadowHosts: 0, iframes: 0, canvases: 0, constructedSheets: 0 });
assert.equal(r.context.colorScheme, 'dark'); assert.deepEqual(r.actual.media, { prefersColorScheme: 'light', forcedColors: 'none' });
values['box-shadow'] = 'none'; values['font-family'] = 'Arial'; row = measureUI(cfg(style({ properties: ['font-family', 'box-shadow'] }))).checks[0];
assert.deepEqual(row.elements[0].derived, { 'font-family-first': 'Arial', 'box-shadow-layers': 0 }); assert.deepEqual(row.elements[0].values, {});
console.log('PASS exact strings, derived fields, media echo');

// 3. Matching per helper: raw count, limit-1 ambiguity, window consumed by skips, truncated, index.
const hidden = () => el({ clientWidth: 0 });
nodes = [el(), el(), el()]; row = measureUI(cfg(style())).checks[0];
assert.equal(row.status, 'NOT_TESTED'); assert.equal(row.reason, 'ambiguous-target'); assert.equal(row.matched, 3);
nodes = [el(), hidden()]; assert.equal(measureUI(cfg(style())).checks[0].reason, 'ambiguous-target');
nodes = [el(), el(), el()]; row = measureUI(cfg(style({ limit: 2 }))).checks[0];
assert.deepEqual([row.status, row.matched, row.returned, row.truncated], ['OBSERVED', 3, 2, true]);
assert.equal(measureUI(cfg(style({ limit: 3 }))).checks[0].truncated, false);
nodes = [hidden(), el(), el()]; row = measureUI(cfg(style({ limit: 2 }))).checks[0];
assert.deepEqual([row.returned, row.skipped['unrendered-target'], row.elements[0].index, row.truncated], [1, 1, 1, true]);
console.log('PASS raw-count matching, window and truncation');

// 4. Skip buckets and reason order.
const svg = () => el({ namespaceURI: 'http://www.w3.org/2000/svg' });
const anim = () => el({ getAnimations: () => [{ playState: 'running' }] });
const noAnim = () => el({ getAnimations: undefined });
const contents = () => el({ getClientRects: () => [] });
nodes = [hidden(), contents(), anim(), svg(), noAnim(), el()]; row = measureUI(cfg(style({ limit: 6 }))).checks[0];
assert.equal(row.status, 'OBSERVED');
assert.deepEqual(row.skipped, { 'non-html-target': 1, 'unrendered-target': 2, 'animation-state-unavailable': 1, 'active-animation': 1 });
assert.equal(row.returned + Object.values(row.skipped).reduce((a, b) => a + b), 6);
nodes = [anim(), hidden(), svg()]; row = measureUI(cfg(style({ limit: 3 }))).checks[0]; assert.equal(row.reason, 'non-html-target');
nodes = [anim(), hidden()]; assert.equal(measureUI(cfg(style({ limit: 2 }))).checks[0].reason, 'unrendered-target');
nodes = [anim(), noAnim()]; assert.equal(measureUI(cfg(style({ limit: 2 }))).checks[0].reason, 'animation-state-unavailable');
nodes = [anim()]; assert.equal(measureUI(cfg(style())).checks[0].reason, 'active-animation');
console.log('PASS skip buckets and fixed reason order');

// 5. Existing reasons.
nodes = []; assert.equal(measureUI(cfg(style())).checks[0].reason, 'missing-target');
assert.equal(measureUI(cfg(style({ selector: '((' }))).checks[0].reason, 'invalid-selector');
nodes = [el()]; assert.equal(measureUI({ context: { ...context, route: '/other' }, checks: [style()] }).checks[0].reason, 'route-mismatch');
document.fonts.status = 'loading'; assert.equal(measureUI(cfg(style())).checks[0].reason, 'fonts-not-settled'); document.fonts.status = 'loaded';
console.log('PASS existing reason strings');

// 6/12/12a. Byte caps.
const big = 'ж'.repeat(65);                 // 130 B (2-byte chars), > 128
values = { 'font-family': big, 'padding-top': 'x'.repeat(256), 'margin-top': 'x'.repeat(257), color: 'rgb(0, 0, 0)' };
nodes = [el({ localName: 'x-' + 'a'.repeat(63), role: 'r'.repeat(65), inline: ['--' + 'n'.repeat(63), ...Array(40).fill(0).map((_, i) => 'p' + i)] })];
let e = measureUI(cfg(style({ properties: ['font-family', 'padding-top', 'margin-top', 'color'] }))).checks[0].elements[0];
assert.equal(e.tag, null); assert.equal(e.ariaRole, null);
assert.deepEqual(e.oversized.sort(), ['ariaRole', 'font-family-first', 'inlineProperties', 'margin-top', 'tag']);
assert.equal(e.values['padding-top'].length, 256); assert.equal('margin-top' in e.values, false); assert.equal('font-family-first' in e.derived, false);
assert.equal(e.inlineProperties.length, 32); assert.equal(e.inlinePropertiesTruncated, true);
values = { 'font-family': 'a'.repeat(128) }; nodes = [el({ localName: 'x-' + 'a'.repeat(62), role: 'r'.repeat(64) })];
e = measureUI(cfg(style({ properties: ['font-family'] }))).checks[0].elements[0];
assert.equal(e.derived['font-family-first'].length, 128); assert.equal(e.tag.length, 64); assert.equal(e.ariaRole.length, 64); assert.deepEqual(e.oversized, []);
console.log('PASS UTF-8 field caps at and over each bound');

// 8. Element budget 400 / 401.
nodes = Array(50).fill(0).map(() => el()); values = { 'padding-top': '1px' };
const eight = n => Array(n).fill(0).map((_, i) => style({ id: 'b' + i, limit: 50 }));
r = measureUI(cfg(...eight(8))); assert.ok(r.checks.every(c => c.status === 'OBSERVED')); assert.equal(r.checks.reduce((a, c) => a + c.returned, 0), 400);
r = measureUI(cfg(...eight(8), style({ id: 'extra', limit: 2 }), style({ id: 'later', selector: '.other' })));
nodes = Array(50).fill(0).map(() => el());
assert.equal(r.checks[8].reason, 'budget'); assert.equal(r.checks[9].reason, 'budget'); assert.deepEqual(Object.keys(r.checks[8]), ['id', 'kind', 'selector', 'status', 'reason']);
assert.ok(r.checks.slice(0, 8).every(c => c.status === 'OBSERVED'));
console.log('PASS element budget at 400 and 401');

// 13. Byte budget: exact bound, reserve, escaping.
function sized(target, checks) {     // find a padding value length so the style array is exactly target bytes
  for (let pad = 0; pad < 300; pad++) {
    values = { 'padding-top': 'q'.repeat(pad) };
    const r = measureUI(cfg(...checks));
    if (styleArray(r) === target) return { r, pad };
  }
  return null;
}
nodes = Array(50).fill(0).map(() => el());
// Each 50-element row is ~ 50 * per-element bytes; use many checks and stretch with long values via a big shared value set.
values = {};
const props = ['padding-top', 'padding-right', 'padding-bottom', 'padding-left', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left', 'width', 'height', 'min-width', 'min-height', 'row-gap', 'column-gap', 'color', 'opacity'];
const fat = (id, sel = '.t') => style({ id, selector: sel, limit: 50, properties: props });
function fill(len) { values = Object.fromEntries(props.map(p => [p, 'v'.repeat(len)])); }
fill(256);
r = measureUI(cfg(...Array(8).fill(0).map((_, i) => fat('f' + i))));
const perRow = bytes(JSON.stringify(r.checks[0]));
assert.ok(styleArray(r) > LIMIT || r.checks.some(c => c.reason === 'budget'), 'fixture large enough to reach the byte budget');
assert.ok(styleArray(r) <= LIMIT, 'serialized style array never exceeds the bound');
const firstBudget = r.checks.findIndex(c => c.reason === 'budget'); assert.ok(firstBudget > 0);
assert.ok(r.checks.slice(firstBudget).every(c => c.reason === 'budget'));
// escaping and multibyte in ids/selectors are counted
const tricky = (i) => fat('id"\\ж' + i, '.t');
r = measureUI(cfg(...Array(8).fill(0).map((_, i) => tricky(i)), style({ id: '\u0001"\\'.repeat(20), selector: '.z' })));
assert.ok(styleArray(r) <= LIMIT);
// exact bound on the last row (reserve is 0 for the last style check)
const route = map => { document.querySelectorAll = sel => sel === '*' || sel === 'iframe, frame' || sel === 'canvas' ? [] : (map[sel] || []); };
const fatNodes = Array(50).fill(0).map(() => el()); const medNodes = Array(50).fill(0).map(() => el({ values: { color: 'm'.repeat(256) } }));
const lastNodes = Array(50).fill(0).map(() => el({ values: Object.fromEntries(props.map(p => [p, ''])) }));
route({ '.t': fatNodes, '.m': medNodes, '.last': lastNodes }); fill(256);
const last = style({ id: 'last', selector: '.last', limit: 50, properties: props });
const checks = [];
while (true) {
  const probe = measureUI(cfg(...checks, fat('f' + checks.length), last));
  if (probe.checks.some(c => c.reason === 'budget')) break; checks.push(fat('f' + checks.length));
}
let probe, exact = false;
while (true) {
  probe = measureUI(cfg(...checks, last)); const gap = LIMIT - styleArray(probe);
  if (gap <= 50 * 16 * 256) break; checks.push(style({ id: 'm' + checks.length, selector: '.m', limit: 50, properties: ['color'] }));
}
let left = LIMIT - styleArray(probe);
for (const ln of lastNodes) for (const p of props) { const add = Math.min(256, left); ln.values[p] = 'c'.repeat(add); left -= add; }
const hit = measureUI(cfg(...checks, last));
assert.equal(styleArray(hit), LIMIT); assert.equal(hit.checks.at(-1).status, 'OBSERVED'); exact = true;
const slot = lastNodes.flatMap(ln => props.map(p => [ln, p])).find(([ln, p]) => ln.values[p].length < 256);
slot[0].values[slot[1]] += 'c';
const over = measureUI(cfg(...checks, last)); assert.equal(over.checks.at(-1).reason, 'budget'); assert.ok(styleArray(over) <= LIMIT);
// a row that fits alone but not with the reserve of later checks becomes budget, and later rows too
slot[0].values[slot[1]] = slot[0].values[slot[1]].slice(0, -1);   // back to exactly LIMIT
assert.equal(styleArray(measureUI(cfg(...checks, last))), LIMIT);
const withTail = measureUI(cfg(...checks, last, style({ id: 'tail', selector: '.m', limit: 2 })));
assert.equal(withTail.checks.at(-2).reason, 'budget'); assert.equal(withTail.checks.at(-1).reason, 'budget'); assert.ok(styleArray(withTail) <= LIMIT);
assert.ok(exact, 'a last style row landing exactly on the byte bound is kept');
console.log('PASS byte budget: bound never exceeded, exact last-row bound kept, overflow becomes budget, escaping counted');

// 9/14. Aggregate.
document.querySelectorAll = sel => sel === '*' ? [] : sel === 'iframe, frame' || sel === 'canvas' ? [] : sel === '#fit' ? [fitNode] : sel === '#none' ? [] : nodes;
const fitNode = el({ textContent: '', children: [], scrollWidth: 10, scrollHeight: 10, cs: { ...base, overflowX: 'visible', overflowY: 'visible' } });
values = { 'padding-top': '1px' }; nodes = [];
r = measureUI(cfg({ id: 'fit', kind: 'fit', selector: '#fit' }, style()));
assert.equal(r.status, 'PASS'); assert.equal(r.styleStatus, 'NOT_TESTED');
r = measureUI(cfg(style())); assert.equal(r.status, 'NOT_TESTED'); assert.notEqual(r.status, 'PASS');
nodes = [el()]; r = measureUI(cfg(style(), style({ id: 'm', selector: '#none' })));
assert.equal(r.status, 'OBSERVED'); assert.equal(r.styleStatus, 'NOT_TESTED');
r = measureUI(cfg({ id: 'fit', kind: 'fit', selector: '#fit' })); assert.equal(r.styleStatus, undefined); assert.equal(r.actual.media, undefined);
console.log('PASS aggregate excludes style rows; style-only never PASS');
})();

/* Whole serialized report bound (2 MiB), route echo cap, sparse properties, escaped font families. */
(() => {
const bytes = v => new TextEncoder().encode(v).length;
const REPORT = 2097152;
const HTML = 'http://www.w3.org/1999/xhtml';
const ctx = (over = {}) => ({ revision: 'r', state: 's', fixture: 'f', evidence: 'e', route: '/x', settled: true, ...over });
const reads = [];
const recorder = name => new Proxy(function () {}, { get(_, k) { reads.push(name + '.' + String(k)); return undefined; }, apply() { reads.push(name + '()'); } });
global.window = recorder('window'); global.document = recorder('document'); global.getComputedStyle = recorder('getComputedStyle');
for (const properties of [Array(1), [, 'color'], ['color', , 'opacity']]) {
  reads.length = 0;
  assert.throws(() => measureUI({ context: ctx(), checks: [{ id: 'a', kind: 'style', selector: '.a', properties }] }), /Invalid UI measurement config/);
  assert.deepEqual(reads, [], 'sparse properties rejected before page reads');
}
console.log('PASS sparse property arrays fail closed before page reads');

let computed = {}, text = '', pv = null;   // pv: values returned by getPropertyValue, when set
const el = (over = {}) => ({ namespaceURI: HTML, localName: 'div', parentElement: null, children: [], clientWidth: 5, clientHeight: 5,
  scrollWidth: 5, scrollHeight: 5, get textContent() { return text; }, getClientRects: () => [{}], getAnimations: () => [],
  getBoundingClientRect: () => ({ width: 5, height: 5 }), getAttribute: () => null, style: { length: 0, item: () => null }, ...over });
const setPage = (pathname, nodes = [el()]) => {
  global.window = { location: { pathname }, innerWidth: 390, innerHeight: 844, devicePixelRatio: 1, visualViewport: { scale: 1 } }; window.top = window;
  global.document = { fonts: { status: 'loaded' }, adoptedStyleSheets: [], querySelectorAll: s => s === '*' || s === 'iframe, frame' || s === 'canvas' ? [] : nodes };
};
const base = { display: 'block', visibility: 'visible', opacity: '1', contentVisibility: 'visible', filter: 'none', backdropFilter: 'none', mixBlendMode: 'normal',
  transform: 'none', perspective: 'none', clipPath: 'none', maskImage: 'none', webkitMaskImage: 'none', backgroundImage: 'none', backgroundBlendMode: 'normal',
  backgroundClip: 'border-box', color: 'rgb(0, 0, 0)', backgroundColor: 'rgb(255, 255, 255)', textShadow: 'none', boxShadow: 'none', textIndent: '0px',
  webkitTextFillColor: 'rgb(0, 0, 0)', webkitTextStrokeWidth: '0px', fontSize: '16px', fontWeight: '400', overflowX: 'visible', overflowY: 'visible', content: 'none' };
global.getComputedStyle = () => ({ ...base, ...computed, getPropertyValue: p => { const m = pv || computed; return p in m ? m[p] : ''; } });
const sizeOf = r => bytes(JSON.stringify(r));

// Escaped font family names are resolved, so distinct names stay distinct.
setPage('/x');
const fam = v => { computed = { 'font-family': v }; return measureUI({ context: ctx(), checks: [{ id: 'f', kind: 'style', selector: '.a', properties: ['font-family'] }] }).checks[0].elements[0].derived['font-family-first']; };
assert.equal(fam('"Alpha\\" Beta", serif'), 'Alpha" Beta');
assert.equal(fam('"A\\\\B", serif'), 'A\\B');
assert.equal(fam("'It\\'s', serif"), "It's");
assert.equal(fam('"\\41 BC", serif'), 'ABC');
assert.equal(fam('Foo\\,Bar, serif'), 'Foo,Bar');
assert.equal(fam('Inter, system-ui'), 'Inter');
assert.notEqual(fam('"Alpha\\" Beta", serif'), fam('"Alpha\\\\", serif'));
assert.equal(fam('\u00a0Alpha, serif'), '\u00a0Alpha'); assert.notEqual(fam('\u00a0Alpha, serif'), fam('Alpha, serif'));
assert.equal(fam('"\\41\u00a0B", serif'), 'A\u00a0B');
assert.equal(fam('"\\41\r\nB", serif'), 'AB');
assert.equal(fam('Foo\\ , serif'), 'Foo ');
assert.equal(fam(' \t Inter ,serif'), 'Inter');
assert.equal(fam('Foo\\ '), 'Foo '); assert.notEqual(fam('Foo\\ '), fam('Foo'));
assert.equal(fam('Foo\\\t'), 'Foo\t');
console.log('PASS escaped font-family names resolved and kept distinct');

// Route echo: full pathname still decides route-mismatch; the echoed route is capped at 2048 JSON bytes.
const sc = { id: 's', kind: 'style', selector: '.a', properties: ['color'] };
computed = { color: 'rgb(0, 0, 0)' };
const tricky = '/orders/ж"\\\u0001';
setPage(tricky); let r = measureUI({ context: ctx({ route: tricky }), checks: [sc] });
assert.equal(r.actual.route, tricky); assert.equal(r.checks[0].status, 'OBSERVED'); assert.equal(r.actual.routeOversized, undefined);
const atCap = '/' + 'a'.repeat(2048 - 3);           // JSON string = 2 quotes + 2046 chars = 2048 bytes
setPage(atCap); r = measureUI({ context: ctx({ route: '/x' }), checks: [sc] });
assert.equal(bytes(JSON.stringify(atCap)), 2048); assert.equal(r.actual.route, atCap); assert.equal(r.checks[0].reason, 'route-mismatch');
setPage(atCap + 'a'); r = measureUI({ context: ctx(), checks: [sc] });
assert.equal(r.actual.route, null); assert.equal(r.actual.routeOversized, true); assert.equal(r.checks[0].reason, 'route-mismatch');
const huge = '/' + 'ж"\\\u0001'.repeat(200000);
setPage(huge); r = measureUI({ context: ctx({ route: '/' + 'x'.repeat(511) }), checks: [sc, { id: 'fit', kind: 'fit', selector: '.a' }] });
assert.equal(r.actual.route, null); assert.ok(sizeOf(r) < 10000); assert.notEqual(r.status, 'PASS');
// A huge pathname is rejected by length before any serialization (JSON.stringify of it would throw).
const realStringify = JSON.stringify;
JSON.stringify = (v, ...rest) => { if (typeof v === 'string' && v.length > 4096) throw new RangeError('Invalid string length'); return realStringify(v, ...rest); };
try { setPage('/' + '"'.repeat(1000000)); r = measureUI({ context: ctx(), checks: [sc] }); } finally { JSON.stringify = realStringify; }
assert.equal(r.actual.route, null); assert.equal(r.actual.routeOversized, true); assert.equal(r.checks[0].reason, 'route-mismatch');
console.log('PASS route echo capped; full pathname still binds or mismatches the declared route');

// Worst-case configuration within every config cap stays under the report bound with all rows intact.
const ctrl = n => '\u0001'.repeat(n);                // 6 JSON bytes per char
text = ctrl(2048);
const ctxMax = ctx({ revision: ctrl(512), state: ctrl(512), fixture: ctrl(512), evidence: ctrl(512), route: '/x', declaredZoom: ctrl(512), colorScheme: ctrl(512) });
const textChecks = Array(32).fill(0).map((_, i) => ({ id: String(i).padEnd(80, '"'), kind: 'text', selector: '\\'.repeat(250) + String(i).padStart(6, '0'),
  expected: ctrl(2048), fixture: { id: ctxMax.fixture, source: ctrl(512), stable: true } }));
setPage('/x'); r = measureUI({ context: ctxMax, checks: textChecks });
assert.ok(r.checks.every(c => c.status === 'PASS'), 'no row dropped at the config maximum'); assert.ok(sizeOf(r) <= REPORT, String(sizeOf(r)));
console.log('PASS worst-case text config: ' + sizeOf(r) + ' bytes <= ' + REPORT + ', all rows kept');

// Echoed computed strings are capped (64 bytes) so every row is bounded by construction: huge values
// (2 Mi control characters) give NOT_TESTED oversized-value, serialization never throws, never PASS.
text = 'x'; computed = { fontSize: '\u0001'.repeat(2097152), fontWeight: '\u0001'.repeat(2097152) };
const cc = Array(32).fill(0).map((_, i) => ({ id: 'c' + i, kind: 'contrast', selector: '.a', minimum: 4.5, source: 'agreed' }));
r = measureUI({ context: ctx(), checks: cc });
assert.ok(r.checks.every(c => c.status === 'NOT_TESTED' && c.reason === 'oversized-value' && c.actual === null));
assert.equal(r.status, 'NOT_TESTED'); assert.ok(sizeOf(r) <= REPORT, String(sizeOf(r)));
computed = { overflowX: 'v'.repeat(65), overflowY: 'visible' };
r = measureUI({ context: ctx(), checks: [{ id: 'fit', kind: 'fit', selector: '.a' }] });
assert.equal(r.checks[0].reason, 'oversized-value'); assert.notEqual(r.status, 'PASS');
computed = { fontSize: 'x'.repeat(64) };
assert.equal(measureUI({ context: ctx(), checks: cc.slice(0, 1) }).checks[0].status, 'PASS', '64 bytes is kept');
console.log('PASS echoed computed strings capped; huge values are NOT_TESTED oversized-value, report ' + sizeOf(r) + ' bytes');

// Worst mixed case: maximal escaped non-style rows plus style rows filling the style cap stay under the
// whole-report bound (the runtime admission and report-budget fallback are defensive under these caps).
pv = Object.fromEntries(['padding-top','padding-right','padding-bottom','padding-left','margin-top','margin-right','margin-bottom','margin-left','width','height','min-width','min-height','row-gap','column-gap','color','opacity'].map(p => [p, 'ж'.repeat(128)]));
computed = { fontSize: 'x'.repeat(64) }; text = ctrl(2048);
const many = Array(50).fill(0).map(() => el());
setPage('/x', many);
global.document.querySelectorAll = s => s === '*' || s === 'iframe, frame' || s === 'canvas' ? [] : s.startsWith('.one') ? [el()] : many;
const props = Object.keys(pv);
const fat = i => ({ id: 'st' + i, kind: 'style', selector: '.a', limit: 50, properties: props });
const big = Array(27).fill(0).map((_, i) => ({ id: String(i).padEnd(80, '"'), kind: 'text', selector: '.one' + ' '.repeat(240) + String(i).padStart(6, '0'), expected: ctrl(2048), fixture: { id: 'f', source: ctrl(512), stable: true } }));
r = measureUI({ context: ctx(), checks: [...big, ...Array(5).fill(0).map((_, i) => fat(i))] });
const styleRows = r.checks.filter(c => c.kind === 'style');
assert.ok(styleRows.some(c => c.status === 'OBSERVED') && styleRows.at(-1).reason === 'budget');
assert.ok(big.every((_, i) => r.checks[i].status === 'PASS'), 'non-style rows kept');
assert.ok(sizeOf(styleRows) <= 1048576 && sizeOf(r) <= REPORT, sizeOf(styleRows) + ' / ' + sizeOf(r));
console.log('PASS worst mixed case (27 max text rows + 5 style rows over the style cap): ' + sizeOf(r) + ' bytes <= ' + REPORT);
})();

/* Defensive whole-report fallbacks, exercised with a reduced bound patched into an in-memory copy. */
(() => {
const fs = require('node:fs'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../skills/ui-measurements/scripts/measure-ui.cjs'), 'utf8');
const withBound = n => { const src = source.replace('REPORT_BYTES = 2097152', 'REPORT_BYTES = ' + n); assert.ok(source.includes('REPORT_BYTES = 2097152')); return new Function('module', src + ';return measureUI;')(undefined); };
const bytes = v => new TextEncoder().encode(v).length;
const HTML = 'http://www.w3.org/1999/xhtml';
const el = () => ({ namespaceURI: HTML, localName: 'div', parentElement: null, children: [], clientWidth: 5, clientHeight: 5, scrollWidth: 5, scrollHeight: 5,
  textContent: 'x'.repeat(2000), getClientRects: () => [{}], getAnimations: () => [], getBoundingClientRect: () => ({ width: 5, height: 5 }), getAttribute: () => null, style: { length: 0, item: () => null } });
global.window = { location: { pathname: '/x' }, innerWidth: 390, innerHeight: 844, devicePixelRatio: 1, visualViewport: { scale: 1 } }; window.top = window;
global.document = { fonts: { status: 'loaded' }, adoptedStyleSheets: [], querySelectorAll: s => s === '*' || s === 'iframe, frame' || s === 'canvas' ? [] : [el()] };
global.getComputedStyle = () => ({ display: 'block', visibility: 'visible', opacity: '1', contentVisibility: 'visible', overflowX: 'visible', overflowY: 'visible', getPropertyValue: () => '9px' });
const context = { revision: 'r', state: 's', fixture: 'f', evidence: 'e', route: '/x', settled: true };
const text = i => ({ id: 't' + i, kind: 'text', selector: '.t', expected: 'x'.repeat(2000), fixture: { id: 'f', source: 'seed', stable: true } });
// (a) non-style rows that do not fit are replaced from the end by report-budget rows; never PASS
let m = withBound(6000), r = m({ context, checks: [0, 1, 2, 3, 4].map(text) });
const dropped = r.checks.filter(c => c.reason === 'report-budget');
assert.ok(dropped.length >= 3 && r.checks[0].status === 'PASS' && r.checks.at(-1).reason === 'report-budget');
assert.ok(dropped.every(c => c.status === 'NOT_TESTED' && Object.keys(c).join() === 'id,kind,selector,status,reason'));
assert.equal(r.status, 'NOT_TESTED'); assert.ok(bytes(JSON.stringify(r)) <= 6000, String(bytes(JSON.stringify(r))));
// (b) a style row that fits the style budget but not the whole report becomes a budget row
const st = { id: 's', kind: 'style', selector: '.s', properties: ['padding-top', 'padding-left'], limit: 20 };
global.document.querySelectorAll = s => s === '*' || s === 'iframe, frame' || s === 'canvas' ? [] : s === '.s' ? Array(20).fill(0).map(el) : [el()];
const full = bytes(JSON.stringify(withBound(2097152)({ context, checks: [text(0), st] })));
r = withBound(full - 1)({ context, checks: [text(0), st] });
assert.equal(r.checks[1].reason, 'budget'); assert.equal(r.checks[0].status, 'PASS');
assert.ok(bytes(JSON.stringify(r)) <= full - 1);
r = withBound(2097152)({ context, checks: [text(0), st] }); assert.equal(r.checks[1].status, 'OBSERVED');
console.log('PASS defensive whole-report fallbacks (report-budget rows, style admission) under a reduced bound');
})();

