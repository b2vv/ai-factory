import test from 'node:test';
import assert from 'node:assert/strict';
import {queueView} from './queue.js';

const item = (id,state,extra={}) => ({id,title:'Title '+id,state,summary:'Summary '+id,...extra});

test('recommended first, then by state, stable within a state',()=>{
  const view=queueView({updatedAt:'2026-11-23T00:00:00Z',stale:false,omitted:0,items:[
    item('b1','Blocked',{blockedBy:'T05'}), item('r1','Ready'), item('p1','Proposed'), item('r2','Ready'),
    item('w1','In progress'), item('z1','Paused'), item('r3','Ready',{recommended:true})
  ]});
  assert.deepEqual(view.rows.map(r=>r.id),['r3','w1','r1','r2','p1','z1','b1']);
  assert.equal(view.rows.at(-1).blocked,'Чекає на: T05');
  assert.equal(view.rows[0].label,'Готова');
  assert.equal(view.rows.at(-1).tone,'warn');
  assert.equal(view.note,''); assert.equal(view.more,''); assert.equal(view.stale,false);
});

test('absent, empty, overflow and stale lists say so',()=>{
  assert.equal(queueView(undefined).note,'Список задач не опубліковано.');
  assert.equal(queueView({items:[],omitted:0}).note,'Відкритих задач немає.');
  assert.equal(queueView({items:[item('a','Ready')],omitted:3}).more,'Не показано задач: 3.');
  assert.equal(queueView({items:[],omitted:0,stale:true}).stale,true);
});
