// Configuração inicial: the company's set-up steps, each ticked by the backend from the real data.
// readOnly = the platform's view (Empresas): no "Ir" buttons, the screens belong to the company.
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, Circle, ArrowRight } from 'lucide-react';

function Row({ item, readOnly, onGo }) {
  const Icon = item.done ? CheckCircle2 : Circle;
  return (
    <div className="flex items-center gap-3 px-4 py-2.5">
      <Icon size={17} className={'shrink-0 ' + (item.done ? 'text-success' : 'text-text-muted')} />
      <div className="flex-1 min-w-0">
        <p className={'text-sm ' + (item.done ? 'text-text-muted' : 'text-text-primary font-medium')}>
          {item.label}
          {item.owner && (
            <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-text-muted border border-border rounded px-1.5 py-0.5">
              {item.owner}
            </span>
          )}
        </p>
        <p className="text-[12px] text-text-muted truncate">
          {item.detail}
          {!item.done && item.owner && !readOnly && ' - definido pela RM SOFT, contacte o suporte'}
        </p>
      </div>
      {!readOnly && !item.done && item.link && (
        <button
          type="button"
          onClick={() => onGo(item.link)}
          className="shrink-0 flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-[12px] font-medium text-accent hover:border-accent transition-colors cursor-pointer"
        >
          Ir <ArrowRight size={13} />
        </button>
      )}
    </div>
  );
}

export default function SetupChecklist({ data, readOnly = false }) {
  const navigate = useNavigate();
  const required = data.items.filter((i) => i.required);
  const recommended = data.items.filter((i) => !i.required);
  const percent = data.required_total ? Math.round((data.required_done / data.required_total) * 100) : 100;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="flex items-center justify-between text-[12px] mb-1.5">
          <span className="text-text-muted">Passos obrigatórios</span>
          <span className={'font-mono font-semibold ' + (data.complete ? 'text-success' : 'text-text-primary')}>
            {data.required_done} / {data.required_total} concluídos
          </span>
        </div>
        <div className="h-2 rounded-full bg-bg-inset overflow-hidden">
          <div className={'h-full rounded-full transition-all ' + (data.complete ? 'bg-success' : 'bg-accent')} style={{ width: percent + '%' }} />
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {[['Obrigatório', required], ['Recomendado', recommended]].map(([title, list]) => (
          <div key={title} className="border border-border rounded-md overflow-hidden">
            <p className="px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted bg-bg-inset border-b border-border">{title}</p>
            <div className="divide-y divide-border">
              {list.map((item) => <Row key={item.key} item={item} readOnly={readOnly} onGo={navigate} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
