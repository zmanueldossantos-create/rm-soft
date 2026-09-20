import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Receipt, Plus, Trash2, Loader2, ArrowLeft, Copy, Eye, X as XIcon } from 'lucide-react';
import Select from '../components/Select';
import Modal from '../components/Modal';
import { createInvoice, createProForma } from '../api/invoices';
import { listProducts } from '../api/products';
import { listServices } from '../api/services';
import { listActivities } from '../api/activity';
import { listCustomers } from '../api/customers';
import { listVatRates } from '../api/vat';
import { paymentTermsApi, paymentMethodsApi, unitsApi, documentTypesApi, banksApi, withholdingTaxesApi } from '../api/catalogs';
import { getMyCompany, getMyCompanyBankAccounts } from '../api/company';
import { listDocumentSeries } from '../api/documentSeries';
import { extractErrorMessage } from '../utils/errors';

const inputClass = "w-full bg-bg-inset border border-border rounded-md px-2.5 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors";
const cellInputClass = "w-full bg-transparent border-none px-1 py-1 text-sm text-text-primary font-mono outline-none focus:bg-bg-inset rounded transition-colors";

const INVOICE_TYPE_CODE = { FACTURA: 'FT', FACTURA_RECIBO: 'FR', PRO_FORMA: 'FP' };
const INVOICE_TYPE_LABEL = { FACTURA: 'Factura', FACTURA_RECIBO: 'Factura/Recibo', PRO_FORMA: 'Factura Pro-forma' };

