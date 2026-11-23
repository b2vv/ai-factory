// Ordering and texts of a project's open-task list; pure, so the node tests can check them without a DOM.
const order = ['In progress','Ready','Proposed','Paused','Blocked'];
const labels = {
  'In progress':['В роботі','good'],
  Ready:['Готова','neutral'],
  Proposed:['Запропонована','neutral'],
  Paused:['На паузі','neutral'],
  Blocked:['Заблокована','warn']
};

export function queueView(queue) {
  if (!queue) return {note:'Список задач не опубліковано.', rows:[], more:'', stale:false};
  const rows = queue.items
    .map((item,index)=>({...item,index}))
    .sort((a,b)=>(b.recommended===true)-(a.recommended===true) || order.indexOf(a.state)-order.indexOf(b.state) || a.index-b.index)
    .map(({index,...item})=>{
      const [label,tone] = labels[item.state] ?? [item.state,'neutral'];
      return {...item, label, tone, blocked: item.blockedBy ? 'Чекає на: '+item.blockedBy : ''};
    });
  return {
    note: rows.length ? '' : 'Відкритих задач немає.',
    rows,
    more: queue.omitted > 0 ? `Не показано задач: ${queue.omitted}.` : '',
    stale: queue.stale === true
  };
}
