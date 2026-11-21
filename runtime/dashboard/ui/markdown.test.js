import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {ReviewedMarkdown} from './markdown.js';

test('renders plain report structure but never HTML, images or navigable links',()=>{
  const content=[
    '### Report', '',
    '- **Recorded** with `evidence`.', '',
    '<iframe src="https://example.invalid/raw"></iframe>', '',
    'Before <img src="https://example.invalid/inline"/> after.', '',
    '![remote](https://example.invalid/image)', '',
    '[external](https://example.invalid/link) [local](/api/status) [script](javascript:alert%281%29)'
  ].join('\n');
  const html=renderToStaticMarkup(createElement(ReviewedMarkdown,null,content));
  assert.match(html,/<h3>Report<\/h3>/);
  assert.match(html,/<strong>Recorded<\/strong>/);
  assert.match(html,/<code>evidence<\/code>/);
  assert.match(html,/<span>external<\/span> <span>local<\/span> <span>script<\/span>/);
  assert.doesNotMatch(html,/<(?:iframe|img|a)\b|href=|src=|example\.invalid|javascript:/);
});
