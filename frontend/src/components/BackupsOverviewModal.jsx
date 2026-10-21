import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, Search } from 'lucide-react';
import Modal from './Modal';
import { getBackupsOverview } from '../api/admin';
import { extractErrorMessage } from '../utils/errors';
import { size, when } from './CompanyBackupsPanel';

// Empresas > «Cópias de segurança»: every company's state at a glance - automatic or manual, last copy, failures,
// space used. A company without a good copy for more than a day is in red. One company's copies: its pencil > Cópias.

export default function BackupsOverviewModal({ open, onClose, onOpenCompany }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('todas');

  useEffect(() => {
    if (!open) return;
    setRows(null);
    setError('');
    setSearch('');
    setFilter('todas');
    getBackupsOverview().then(setRows).catch((err) => setError(extractErrorMessage(err, 'Não foi possível carregar')));
  }, [open]);

  const total = (rows || []).reduce((sum, r) => sum + r.size_bytes, 0);
  const late = (rows || []).filter((r) => r.late && r.is_active).length;
  // the search (name or NIF) and the filters: what needs attention first
  const FILTERS = [
    ['todas', 'Todas', () => true],
    ['atraso', 'Sem cópia recente', (r) => r.late && r.is_active],
    ['erro', 'Com erro', (r) => r.last_status === 'ERRO'],
    ['auto', 'Automáticas', (r) => r.mode === 'AUTOMATICA'],
    ['manual', 'Só manual', (r) => r.mode !== 'AUTOMATICA'],
  ];
  const term = search.trim().toLowerCase();
  const test = FILTERS.find(([key]) => key === filter)[2];
  const shown = (rows || []).filter((r) => test(r) && (!term || r.name.toLowerCase().includes(term) || (r.nif || '').includes(term)));

  return (
    <Modal open={open} onClose={onClose} title="Cópias de segurança" subtitle="Todas as empresas" maxWidthClass="max-w-6xl">
      {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{error}</div>}
      {!rows && !error && <div className="flex items-center gap-2 text-[13px] text-text-muted py-6"><Loader2 size={15} className="animate-spin" /> A carregar...</div>}
      {rows && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-4 flex-wrap text-[13px]">
            <span className="text-text-primary">Espaço ocupado: <span className="font-semibold font-mono">{size(total)}</span></span>
            {late > 0
              ? <span className="flex items-center gap-1.5 text-danger"><AlertTriangle size={14} /> {late} empresa(s) ativa(s) sem cópia há mais de um dia</span>
              : <span className="flex items-center gap-1.5 text-success"><CheckCircle2 size={14} /> Todas as empresas ativas com cópia recente</span>}
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="relative w-full sm:w-72">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Pesquisar por nome ou NIF..." autoFocus
                className="w-full bg-bg-inset border border-border rounded-md pl-9 pr-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
            </div>
            <div className="flex items-center bg-bg-inset border border-border rounded-md p-0.5 flex-wrap">
              {FILTERS.map(([key, label, f]) => (
                <button key={key} type="button" onClick={() => setFilter(key)}
                  className={'px-3 py-1.5 rounded text-[12px] font-medium transition-colors cursor-pointer ' + (filter === key ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}>
                  {label} <span className="opacity-70">({rows.filter(f).length})</span>
                </button>
              ))}
            </div>
          </div>
          <div className="border border-border rounded-md overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg-inset text-[11px] uppercase tracking-wide text-text-muted">
                <tr>
                  <th className="text-left px-4 py-2.5 font-medium">Empresa</th>
                  <th className="text-left px-4 py-2.5 font-medium">Modo</th>
                  <th className="text-left px-4 py-2.5 font-medium">Última cópia feita</th>
                  <th className="text-left px-4 py-2.5 font-medium">Última tentativa</th>
                  <th className="text-right px-4 py-2.5 font-medium">Cópias</th>
                  <th className="text-right px-4 py-2.5 font-medium">Espaço</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {shown.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-text-muted text-[13px]">Nenhuma empresa corresponde.</td></tr>
                )}
                {shown.map((r) => (
                  <tr key={r.company_id} className={onOpenCompany ? 'cursor-pointer hover:bg-bg-inset/40' : ''} onClick={() => onOpenCompany?.(r.company_id)}>
                    <td className="px-4 py-2.5">
                      <div className="text-text-primary text-[13px] font-medium">{r.name}</div>
                      <div className="text-[11px] text-text-muted font-mono">{r.nif}{!r.is_active && ' · inativa'}</div>
                    </td>
                    <td className="px-4 py-2.5 text-[13px] text-text-primary">
                      {r.mode === 'AUTOMATICA' ? 'Automática ' + r.times.join(', ') : 'Só manual'}
                    </td>
                    <td className={'px-4 py-2.5 font-mono text-[12px] whitespace-nowrap ' + (r.late && r.is_active ? 'text-danger font-semibold' : 'text-text-primary')}>
                      {r.last_ok_at ? when(r.last_ok_at) : 'nenhuma'}
                    </td>
                    <td className="px-4 py-2.5 text-[12px]">
                      {r.last_status === 'ERRO'
                        ? <span className="text-danger" title={r.last_error || ''}>Erro{r.last_error ? ' - ' + r.last_error : ''}</span>
                        : r.last_status === 'FEITA' ? <span className="text-success">Feita</span> : <span className="text-text-muted">-</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px] text-text-primary">{r.copies}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px] text-text-muted">{size(r.size_bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[12px] text-text-muted">
            As cópias ficam no servidor, na pasta de cópias (fora do site). Copie essa pasta regularmente para fora do servidor:
            uma cópia que fica na mesma máquina não protege de uma avaria dessa máquina.
          </p>
        </div>
      )}
    </Modal>
  );
}
