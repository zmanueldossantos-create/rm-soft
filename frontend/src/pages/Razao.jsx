import { useEffect, useMemo, useState } from 'react';
import { BookOpenText, Loader2, FileSpreadsheet, FileText, Search } from 'lucide-react';
import Select from '../components/Select';
import DateInput from '../components/DateInput';
import { getChart, getGeneralLedger, downloadAccountingFile } from '../api/accounting';
import { extractErrorMessage } from '../utils/errors';
import { formatKz } from '../utils/format';
import { toast } from '../store/toastStore';

// Contabilidade › Razão (grande livro): the extrato of every last-level account of a range of codes (all by default)
// that holds a balance or moved in the period - its opening balance, its lines with the running balance, its totals.
// A bound covers its sub-accounts («4» to «45» reaches 45.9.9). Only the posted entries count. PDF and Excel.

const inputCls = 'bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const btnGhost = 'flex items-center gap-1.5 border border-border hover:border-accent text-text-primary hover:text-accent text-[13px] font-semibold px-3.5 py-2.5 rounded-md transition-colors cursor-pointer disabled:opacity-50';

const iso = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); // local day
const fmtDate = (value) => value.slice(8, 10) + '/' + value.slice(5, 7) + '/' + value.slice(0, 4);
const amount = (v) => (Number(v) ? formatKz(Number(v)) : '');
const side = (v) => { const n = Number(v); return n ? formatKz(Math.abs(n)) + (n > 0 ? ' D' : ' C') : '0,00'; };

export default function Razao() {
  const today = new Date();
  const [filters, setFilters] = useState({ date_from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), date_to: iso(today), code_from: '', code_to: '' });
  const [accounts, setAccounts] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getChart().then((c) => setAccounts(c.accounts || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!filters.date_from || !filters.date_to) return undefined;
    const timer = setTimeout(() => {
      setLoading(true);
      getGeneralLedger(params(filters)).then(setData)
        .catch((err) => toast.error(extractErrorMessage(err, 'Erro ao calcular o razão')))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [filters]);

  // any account of the chart as a bound (a class or an account covers its sub-accounts)
  const options = useMemo(() => [{ value: '', label: '— Todas —' },
    ...accounts.map((a) => ({ value: a.code, label: a.code + ' · ' + a.name }))], [accounts]);

  function params(f) {
    return { date_from: f.date_from, date_to: f.date_to, ...(f.code_from ? { code_from: f.code_from } : {}), ...(f.code_to ? { code_to: f.code_to } : {}) };
  }

  function download(kind) {
    downloadAccountingFile('/accounting/general-ledger/' + kind, params(filters), 'razao_' + filters.date_from + '_' + filters.date_to + '.xlsx', kind === 'pdf')
      .catch(() => toast.error('Erro ao gerar o ficheiro'));
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <h1 className="font-display text-2xl sm:text-[28px] font-bold text-text-primary flex items-center gap-3"><BookOpenText className="text-accent" size={26} /> Razão (grande livro)</h1>
          <p className="text-text-muted text-sm mt-1">Os movimentos de cada conta no período, com o saldo inicial e o saldo acumulado - só os lançamentos lançados</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className={btnGhost} onClick={() => download('pdf')}><FileText size={15} /> PDF</button>
          <button type="button" className={btnGhost} onClick={() => download('excel')}><FileSpreadsheet size={15} /> Excel</button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <div>
          <label className={labelCls}>De</label>
          <DateInput value={filters.date_from} onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))} className={inputCls + ' w-full'} />
        </div>
        <div>
          <label className={labelCls}>Até</label>
          <DateInput value={filters.date_to} min={filters.date_from || undefined} onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value }))} className={inputCls + ' w-full'} />
        </div>
        <div>
          <label className={labelCls}>Da conta</label>
          <Select value={filters.code_from} onChange={(v) => setFilters((f) => ({ ...f, code_from: v }))} options={options} placeholder="— Todas —" />
        </div>
        <div>
          <label className={labelCls}>À conta</label>
          <Select value={filters.code_to} onChange={(v) => setFilters((f) => ({ ...f, code_to: v }))} options={options} placeholder="— Todas —" />
        </div>
      </div>

      {(!data || loading) && <div className="flex justify-center py-12"><Loader2 className="animate-spin text-accent" /></div>}
      {data && !loading && data.accounts.length === 0 && (
        <div className="bg-bg-elevated border border-border rounded-lg py-12 text-center text-text-muted text-[13px] flex flex-col items-center gap-2">
          <Search size={20} /> Nenhuma conta com saldo ou movimento no período
        </div>
      )}
      {data && !loading && (
        <div className="flex flex-col gap-4">
          {data.accounts.map((a) => (
            <div key={a.id} className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
              <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border flex-wrap">
                <p className="text-[14px] font-semibold text-text-primary"><span className="font-mono">{a.code}</span> · {a.name}</p>
                <p className="text-[12px] text-text-muted">Saldo inicial <span className="font-mono text-text-primary">{side(a.opening)}</span> · saldo final <span className="font-mono text-text-primary">{side(a.closing)}</span></p>
              </div>
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted border-b border-border bg-bg-inset/60">
                    <th className="px-4 py-2 font-medium w-28">Data</th>
                    <th className="px-4 py-2 font-medium w-36">Lançamento</th>
                    <th className="px-4 py-2 font-medium">Descrição</th>
                    <th className="px-4 py-2 font-medium text-right w-36">Débito</th>
                    <th className="px-4 py-2 font-medium text-right w-36">Crédito</th>
                    <th className="px-4 py-2 font-medium text-right w-40">Saldo</th>
                  </tr>
                </thead>
                <tbody>
                  {a.lines.length === 0 && <tr><td colSpan={6} className="px-4 py-2.5 text-text-muted">Sem movimentos no período</td></tr>}
                  {a.lines.map((l, i) => (
                    <tr key={i} className="border-b border-border last:border-0">
                      <td className="px-4 py-2 whitespace-nowrap text-text-muted">{fmtDate(l.date)}</td>
                      <td className="px-4 py-2 whitespace-nowrap font-mono">{l.entry}</td>
                      <td className="px-4 py-2 text-text-primary">{l.description}{l.document_ref && <span className="text-text-muted"> · {l.document_ref}</span>}</td>
                      <td className="px-4 py-2 text-right font-mono whitespace-nowrap">{amount(l.debit)}</td>
                      <td className="px-4 py-2 text-right font-mono whitespace-nowrap">{amount(l.credit)}</td>
                      <td className="px-4 py-2 text-right font-mono whitespace-nowrap">{side(l.balance)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-border bg-bg-inset/60 font-semibold">
                    <td colSpan={3} className="px-4 py-2.5">Totais do período</td>
                    <td className="px-4 py-2.5 text-right font-mono">{amount(a.total_debit)}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{amount(a.total_credit)}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{side(a.closing)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
