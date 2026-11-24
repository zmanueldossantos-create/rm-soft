import { useEffect, useState } from 'react';
import { Loader2, SlidersHorizontal, Trash2, Plus } from 'lucide-react';
import Modal from './Modal';
import { getVacations, listVacationAdjustments, addVacationAdjustment, deleteVacationAdjustment } from '../api/hr';
import { formatDate } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Ausências → Saldo de férias: for each employee of the year, the days he is entitled to, brought from the year before,
// corrected, taken (approved), asked, and what is left. The corrections (the balance from before RM SOFT, days agreed)
// are typed with their reason.
const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const n = (v) => String(v).replace('.', ',');

export default function VacationBalances({ year, canAdjust }) {
  const [data, setData] = useState(null);
  const [adjusting, setAdjusting] = useState(null); // { row, list, days, note }
  const [busy, setBusy] = useState(false);

  const load = () => getVacations(year).then(setData).catch((e) => toast.error(extractErrorMessage(e, 'Erro ao carregar os saldos')));
  useEffect(() => { setData(null); load(); }, [year]); // eslint-disable-line react-hooks/exhaustive-deps

  async function open(row) {
    try {
      setAdjusting({ row, list: await listVacationAdjustments(row.employee_id, year), days: '', note: '' });
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar os ajustes'));
    }
  }
  async function add(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const list = await addVacationAdjustment({ employee_id: adjusting.row.employee_id, year,
        days: adjusting.days === '' ? null : Number(String(adjusting.days).replace(',', '.')), note: adjusting.note });
      setAdjusting((p) => ({ ...p, list, days: '', note: '' }));
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao registar o ajuste'));
    } finally {
      setBusy(false);
    }
  }
  async function remove(a) {
    try {
      await deleteVacationAdjustment(a.id);
      setAdjusting((p) => ({ ...p, list: p.list.filter((x) => x.id !== a.id) }));
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao apagar o ajuste'));
    }
  }

  if (!data) return <div className="flex justify-center py-16"><Loader2 size={18} className="animate-spin text-text-muted" /></div>;
  return (
    <>
      <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
              <th className="text-left px-4 py-2.5">Colaborador</th><th className="text-left px-4 py-2.5">Admissão</th>
              <th className="text-right px-4 py-2.5">Direito {year}</th><th className="text-right px-4 py-2.5">Transitados</th>
              <th className="text-right px-4 py-2.5">Ajustes</th><th className="text-right px-4 py-2.5">Gozados</th>
              <th className="text-right px-4 py-2.5">Pedidos</th><th className="text-right px-4 py-2.5">Saldo</th><th />
            </tr>
          </thead>
          <tbody>
            {data.employees.length === 0 && <tr><td colSpan={9} className="text-center text-text-muted py-10">Nenhum colaborador em {year}</td></tr>}
            {data.employees.map((r) => (
              <tr key={r.employee_id} className={'border-b border-border last:border-0 ' + (r.is_active ? '' : 'opacity-60')}>
                <td className="px-4 py-2.5"><span className="text-text-primary font-medium">{r.name}</span> <span className="font-mono text-[11px] text-text-muted">{r.number}</span></td>
                <td className="px-4 py-2.5 text-text-muted">{formatDate(r.hired_on)}</td>
                <td className="px-4 py-2.5 text-right font-mono">{n(r.entitled)}</td>
                <td className="px-4 py-2.5 text-right font-mono text-text-muted">{n(r.brought)}</td>
                <td className="px-4 py-2.5 text-right font-mono text-text-muted">{r.adjusted ? (r.adjusted > 0 ? '+' : '') + n(r.adjusted) : '-'}</td>
                <td className="px-4 py-2.5 text-right font-mono">{n(r.taken)}</td>
                <td className="px-4 py-2.5 text-right font-mono text-amber-500">{r.asked ? n(r.asked) : '-'}</td>
                <td className={'px-4 py-2.5 text-right font-mono font-semibold ' + (r.balance < 0 ? 'text-danger' : 'text-text-primary')}>
                  {n(r.balance)}{r.asked > 0 && <span className="block text-[11px] font-normal text-text-muted">disponível {n(r.available)}</span>}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <button type="button" title="Ajustes do saldo" onClick={() => open(r)} className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary cursor-pointer"><SlidersHorizontal size={13} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[12px] text-text-muted mt-3">Saldo = direito + transitados + ajustes - gozados. As regras (dias por ano, ano de admissão, dias que transitam) estão em Parâmetros de RH → Tipos de ausência.</p>

      <Modal open={!!adjusting} onClose={() => setAdjusting(null)} title={`Ajustes de ${year}`} subtitle={adjusting?.row.name} maxWidthClass="max-w-lg">
        {adjusting && (
          <div className="flex flex-col gap-3">
            {adjusting.list.length === 0 ? <p className="text-sm text-text-muted">Nenhum ajuste neste ano.</p> : (
              <div className="border border-border rounded-md divide-y divide-border">
                {adjusting.list.map((a) => (
                  <div key={a.id} className="flex items-center gap-3 px-3 py-2">
                    <span className={'w-14 font-mono text-right ' + (a.days < 0 ? 'text-danger' : 'text-success')}>{a.days > 0 ? '+' : ''}{n(a.days)}</span>
                    <span className="flex-1 text-sm text-text-primary">{a.note}<span className="block text-[11px] text-text-muted">{a.created_by} · {formatDate(a.created_at)}</span></span>
                    {canAdjust && <button type="button" title="Apagar" onClick={() => remove(a)} className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger flex items-center justify-center cursor-pointer"><Trash2 size={13} /></button>}
                  </div>
                ))}
              </div>
            )}
            {canAdjust && (
              <form noValidate onSubmit={add} className="flex gap-2 items-start">
                <input value={adjusting.days} inputMode="decimal" placeholder="Dias (ex.: 5 ou -2)" onChange={(e) => setAdjusting((p) => ({ ...p, days: e.target.value }))} className={inputClass + ' max-w-[140px] font-mono'} />
                <input value={adjusting.note} maxLength={300} placeholder="Motivo (ex.: saldo anterior ao RM SOFT)" onChange={(e) => setAdjusting((p) => ({ ...p, note: e.target.value }))} className={inputClass} />
                <button type="submit" disabled={busy} className="h-[38px] px-3 rounded-md bg-accent hover:bg-accent-hover text-white text-sm font-medium flex items-center gap-1.5 cursor-pointer disabled:opacity-50"><Plus size={14} /></button>
              </form>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}
