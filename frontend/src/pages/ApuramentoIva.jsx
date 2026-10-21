import { useEffect, useState } from 'react';
import { Calculator, Loader2, FileText, Eye } from 'lucide-react';
import Select from '../components/Select';
import Modal from '../components/Modal';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { listVatPeriods, getVatReturn, listVatDocuments, fetchVatReturnPdfBlob } from '../api/vatReturn';
import { fetchInvoicePdfBlob } from '../api/invoices';
import { getPurchaseInvoice } from '../api/purchases';
import { useCan } from '../utils/permissions';
import { useToastState } from '../components/Toaster';

// Apuramento do IVA (vat_return_service): the VAT of a month - charged on the sales documents (a credit note against),
// deductible on the purchase invoices of the period - and the result by the company's regime (its data). Each line
// opens the documents behind it (Ver documentos), each one openable (its PDF, or the purchase invoice), for the
// accountant to check. A read only.
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2.5 whitespace-nowrap';
const kz = (v) => formatKz(v) + ' Kz';
const rateLabel = (l) => l.tax_code + ' ' + Number(l.rate) + ' %' + (l.exemption_code ? ' · ' + l.exemption_code : '');
const actionBtn = 'inline-flex items-center gap-1.5 border border-border hover:border-accent hover:text-accent text-text-primary text-[12px] font-medium px-2.5 py-1.5 rounded-md cursor-pointer whitespace-nowrap transition-colors';
const day = (v) => new Date(v + 'T00:00:00').toLocaleDateString('pt-PT');

function Kpi({ label, value, tone = 'text-text-primary', hint }) {
  return (
    <div className="bg-bg-elevated border border-border rounded-lg px-5 py-4">
      <p className="text-[11px] uppercase tracking-wide text-text-muted">{label}</p>
      <p className={'font-mono font-semibold text-2xl mt-1 whitespace-nowrap ' + tone}>{value}</p>
      {hint && <p className="text-[12px] text-text-muted mt-0.5">{hint}</p>}
    </div>
  );
}

function VatTable({ title, lines, purchases, total, onOpen }) {
  return (
    <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
      <p className="px-4 pt-3.5 pb-2 font-semibold text-sm text-text-primary">{title}</p>
      <table className="w-full text-sm">
        <thead><tr className="border-y border-border">
          <th className={th + ' text-left'}>Taxa</th><th className={th + ' text-right'}>Documentos</th><th className={th + ' text-right'}>Base</th>
          <th className={th + ' text-right'}>{purchases ? 'IVA suportado' : 'IVA'}</th>{purchases && <th className={th + ' text-right'}>Dedutível</th>}<th className={th + ' text-right w-44'}>Ações</th>
        </tr></thead>
        <tbody>
          {lines.length === 0 ? (
            <tr><td colSpan={purchases ? 6 : 5} className="px-4 py-6 text-center text-[13px] text-text-muted">{purchases ? 'Sem faturas de compra neste período' : 'Sem vendas neste período'}</td></tr>
          ) : lines.map((l) => (
            <tr key={rateLabel(l)} className="border-b border-border last:border-0">
              <td className="px-4 py-2.5 font-mono text-text-primary">{rateLabel(l)}</td>
              <td className="px-4 py-2.5 text-right font-mono text-text-primary">{l.documents}</td>
              <td className="px-4 py-2.5 text-right font-mono text-text-primary whitespace-nowrap">{kz(l.base)}</td>
              <td className="px-4 py-2.5 text-right font-mono text-text-primary whitespace-nowrap">{kz(l.vat)}</td>
              {purchases && <td className="px-4 py-2.5 text-right font-mono text-success whitespace-nowrap">{kz(l.deductible)}</td>}
              <td className="px-4 py-2 text-right"><button type="button" onClick={() => onOpen(l)} className={actionBtn}><Eye size={14} /> Ver documentos</button></td>
            </tr>
          ))}
        </tbody>
        {lines.length > 0 && (
          <tfoot><tr className="border-t border-border bg-bg-inset/40 font-semibold">
            <td className="px-4 py-2.5 text-text-primary" colSpan={2}>Total</td>
            {total.map((v, i) => <td key={i} className={'px-4 py-2.5 text-right font-mono whitespace-nowrap ' + (purchases && i === 2 ? 'text-success' : 'text-text-primary')}>{kz(v)}</td>)}
            <td />
          </tr></tfoot>
        )}
      </table>
    </div>
  );
}

