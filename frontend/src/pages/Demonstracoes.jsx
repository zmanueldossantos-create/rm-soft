import { useEffect, useState } from 'react';
import { Landmark, Loader2, FileSpreadsheet, FileText, CheckCircle2, AlertTriangle } from 'lucide-react';
import Select from '../components/Select';
import DateInput from '../components/DateInput';
import { getFinancialStatements, downloadAccountingFile } from '../api/accounting';
import { extractErrorMessage } from '../utils/errors';
import { formatKz } from '../utils/format';
import { toast } from '../store/toastStore';

// Contabilidade › Demonstrações financeiras: the Balanço at a date and the Demonstração de resultados por natureza of
// the year up to that date, in the format of the PGC de Angola, with the figures of one year before (N-1). A cost and a
// negative figure in parentheses, as on the statements.

const inputCls = 'bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const btnGhost = 'flex items-center gap-1.5 border border-border hover:border-accent text-text-primary hover:text-accent text-[13px] font-semibold px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50';

const signed = (v) => {
  if (v === null || v === undefined) return '';
  const n = Number(v);
  if (!n) return '-';
  return n < 0 ? '(' + formatKz(-n) + ')' : formatKz(n);
};
const fmtDate = (value) => value.slice(8, 10) + '/' + value.slice(5, 7) + '/' + value.slice(0, 4);

function Statement({ title, rows, columns }) {
  return (
    <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted border-b border-border">
            <th className="px-4 py-3 font-semibold text-text-primary">{title}</th>
            <th className="px-4 py-3 font-medium text-right w-44">{columns[0]}</th>
            <th className="px-4 py-3 font-medium text-right w-44">{columns[1]}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            r.kind === 'section'
              ? <tr key={r.key} className="border-b border-border"><td colSpan={3} className="px-4 pt-4 pb-2 text-[12px] font-semibold uppercase tracking-wide text-accent">{r.label}</td></tr>
              : (
                <tr key={r.key} className={'border-b border-border last:border-0 ' + (r.kind === 'total' ? 'bg-bg-inset/60 font-semibold' : '')}>
                  <td className={'py-2 text-text-primary ' + (r.kind === 'total' ? 'px-4' : 'pl-8 pr-4')}>{r.label}</td>
                  <td className="px-4 py-2 text-right font-mono whitespace-nowrap">{signed(r.value)}</td>
                  <td className="px-4 py-2 text-right font-mono whitespace-nowrap text-text-muted">{signed(r.previous)}</td>
                </tr>
              )
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Demonstracoes() {
  const today = new Date();
  const thisYear = today.getFullYear();
  const [year, setYear] = useState(String(thisYear));
  const [dateTo, setDateTo] = useState(today.toISOString().slice(0, 10));
  const [view, setView] = useState('balance'); // balance | income
  const [data, setData] = useState(null);
  const dateFrom = year + '-01-01';

  useEffect(() => {
    if (!dateTo) return;
    setData(null);
    getFinancialStatements(dateFrom, dateTo).then(setData)
      .catch((err) => toast.error(extractErrorMessage(err, 'Erro ao calcular as demonstrações')));
  }, [dateFrom, dateTo]);

  function chooseYear(value) {
    setYear(value);
    // the whole year when it is over, up to today for the current one
    setDateTo(Number(value) < thisYear ? value + '-12-31' : today.toISOString().slice(0, 10));
  }

  function download(kind) {
    const params = { date_from: dateFrom, date_to: dateTo, ...(kind === 'pdf' ? { which: view === 'balance' ? 'balance' : 'income' } : {}) };
    downloadAccountingFile('/accounting/financial-statements/' + kind, params, 'demonstracoes_' + dateTo + '.xlsx', kind === 'pdf')
      .catch(() => toast.error('Erro ao gerar o ficheiro'));
  }

  const years = Array.from({ length: 5 }, (_, i) => String(thisYear - i)).map((y) => ({ value: y, label: 'Exercício ' + y }));
  const sheet = data?.balance_sheet;

  return (
    <main className="max-w-[1200px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-text-primary flex items-center gap-2.5"><Landmark size={22} className="text-accent" /> Demonstrações financeiras</h1>
          <p className="text-text-muted text-sm mt-1">Balanço e demonstração de resultados por natureza, no modelo do PGC de Angola, com o exercício anterior</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => download('excel')} className={btnGhost}><FileSpreadsheet size={15} /> Excel</button>
          <button type="button" onClick={() => download('pdf')} className={btnGhost}><FileText size={15} /> PDF</button>
        </div>
      </div>

      <div className="flex items-end gap-3 flex-wrap mb-4">
        <div className="w-48">
          <label className={labelCls}>Exercício</label>
          <Select value={year} onChange={chooseYear} options={years} />
        </div>
        <div className="w-44">
          <label className={labelCls}>Até</label>
          <DateInput value={dateTo} min={dateFrom} max={year + '-12-31'} onChange={(e) => setDateTo(e.target.value)} className={inputCls + ' w-full'} />
        </div>
      </div>

      <div className="flex gap-1 mb-5 border-b border-border">
        {[['balance', 'Balanço'], ['income', 'Demonstração de resultados']].map(([key, label]) => (
          <button key={key} type="button" onClick={() => setView(key)}
            className={'px-4 py-2.5 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer ' + (view === key ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary')}>
            {label}
          </button>
        ))}
      </div>

      {!data && <div className="flex justify-center py-12"><Loader2 className="animate-spin text-accent" /></div>}

      {data && view === 'balance' && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-4 flex-wrap text-[13px]">
            <span className="text-text-muted">Balanço em {fmtDate(data.date_to)} · comparativo em {fmtDate(data.previous_to)}</span>
            {sheet.balanced
              ? <span className="flex items-center gap-1.5 font-semibold text-success"><CheckCircle2 size={15} /> Activo = capital próprio + passivo</span>
              : <span className="flex items-center gap-1.5 font-semibold text-amber-500"><AlertTriangle size={15} /> O balanço não está equilibrado</span>}
          </div>
          {sheet.unclassified.length > 0 && (
            <p className="text-[13px] text-amber-500 bg-amber-500/10 border border-amber-500/30 rounded-md px-4 py-3">
              Contas com saldo fora do modelo do PGC (não aparecem no balanço): {sheet.unclassified.join(', ')}
            </p>
          )}
          <Statement title="Activo" rows={sheet.assets} columns={[fmtDate(data.date_to), fmtDate(data.previous_to)]} />
          <Statement title="Capital próprio e passivo" rows={sheet.equity_liabilities} columns={[fmtDate(data.date_to), fmtDate(data.previous_to)]} />
        </div>
      )}

      {data && view === 'income' && (
        <div className="flex flex-col gap-4">
          <span className="text-[13px] text-text-muted">De {fmtDate(data.date_from)} a {fmtDate(data.date_to)} · comparativo de {fmtDate(data.previous_from)} a {fmtDate(data.previous_to)}</span>
          <Statement title="Proveitos e custos" rows={data.income_statement} columns={['Exercício ' + year, 'Exercício ' + (Number(year) - 1)]} />
        </div>
      )}
    </main>
  );
}
