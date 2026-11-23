// The /api/status shape the page can render; anything else is handled like a failed refresh.
const isObject = v => typeof v === 'object' && v !== null && !Array.isArray(v);
const text = v => typeof v === 'string';

function validCard(p) {
  if (!isObject(p) || !['id','name','task','state','revision'].every(k=>text(p[k])) || !Array.isArray(p.stages)) return false;
  if ('queue' in p && !(isObject(p.queue) && Array.isArray(p.queue.items))) return false;
  if ('transition' in p && !isObject(p.transition)) return false;
  return true;
}

export function validSnapshot(data) {
  return isObject(data) && text(data.checkedAt) && Array.isArray(data.projects) && data.projects.every(validCard);
}