export default function ApuramentoIva() {
  const [periods, setPeriods] = useState([]);
  const [periodId, setPeriodId] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useToastState('error');
  const [detail, setDetail] = useState(null);
  const [pdf, setPdf] = useState(null);
  const [purchase, setPurchase] = useState(null);
  const can = useCan();

  useEffect(() => {
    listVatPeriods().then((list) => {
      setPeriods(list);
      // the open month first, else the most recent one
      setPeriodId((list.find((p) => p.status === 'ABERTO') || list[0])?.id || '');
      if (!list.length) setLoading(false);
    }).catch((err) => { setError(extractErrorMessage(err, 'Erro ao carregar os períodos')); setLoading(false); });
  }, []);

  useEffect(() => {
    if (!periodId) return;
    setLoading(true);
    setError('');
    getVatReturn(periodId).then(setData)
      .catch((err) => setError(extractErrorMessage(err, 'Erro ao calcular o apuramento do IVA')))
      .finally(() => setLoading(false));
  }, [periodId]);

  async function openLine(side, line) {
    setDetail({ side, line, documents: null });
    try {
      const documents = await listVatDocuments(periodId, side, line);
      setDetail({ side, line, documents });
    } catch (err) {
      setDetail(null);
      setError(extractErrorMessage(err, 'Erro ao carregar os documentos'));
    }
  }

  // one document of a line: a sale opens its A4 PDF, a purchase invoice its registration
  async function openDocument(side, doc) {
    try {
      if (side === 'sales') setPdf({ url: await fetchInvoicePdfBlob(doc.id, 'a4'), title: doc.reference, stacked: true });
      else setPurchase(await getPurchaseInvoice(doc.id));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao abrir o documento'));
    }
  }

  async function openPdf() {
    try {
      setPdf({ url: await fetchVatReturnPdfBlob(periodId), title: 'Apuramento do IVA - ' + data.period_label });
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao gerar o PDF'));
    }
  }

  const resultLabel = !data ? '' : data.no_return ? 'Sem apuramento' : data.result >= 0 ? 'IVA a pagar' : 'Crédito de IVA';
  const resultValue = !data ? 0 : data.no_return ? 0 : data.result >= 0 ? data.to_pay : data.credit;

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-end justify-between gap-3 mb-6 flex-wrap">
        <div>
          <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
            <Calculator size={22} className="text-accent" /> Apuramento do IVA
          </h2>
          <p className="text-text-muted text-sm">IVA liquidado nas vendas, IVA dedutível nas compras e o resultado do mês - todas as atividades da empresa</p>
        </div>
        <div className="flex items-end gap-2.5">
          <div className="w-56">
            <label className={labelCls}>Período</label>
            <Select value={periodId} onChange={setPeriodId} placeholder="Selecionar" options={periods.map((p) => ({ value: p.id, label: p.label }))} />
          </div>
          <button onClick={openPdf} disabled={!data} className="flex items-center gap-2 border border-border hover:border-accent text-text-primary font-medium text-sm px-4 py-2.5 rounded-md cursor-pointer disabled:opacity-40">
            <FileText size={16} /> PDF
          </button>
        </div>
      </div>


      {loading ? (
        <div className="flex justify-center py-16"><Loader2 size={20} className="animate-spin text-accent" /></div>
      ) : !data ? (
        <p className="text-text-muted text-[13px] text-center py-16">Nenhum período fiscal</p>
      ) : (
        <div className="flex flex-col gap-5">
          <p className="text-[13px] text-text-muted">
            Regime: <span className="text-text-primary">{data.regime_name || '-'}</span> · IVA dedutível nas compras {data.input_vat_deductible_pct} %
            {data.turnover_vat_pct > 0 && <> · IVA de {data.turnover_vat_pct} % sobre o volume de negócios</>}
            {' '}· {day(data.date_from)} a {day(data.date_to)}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Kpi label="IVA liquidado (vendas)" value={kz(data.output_vat + data.turnover_vat)}
              hint={data.turnover_vat_pct > 0
                ? `inclui ${kz(data.turnover_vat)} sobre o volume de negócios (base ${kz(data.turnover_base)}`
                  + (data.turnover_excluded ? `, sem ${kz(data.turnover_excluded)} isentos ${data.turnover_excluded_codes.join(', ')}` : '') + ')'
                : `base ${kz(data.sales_base)}`} />
            <Kpi label="IVA dedutível (compras)" value={kz(data.deductible_vat)} tone="text-success" hint={`suportado ${kz(data.input_vat)}`} />
            <Kpi label={resultLabel} value={kz(resultValue)} tone={data.no_return ? 'text-text-muted' : data.result >= 0 ? 'text-danger' : 'text-success'}
              hint={data.no_return ? 'O regime da empresa não tem apuramento de IVA' : data.result < 0 ? 'O reporte para o mês seguinte não é calculado aqui' : null} />
          </div>
          <VatTable title="IVA liquidado (vendas)" lines={data.sales} total={[data.sales_base, data.output_vat]} onOpen={(l) => openLine('sales', l)} />
          <VatTable title="IVA dedutível (compras)" lines={data.purchases} purchases total={[data.purchases_base, data.input_vat, data.deductible_vat]} onOpen={(l) => openLine('purchases', l)} />
        </div>
      )}

      <Modal open={!!detail} onClose={() => setDetail(null)} maxWidthClass="max-w-6xl"
        title={detail ? (detail.side === 'sales' ? 'Vendas' : 'Compras') + ' · ' + rateLabel(detail.line) : ''}>
        {detail && (detail.documents === null ? (
          <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-accent" /></div>
        ) : (
          <div className="border border-border rounded-md overflow-auto max-h-[65vh]">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border">
                <th className={th + ' text-left'}>Documento</th><th className={th + ' text-left'}>Data</th>
                <th className={th + ' text-left'}>{detail.side === 'sales' ? 'Cliente' : 'Fornecedor'}</th>
                <th className={th + ' text-right'}>Base</th><th className={th + ' text-right'}>IVA</th>
                {detail.side === 'purchases' && <th className={th + ' text-right'}>Dedutível</th>}
                <th className={th + ' text-right'}>Ações</th>
              </tr></thead>
              <tbody>
                {detail.documents.map((d) => (
                  <tr key={d.reference} className="border-b border-border last:border-0">
                    <td className="px-4 py-2 font-mono text-text-primary whitespace-nowrap">{d.reference}</td>
                    <td className="px-4 py-2 font-mono text-[12px] text-text-muted">{day(d.date)}</td>
                    <td className="px-4 py-2 text-text-primary whitespace-nowrap">{d.party}</td>
                    <td className={'px-4 py-2 text-right font-mono whitespace-nowrap ' + (d.base < 0 ? 'text-danger' : 'text-text-primary')}>{kz(d.base)}</td>
                    <td className={'px-4 py-2 text-right font-mono whitespace-nowrap ' + (d.vat < 0 ? 'text-danger' : 'text-text-primary')}>{kz(d.vat)}</td>
                    {detail.side === 'purchases' && <td className="px-4 py-2 text-right font-mono text-success whitespace-nowrap">{kz(d.deductible)}</td>}
                    <td className="px-4 py-1.5 text-right">
                      {can(detail.side === 'sales' ? 'invoices:view' : 'purchases:view') && (
                        <button type="button" onClick={() => openDocument(detail.side, d)} className={actionBtn}>
                          {detail.side === 'sales' ? <><FileText size={14} /> Ver PDF</> : <><Eye size={14} /> Ver fatura</>}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </Modal>

      <Modal open={!!purchase} onClose={() => setPurchase(null)} stacked maxWidthClass="max-w-4xl"
        title={purchase ? 'Fatura de compra ' + purchase.reference : ''} subtitle={purchase ? purchase.supplier_name + ' · ' + purchase.supplier_document + ' · ' + day(purchase.document_date) : ''}>
        {purchase && (
          <div className="border border-border rounded-md overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border">
                <th className={th + ' text-left'}>Descrição</th><th className={th + ' text-right'}>Qtd</th><th className={th + ' text-left'}>IVA</th>
                <th className={th + ' text-right'}>Base</th><th className={th + ' text-right'}>IVA</th><th className={th + ' text-right'}>Dedutível</th>
              </tr></thead>
              <tbody>
                {purchase.lines.map((l) => (
                  <tr key={l.position} className="border-b border-border last:border-0">
                    <td className="px-4 py-2 text-text-primary">{l.description}</td>
                    <td className="px-4 py-2 text-right font-mono text-text-muted whitespace-nowrap">{l.quantity.toLocaleString('pt-PT')}{l.unit ? ' ' + l.unit : ''}</td>
                    <td className="px-4 py-2 font-mono text-[12px] text-text-muted whitespace-nowrap">{l.tax_category} {l.vat_rate} %{l.exemption_code ? ' · ' + l.exemption_code : ''}</td>
                    <td className="px-4 py-2 text-right font-mono text-text-primary whitespace-nowrap">{kz(l.line_subtotal)}</td>
                    <td className="px-4 py-2 text-right font-mono text-text-primary whitespace-nowrap">{kz(l.line_vat)}</td>
                    <td className="px-4 py-2 text-right font-mono text-success whitespace-nowrap">{kz(l.vat_deductible)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>

      <Modal open={!!pdf} onClose={() => { if (pdf?.url) URL.revokeObjectURL(pdf.url); setPdf(null); }} title={pdf?.title || ''} maxWidthClass="max-w-3xl" stacked={!!pdf?.stacked}>
        {pdf && <iframe src={pdf.url} title={pdf.title} className="w-full h-[70vh] rounded-md border border-border" />}
      </Modal>
    </main>
  );
}
