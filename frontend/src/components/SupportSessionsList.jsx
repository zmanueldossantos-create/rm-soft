// The RM SOFT support accesses to a company: who entered, when, why, until when - for the gestor and the platform.
import { LifeBuoy } from 'lucide-react';

const when = (v) => (v ? new Date(v).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-');

export default function SupportSessionsList({ sessions }) {
  if (!sessions.length) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-text-muted text-sm gap-2">
        <LifeBuoy size={22} className="text-text-muted/50" />
        Nenhum acesso de suporte até hoje.
      </div>
    );
  }
  return (
    <div className="border border-border rounded-md overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-bg-inset text-[11px] uppercase tracking-wide text-text-muted">
          <tr>
            <th className="text-left px-4 py-2.5 font-medium">Entrada</th>
            <th className="text-left px-4 py-2.5 font-medium">Saída</th>
            <th className="text-left px-4 py-2.5 font-medium">Quem</th>
            <th className="text-left px-4 py-2.5 font-medium">Motivo</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {sessions.map((s) => (
            <tr key={s.id}>
              <td className="px-4 py-2.5 font-mono text-[12px] whitespace-nowrap">{when(s.started_at)}</td>
              <td className="px-4 py-2.5 font-mono text-[12px] whitespace-nowrap">
                {s.active ? <span className="text-amber-500 [.light_&]:text-amber-700 font-sans font-medium">Em curso</span> : when(s.ended_at)}
              </td>
              <td className="px-4 py-2.5 whitespace-nowrap">{s.admin_name}</td>
              <td className="px-4 py-2.5 text-text-secondary">{s.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
