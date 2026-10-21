import { useEffect, useState } from 'react';
import { FileText, Loader2, Printer, Search } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import { extractErrorMessage } from '../utils/errors';
import { listPrescriptions, fetchPrescriptionsPdf, getPsychotropicRegister, fetchPsychotropicsPdf, listInsuranceShares, fetchInsuranceSharesPdf } from '../api/pharmacy';
import { listCustomers } from '../api/customers';
import { formatKz } from '../utils/format';
import { useToastState } from '../components/Toaster';

// Farmácia - the registers (pharmacy_register_service): the registo de receitas (every sale dispensed against a
// receita, its medicines and lots) and the registo de psicotrópicos e estupefacientes (per medicine of receita
// especial: the stock at the start, every entry and exit with its receita and patient, the stock at the end) - built
// from what is recorded, nothing to enter. Both printable for the inspection.
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const inputCls = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent';
const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5 whitespace-nowrap';
const qty = (v) => (v == null ? '' : Number(v).toLocaleString('pt-PT', { maximumFractionDigits: 3 }));
const day = (v) => new Date(v.length === 10 ? v + 'T00:00:00' : v).toLocaleDateString('pt-PT');
const pad = (n) => String(n).padStart(2, '0');
const iso = (d) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());

function monthStart() {
  const d = new Date();
  return iso(new Date(d.getFullYear(), d.getMonth(), 1));
}

