import { useState, useEffect, useMemo } from 'react';
import { Plus, Trash2, Loader2, Copy, Eye, ArrowLeft, ArrowRight, Check } from 'lucide-react';
import Select from './Select';
import Modal from './Modal';
import { createInvoice, createProForma } from '../api/invoices';
import { listProducts } from '../api/products';
import { listServices } from '../api/services';
import { listActivities } from '../api/activity';
import { listCustomers } from '../api/customers';
import { listVatRates } from '../api/vat';
import { paymentTermsApi, paymentMethodsApi, unitsApi, documentRulesApi, banksApi, withholdingTaxesApi } from '../api/catalogs';
import { getMyCompany, getMyCompanyBankAccounts } from '../api/company';
import { listDocumentSeries } from '../api/documentSeries';
import { extractErrorMessage } from '../utils/errors';
import { useAuthStore } from '../store/authStore';

const inputClass = "w-full bg-bg-inset border border-border rounded-md px-2.5 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors";
const API_ORIGIN = 'http://127.0.0.1:8001';

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

const STEP_LABELS = ['Tipo de documento', 'Cliente e datas', 'Pagamento', 'Revisao'];

export default function InvoiceWizardModal({ open, onClose, onCreated }) {
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

  const [step, setStep] = useState(1);
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

  const permissionsList = useAuthStore((state) => state.permissions);
  const canManageProducts = Array.isArray(permissionsList) ? permissionsList.includes('products:manage') : true;

  useEffect(() => {
    if (!open) return;
    setStep(1);
    setInvoiceType('');
    setActivityId('');
    setCustomerId('');
    setBusinessDate(todayStr());
    setPaymentTermId('');
    setPaymentMethodId('');
    setBankAccountId('');
    setDueDate(todayStr());
    setAmountReceived('');
    setPaymentDate(todayStr());
    setDocumentReference('');
    setObservations('');
    setDiscountGlobalPercent('0');
    setLines([{ ...emptyLine }]);
    setFormError('');
    if (!Array.isArray(permissionsList)) return;
    async function load() {
      setLoading(true);
      setLoadError('');
      try {
        const [activitiesData, customersData, productsData, servicesData, vatData, unitsData, termsData, methodsData, bankData, companyData, seriesData, docTypesData, banksData, whData] = await Promise.all([
          listActivities(), listCustomers(), canManageProducts ? listProducts() : Promise.resolve([]), listServices(), listVatRates(), unitsApi.list(),
          paymentTermsApi.list(), paymentMethodsApi.list(), getMyCompanyBankAccounts(), getMyCompany(), listDocumentSeries(), documentRulesApi.list(), banksApi.list(), withholdingTaxesApi.list(),
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
  }, [open, Array.isArray(permissionsList)]);

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

  const documentPreview = useMemo(() => {
    const code = INVOICE_TYPE_CODE[invoiceType];
    const docType = documentTypes.find((d) => d.code === code);
    if (!docType) return null;
    const currentYear = new Date(businessDate || todayStr()).getFullYear();
    const series = documentSeries.find((s) => s.document_type_id === docType.id && s.year === currentYear && s.is_active);
    if (!series) return null;
    const nextNumber = series.current_number + 1;
    return { code, series: series.series_code, number: nextNumber, label: `${code} ${series.series_code}/${nextNumber}` };
  }, [invoiceType, businessDate, documentSeries, documentTypes]);

  const issuableTypeCards = useMemo(
    () => Object.entries(INVOICE_TYPE_CODE)
      .map(([type, code]) => [type, documentTypes.find((d) => d.code === code)])
      .filter(([, d]) => d && d.is_active && d.issuable_in_invoices)
      .map(([type, d]) => ({ type, code: d.code, name: d.name, description: d.description })),
    [documentTypes],
  );

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
    let retentionAmount = 0;
    if (line.item_type === 'service' && item?.withholding_tax_id && customerIsJuridica) {
      const wh = whById[item.withholding_tax_id];
      if (wh && Number(wh.rate) > 0) {
        retentionAmount = round2(subtotal * (Number(wh.rate) / 100));
      }
    }
    return { item, unitPrice, vatRate, unitLabel, gross, discountAmount, subtotal, vatAmount, total, retentionAmount };
  }

  const paidOnIssue = !!documentTypes.find((d) => d.code === INVOICE_TYPE_CODE[invoiceType])?.paid_on_issue;

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
    const dueNow = round2(total - totalRetencao);
    const received = paidOnIssue ? dueNow : (parseFloat(amountReceived) || 0);
    const valorAPagar = round2(total - totalRetencao - received);
    return { totalIliquido, totalDescontos, totalIva, totalRetencao, globalDiscountAmount, total, valorAPagar, received };
  }, [lines, productById, serviceById, vatById, whById, customerIsJuridica, discountGlobalPercent, amountReceived, paidOnIssue]);

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

  const requiresPaymentTerm = !!documentTypes.find((d) => d.code === INVOICE_TYPE_CODE[invoiceType])?.requires_payment_term;
  const requiresCustomer = !!documentTypes.find((d) => d.code === INVOICE_TYPE_CODE[invoiceType])?.requires_customer;
  const isFormValid = activityId && invoiceType && businessDate && lines.length > 0 &&
    (!requiresPaymentTerm || paymentTermId) &&
    (!requiresCustomer || customerId) &&
    lines.every((l) => {
      const item = getLineItem(l);
      return item && parseFloat(l.quantity) > 0;
    });

  const hasUsableLines = lines.some((l) => getLineItem(l) && parseFloat(l.quantity) > 0);

  async function handleSubmit() {
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
          amount_received: paidOnIssue ? (totals.received > 0 ? totals.received : null) : (amountReceived ? parseFloat(amountReceived) : null),
          payment_date: paymentDate || null,
          observations: observations || null,
          document_reference: documentReference || null,
          discount_global_percent: parseFloat(discountGlobalPercent) || 0,
          lines: commonLines,
        });
      }
      onCreated?.();
      onClose();
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao criar fatura'));
    } finally {
      setSaving(false);
    }
  }

  if (!open) return null;

  const currentTypeLabel = invoiceType ? `${INVOICE_TYPE_LABEL[invoiceType]} (${INVOICE_TYPE_CODE[invoiceType]})` : undefined;

  function stepReached(n) {
    if (n === 1) return true;
    if (n === 2) return !!invoiceType;
    if (n === 3) return !!invoiceType && !!activityId && !!businessDate;
    if (n === 4) return !!invoiceType && !!activityId && !!businessDate;
    return false;
  }

  const footer = (
    <div className="flex items-center justify-between px-6 py-3.5">
      {step > 1 ? (
        <button type="button" onClick={() => setStep((s) => s - 1)} className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-sm px-4 py-2 rounded-md transition-colors cursor-pointer">
          <ArrowLeft size={14} /> Voltar
        </button>
      ) : (
        <button type="button" onClick={onClose} className="border border-border hover:border-danger text-text-primary text-sm px-4 py-2 rounded-md transition-colors cursor-pointer">
          Cancelar
        </button>
      )}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setPreviewOpen(true)}
          disabled={!hasUsableLines}
          className="flex items-center gap-1.5 border border-border hover:border-accent disabled:opacity-40 disabled:cursor-not-allowed text-text-primary text-sm px-4 py-2 rounded-md transition-colors cursor-pointer"
        >
          <Eye size={15} /> Pre-visualizar
        </button>
        {step < 4 ? (
          <button type="button" onClick={() => setStep((s) => s + 1)} disabled={step === 1 && !invoiceType} className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm px-5 py-2 rounded-md transition-colors cursor-pointer">
            Seguinte <ArrowRight size={14} />
          </button>
        ) : (
          <button type="button" onClick={handleSubmit} disabled={saving || !isFormValid} className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm px-5 py-2 rounded-md transition-colors cursor-pointer">
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
            {saving ? 'A criar...' : (invoiceType === 'PRO_FORMA' ? 'Gerar pro-forma' : 'Criar factura')}
          </button>
        )}
      </div>
    </div>
  );

  return (
    <>
      <Modal open={open} onClose={onClose} title="Nova fatura" subtitle={currentTypeLabel} maxWidthClass="max-w-6xl" footer={footer}>
        {loading ? (
          <div className="flex items-center justify-center py-16"><Loader2 size={24} className="animate-spin text-accent" /></div>
        ) : loadError ? (
          <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-sm rounded-r">{loadError}</div>
        ) : (
          <>
            <div className="flex items-center gap-1.5 -mt-1 mb-5">
              {STEP_LABELS.map((label, i) => {
                const n = i + 1;
                const done = step > n;
                const active = step === n;
                return (
                  <div key={label} className="flex items-center gap-1.5 flex-1 last:flex-none">
                    <button
                      type="button"
                      onClick={() => stepReached(n) && setStep(n)}
                      disabled={!stepReached(n)}
                      className="flex items-center gap-1.5 shrink-0 cursor-pointer disabled:cursor-not-allowed"
                    >
                      <span className={'w-[22px] h-[22px] rounded-full flex items-center justify-center text-[11px] font-medium shrink-0 ' + (done ? 'bg-success text-white' : active ? 'bg-accent text-white' : 'border border-border text-text-muted')}>
                        {done ? <Check size={13} /> : n}
                      </span>
                      <span className={'text-[12.5px] whitespace-nowrap ' + (active ? 'font-medium text-text-primary' : 'text-text-muted')}>{label}</span>
                    </button>
                    {n < 4 && <div className="flex-1 h-px bg-border" />}
                  </div>
                );
              })}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.2fr] gap-6">
              <div className="min-h-[380px]">
                {step === 1 && (
                  <div className="flex flex-col gap-3">
                    <p className="text-[12.5px] text-text-muted mb-1">Selecionar o tipo de documento a emitir</p>
                    {issuableTypeCards.map((c) => (
                      <button
                        key={c.type}
                        type="button"
                        onClick={() => setInvoiceType(c.type)}
                        className={'text-left border-2 rounded-xl p-3.5 flex items-start gap-3 transition-colors cursor-pointer ' + (invoiceType === c.type ? 'border-accent bg-accent/5' : 'border-border hover:border-accent/50')}
                      >
                        <div>
                          <p className="text-sm font-medium text-text-primary">{c.name}</p>
                          {c.description && <p className="text-[12px] text-text-muted mt-0.5">{c.description}</p>}
                        </div>
                      </button>
                    ))}
                    {issuableTypeCards.length === 0 && (
                      <p className="text-[13px] text-text-muted">Nenhum tipo de documento disponivel para emissao aqui.</p>
                    )}
                  </div>
                )}

                {step === 2 && (
                  <div className="flex flex-col gap-4">
                    <div>
                      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Atividade *</label>
                      <Select value={activityId} onChange={setActivityId} options={activities.map((a) => ({ value: a.id, label: a.name }))} placeholder="Selecionar" />
                    </div>
                    <div>
                      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Cliente</label>
                      <Select value={customerId} onChange={handleCustomerChange} options={[{ value: '', label: 'Sem cliente (venda ao balcao)' }, ...customers.map((c) => ({ value: c.id, label: c.name + ' - ' + c.nif }))]} placeholder="Selecionar cliente" />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Data do documento *</label>
                        <input type="date" value={businessDate} max={maxBusinessDate || undefined} onChange={(e) => handleBusinessDateChange(e.target.value)} required className={inputClass} />
                      </div>
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Documento (No)</label>
                        <input value={documentPreview ? documentPreview.label : 'Serie nao configurada'} disabled className={inputClass + ' opacity-60 cursor-not-allowed'} />
                      </div>
                    </div>
                  </div>
                )}

                {step === 3 && (
                  <div className="flex flex-col gap-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Condicao de pagamento{requiresPaymentTerm ? ' *' : ''}</label>
                        <Select value={paymentTermId} onChange={applyPaymentTerm} options={paymentTerms.map((t) => ({ value: t.id, label: t.name }))} placeholder="Selecionar" />
                      </div>
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Data de vencimento</label>
                        <input type="date" value={dueDate} min={todayStr()} onChange={(e) => setDueDate(e.target.value)} className={inputClass} />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Data de pagamento</label>
                        <input type="date" value={paymentDate} min={todayStr()} onChange={(e) => handlePaymentDateChange(e.target.value)} className={inputClass} />
                      </div>
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Metodo de pagamento</label>
                        <Select value={paymentMethodId} onChange={setPaymentMethodId} options={paymentMethods.map((m) => ({ value: m.id, label: m.name }))} placeholder="Selecionar" />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Conta bancaria</label>
                        <Select value={bankAccountId} onChange={setBankAccountId} options={bankAccounts.map((b) => ({ value: b.id, label: (bankById[b.bank_id]?.acronym || '?') + ' - ' + b.account_number }))} placeholder="Selecionar" />
                      </div>
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Referencia</label>
                        <input value={documentReference} onChange={(e) => setDocumentReference(e.target.value)} placeholder="Ex: PO-2026-004" className={inputClass} />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Valor recebido</label>
                        <input type="number" step="0.01" min="0" value={paidOnIssue ? totals.received : amountReceived} onChange={(e) => setAmountReceived(e.target.value)} placeholder="0.00" readOnly={paidOnIssue} className={inputClass + (paidOnIssue ? ' opacity-70 cursor-not-allowed' : '')} />
                      </div>
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Desconto global %</label>
                        <input type="number" step="0.01" min="0" max="100" value={discountGlobalPercent} onChange={(e) => setDiscountGlobalPercent(e.target.value)} className={inputClass} />
                      </div>
                    </div>
                  </div>
                )}

                {step === 4 && (
                  <div className="flex flex-col gap-4">
                    <div>
                      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Observacoes</label>
                      <textarea value={observations} onChange={(e) => setObservations(e.target.value)} rows={3} className={inputClass + ' resize-none'} placeholder="Opcional" />
                    </div>
                    <div className="border border-border rounded-md p-3.5">
                      <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-2">Resumo</p>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12.5px]">
                        <span className="text-text-muted">Tipo</span><span className="text-text-primary">{currentTypeLabel || '-'}</span>
                        <span className="text-text-muted">Atividade</span><span className="text-text-primary">{activities.find((a) => a.id === activityId)?.name || '-'}</span>
                        <span className="text-text-muted">Cliente</span><span className="text-text-primary">{selectedCustomer?.name || 'Sem cliente'}</span>
                        <span className="text-text-muted">Data</span><span className="text-text-primary">{businessDate}</span>
                        <span className="text-text-muted">Vencimento</span><span className="text-text-primary">{dueDate || '-'}</span>
                        <span className="text-text-muted">Pagamento</span><span className="text-text-primary">{paymentMethods.find((m) => m.id === paymentMethodId)?.name || '-'}</span>
                      </div>
                    </div>
                    {formError && (
                      <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{formError}</div>
                    )}
                  </div>
                )}
              </div>

              <div className="flex flex-col border border-border rounded-lg overflow-hidden">
                <div className="p-4 flex-1 overflow-y-auto scrollbar-thin max-h-[340px]">
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-[13px] font-medium text-text-primary">Produtos e servicos</p>
                    <button type="button" onClick={addLine} className="flex items-center gap-1 text-accent hover:text-accent-hover text-[12px] font-medium transition-colors cursor-pointer">
                      <Plus size={13} /> Linha
                    </button>
                  </div>
                  <div className="flex flex-col gap-2.5">
                    {lines.map((line, idx) => {
                      const c = computeLine(line);
                      return (
                        <div key={idx} className="border border-border rounded-md p-2.5 flex flex-col gap-2">
                          <div className="flex items-center gap-2">
                            <div className="flex bg-bg-inset border border-border rounded-md overflow-hidden shrink-0">
                              <button type="button" onClick={() => updateLineType(idx, 'product')} className={'px-2 py-1.5 text-[10px] font-medium transition-colors cursor-pointer ' + (line.item_type === 'product' ? 'bg-accent text-white' : 'text-text-muted')}>Prod</button>
                              <button type="button" onClick={() => updateLineType(idx, 'service')} className={'px-2 py-1.5 text-[10px] font-medium transition-colors cursor-pointer ' + (line.item_type === 'service' ? 'bg-accent text-white' : 'text-text-muted')}>Serv</button>
                            </div>
                            <div className="flex-1 min-w-0">
                              {line.item_type === 'service' ? (
                                <Select value={line.service_id} onChange={(v) => updateLine(idx, 'service_id', v)} options={services.map((s) => ({ value: s.id, label: s.code + ' - ' + s.name }))} placeholder="Selecionar servico" compact />
                              ) : (
                                <Select value={line.product_id} onChange={(v) => updateLine(idx, 'product_id', v)} options={products.map((p) => ({ value: p.id, label: p.code + ' - ' + p.name }))} placeholder="Selecionar produto" compact />
                              )}
                            </div>
                            <button type="button" onClick={() => duplicateLine(idx)} title="Duplicar" className="text-text-muted hover:text-accent transition-colors cursor-pointer shrink-0">
                              <Copy size={13} />
                            </button>
                            <button type="button" onClick={() => removeLine(idx)} disabled={lines.length === 1} title="Remover" className="text-text-muted hover:text-danger disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer shrink-0">
                              <Trash2 size={14} />
                            </button>
                          </div>
                          <div className="flex items-center gap-2 text-[11px]">
                            <div className="flex items-center gap-1">
                              <span className="text-text-muted">Qtd</span>
                              <input type="number" step={c.item?.is_sold_by_weight ? '0.001' : '1'} min="0" value={line.quantity} onChange={(e) => updateLine(idx, 'quantity', e.target.value)} className="w-14 bg-bg-inset border border-border rounded px-1.5 py-1 text-[11px] text-text-primary font-mono outline-none focus:border-accent" />
                            </div>
                            <div className="flex items-center gap-1">
                              <span className="text-text-muted">Desc%</span>
                              <input type="number" step="0.01" min="0" max="100" value={line.discount_percent} onChange={(e) => updateLine(idx, 'discount_percent', e.target.value)} className="w-14 bg-bg-inset border border-border rounded px-1.5 py-1 text-[11px] text-text-primary font-mono outline-none focus:border-accent" />
                            </div>
                            <span className="text-text-muted ml-auto">IVA {c.vatRate}%</span>
                            <span className="font-mono text-accent font-medium">{formatMoney(c.total)}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
                <div className="border-t border-border p-4">
                  <p className="text-[13px] font-medium text-text-primary mb-2">Detalhes</p>
                  <div className="flex flex-col gap-1 text-[12.5px]">
                    <div className="flex justify-between"><span className="text-text-muted">Total iliquido</span><span className="font-mono text-text-primary">{formatMoney(totals.totalIliquido)}</span></div>
                    <div className="flex justify-between"><span className="text-text-muted">IVA</span><span className="font-mono text-text-primary">{formatMoney(totals.totalIva)}</span></div>
                    {totals.totalDescontos > 0 && (
                      <div className="flex justify-between"><span className="text-text-muted">Descontos</span><span className="font-mono text-text-primary">{formatMoney(totals.totalDescontos)}</span></div>
                    )}
                    {totals.totalRetencao > 0 && (
                      <div className="flex justify-between"><span className="text-text-muted">Retencoes</span><span className="font-mono text-text-primary">{formatMoney(totals.totalRetencao)}</span></div>
                    )}
                    <div className="flex justify-between pt-1.5 mt-1 border-t border-border text-[13.5px] font-medium">
                      <span className="text-text-primary">Total</span><span className="font-mono text-accent">{formatMoney(totals.total)}</span>
                    </div>
                    {totals.valorAPagar !== totals.total && (
                      <div className="flex justify-between"><span className="text-text-accent">Valor a pagar</span><span className="font-mono text-text-accent">{formatMoney(totals.valorAPagar)}</span></div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </Modal>

      <Modal open={previewOpen} onClose={() => setPreviewOpen(false)} title="Pre-visualizacao" maxWidthClass="max-w-[1000px]" stacked>
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
                  <p className="font-semibold text-[11px]">Data de emissao</p>
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
                  <p className="font-semibold text-[11px]">Condicao de pagamento</p>
                  <p>{paymentTerms.find((t) => t.id === paymentTermId)?.name || '-'}</p>
                </td>
              </tr>
            </tbody>
          </table>

          <table className="w-full mb-3">
            <thead>
              <tr className="border-b border-gray-300 text-left text-[11px] font-semibold">
                <th className="py-1 pr-2">Referencia</th>
                <th className="py-1 pr-2">Designacao</th>
                <th className="py-1 pr-2 text-right">Qtd</th>
                <th className="py-1 pr-2">Un</th>
                <th className="py-1 pr-2 text-right">Preco</th>
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
              <p className="font-semibold text-blue-700 text-[12px]">Observacoes:</p>
              <p>{observations}</p>
            </div>
          )}

          <p className="text-[10px] text-gray-500 mt-4">SIMUL - Processado por programa nao homologado (simulacao)</p>

          <div className="flex justify-between items-start mt-2 pt-2 border-t border-gray-300">
            <div className="text-[11px] flex-1 pr-4">
              <p className="font-semibold mb-1">Resumo de impostos</p>
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="border-b border-gray-300 text-left font-semibold">
                    <th className="py-1 pr-2">Imposto</th>
                    <th className="py-1 pr-2 text-right">Taxa(%)</th>
                    <th className="py-1 pr-2 text-right">Incidencia</th>
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
                <tr><td className="pr-4 pl-2 py-1 text-right">Total Iliquido</td><td className="pr-2 text-right font-mono">{formatMoney(totals.totalIliquido)}</td></tr>
                <tr><td className="pr-4 pl-2 py-1 text-right">Total Desconto</td><td className="pr-2 text-right font-mono">{formatMoney(totals.totalDescontos)}</td></tr>
                <tr><td className="pr-4 pl-2 py-1 text-right">Total Imposto</td><td className="pr-2 text-right font-mono">{formatMoney(totals.totalIva)}</td></tr>
                <tr className="border-t border-gray-300 font-bold"><td className="pr-4 pl-2 py-1 text-right">Total (AKZ)</td><td className="pr-2 text-right font-mono">{formatMoney(totals.total)}</td></tr>
              </tbody>
            </table>
          </div>

          {totals.totalRetencao > 0 && (
            <p className="text-[11px] text-right mt-1">Retencoes: <span className="font-mono">{formatMoney(totals.totalRetencao)}</span> &nbsp; A Pagar: <span className="font-mono font-bold">{formatMoney(totals.valorAPagar)}</span></p>
          )}

          <p className="font-bold text-[11px] mt-3">Total: {amountInWords}</p>

          <div className="border-t border-gray-300 mt-3 pt-2">
            {bankAccounts.length > 0 && (
              <>
                <p className="font-semibold text-[11px]">Coordenadas Bancarias</p>
                {bankAccounts.map((b) => (
                  <p key={b.id} className="text-[10px]">{bankById[b.bank_id]?.acronym || '?'}: {b.account_number} &nbsp; IBAN: {b.iban}</p>
                ))}
              </>
            )}
          </div>

          {invoiceType === 'PRO_FORMA' && (
            <p className="text-[10px] italic text-gray-500 mt-3">Este documento nao serve como factura</p>
          )}

          <p className="text-[11px] italic mt-4 text-center text-gray-500">O numero definitivo do documento e atribuido ao guardar.</p>
        </div>
        <div className="flex justify-end pt-3">
          <button
            type="button"
            onClick={() => setPreviewOpen(false)}
            className="border border-border hover:border-danger text-text-primary text-sm px-5 py-2.5 rounded-md transition-colors cursor-pointer"
          >
            Fechar
          </button>
        </div>
      </Modal>
    </>
  );
}