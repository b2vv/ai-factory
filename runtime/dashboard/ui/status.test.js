import test from 'node:test';
import assert from 'node:assert/strict';
import {validSnapshot} from './status.js';

const card = (extra={}) => ({id:'a',name:'A',task:'T',state:'Unknown',revision:'Unknown',next:'',stages:[],...extra});

test('accepts the status shape the server sends',()=>{
  assert.equal(validSnapshot({checkedAt:'2026-11-23T00:00:00Z',projects:[card(),card({queue:{items:[]},transition:{text:'x'}})]}),true);
  assert.equal(validSnapshot({checkedAt:'2026-11-23T00:00:00Z',projects:[]}),true);
});

test('rejects shapes the page cannot render',()=>{
  for (const bad of [null, 'text', {}, {checkedAt:'x'}, {checkedAt:'x',projects:{}}, {checkedAt:1,projects:[]},
    {checkedAt:'x',projects:[null]}, {checkedAt:'x',projects:[card({stages:undefined})]},
    {checkedAt:'x',projects:[card({id:7})]}, {checkedAt:'x',projects:[card({queue:{items:{}}})]},
    {checkedAt:'x',projects:[card({queue:null})]}, {checkedAt:'x',projects:[card({transition:'x'})]}]) {
    assert.equal(validSnapshot(bad),false,JSON.stringify(bad));
  }
});
