// The activities whose tills offer an article (a service, a product category): none ticked = every activity. Shown
// only to a company with more than one activity (Padaria + Hotel) - with one, there is nothing to choose.
import { useEffect, useState } from 'react';
import { listActivities } from '../api/activity';

export default function ActivityScopePicker({ value = [], onChange }) {
  const [activities, setActivities] = useState([]);
  useEffect(() => {
    listActivities().then((d) => setActivities((d || []).filter((a) => a.is_active))).catch(() => setActivities([]));
  }, []);
  if (activities.length < 2) return null;
  const toggle = (id) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Disponível nas caixas de</p>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        {activities.map((a) => (
          <label key={a.id} className="flex items-center gap-2 cursor-pointer select-none">
            <input type="checkbox" checked={value.includes(a.id)} onChange={() => toggle(a.id)} className="w-4 h-4 accent-accent cursor-pointer" />
            <span className="text-sm text-text-primary">{a.name}</span>
          </label>
        ))}
      </div>
      <p className="text-[11px] text-text-muted">{value.length ? 'Só aparece nas caixas destas atividades.' : 'Nenhuma marcada: aparece em todas as atividades.'}</p>
    </div>
  );
}

// Is an article offered at a till of this activity? None ticked (or no activity known) = yes.
export function offeredIn(activityIds, activityId) {
  return !activityId || !activityIds || activityIds.length === 0 || activityIds.includes(activityId);
}
