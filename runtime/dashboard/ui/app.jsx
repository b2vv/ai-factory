import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ReviewedMarkdown} from './markdown.js';
import {queueView} from './queue.js';
import {validSnapshot} from './status.js';

const names = {Plan:'План',Implementation:'Реалізація',Tests:'Тести',Review:'Рев’ю',Push:'Push',Update:'Update'};
const states = {
  Unknown:['Невідомо','neutral'],
  'Verified locally':['Локальні перевірки зафіксовано','neutral'],
  'Decision needed':['Потрібне рішення','warn'],
  'Plan accepted':['План погоджено','good'],
  Accepted:['Погодження зафіксовано','neutral'],
  Recorded:['Зафіксовано','neutral'],
  'Recorded pass':['Пройдено за звітом','good'],
  'Final verdict not recorded':['Фінальний вердикт не зафіксовано','neutral'],
  'Not recorded':['Не зафіксовано','neutral'],
  'Plan only':['Лише план','neutral'],
  'Probes recorded':['Проби зафіксовано','neutral'],
  'Verification pending':['Чекає на перевірку','warn'],
  'Partial evidence':['Часткові докази','neutral'],
  Blocked:['Заблоковано','warn'],
  Stale:['Застаріло','warn']
};
const stamp = value => value ? new Intl.DateTimeFormat('uk-UA',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)) : 'невідомо';