const PT_ONES = ['', 'um', 'dois', 'tres', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez', 'onze', 'doze', 'treze', 'catorze', 'quinze', 'dezasseis', 'dezassete', 'dezoito', 'dezanove'];
const PT_TENS = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa'];
const PT_HUNDREDS = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos'];

function numberToWordsPT(n) {
  if (n === 0) return 'zero';
  function belowThousand(num) {
    if (num === 100) return 'cem';
    let parts = [];
    if (num >= 100) { parts.push(PT_HUNDREDS[Math.floor(num / 100)]); num %= 100; }
    if (num >= 20) {
      parts.push(PT_TENS[Math.floor(num / 10)]);
      if (num % 10) parts.push(PT_ONES[num % 10]);
    } else if (num > 0) {
      parts.push(PT_ONES[num]);
    }
    return parts.join(' e ');
  }
  const millions = Math.floor(n / 1000000);
  const thousands = Math.floor((n % 1000000) / 1000);
  const rest = n % 1000;
  let segments = [];
  if (millions) segments.push(belowThousand(millions) + (millions === 1 ? ' milhao' : ' milhoes'));
  if (thousands) segments.push((thousands === 1 ? 'mil' : belowThousand(thousands) + ' mil'));
  if (rest) segments.push(belowThousand(rest));
  return segments.join(' e ');
}
const API_ORIGIN = 'http://127.0.0.1:8001';

function formatMoney(v) {
  return (v || 0).toLocaleString('pt-AO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Kz';
}

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function addDays(dateStr, days) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

const emptyLine = { item_type: 'product', product_id: '', service_id: '', quantity: '1', discount_percent: '0' };

export default function NovaFatura() {
  const navigate = useNavigate();

  const [activities, setActivities] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [services, setServices] = useState([]);
  const [vatRates, setVatRates] = useState([]);
  const [units, setUnits] = useState([]);
  const [paymentTerms, setPaymentTerms] = useState([]);
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [company, setCompany] = useState(null);
  const [documentSeries, setDocumentSeries] = useState([]);
  const [documentTypes, setDocumentTypes] = useState([]);
  const [banks, setBanks] = useState([]);
  const [withholdingTaxes, setWithholdingTaxes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [invoiceType, setInvoiceType] = useState('');
  const [activityId, setActivityId] = useState('');
  const [customerId, setCustomerId] = useState('');
  const [businessDate, setBusinessDate] = useState(todayStr());
  const [paymentTermId, setPaymentTermId] = useState('');
  const [paymentMethodId, setPaymentMethodId] = useState('');
  const [bankAccountId, setBankAccountId] = useState('');
  const [dueDate, setDueDate] = useState(todayStr());
  const [amountReceived, setAmountReceived] = useState('');
  const [paymentDate, setPaymentDate] = useState(todayStr());
  const [documentReference, setDocumentReference] = useState('');
  const [observations, setObservations] = useState('');
  const [discountGlobalPercent, setDiscountGlobalPercent] = useState('0');
  const [lines, setLines] = useState([{ ...emptyLine }]);

  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setLoadError('');
      try {
        const [activitiesData, customersData, productsData, servicesData, vatData, unitsData, termsData, methodsData, bankData, companyData, seriesData, docTypesData, banksData, whData] = await Promise.all([
          listActivities(), listCustomers(), listProducts(), listServices(), listVatRates(), unitsApi.list(),
          paymentTermsApi.list(), paymentMethodsApi.list(), getMyCompanyBankAccounts(), getMyCompany(), listDocumentSeries(), documentTypesApi.list(), banksApi.list(), withholdingTaxesApi.list(),
        ]);
        setActivities(activitiesData.filter((a) => a.is_active));
        setCustomers(customersData.filter((c) => c.is_active));
        setProducts(productsData.filter((p) => p.is_active && !p.is_raw_material));
        setServices(servicesData.filter((s) => s.is_active));
        setVatRates(vatData);
        setUnits(unitsData);
        setPaymentTerms(termsData.filter((t) => t.is_active));
        setPaymentMethods(methodsData.filter((m) => m.is_active));
        setBankAccounts(bankData.filter((b) => b.is_active));
        setCompany(companyData);
        setDocumentSeries(seriesData);
        setDocumentTypes(docTypesData);
        setBanks(banksData);
        setWithholdingTaxes(whData);
        const activeOnes = activitiesData.filter((a) => a.is_active);
        if (activeOnes.length === 1) setActivityId(activeOnes[0].id);
      } catch (err) {
        setLoadError(extractErrorMessage(err, 'Erro ao carregar dados'));
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const productById = useMemo(() => {
    const map = {};
    products.forEach((p) => { map[p.id] = p; });
    return map;
  }, [products]);

  const serviceById = useMemo(() => {
    const map = {};
    services.forEach((s) => { map[s.id] = s; });
    return map;
  }, [services]);

  const vatById = useMemo(() => {
    const map = {};
    vatRates.forEach((v) => { map[v.id] = v; });
    return map;
  }, [vatRates]);

  const unitById = useMemo(() => {
    const map = {};
    units.forEach((u) => { map[u.id] = u; });
    return map;
  }, [units]);

  const bankById = useMemo(() => {
    const map = {};
    banks.forEach((b) => { map[b.id] = b; });
    return map;
  }, [banks]);

  const whById = useMemo(() => {
    const map = {};
    withholdingTaxes.forEach((w) => { map[w.id] = w; });
    return map;
  }, [withholdingTaxes]);

  const selectedCustomer = useMemo(() => customers.find((c) => c.id === customerId), [customers, customerId]);
  const customerIsJuridica = selectedCustomer?.legal_person_type === 'JURIDICA';

  const maxBusinessDate = company?.allows_future_sale_date ? null : todayStr();

  // Preview of the document that WOULD be issued - finds the active series for this
  // document type/year and shows its next number, without consuming it (the real number
  // is only assigned server-side on save - see get_or_create_current_series/get_next_number).
  const documentPreview = useMemo(() => {
    const code = INVOICE_TYPE_CODE[invoiceType];
    const docType = documentTypes.find((d) => d.code === code);
    if (!docType) return null;
    const currentYear = new Date(businessDate || todayStr()).getFullYear();
    const series = documentSeries.find((s) => s.document_type_id === docType.id && s.year === currentYear && s.is_active);
    if (!series) return null;
    const nextNumber = series.current_number + 1;
    const padded = String(nextNumber);
    return { code, series: series.series_code, number: nextNumber, label: `${code} ${series.series_code}/${padded}` };
  }, [invoiceType, businessDate, documentSeries, documentTypes]);

  function getLineItem(line) {
    return line.item_type === 'service' ? serviceById[line.service_id] : productById[line.product_id];
  }

  function round2(v) {
    return Math.round((v + Number.EPSILON) * 100) / 100;
  }

  function computeLine(line) {
    const item = getLineItem(line);
    const unitPrice = item ? Number(item.price || 0) : 0;
    const vatRate = item ? Number(vatById[item.vat_id]?.rate || 0) : 0;
    const unitLabel = item?.unit_of_measure_id ? (unitById[item.unit_of_measure_id]?.code || '') : (item?.unit_of_measure_legacy || '');
    const qty = parseFloat(line.quantity) || 0;
    const discPct = parseFloat(line.discount_percent) || 0;
    const gross = qty * unitPrice;
    const discountAmount = round2(gross * (discPct / 100));
    const subtotal = round2(gross - discountAmount);
    const vatAmount = round2(subtotal * (vatRate / 100));
    const total = round2(subtotal + vatAmount);
    // AGT rule (Ulemo 8.8): retention only on Service lines with withholding_tax_id set, only for pessoa coletiva customers.
    let retentionAmount = 0;
    if (line.item_type === 'service' && item?.withholding_tax_id && customerIsJuridica) {
      const wh = whById[item.withholding_tax_id];
      if (wh && Number(wh.rate) > 0) {
        retentionAmount = round2(subtotal * (Number(wh.rate) / 100));
      }
    }
    return { item, unitPrice, vatRate, unitLabel, gross, discountAmount, subtotal, vatAmount, total, retentionAmount };
  }

  const totals = useMemo(() => {
    let totalIliquido = 0;
    let totalDescontos = 0;
    let totalIva = 0;
    let totalRetencao = 0;
    for (const line of lines) {
      const c = computeLine(line);
      totalIliquido += c.subtotal;
      totalDescontos += c.discountAmount;
      totalIva += c.vatAmount;
      totalRetencao += c.retentionAmount;
    }
    totalIliquido = round2(totalIliquido);
    totalDescontos = round2(totalDescontos);
    totalIva = round2(totalIva);
    totalRetencao = round2(totalRetencao);
    const beforeGlobalDiscount = round2(totalIliquido + totalIva);
    const globalDiscountAmount = round2(beforeGlobalDiscount * ((parseFloat(discountGlobalPercent) || 0) / 100));
    const total = round2(beforeGlobalDiscount - globalDiscountAmount);
    const received = parseFloat(amountReceived) || 0;
    const valorAPagar = round2(total - totalRetencao - received);
    return { totalIliquido, totalDescontos, totalIva, totalRetencao, globalDiscountAmount, total, valorAPagar };
  }, [lines, productById, serviceById, vatById, whById, customerIsJuridica, discountGlobalPercent, amountReceived]);

  const vatSummary = useMemo(() => {
    const groups = {};
    for (const line of lines) {
      const c = computeLine(line);
      if (!c.item) continue;
      const rate = c.vatRate;
      if (!groups[rate]) groups[rate] = { rate, incidencia: 0, montante: 0 };
      groups[rate].incidencia += c.subtotal;
      groups[rate].montante += c.vatAmount;
    }
    return Object.values(groups).sort((a, b) => a.rate - b.rate);
  }, [lines, productById, serviceById, vatById]);

  const amountInWords = useMemo(() => {
    const intPart = Math.round(totals.total);
    if (!intPart) return '-';
    return numberToWordsPT(intPart).toUpperCase() + ' KWANZAS';
  }, [totals.total]);

  function updateLine(index, field, value) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));
  }

  function updateLineType(index, itemType) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...emptyLine, item_type: itemType, quantity: l.quantity, discount_percent: l.discount_percent } : l)));
  }

  function addLine() {
    setLines((prev) => [...prev, { ...emptyLine }]);
  }

  function duplicateLine(index) {
    setLines((prev) => {
      const copy = { ...prev[index] };
      const next = [...prev];
      next.splice(index + 1, 0, copy);
      return next;
    });
  }

  function removeLine(index) {
    setLines((prev) => prev.filter((_, i) => i !== index));
  }

  function handleCustomerChange(newCustomerId) {
    setCustomerId(newCustomerId);
    const customer = customers.find((c) => c.id === newCustomerId);
    if (customer) {
      if (customer.payment_term_id) applyPaymentTerm(customer.payment_term_id);
      if (customer.payment_method_id) setPaymentMethodId(customer.payment_method_id);
    }
  }

  function applyPaymentTerm(termId) {
    setPaymentTermId(termId);
    const term = paymentTerms.find((t) => t.id === termId);
    if (term && term.days > 0) {
      setDueDate(addDays(paymentDate, term.days));
    }
  }

  function handleBusinessDateChange(newDate) {
    setBusinessDate(newDate);
  }

  function handlePaymentDateChange(newDate) {
    setPaymentDate(newDate);
    const term = paymentTerms.find((t) => t.id === paymentTermId);
    if (term && term.days > 0) {
      setDueDate(addDays(newDate, term.days));
    }
  }

  const isFormValid = activityId && invoiceType && businessDate && lines.length > 0 && lines.every((l) => {
    const item = getLineItem(l);
    return item && parseFloat(l.quantity) > 0;
  });

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      const commonLines = lines.map((l) => ({
        product_id: l.item_type === 'service' ? null : l.product_id,
        service_id: l.item_type === 'service' ? l.service_id : null,
        quantity: parseFloat(l.quantity),
        discount_percent: parseFloat(l.discount_percent) || 0,
      }));

      if (invoiceType === 'PRO_FORMA') {
        // FP is non-fiscal - no payment/bank/due-date fields apply (see create_pro_forma).
        await createProForma({
          activity_id: activityId,
          customer_id: customerId || null,
          observations: observations || null,
          document_reference: documentReference || null,
          discount_global_percent: parseFloat(discountGlobalPercent) || 0,
          lines: commonLines,
        });
      } else {
        await createInvoice({
          activity_id: activityId,
          customer_id: customerId || null,
          invoice_type: invoiceType,
          business_date: businessDate,
          payment_term_id: paymentTermId || null,
          payment_method_id: paymentMethodId || null,
          bank_account_id: bankAccountId || null,
          due_date: dueDate || null,
          amount_received: amountReceived ? parseFloat(amountReceived) : null,
          payment_date: paymentDate || null,
          observations: observations || null,
          document_reference: documentReference || null,
          discount_global_percent: parseFloat(discountGlobalPercent) || 0,
          lines: commonLines,
        });
      }
      navigate('/invoices');
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao criar fatura'));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-9">
        <div className="flex items-center justify-center h-64"><Loader2 size={24} className="animate-spin text-accent" /></div>
      </main>
    );
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/invoices')} className="text-text-muted hover:text-text-primary transition-colors cursor-pointer">
            <ArrowLeft size={20} />
          </button>
          <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
            <Receipt size={22} className="text-accent" />
            Nova Fatura
          </h2>
        </div>
        <div className="text-right text-[12px] text-text-muted font-mono">
          Moeda: <span className="text-text-primary">AOA</span>
        </div>
      </div>
      <p className="text-text-muted text-sm mb-6 ml-8">Preencha os dados e os itens da fatura</p>

      {loadError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-sm rounded-r mb-5">{loadError}</div>}

      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <div className="bg-bg-elevated border border-border rounded-lg p-5 flex flex-col gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Atividade *</label>
              <Select value={activityId} onChange={setActivityId} options={activities.map((a) => ({ value: a.id, label: a.name }))} placeholder="Selecionar" />
            </div>
            <div className="lg:col-span-2">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Cliente</label>
              <Select value={customerId} onChange={handleCustomerChange} options={[{ value: '', label: 'Sem cliente (venda ao balcão)' }, ...customers.map((c) => ({ value: c.id, label: c.name + ' - ' + c.nif }))]} placeholder="Selecionar cliente" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Tipo de documento *</label>
              <Select value={invoiceType} onChange={setInvoiceType} options={[{ value: 'FACTURA', label: 'FT - Fatura' }, { value: 'FACTURA_RECIBO', label: 'FR - Fatura/Recibo' }, { value: 'PRO_FORMA', label: 'FP - Fatura Pro-forma' }]} placeholder="Selecionar" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Documento (Nº)</label>
              <input value={documentPreview ? documentPreview.label : 'Serie nao configurada'} disabled className={inputClass + ' opacity-60 cursor-not-allowed'} />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Data do documento *</label>
              <input type="date" value={businessDate} max={maxBusinessDate || undefined} onChange={(e) => handleBusinessDateChange(e.target.value)} required className={inputClass} />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Data de pagamento</label>
              <input type="date" value={paymentDate} min={todayStr()} onChange={(e) => handlePaymentDateChange(e.target.value)} className={inputClass} />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Condição de pagamento</label>
              <Select value={paymentTermId} onChange={applyPaymentTerm} options={paymentTerms.map((t) => ({ value: t.id, label: t.name }))} placeholder="Selecionar" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Data de vencimento</label>
              <input type="date" value={dueDate} min={todayStr()} onChange={(e) => setDueDate(e.target.value)} className={inputClass} />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Método de pagamento</label>
              <Select value={paymentMethodId} onChange={setPaymentMethodId} options={paymentMethods.map((m) => ({ value: m.id, label: m.name }))} placeholder="Selecionar" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Conta bancária</label>
              <Select value={bankAccountId} onChange={setBankAccountId} options={bankAccounts.map((b) => ({ value: b.id, label: (bankById[b.bank_id]?.acronym || '?') + ' - ' + b.account_number }))} placeholder="Selecionar" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Referência</label>
              <input value={documentReference} onChange={(e) => setDocumentReference(e.target.value)} placeholder="Ex: PO-2026-004" className={inputClass} />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Valor recebido</label>
              <input type="number" step="0.01" min="0" value={amountReceived} onChange={(e) => setAmountReceived(e.target.value)} placeholder="0.00" className={inputClass} />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Desconto global %</label>
              <input type="number" step="0.01" min="0" max="100" value={discountGlobalPercent} onChange={(e) => setDiscountGlobalPercent(e.target.value)} className={inputClass} />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Observações</label>
              <input value={observations} onChange={(e) => setObservations(e.target.value)} className={inputClass} />
            </div>
          </div>
        </div>

        <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[1200px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-3">Tipo</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-3">Código / Designação</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-2 py-3">Qtd</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-2 py-3">UN</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-2 py-3">Preço</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-2 py-3">Desc%</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-2 py-3">Desc</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-2 py-3">Subtotal</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-2 py-3">IVA%</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-2 py-3">IVA</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-2 py-3">Total</th>
                  <th className="px-2 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line, idx) => {
                  const c = computeLine(line);
                  return (
                    <tr key={idx} className="border-b border-border last:border-0">
                      <td className="px-3 py-2">
                        <div className="flex bg-bg-inset border border-border rounded-md overflow-hidden w-fit">
                          <button type="button" onClick={() => updateLineType(idx, 'product')} className={'px-2 py-1.5 text-[10px] font-medium transition-colors cursor-pointer ' + (line.item_type === 'product' ? 'bg-accent text-white' : 'text-text-muted')}>Prod</button>
                          <button type="button" onClick={() => updateLineType(idx, 'service')} className={'px-2 py-1.5 text-[10px] font-medium transition-colors cursor-pointer ' + (line.item_type === 'service' ? 'bg-accent text-white' : 'text-text-muted')}>Serv</button>
                        </div>
                      </td>
                      <td className="px-3 py-2 min-w-[220px]">
                        {line.item_type === 'service' ? (
                          <Select value={line.service_id} onChange={(v) => updateLine(idx, 'service_id', v)} options={services.map((s) => ({ value: s.id, label: s.code + ' - ' + s.name }))} placeholder="Selecionar servico" />
                        ) : (
                          <Select value={line.product_id} onChange={(v) => updateLine(idx, 'product_id', v)} options={products.map((p) => ({ value: p.id, label: p.code + ' - ' + p.name }))} placeholder="Selecionar produto" />
                        )}
                      </td>
                      <td className="px-2 py-2 w-20">
                        <input type="number" step={c.item?.is_sold_by_weight ? '0.001' : '1'} min="0" value={line.quantity} onChange={(e) => updateLine(idx, 'quantity', e.target.value)} className={cellInputClass + ' text-right'} />
                      </td>
                      <td className="px-2 py-2 text-[12px] text-text-muted">{c.unitLabel || '-'}</td>
                      <td className="px-2 py-2 text-right font-mono text-text-muted text-[13px]">{formatMoney(c.unitPrice)}</td>
                      <td className="px-2 py-2 w-16">
                        <input type="number" step="0.01" min="0" max="100" value={line.discount_percent} onChange={(e) => updateLine(idx, 'discount_percent', e.target.value)} className={cellInputClass + ' text-right'} />
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-text-muted text-[13px]">{formatMoney(c.discountAmount)}</td>
                      <td className="px-2 py-2 text-right font-mono text-text-primary text-[13px]">{formatMoney(c.subtotal)}</td>
                      <td className="px-2 py-2 text-right font-mono text-text-muted text-[13px]">{c.vatRate}%</td>
                      <td className="px-2 py-2 text-right font-mono text-text-muted text-[13px]">{formatMoney(c.vatAmount)}</td>
                      <td className="px-2 py-2 text-right font-mono text-accent font-medium text-[13px]">{formatMoney(c.total)}</td>
                      <td className="px-2 py-2">
                        <div className="flex items-center gap-1.5 justify-end">
                          <button type="button" onClick={() => duplicateLine(idx)} title="Duplicar" className="text-text-muted hover:text-accent transition-colors cursor-pointer">
                            <Copy size={14} />
                          </button>
                          <button type="button" onClick={() => removeLine(idx)} disabled={lines.length === 1} title="Remover" className="text-text-muted hover:text-danger disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer">
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="p-3 border-t border-border">
            <button type="button" onClick={addLine} className="flex items-center gap-1.5 text-accent hover:text-accent-hover text-sm font-medium transition-colors cursor-pointer">
              <Plus size={15} /> Adicionar linha
            </button>
          </div>
        </div>

        <div className="flex justify-end">
          <div className="bg-bg-elevated border border-border rounded-lg p-5 w-full sm:w-96 flex flex-col gap-2">
            <div className="flex justify-between text-sm">
              <span className="text-text-muted">Total Ilíquido</span>
              <span className="font-mono text-text-primary">{formatMoney(totals.totalIliquido)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-text-muted">Total Descontos</span>
              <span className="font-mono text-text-primary">{formatMoney(totals.totalDescontos)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-text-muted">IVA</span>
              <span className="font-mono text-text-primary">{formatMoney(totals.totalIva)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-text-muted">Retenções</span>
              <span className="font-mono text-text-primary">{formatMoney(totals.totalRetencao)}</span>
            </div>
            {parseFloat(discountGlobalPercent) > 0 && (
              <div className="flex justify-between text-sm">
                <span className="text-text-muted">Desconto Global ({discountGlobalPercent}%)</span>
                <span className="font-mono text-danger">-{formatMoney(totals.globalDiscountAmount)}</span>
              </div>
            )}
            <div className="flex justify-between text-base font-semibold pt-2 border-t border-border">
              <span className="text-text-primary">Total</span>
              <span className="font-mono text-accent">{formatMoney(totals.total)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-text-muted">Valor a Pagar</span>
              <span className="font-mono text-text-primary">{formatMoney(totals.valorAPagar)}</span>
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <div className="w-full sm:w-96 flex flex-col gap-2.5">
            {formError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-sm rounded-r">{formError}</div>}
            <button type="submit" disabled={saving || !isFormValid} className="w-full bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-md px-6 py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
              {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
              {saving ? 'A criar...' : 'Criar Fatura'}
            </button>
            <div className="flex gap-2.5">
              <button type="button" onClick={() => setPreviewOpen(true)} className="flex-1 border border-border hover:border-accent text-text-primary text-sm px-4 py-2.5 rounded-md flex items-center justify-center gap-2 transition-colors cursor-pointer">
                <Eye size={15} /> Pré-visualizar
              </button>
              <button type="button" onClick={() => navigate('/invoices')} className="flex-1 border border-border hover:border-danger text-text-primary text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer">
                Cancelar
              </button>
            </div>
          </div>
        </div>
      </form>

      <Modal open={previewOpen} onClose={() => setPreviewOpen(false)} title="Pré-visualização" maxWidthClass="max-w-[1000px]">
        <div className="bg-white text-black p-6 rounded-md text-[12px] leading-snug max-h-[75vh] overflow-y-auto scrollbar-thin" style={{ fontFamily: 'Arial, sans-serif' }}>
          <p className="text-right text-[11px] italic text-gray-500 mb-2">Original</p>

          <div className="flex justify-between items-start mb-4">
            <div className="flex gap-3 items-start">
              {company?.logo_path && (
                <img src={API_ORIGIN + company.logo_path} alt="Logotipo" className="h-16 w-16 object-contain shrink-0" />
              )}
            </div>
          </div>

          <div className="flex justify-between items-start mb-4">
            <div>
              <p className="font-bold text-[14px]">{company?.name || ''}</p>
              <p>NIF: {company?.nif || ''}</p>
              {company?.address && <p>{company.address}</p>}
              <p>{[company?.phone_number, company?.phone_number_2].filter(Boolean).join(' / ')}</p>
              {company?.email && <p>E-mail: {company.email}</p>}
              {company?.website && <p>Website: {company.website}</p>}
            </div>
            <div className="text-right">
              <p className="font-bold text-blue-700 text-[14px]">
                {INVOICE_TYPE_LABEL[invoiceType] || '?'}: {documentPreview ? documentPreview.series + '/' + documentPreview.number : '-'}
              </p>
              {selectedCustomer && (
                <>
                  <p className="font-semibold mt-1">{selectedCustomer.name}</p>
                  <p>NIF: {selectedCustomer.nif}</p>
                  {selectedCustomer.address && <p>{selectedCustomer.address}</p>}
                </>
              )}
              {!selectedCustomer && <p className="mt-1">Consumidor Final</p>}
            </div>
          </div>

          <table className="w-full border-t border-b border-gray-300 mb-3">
            <tbody>
              <tr className="text-left align-top">
                <td className="py-1.5 pr-4">
                  <p className="font-semibold text-[11px]">Data de emissão</p>
                  <p>{businessDate || '-'}</p>
                </td>
                <td className="py-1.5 pr-4">
                  <p className="font-semibold text-[11px]">Data de vencimento</p>
                  <p>{dueDate || '-'}</p>
                </td>
                <td className="py-1.5 pr-4">
                  <p className="font-semibold text-[11px]">Modo de pagamento</p>
                  <p>{paymentMethods.find((m) => m.id === paymentMethodId)?.name || '-'}</p>
                </td>
                <td className="py-1.5">
                  <p className="font-semibold text-[11px]">Condição de pagamento</p>
                  <p>{paymentTerms.find((t) => t.id === paymentTermId)?.name || '-'}</p>
                </td>
              </tr>
            </tbody>
          </table>

          <table className="w-full mb-3">
            <thead>
              <tr className="border-b border-gray-300 text-left text-[11px] font-semibold">
                <th className="py-1 pr-2">Referência</th>
                <th className="py-1 pr-2">Designação</th>
                <th className="py-1 pr-2 text-right">Qtd</th>
                <th className="py-1 pr-2">Un</th>
                <th className="py-1 pr-2 text-right">Preço</th>
                <th className="py-1 pr-2 text-right">Desc</th>
                <th className="py-1 pr-2 text-right">Taxa(%)</th>
                <th className="py-1 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line, idx) => {
                const c = computeLine(line);
                return (
                  <tr key={idx} className="border-b border-gray-100 align-top">
                    <td className="py-1.5 pr-2">{c.item?.code || '-'}</td>
                    <td className="py-1.5 pr-2">{c.item?.name || '(sem item)'}</td>
                    <td className="py-1.5 pr-2 text-right">{line.quantity}</td>
                    <td className="py-1.5 pr-2">{c.unitLabel || '-'}</td>
                    <td className="py-1.5 pr-2 text-right">{formatMoney(c.unitPrice)}</td>
                    <td className="py-1.5 pr-2 text-right">{formatMoney(c.discountAmount)}</td>
                    <td className="py-1.5 pr-2 text-right">{c.vatRate.toFixed(2)}</td>
                    <td className="py-1.5 text-right">{formatMoney(c.total)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {observations && (
            <div className="mb-3">
              <p className="font-semibold text-blue-700 text-[12px]">Observações:</p>
              <p>{observations}</p>
            </div>
          )}

          <p className="text-[10px] text-gray-500 mt-4">SIMUL - Processado por programa não homologado (simulação)</p>

          <div className="flex justify-between items-start mt-2 pt-2 border-t border-gray-300">
            <div className="text-[11px] flex-1 pr-4">
              <p className="font-semibold mb-1">Resumo de impostos</p>
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="border-b border-gray-300 text-left font-semibold">
                    <th className="py-1 pr-2">Imposto</th>
                    <th className="py-1 pr-2 text-right">Taxa(%)</th>
                    <th className="py-1 pr-2 text-right">Incidência</th>
                    <th className="py-1 pr-2">Motivo</th>
                    <th className="py-1 text-right">Montante (AKZ)</th>
                  </tr>
                </thead>
                <tbody>
                  {vatSummary.map((v) => (
                    <tr key={v.rate}>
                      <td className="py-1 pr-2">IVA</td>
                      <td className="py-1 pr-2 text-right">{v.rate.toFixed(2)}</td>
                      <td className="py-1 pr-2 text-right">{formatMoney(v.incidencia)}</td>
                      <td className="py-1 pr-2">{v.rate === 0 ? 'Isento' : 'IVA'}</td>
                      <td className="py-1 text-right">{formatMoney(v.montante)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <table className="text-[12px] border border-gray-300 shrink-0">
              <tbody>
                <tr><td className="pr-4 pl-2 py-1 text-right">Total Ilíquido</td><td className="pr-2 text-right font-mono">{formatMoney(totals.totalIliquido)}</td></tr>
                <tr><td className="pr-4 pl-2 py-1 text-right">Total Desconto</td><td className="pr-2 text-right font-mono">{formatMoney(totals.totalDescontos)}</td></tr>
                <tr><td className="pr-4 pl-2 py-1 text-right">Total Imposto</td><td className="pr-2 text-right font-mono">{formatMoney(totals.totalIva)}</td></tr>
                <tr className="border-t border-gray-300 font-bold"><td className="pr-4 pl-2 py-1 text-right">Total (AKZ)</td><td className="pr-2 text-right font-mono">{formatMoney(totals.total)}</td></tr>
              </tbody>
            </table>
          </div>

          {totals.totalRetencao > 0 && (
            <p className="text-[11px] text-right mt-1">Retenções: <span className="font-mono">{formatMoney(totals.totalRetencao)}</span> &nbsp; A Pagar: <span className="font-mono font-bold">{formatMoney(totals.valorAPagar)}</span></p>
          )}

          <p className="font-bold text-[11px] mt-3">Total: {amountInWords}</p>

          <div className="border-t border-gray-300 mt-3 pt-2">
            {bankAccounts.length > 0 && (
              <>
                <p className="font-semibold text-[11px]">Coordenadas Bancárias</p>
                {bankAccounts.map((b) => (
                  <p key={b.id} className="text-[10px]">{bankById[b.bank_id]?.acronym || '?'}: {b.account_number} &nbsp; IBAN: {b.iban}</p>
                ))}
              </>
            )}
          </div>

          {invoiceType === 'PRO_FORMA' && (
            <p className="text-[10px] italic text-gray-500 mt-3">Este documento não serve como factura</p>
          )}

          <p className="text-[11px] italic mt-4 text-center text-gray-500">O número definitivo do documento é atribuído ao guardar.</p>
        </div>
        <div className="flex justify-end pt-3">
          <button
            type="button"
            onClick={() => setPreviewOpen(false)}
            className="border border-border hover:border-danger text-text-primary text-sm px-5 py-2.5 rounded-md transition-colors cursor-pointer"
          >
            Cancelar
          </button>
        </div>
      </Modal>

    </main>
  );
}
