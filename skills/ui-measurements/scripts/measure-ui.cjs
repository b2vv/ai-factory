/* Evaluate this function through the project's existing browser runner. No I/O or DOM writes. */
function measureUI(config) {
  const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const text = (v, max = 512, empty = false) => typeof v === 'string' && v.length <= max && (empty || v.trim().length > 0);
  const only = (v, keys) => Object.keys(v).every(k => keys.includes(k));
  const invalid = () => { throw new Error('Invalid UI measurement config'); };
  const STYLE_PROPERTIES = ['font-size', 'font-weight', 'font-style', 'line-height', 'letter-spacing',
    'text-transform', 'font-family', 'color', 'background-color', 'opacity',
    'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'margin-top', 'margin-right', 'margin-bottom', 'margin-left', 'row-gap', 'column-gap',
    'width', 'height', 'min-width', 'min-height',
    'border-top-width', 'border-right-width', 'border-bottom-width', 'border-left-width',
    'border-top-color', 'border-right-color', 'border-bottom-color', 'border-left-color',
    'border-top-left-radius', 'border-top-right-radius', 'border-bottom-right-radius', 'border-bottom-left-radius',
    'box-shadow', 'display', 'position'];
  if (!object(config) || !object(config.context) || !Array.isArray(config.checks)
    || config.checks.length < 1 || config.checks.length > 32
    || !only(config, ['context', 'checks', 'tolerance'])
    || !only(config.context, ['revision', 'state', 'fixture', 'evidence', 'route', 'settled', 'declaredZoom', 'colorScheme'])) invalid();
  const encoder = new TextEncoder();
  const bytes = value => encoder.encode(value).length;
  // UTF-8 bytes >= UTF-16 length, so the length test rejects huge strings before encoding them.
  const fits = (value, max) => typeof value === 'string' && value.length <= max && bytes(value) <= max;
  const ROUTE_BYTES = 2048;
  // The declared route may be as long as a pathname the report can echo (its JSON string within ROUTE_BYTES).
  const routeOK = v => text(v, ROUTE_BYTES) && fits(v, ROUTE_BYTES) && bytes(JSON.stringify(v)) <= ROUTE_BYTES;
  if (!['revision', 'state', 'fixture', 'evidence'].every(k => text(config.context[k])) || !routeOK(config.context.route)
    || typeof config.context.settled !== 'boolean'
    || (config.context.declaredZoom !== undefined && !text(config.context.declaredZoom))
    || (config.context.colorScheme !== undefined && !text(config.context.colorScheme))) invalid();
  if (config.tolerance !== undefined && (!Number.isFinite(config.tolerance) || config.tolerance < 0 || config.tolerance > 2)) invalid();
  const ids = new Set();
  for (const c of config.checks) {
    if (!object(c) || !text(c.id, 80) || ids.has(c.id) || !text(c.selector, 256)
      || !['fit', 'contrast', 'text', 'style'].includes(c.kind)) invalid();
    const fields = { fit: ['axis', 'scrollX'], contrast: ['minimum', 'source'], text: ['expected', 'fixture'], style: ['properties', 'limit'] };
    if (!only(c, ['id', 'kind', 'selector', ...fields[c.kind]])
      || (c.axis !== undefined && !['x', 'y', 'both'].includes(c.axis))) invalid();
    ids.add(c.id);
    if (c.scrollX !== undefined && (c.kind !== 'fit' || !object(c.scrollX)
      || (c.axis !== undefined && c.axis !== 'both') || !only(c.scrollX, ['reason', 'evidence'])
      || !text(c.scrollX.reason) || !text(c.scrollX.evidence))) invalid();
    if (c.kind === 'contrast' && (!Number.isFinite(c.minimum) || c.minimum < 1 || c.minimum > 21 || !text(c.source))) invalid();
    if (c.kind === 'text' && !text(c.expected, 2048, true)) invalid();
    if (c.kind === 'style' && (!Array.isArray(c.properties) || c.properties.length < 1 || c.properties.length > 16
      || Array.from(c.properties).some(p => typeof p !== 'string' || !STYLE_PROPERTIES.includes(p))
      || new Set(c.properties).size !== c.properties.length
      || (c.limit !== undefined && (!Number.isInteger(c.limit) || c.limit < 1 || c.limit > 50)))) invalid();
    if (c.fixture !== undefined && (!object(c.fixture) || !only(c.fixture, ['id', 'source', 'stable'])
      || (c.fixture.stable !== undefined && typeof c.fixture.stable !== 'boolean')
      || (c.fixture.id !== undefined && !text(c.fixture.id))
      || (c.fixture.source !== undefined && !text(c.fixture.source)))) invalid();
  }
  const context = config.context;
  const REPORT_BYTES = 2097152;
  const pathname = window.location.pathname;
  const tolerance = config.tolerance === undefined ? 1 : config.tolerance;
  const report = {
    context: { ...context },
    actual: {
      route: fits(pathname, ROUTE_BYTES) && bytes(JSON.stringify(pathname)) <= ROUTE_BYTES ? pathname : null,
      viewport: { width: window.innerWidth, height: window.innerHeight,
        dpr: window.devicePixelRatio, visualScale: window.visualViewport?.scale ?? null },
      frame: window === window.top ? 'top' : 'child'
    },
    checks: [],
    scope: 'Selected observations only; no visual, keyboard, ink-clipping or WCAG certification.'
  };
  function opaqueRGB(value) {
    const match = /^rgba?\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)(?:,\s*(\d+(?:\.\d+)?))?\)$/.exec(value);
    if (!match || (match[4] !== undefined && Number(match[4]) !== 1)) return null;
    const rgb = match.slice(1, 4).map(Number);
    return rgb.every(v => v >= 0 && v <= 255) ? rgb : null;
  }
  function contrast(node, result, check) {
    const style = getComputedStyle(node);
    if (node.namespaceURI !== 'http://www.w3.org/1999/xhtml' || node.children.length || !node.textContent.trim()) {
      result.reason = 'unsupported-text-target'; return;
    }
    for (let ancestor = node; ancestor; ancestor = ancestor.parentElement) {
      const a = getComputedStyle(ancestor);
      if (Number(a.opacity) !== 1 || a.filter !== 'none' || a.backdropFilter !== 'none'
        || a.mixBlendMode !== 'normal' || a.transform !== 'none' || a.perspective !== 'none'
        || a.clipPath !== 'none' || a.maskImage !== 'none' || a.webkitMaskImage !== 'none') {
        result.reason = 'unsupported-compositing'; return;
      }
    }
    if (style.backgroundImage !== 'none' || style.backgroundBlendMode !== 'normal'
      || style.textShadow !== 'none' || style.boxShadow !== 'none'
      || parseFloat(style.textIndent) !== 0 || !['border-box', 'padding-box'].includes(style.backgroundClip)
      || node.scrollWidth > node.clientWidth || node.scrollHeight > node.clientHeight
      || (style.webkitTextFillColor && style.webkitTextFillColor !== style.color)
      || (style.webkitTextStrokeWidth && parseFloat(style.webkitTextStrokeWidth) !== 0)
      || ['::before', '::after'].some(p => !['none', 'normal', ''].includes(getComputedStyle(node, p).content))) {
      result.reason = 'unsupported-paint'; return;
    }
    for (const pseudo of ['::first-letter', '::first-line']) {
      const p = getComputedStyle(node, pseudo);
      const keys = ['color', 'backgroundImage', 'textShadow', 'boxShadow', 'webkitTextFillColor',
        'webkitTextStrokeWidth', 'filter', 'mixBlendMode', 'opacity', 'transform', 'clipPath', 'maskImage'];
      if (keys.some(key => p[key] !== style[key])
        || !['rgba(0, 0, 0, 0)', 'transparent', style.backgroundColor].includes(p.backgroundColor)) {
        result.reason = 'unsupported-pseudo-paint'; return;
      }
    }
    const foreground = opaqueRGB(style.color), background = opaqueRGB(style.backgroundColor);
    if (!foreground || !background) { result.reason = 'non-opaque-or-non-srgb'; return; }
    const luminance = rgb => {
      const v = rgb.map(c => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
      return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
    };
    const a = luminance(foreground), b = luminance(background);
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    if (!fits(style.fontSize, 64) || !fits(style.fontWeight, 64)) { result.reason = 'oversized-value'; return; }
    result.actual = { foreground, background, ratio, fontSize: style.fontSize, fontWeight: style.fontWeight };
    result.status = ratio >= check.minimum ? 'PASS' : 'FAIL';
  }
  function renderReason(node) {
    if (node.namespaceURI !== 'http://www.w3.org/1999/xhtml') return 'non-html-target';
    if (!node.getClientRects().length || node.clientWidth === 0 || node.clientHeight === 0) return 'unrendered-target';
    for (let current = node; current; current = current.parentElement) {
      const style = getComputedStyle(current);
      if (style.display === 'none' || ['hidden', 'collapse'].includes(style.visibility)
        || Number(style.opacity) === 0 || style.contentVisibility !== 'visible') return 'unrendered-target';
      if (typeof current.getAnimations !== 'function') return 'animation-state-unavailable';
      if (current.getAnimations().some(a => a.pending || ['running', 'paused'].includes(a.playState))) return 'active-animation';
    }
    return null;
  }
  const runtimeReason = !Number.isFinite(window.innerWidth) || !Number.isFinite(window.innerHeight)
    || window.innerWidth <= 0 || window.innerHeight <= 0 ? 'viewport-unavailable'
    : context.route !== pathname ? 'route-mismatch'
    : !context.settled ? 'state-not-settled'
    : !document.fonts || document.fonts.status !== 'loaded' ? 'fonts-not-settled' : null;
  const STYLE_BYTES = 1048576, STYLE_ELEMENTS = 400;
  const SKIPS = ['non-html-target', 'unrendered-target', 'animation-state-unavailable', 'active-animation'];
  const budgetRow = check => ({ id: check.id, kind: 'style', selector: check.selector, status: 'NOT_TESTED', reason: 'budget' });
  const styleChecks = config.checks.filter(c => c.kind === 'style');
  const reserve = [0];  // reserve[i]: bytes needed if the last i style checks all become budget rows
  for (let i = styleChecks.length - 1; i >= 0; i--) reserve.unshift(reserve[0] + 1 + bytes(JSON.stringify(budgetRow(styleChecks[i]))));
  const style = { index: 0, rows: 0, bytes: 0, elements: 0, exhausted: false };
  let untraversedCounts = null;
  function untraversed() {
    if (!untraversedCounts) {
      let openShadowHosts = 0;
      for (const element of document.querySelectorAll('*')) if (element.shadowRoot) openShadowHosts++;
      untraversedCounts = { openShadowHosts, iframes: document.querySelectorAll('iframe, frame').length,
        canvases: document.querySelectorAll('canvas').length,
        constructedSheets: Array.isArray(document.adoptedStyleSheets) ? document.adoptedStyleSheets.length : 0 };
    }
    return { ...untraversedCounts };
  }
  function firstFamily(value) {
    // First family of a computed font-family list, with CSS escapes resolved (\" \\ \41 ).
    // CSS whitespace only (space, tab, LF, CR, FF); NBSP and other Unicode spaces are name characters.
    const ws = c => c === ' ' || c === '\t' || c === '\n' || c === '\r' || c === '\f';
    let a = 0;
    while (a < value.length && ws(value[a])) a++;
    const v = value.slice(a), quote = v[0] === '"' || v[0] === "'" ? v[0] : null;
    let out = '', kept = 0;   // kept: out length up to the last escaped character (never trimmed)
    for (let i = quote ? 1 : 0; i < v.length; i++) {
      const ch = v[i];
      if (ch === '\\') {
        const hex = /^[0-9a-fA-F]{1,6}/.exec(v.slice(i + 1));
        if (hex) {
          const cp = parseInt(hex[0], 16);
          out += cp === 0 || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff) ? '\ufffd' : String.fromCodePoint(cp);
          i += hex[0].length;
          if (v[i + 1] === '\r' && v[i + 2] === '\n') i += 2; else if (ws(v[i + 1] || '')) i++;
        } else if (i + 1 < v.length) out += v[++i];
        kept = out.length;
      } else if (quote ? ch === quote : ch === ',') break;
      else out += ch;
    }
    if (quote) return out;
    let end = out.length;
    while (end > kept && ws(out[end - 1])) end--;
    return out.slice(0, end);
  }
  function shadowLayers(value) {
    if (value.trim() === 'none' || !value.trim()) return 0;
    let depth = 0, layers = 1;
    for (const ch of value) { if (ch === '(') depth++; else if (ch === ')') depth--; else if (ch === ',' && depth === 0) layers++; }
    return layers;
  }
  function readElement(node, index, properties) {
    const computed = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    const element = { index, tag: node.localName, ariaRole: node.getAttribute('role'),
      box: { width: Math.round(rect.width), height: Math.round(rect.height) },
      values: {}, derived: {}, inlineProperties: [], oversized: [] };
    if (!fits(element.tag, 64)) { element.tag = null; element.oversized.push('tag'); }
    if (element.ariaRole !== null && !fits(element.ariaRole, 64)) { element.ariaRole = null; element.oversized.push('ariaRole'); }
    for (const property of properties) {
      const raw = computed.getPropertyValue(property);
      const value = typeof raw === 'string' ? raw : '';
      if (property === 'font-family') {
        const first = firstFamily(value);
        if (!fits(first, 128)) element.oversized.push('font-family-first'); else element.derived['font-family-first'] = first;
      } else if (property === 'box-shadow') {
        element.derived['box-shadow-layers'] = shadowLayers(value);
      } else if (!fits(value, 256)) element.oversized.push(property);
      else element.values[property] = value;
    }
    const inline = node.style && typeof node.style.length === 'number' && typeof node.style.item === 'function' ? node.style : null;
    for (let i = 0; inline && i < inline.length; i++) {
      const name = inline.item(i);
      if (typeof name === 'string' && name.startsWith('--')) continue;   // custom properties are never reported
      if (element.inlineProperties.length === 32) { element.inlinePropertiesTruncated = true; break; }
      if (!fits(name, 64)) { if (!element.oversized.includes('inlineProperties')) element.oversized.push('inlineProperties'); }
      else element.inlineProperties.push(name);
    }
    return element;
  }
  function styleRow(check) {
    const row = { id: check.id, kind: 'style', selector: check.selector, status: 'NOT_TESTED' };
    if (runtimeReason) { row.reason = runtimeReason; return row; }
    let nodes;
    try { nodes = document.querySelectorAll(check.selector); }
    catch (_) { row.reason = 'invalid-selector'; return row; }
    const limit = check.limit === undefined ? 1 : check.limit;
    Object.assign(row, { matched: nodes.length, returned: 0, truncated: nodes.length > limit,
      skipped: Object.fromEntries(SKIPS.map(k => [k, 0])), elements: [], untraversed: untraversed() });
    if (!nodes.length) { row.reason = 'missing-target'; return row; }
    if (limit === 1 && nodes.length > 1) { row.reason = 'ambiguous-target'; return row; }
    for (let i = 0; i < Math.min(nodes.length, limit); i++) {
      const skip = renderReason(nodes[i]);
      if (skip) row.skipped[skip]++; else row.elements.push(readElement(nodes[i], i, check.properties));
    }
    row.returned = row.elements.length;
    if (row.returned) row.status = 'OBSERVED'; else row.reason = SKIPS.find(k => row.skipped[k] > 0);
    return row;
  }
  function admitStyle(check, fitsReport) {
    let row = style.exhausted ? budgetRow(check) : styleRow(check);
    const total = r => style.rows === 0 ? 2 + bytes(JSON.stringify(r)) : style.bytes + 1 + bytes(JSON.stringify(r));
    const count = (row.elements || []).length;
    if (!style.exhausted && (style.elements + count > STYLE_ELEMENTS || total(row) + reserve[style.index + 1] > STYLE_BYTES
      || !fitsReport(row))) {
      style.exhausted = true;
    }
    if (style.exhausted) row = budgetRow(check);
    style.bytes = total(row); style.rows++; style.index++; style.elements += (row.elements || []).length;
    return row;
  }
  for (const check of config.checks) {
    if (check.kind === 'style') { report.checks.push(budgetRow(check)); continue; }
    const result = { id: check.id, kind: check.kind, selector: check.selector,
      status: 'NOT_TESTED', expected: check.kind === 'contrast' ? { minimum: check.minimum, source: check.source }
        : check.kind === 'text' ? { value: check.expected, fixture: check.fixture?.id ?? null, source: check.fixture?.source ?? null }
        : { horizontal: check.axis === 'y' ? 'not-requested' : check.scrollX ? 'fit-or-local-scroll' : 'fit', vertical: check.axis === 'x' ? 'not-requested' : 'fit', axis: check.axis ?? 'both', tolerance, scrollX: check.scrollX ? { ...check.scrollX } : null }, actual: null };
    if (runtimeReason) { result.reason = runtimeReason; report.checks.push(result); continue; }
    let nodes;
    try { nodes = document.querySelectorAll(check.selector); }
    catch (_) { result.reason = 'invalid-selector'; report.checks.push(result); continue; }
    if (nodes.length !== 1) {
      result.reason = nodes.length ? 'ambiguous-target' : 'missing-target';
    } else {
      const node = nodes[0];
      const unavailable = renderReason(node);
      if (unavailable) {
        result.reason = unavailable;
      } else if (check.kind === 'fit') {
        const style = getComputedStyle(node);
        const x = node.scrollWidth - node.clientWidth;
        const y = node.scrollHeight - node.clientHeight;
        if (!fits(style.overflowX, 64) || !fits(style.overflowY, 64)) {
          result.reason = 'oversized-value'; report.checks.push(result); continue;
        }
        const localScroll = !!check.scrollX && ['auto', 'scroll'].includes(style.overflowX);
        result.actual = { clientWidth: node.clientWidth, scrollWidth: node.scrollWidth,
          clientHeight: node.clientHeight, scrollHeight: node.scrollHeight,
          overflowX: style.overflowX, overflowY: style.overflowY };
        result.status = (check.axis === 'y' || x <= tolerance || localScroll)
          && (check.axis === 'x' || y <= tolerance) ? 'PASS' : 'FAIL';
      } else if (check.kind === 'contrast') {
        contrast(node, result, check);
      } else if (check.kind === 'text') {
        if (check.fixture?.stable !== true || check.fixture.id !== context.fixture || !check.fixture.source) {
          result.reason = 'stable-fixture-not-established';
        } else if (node.textContent.length > 2048) {
          result.reason = 'oversized-text'; result.actual = { length: node.textContent.length };
        } else {
          result.actual = { value: node.textContent };
          result.status = node.textContent === check.expected ? 'PASS' : 'FAIL';
        }
      } else {
        result.reason = 'unsupported-check';
      }
    }
    report.checks.push(result);
  }
  if (styleChecks.length || context.colorScheme !== undefined) {
    const media = q => typeof window.matchMedia === 'function' ? window.matchMedia(q).matches : null;
    const dark = media('(prefers-color-scheme: dark)'), light = media('(prefers-color-scheme: light)');
    report.actual.media = { prefersColorScheme: dark === null ? null : dark ? 'dark' : light ? 'light' : 'no-preference',
      forcedColors: media('(forced-colors: active)') === null ? null : media('(forced-colors: active)') ? 'active' : 'none' };
  }
  if (report.actual.route === null) report.actual.routeOversized = true;
  // Whole-report byte bound: measure with every style row as its fixed budget row and the longest
  // status strings; non-style rows that do not fit become NOT_TESTED report-budget (never PASS).
  report.status = 'NOT_TESTED'; if (styleChecks.length) report.styleStatus = 'NOT_TESTED';
  let reportBytes = bytes(JSON.stringify(report));
  for (let i = report.checks.length - 1; i >= 0 && reportBytes > REPORT_BYTES; i--) {
    const c = report.checks[i];
    if (c.kind === 'style') continue;
    report.checks[i] = { id: c.id, kind: c.kind, selector: c.selector, status: 'NOT_TESTED', reason: 'report-budget' };
    reportBytes = bytes(JSON.stringify(report));
  }
  report.checks.forEach((c, i) => {
    if (c.kind !== 'style') return;
    const check = config.checks[i], placeholder = bytes(JSON.stringify(c));
    const row = admitStyle(check, r => reportBytes + bytes(JSON.stringify(r)) - placeholder <= REPORT_BYTES);
    reportBytes += bytes(JSON.stringify(row)) - placeholder; report.checks[i] = row;
  });
  const measured = report.checks.filter(c => c.kind !== 'style');
  const styleRows = report.checks.filter(c => c.kind === 'style');
  report.status = !measured.length ? (styleRows.some(c => c.status === 'OBSERVED') ? 'OBSERVED' : 'NOT_TESTED')
    : measured.some(c => c.status === 'FAIL') ? 'FAIL'
    : measured.some(c => c.status === 'NOT_TESTED') ? 'NOT_TESTED' : 'PASS';
  if (styleRows.length) report.styleStatus = styleRows.every(c => c.status === 'OBSERVED') ? 'OBSERVED' : 'NOT_TESTED';
  return report;
}
if (typeof module !== 'undefined') module.exports = measureUI;