function Badge({state}) {
  const [label,tone] = states[state] ?? states.Unknown;
  return <span className={'badge '+tone}><span aria-hidden="true"></span>{label}</span>;
}
function PilotDetails({id,token,label}) {
  const [open,setOpen]=useState(false);
  const [state,setState]=useState({kind:'loading',token});
  useEffect(()=>{
    if(!open) return;
    const request=new AbortController();
    let active=true;
    const deadline=setTimeout(()=>request.abort(),6000);
    setState({kind:'loading',token});
    (async()=>{
      try {
        const response=await fetch('/api/details/'+encodeURIComponent(id),{cache:'no-store',signal:request.signal});
        if(response.status===404){if(active)setState({kind:'unavailable',token});return;}
        if(!response.ok) throw Error('unavailable');
        if(response.headers.get('X-Dashboard-Detail-Token')!==token){if(active)setState({kind:'unavailable',token});return;}
        const body=await response.text();
        if(active)setState({kind:'ready',body,token});
      } catch {if(active)setState({kind:'failed',token});}
      finally {clearTimeout(deadline);}
    })();
    return ()=>{active=false;clearTimeout(deadline);request.abort();};
  },[open,id,token]);

  return <details className="pilot-details" onToggle={event=>{
    const next=event.currentTarget.open;
    if(next && !open) setState({kind:'loading',token});
    setOpen(next);
  }}>
    <summary>{label}</summary>
    {open && <div className="pilot-details-body">
      {(state.kind==='loading'||state.token!==token) && <p role="status">Завантажую деталі…</p>}
      {state.token===token && state.kind==='unavailable' && <p role="status">Запис або ревізія змінилися. Деталі недоступні.</p>}
      {state.token===token && state.kind==='failed' && <p role="status">Не вдалося завантажити деталі. Закрий і відкрий їх, щоб повторити.</p>}
      {state.token===token && state.kind==='ready' && <ReviewedMarkdown>{state.body}</ReviewedMarkdown>}
    </div>}
  </details>;
}
function OpenTasks({queue}) {
  const view=queueView(queue);
  return <section className="queue" aria-labelledby="queue-title">
    <h3 id="queue-title">Відкриті задачі</h3>
    {queue && <p className="observed">Список опубліковано: <time dateTime={queue.updatedAt}>{stamp(queue.updatedAt)}</time>.{view.stale && ' Список задач застарів.'}</p>}
    {view.note && <p className="observed">{view.note}</p>}
    {view.rows.length>0 && <ul className="queue-list">{view.rows.map(r=><li key={r.id}>
      <div className="queue-head"><strong>{r.id.toUpperCase()} · {r.title}</strong>{r.recommended && <span className="queue-pick">Рекомендовано</span>}</div>
      <p>{r.summary}</p>
      {r.blocked && <p className="observed">{r.blocked}</p>}
      <span className={'badge '+r.tone}><span aria-hidden="true"></span>{r.label}</span>
    </li>)}</ul>}
    {view.more && <p className="observed">{view.more}</p>}
  </section>;
}
function App() {
  const [result,setResult]=useState(null);
  const [failed,setFailed]=useState(false);
  const [selected,setSelected]=useState(null);
  useEffect(()=>{
    let alive=true, timer, active;
    const refresh=async()=>{
      active=new AbortController();
      const cutoff=setTimeout(()=>active.abort(),6000);
      try {
        const res=await fetch('/api/status',{cache:'no-store',signal:active.signal});
        if(!res.ok) throw Error('unavailable');
        const data=await res.json();
        if(!validSnapshot(data)) throw Error('unexpected status shape');
        if(alive){setResult(data);setFailed(false);}
      } catch { if(alive)setFailed(true); }
      finally {clearTimeout(cutoff);if(alive)timer=setTimeout(refresh,10000);}
    };
    refresh();
    return ()=>{alive=false;clearTimeout(timer);active?.abort();};
  },[]);
  // Keep the last check time, but never render its gates as current after a failed refresh.
  const visibleResult=failed ? null : result;
  const chosen=visibleResult?.projects.find(p=>p.id===selected) ?? visibleResult?.projects[0];
  return <main className="shell">
    <header className="mast"><span className="mark" aria-hidden="true">AF</span><span>AI FACTORY</span><span className="readonly">Локально · лише читання</span></header>
    <section className="intro" aria-labelledby="heading">
      <p className="eyebrow">Робочий огляд</p>
      <h1 id="heading">Стан роботи</h1>
      <p>Налаштовані проєкти, шість етапів і джерело кожного висновку. Дашборд повторно звіряє відомі записи та ревізії, а не стежить за агентами. Запис для старішої ревізії або понад 48 год тому показано з позначкою «Застаріло» — як останній відомий, не поточний. Відсутні записи позначено «Невідомо».</p>
    </section>
    <div className="freshness" role="status">{failed ? (result ? 'Дані застаріли: джерело не відповіло. ' : 'Джерело не відповіло. Спробую знову. ') : !result ? 'Звіряю джерела…' : 'Джерела звірено: '}{result && <time dateTime={result.checkedAt}>{stamp(result.checkedAt)}</time>}</div>
    {visibleResult && <div className="project-grid" aria-label="Проєкти">{visibleResult.projects.map((p,i)=>
      <button key={p.id} className="project-card" aria-pressed={chosen?.id===p.id} aria-controls="project-evidence" onClick={()=>setSelected(p.id)}>
        <span className="project-top"><span className="project-index">{String(i+1).padStart(2,'0')} / {p.name}</span><Badge state={p.state}/></span>
        <strong>{p.task}</strong>
        <span className="revision">{p.revision==='Unknown'?'Ревізія невідома':p.revision} <span aria-hidden="true">↗</span><span className="visually-hidden">відкрити докази</span></span>
      </button>)}</div>}
    {chosen && <section className="detail" id="project-evidence" aria-labelledby="detail-title">
      <header className="detail-head"><div><p className="eyebrow">{chosen.name} · докази</p><h2 id="detail-title">{chosen.task}</h2></div><Badge state={chosen.state}/></header>
      <p className="next">{chosen.next}</p>
      <p className="observed">Опубліковано запис: {chosen.observed?<time dateTime={chosen.observed}>{stamp(chosen.observed)}</time>:'невідомо'}. Це не час останньої дії агента.</p>
      {chosen.provenance && <p className="observed">{chosen.provenance}</p>}
      {chosen.transition && <p className="observed">{chosen.transition.text}: <time dateTime={chosen.transition.updatedAt}>{stamp(chosen.transition.updatedAt)}</time>. Збіг зрізу: {chosen.transition.bound?'так':'не підтверджено'}. Це не результат гейта.</p>}

      {chosen.workflow && <p className="observed">{chosen.workflow}</p>}
      {chosen.detailId && <PilotDetails key={chosen.detailId} id={chosen.detailId} token={chosen.detailToken} label='Деталі задачі'/>}
      <ol className="stages">{chosen.stages.map((s,i)=><li key={s.name}>
        <span aria-hidden="true" className="stage-index">0{i+1}</span>
        <div className="stage-copy"><h3>{names[s.name]}</h3><p>{s.detail}</p>{s.source&&<p className="source">{s.source}</p>}</div>
        <Badge state={s.state}/>
      </li>)}</ol>
      <OpenTasks queue={chosen.queue}/>
    </section>}
  </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
