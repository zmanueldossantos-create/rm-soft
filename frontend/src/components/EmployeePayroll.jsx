import { useEffect, useMemo, useState } from 'react';
import { Loader2, Plus, Trash2, Save, Calculator, AlertTriangle } from 'lucide-react';
import Select from './Select';
import { getEmployeePayrollItems, setEmployeePayrollItems, listPayrollItems, simulatePayslip } from '../api/hr';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Remuneração of an existing employee: his own rubricas (a transport allowance of 15 000 Kz, a % of his salary) and the
// simulation of his payslip with the current settings - gross, INSS, IRT, net - with the month's values to try
// (overtime, a prize, absences). Nothing is paid here: the monthly processing comes in step 4.
const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const num = (v) => (v === '' || v === null || v === undefined ? null : Number(String(v).replace(/\s/g, '').replace(',', '.')));

function Row({ label, value, strong, muted, sign = '' }) {
  return (
    <div className={'flex justify-between gap-3 py-1 ' + (strong ? 'font-semibold text-text-primary' : muted ? 'text-text-muted' : 'text-text-primary')}>
      <span>{label}</span><span className="font-mono whitespace-nowrap">{sign}{formatKz(value)} Kz</span>
    </div>
  );
}

export default function EmployeePayroll({ employee, canManage }) {
  const [catalog, setCatalog] = useState(null);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState('');
  const [month, setMonth] = useState({});
  const [slip, setSlip] = useState(null);
  const [simulating, setSimulating] = useState(false);

  async function load() {
    try {
      const [cat, mine] = await Promise.all([listPayrollItems(), getEmployeePayrollItems(employee.id)]);
      setCatalog(cat);
      setRows(mine.map((r) => ({ ...r, amount: r.amount === null ? '' : String(r.amount), rate: r.rate === null ? '' : String(r.rate) })));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar as rubricas'));
    }
  }
  useEffect(() => { setSlip(null); setMonth({}); load(); }, [employee.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const assignable = useMemo(() => (catalog?.items || []).filter((i) => i.is_active && i.calc_method !== 'MENSAL' && !rows.some((r) => r.item_id === i.id)), [catalog, rows]);
  const monthly = useMemo(() => (catalog?.items || []).filter((i) => i.is_active && i.calc_method === 'MENSAL'), [catalog]);
  const forAll = useMemo(() => (catalog?.items || []).filter((i) => i.is_active && i.applies_to_all && !rows.some((r) => r.item_id === i.id)), [catalog, rows]);

  function add(itemId) {
    const item = catalog.items.find((i) => i.id === itemId);
    if (!item) return;
    setRows((p) => [...p, { item_id: item.id, code: item.code, name: item.name, nature: item.nature, calc_method: item.calc_method,
      amount: item.amount === null ? '' : String(item.amount), rate: '', default_rate: item.rate, default_amount: item.amount }]);
    setAdding('');
  }

  async function save() {
    setBusy(true);
    try {
      await setEmployeePayrollItems(employee.id, rows.map((r) => ({ item_id: r.item_id, amount: num(r.amount), rate: num(r.rate) })));
      toast.success('Rubricas do colaborador guardadas');
      setSlip(null);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar as rubricas'));
    } finally {
      setBusy(false);
    }
  }

  async function simulate() {
    setSimulating(true);
    try {
      const values = Object.fromEntries(Object.entries(month).map(([k, v]) => [k, num(v) || 0]).filter(([, v]) => v > 0));
      setSlip(await simulatePayslip(employee.id, values));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro na simulação'));
    } finally {
      setSimulating(false);
    }
  }

  if (!catalog) return <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-text-muted" /></div>;
  return (
    <div className="flex flex-col gap-4 border-t border-border pt-4">
      <div>
        <h4 className="text-sm font-semibold text-text-primary mb-2">Rubricas do colaborador</h4>
        {rows.length === 0 && <p className="text-[13px] text-text-muted mb-2">Nenhuma rubrica própria.</p>}
        {rows.map((r, k) => (
          <div key={r.item_id} className="flex items-center gap-2 mb-2">
            <span className="flex-1 text-sm text-text-primary">{r.name} <span className="text-[11px] font-mono text-text-muted">{r.code}</span></span>
            {r.calc_method === 'FIXO' && (
              <input value={r.amount} disabled={!canManage} inputMode="decimal" placeholder="Valor (Kz)" onChange={(e) => setRows((p) => p.map((x, i) => (i === k ? { ...x, amount: e.target.value } : x)))} className={inputClass + ' max-w-[160px] font-mono text-right'} />
            )}
            {r.calc_method === 'PERCENTAGEM' && (
              <input value={r.rate} disabled={!canManage} inputMode="decimal" placeholder={`${r.default_rate ?? ''} %`} onChange={(e) => setRows((p) => p.map((x, i) => (i === k ? { ...x, rate: e.target.value } : x)))} className={inputClass + ' max-w-[160px] font-mono text-right'} />
            )}
            {r.calc_method === 'FORMULA' && <span className="text-[12px] text-text-muted max-w-[160px]">Pela fórmula</span>}
            {canManage && <button type="button" title="Retirar" onClick={() => setRows((p) => p.filter((_, i) => i !== k))} className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger flex items-center justify-center cursor-pointer"><Trash2 size={13} /></button>}
          </div>
        ))}
        {forAll.length > 0 && <p className="text-[12px] text-text-muted mb-2">Para todos: {forAll.map((i) => i.name).join(', ')}.</p>}
        {canManage && (
          <div className="flex gap-2 items-center">
            <div className="flex-1"><Select value={adding} onChange={add} placeholder="Acrescentar uma rubrica..." options={assignable.map((i) => ({ value: i.id, label: `${i.name} (${i.code})` }))} /></div>
            <button type="button" onClick={save} disabled={busy} className="h-[38px] px-4 rounded-md border border-accent text-accent text-sm font-medium flex items-center gap-1.5 hover:bg-accent/10 cursor-pointer disabled:opacity-50">
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Guardar rubricas
            </button>
          </div>
        )}
      </div>

      <div className="border border-border rounded-md p-3">
        <h4 className="text-sm font-semibold text-text-primary mb-1 flex items-center gap-2"><Calculator size={15} className="text-accent" /> Simulação do recibo</h4>
        <p className="text-[12px] text-text-muted mb-3">Com o salário base e as rubricas guardados e os parâmetros salariais atuais. Indique, se quiser, os valores de um mês:</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
          {monthly.map((i) => (
            <div key={i.id}>
              <label className={labelClass}>{i.name}</label>
              <input value={month[i.code] || ''} inputMode="decimal" placeholder="0" onChange={(e) => setMonth((p) => ({ ...p, [i.code]: e.target.value }))} className={inputClass + ' font-mono text-right'} />
            </div>
          ))}
        </div>
        <button type="button" onClick={simulate} disabled={simulating} className="h-9 px-4 rounded-md bg-accent hover:bg-accent-hover text-white text-sm font-medium flex items-center gap-1.5 cursor-pointer disabled:opacity-50">
          {simulating ? <Loader2 size={14} className="animate-spin" /> : <Calculator size={14} />} Simular
        </button>
        {slip && (
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-5 text-sm">
            <div>
              <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">Abonos</p>
              <Row label="Salário base" value={slip.base_salary} />
              {slip.allowances.map((a) => <Row key={a.code} label={a.name + (a.irt_taxed < a.value ? ` (tributado ${formatKz(a.irt_taxed)})` : '')} value={a.value} />)}
              <div className="border-t border-border mt-1 pt-1"><Row label="Total ilíquido" value={slip.gross} strong /></div>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">Descontos</p>
              <Row label={`INSS (base ${formatKz(slip.inss_base)})`} value={slip.inss_employee} sign="- " />
              <Row label={`IRT (base ${formatKz(slip.irt_base)})`} value={slip.irt} sign="- " />
              {slip.deductions.map((d) => <Row key={d.code} label={d.name} value={d.value} sign="- " />)}
              <div className="border-t border-border mt-1 pt-1"><Row label="Líquido a receber" value={slip.net} strong /></div>
              <Row label="INSS da empresa" value={slip.inss_employer} muted />
              <Row label="Custo para a empresa" value={slip.employer_cost} muted />
              {slip.irt_table && <p className="text-[11px] text-text-muted mt-1">Tabela de IRT: {slip.irt_table}</p>}
              {slip.warning && <p className="text-[12px] text-danger mt-1 flex items-center gap-1.5"><AlertTriangle size={13} /> {slip.warning}</p>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