export default function Receitas() {
  const [tab, setTab] = useState('receitas');
  const [filters, setFilters] = useState({ dateFrom: monthStart(), dateTo: iso(new Date()), special: 'todas', q: '', insurerId: '' });
  const [shares, setShares] = useState(null); // Comparticipações: the sales shared with insurers
  const [insurers, setInsurers] = useState([]);
  useEffect(() => { listCustomers().then((list) => setInsurers(list.filter((c) => c.is_insurer))).catch(() => setInsurers([])); }, []);
  const [prescriptions, setPrescriptions] = useState(null);
  const [register, setRegister] = useState(null);
  const [error, setError] = useToastState('error');
  const [pdf, setPdf] = useState(null);
  const set = (field, value) => setFilters((prev) => ({ ...prev, [field]: value }));

  useEffect(() => {
    if (!filters.dateFrom || !filters.dateTo) return;
    setError('');
    if (tab === 'receitas') {
      setPrescriptions(null);
      const timer = setTimeout(() => {
        listPrescriptions(filters).then(setPrescriptions).catch((err) => { setPrescriptions([]); setError(extractErrorMessage(err, 'Erro ao carregar as receitas')); });
      }, 250);  // the search box: one request once the typing stops
      return () => clearTimeout(timer);
    }
    if (tab === 'comparticipacoes') {
      setShares(null);
      listInsuranceShares(filters).then(setShares).catch((err) => { setShares([]); setError(extractErrorMessage(err, 'Erro ao carregar as comparticipações')); });
      return undefined;
    }
    setRegister(null);
    getPsychotropicRegister(filters).then(setRegister).catch((err) => { setRegister([]); setError(extractErrorMessage(err, 'Erro ao carregar o registo')); });
    return undefined;
  }, [tab, filters]);

  async function print() {
    try {
      const url = tab === 'receitas' ? await fetchPrescriptionsPdf(filters)
        : tab === 'comparticipacoes' ? await fetchInsuranceSharesPdf(filters) : await fetchPsychotropicsPdf(filters);
      setPdf({ url, title: tab === 'receitas' ? 'Registo de receitas' : tab === 'comparticipacoes' ? 'Relação de comparticipações' : 'Registo de psicotrópicos e estupefacientes' });
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao gerar o PDF'));
    }
  }

  const loading = tab === 'receitas' ? prescriptions === null : tab === 'comparticipacoes' ? shares === null : register === null;

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <FileText size={22} className="text-accent" />
        Receitas e registos
      </h2>
      <p className="text-text-muted text-sm mb-6">As vendas com receita médica, o registo dos psicotrópicos e estupefacientes, e as comparticipações das seguradoras</p>

      <div className="flex gap-1 border-b border-border mb-5">
        {[['receitas', 'Receitas'], ['psicotropicos', 'Psicotrópicos e estupefacientes'], ['comparticipacoes', 'Comparticipações']].map(([key, label]) => (
          <button key={key} type="button" onClick={() => setTab(key)} className={'px-3.5 py-2 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer ' + (tab === key ? 'border-accent text-text-primary' : 'border-transparent text-text-muted hover:text-text-primary')}>
            {label}
          </button>
        ))}
      </div>

      <div className="flex items-end gap-3 flex-wrap mb-5">
        <div className="w-40"><label className={labelCls}>De</label><input type="date" value={filters.dateFrom} onChange={(e) => set('dateFrom', e.target.value)} className={inputCls} /></div>
        <div className="w-40"><label className={labelCls}>Até</label><input type="date" value={filters.dateTo} onChange={(e) => set('dateTo', e.target.value)} className={inputCls} /></div>
        {tab === 'receitas' && (
          <>
            <div className="w-48"><label className={labelCls}>Tipo</label>
              <Select value={filters.special} onChange={(v) => set('special', v)} options={[{ value: 'todas', label: 'Todas' }, { value: 'normal', label: 'Receita médica' }, { value: 'especial', label: 'Receita especial' }]} />
            </div>
            <div className="relative w-72">
              <label className={labelCls}>Pesquisar</label>
              <Search size={15} className="absolute left-3 bottom-2.5 text-text-muted" />
              <input value={filters.q} onChange={(e) => set('q', e.target.value)} placeholder="N.º, médico, utente, medicamento..." className={inputCls + ' pl-9 font-sans'} />
            </div>
          </>
        )}
        {tab === 'comparticipacoes' && (
          <div className="w-64"><label className={labelCls}>Entidade</label>
            <Select value={filters.insurerId} onChange={(v) => set('insurerId', v)} options={[{ value: '', label: 'Todas as entidades' }, ...insurers.map((c) => ({ value: c.id, label: c.name }))]} />
          </div>
        )}
        <button type="button" onClick={print} disabled={loading} className="ml-auto flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-semibold rounded-md px-4 py-2.5 cursor-pointer">
          <Printer size={15} /> Imprimir
        </button>
      </div>

      {loading && <div className="flex justify-center py-16"><Loader2 size={20} className="animate-spin text-accent" /></div>}

      {!loading && tab === 'receitas' && (
        <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
          {prescriptions.length === 0 ? (
            <p className="text-center py-14 text-text-muted text-sm">Nenhuma venda com receita neste período</p>
          ) : (
            <table className="w-full text-sm min-w-[1100px]">
              <thead><tr className="border-b border-border">
                <th className={th + ' text-left'}>Data</th><th className={th + ' text-left'}>Documento</th><th className={th + ' text-left'}>N.º receita</th>
                <th className={th + ' text-left'}>Médico · unidade de saúde</th><th className={th + ' text-left'}>Utente</th><th className={th + ' text-left'}>Medicamentos</th>
              </tr></thead>
              <tbody>
                {prescriptions.map((e) => (
                  <tr key={e.id} className="border-b border-border last:border-0 align-top">
                    <td className="px-3 py-2.5 font-mono text-text-muted whitespace-nowrap">{day(e.date)}</td>
                    <td className="px-3 py-2.5 font-mono text-text-primary whitespace-nowrap">{e.reference}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <span className="font-mono text-text-primary">{e.number || '-'}</span>
                      {e.is_special && <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-danger/10 text-danger">Especial</span>}
                    </td>
                    <td className="px-3 py-2.5 text-text-primary">{e.prescriber || '-'}{e.health_unit && <span className="block text-[12px] text-text-muted">{e.health_unit}</span>}</td>
                    <td className="px-3 py-2.5 text-text-primary">{e.patient_name || '-'}{e.patient_document && <span className="block font-mono text-[12px] text-text-muted">{e.patient_document}</span>}</td>
                    <td className="px-3 py-2.5">
                      {e.items.map((i, k) => (
                        <span key={k} className="block text-text-primary">
                          {i.product_name} <span className="font-mono text-text-muted">{qty(i.quantity)} {i.unit || ''}</span>
                          {i.lots.length > 0 && <span className="block text-[11px] text-text-muted">{i.lots.join(' · ')}</span>}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {!loading && tab === 'psicotropicos' && (
        register.length === 0 ? (
          <div className="bg-bg-elevated border border-border rounded-lg text-center py-14 text-text-muted text-sm">Nenhum medicamento de receita especial com stock ou movimentos neste período</div>
        ) : (
          <div className="flex flex-col gap-5">
            {register.map((p) => (
              <div key={p.product_id} className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
                <div className="flex items-center justify-between gap-3 flex-wrap px-4 pt-3.5 pb-2.5">
                  <p className="font-semibold text-sm text-text-primary">
                    <span className="font-mono text-text-muted text-[12px] mr-2">{p.product_code}</span>{p.product_name}
                    {p.active_substance && <span className="font-normal text-text-muted"> · {p.active_substance}{p.dosage ? ' ' + p.dosage : ''}</span>}
                  </p>
                  <p className="text-[12px] text-text-muted">
                    Inicial <span className="font-mono text-text-primary">{qty(p.opening)}</span> · Entradas <span className="font-mono text-success">{qty(p.total_in)}</span> ·
                    Saídas <span className="font-mono text-danger">{qty(p.total_out)}</span> · Final <span className="font-mono text-text-primary font-semibold">{qty(p.closing)}</span>
                  </p>
                </div>
                <table className="w-full text-sm min-w-[1150px]">
                  <thead><tr className="border-y border-border">
                    <th className={th + ' text-left'}>Data</th><th className={th + ' text-left'}>Movimento</th><th className={th + ' text-left'}>Documento</th>
                    <th className={th + ' text-left'}>Fornecedor / cliente / motivo</th><th className={th + ' text-left'}>Receita</th><th className={th + ' text-left'}>Utente</th>
                    <th className={th + ' text-left'}>Lote</th><th className={th + ' text-right'}>Entrada</th><th className={th + ' text-right'}>Saída</th><th className={th + ' text-right'}>Saldo</th>
                  </tr></thead>
                  <tbody>
                    {p.lines.length === 0 && (
                      <tr><td colSpan={10} className="px-3 py-4 text-center text-[13px] text-text-muted">Sem movimentos no período</td></tr>
                    )}
                    {p.lines.map((l, i) => (
                      <tr key={i} className="border-b border-border last:border-0">
                        <td className="px-3 py-2 font-mono text-text-muted whitespace-nowrap">{day(l.date)}</td>
                        <td className="px-3 py-2 text-text-primary">{l.type}</td>
                        <td className="px-3 py-2 font-mono text-text-primary whitespace-nowrap">{l.reference || '-'}</td>
                        <td className="px-3 py-2 text-text-primary">{l.detail || '-'}</td>
                        <td className="px-3 py-2 font-mono text-text-primary">{l.prescription || ''}</td>
                        <td className="px-3 py-2 text-text-primary">{l.patient || ''}{l.patient_document && <span className="block font-mono text-[11px] text-text-muted">{l.patient_document}</span>}</td>
                        <td className="px-3 py-2 text-[12px] text-text-muted">{l.lots.join(' · ')}</td>
                        <td className="px-3 py-2 font-mono text-success text-right">{qty(l.quantity_in)}</td>
                        <td className="px-3 py-2 font-mono text-danger text-right">{qty(l.quantity_out)}</td>
                        <td className="px-3 py-2 font-mono text-text-primary text-right">{qty(l.balance)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )
      )}

      {!loading && tab === 'comparticipacoes' && (
        <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
          {shares.length === 0 ? (
            <p className="text-center py-14 text-text-muted text-sm">Nenhuma venda comparticipada neste período</p>
          ) : (
            <table className="w-full text-sm min-w-[1150px]">
              <thead><tr className="border-b border-border">
                <th className={th + ' text-left'}>Data</th><th className={th + ' text-left'}>Entidade</th><th className={th + ' text-left'}>Fatura entidade</th>
                <th className={th + ' text-left'}>Documento utente</th><th className={th + ' text-left'}>Beneficiário · cartão</th><th className={th + ' text-left'}>Receita</th>
                <th className={th + ' text-right'}>Taxa</th><th className={th + ' text-right'}>Parte do utente</th><th className={th + ' text-right'}>Entidade</th><th className={th + ' text-right'}>Por receber</th>
              </tr></thead>
              <tbody>
                {shares.map((r) => (
                  <tr key={r.id} className="border-b border-border last:border-0">
                    <td className="px-3 py-2.5 font-mono text-text-muted whitespace-nowrap">{day(r.date)}</td>
                    <td className="px-3 py-2.5 text-text-primary">{r.insurer}</td>
                    <td className="px-3 py-2.5 font-mono text-text-primary whitespace-nowrap">{r.insurer_reference}</td>
                    <td className="px-3 py-2.5 font-mono text-text-primary whitespace-nowrap">{r.patient_reference || '-'}</td>
                    <td className="px-3 py-2.5 text-text-primary">{r.beneficiary_name || '-'}<span className="block font-mono text-[12px] text-text-muted">{r.card_number}</span></td>
                    <td className="px-3 py-2.5 font-mono text-text-primary">{r.prescription || ''}</td>
                    <td className="px-3 py-2.5 font-mono text-text-muted text-right">{r.coverage_pct}%</td>
                    <td className="px-3 py-2.5 font-mono text-text-primary text-right whitespace-nowrap">{formatKz(r.patient_amount)}</td>
                    <td className="px-3 py-2.5 font-mono text-text-primary text-right whitespace-nowrap">{formatKz(r.insurer_amount)}</td>
                    <td className={'px-3 py-2.5 font-mono text-right whitespace-nowrap ' + (r.amount_due > 0 ? 'text-danger' : 'text-success')}>{formatKz(r.amount_due)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr className="border-t border-border bg-bg-inset/40 font-semibold">
                <td colSpan={8} className="px-3 py-2.5 text-text-primary">Total ({shares.length} venda{shares.length === 1 ? '' : 's'})</td>
                <td className="px-3 py-2.5 font-mono text-text-primary text-right whitespace-nowrap">{formatKz(shares.reduce((a, r) => a + r.insurer_amount, 0))}</td>
                <td className={'px-3 py-2.5 font-mono text-right whitespace-nowrap ' + (shares.some((r) => r.amount_due > 0) ? 'text-danger' : 'text-success')}>{formatKz(shares.reduce((a, r) => a + r.amount_due, 0))}</td>
              </tr></tfoot>
            </table>
          )}
        </div>
      )}

      <Modal open={!!pdf} onClose={() => { if (pdf?.url) URL.revokeObjectURL(pdf.url); setPdf(null); }} title={pdf?.title || ''} maxWidthClass="max-w-6xl">
        {pdf && <iframe src={pdf.url} title={pdf.title} className="w-full h-[75vh] rounded-md border border-border" />}
      </Modal>
    </main>
  );
}
