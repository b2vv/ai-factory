/* Evaluate this function through the project's existing browser runner. No I/O or DOM writes. */
function measureUI(config) {
  const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const text = (v, max = 512, empty = false) => typeof v === 'string' && v.length <= max && (empty || v.trim().length > 0);
  const only = (v, keys) => Object.keys(v).every(k => keys.includes(k));
  const invalid = () => { throw new Error('Invalid UI measurement config'); };
  if (!object(config) || !object(config.context) || !Array.isArray(config.checks)
    || config.checks.length < 1 || config.checks.length > 32
    || !only(config, ['context', 'checks', 'tolerance'])
    || !only(config.context, ['revision', 'state', 'fixture', 'evidence', 'route', 'settled', 'declaredZoom'])) invalid();
  if (!['revision', 'state', 'fixture', 'evidence', 'route'].every(k => text(config.context[k]))
    || typeof config.context.settled !== 'boolean'
    || (config.context.declaredZoom !== undefined && !text(config.context.declaredZoom))) invalid();
  if (config.tolerance !== undefined && (!Number.isFinite(config.tolerance) || config.tolerance < 0 || config.tolerance > 2)) invalid();
  const ids = new Set();
  for (const c of config.checks) {
    if (!object(c) || !text(c.id, 80) || ids.has(c.id) || !text(c.selector, 256)
      || !['fit', 'contrast', 'text'].includes(c.kind)) invalid();
    const fields = { fit: ['axis', 'scrollX'], contrast: ['minimum', 'source'], text: ['expected', 'fixture'] };
    if (!only(c, ['id', 'kind', 'selector', ...fields[c.kind]])
      || (c.axis !== undefined && !['x', 'y', 'both'].includes(c.axis))) invalid();
    ids.add(c.id);
    if (c.scrollX !== undefined && (c.kind !== 'fit' || !object(c.scrollX)
      || (c.axis !== undefined && c.axis !== 'both') || !only(c.scrollX, ['reason', 'evidence'])
      || !text(c.scrollX.reason) || !text(c.scrollX.evidence))) invalid();
    if (c.kind === 'contrast' && (!Number.isFinite(c.minimum) || c.minimum < 1 || c.minimum > 21 || !text(c.source))) invalid();
    if (c.kind === 'text' && !text(c.expected, 2048, true)) invalid();
    if (c.fixture !== undefined && (!object(c.fixture) || !only(c.fixture, ['id', 'source', 'stable'])
      || (c.fixture.stable !== undefined && typeof c.fixture.stable !== 'boolean')
      || (c.fixture.id !== undefined && !text(c.fixture.id))
      || (c.fixture.source !== undefined && !text(c.fixture.source)))) invalid();
  }
  const context = config.context;
  const tolerance = config.tolerance === undefined ? 1 : config.tolerance;
  const report = {
    context: { ...context },
    actual: {
      route: window.location.pathname,
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
    : context.route !== report.actual.route ? 'route-mismatch'
    : !context.settled ? 'state-not-settled'
    : !document.fonts || document.fonts.status !== 'loaded' ? 'fonts-not-settled' : null;
  for (const check of config.checks) {
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
  report.status = report.checks.some(c => c.status === 'FAIL') ? 'FAIL'
    : report.checks.some(c => c.status === 'NOT_TESTED') ? 'NOT_TESTED' : 'PASS';
  return report;
}
if (typeof module !== 'undefined') module.exports = measureUI;
