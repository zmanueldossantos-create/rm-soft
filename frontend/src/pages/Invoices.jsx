import { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCan } from '../utils/permissions';
import { createPortal } from 'react-dom';
import { Receipt, Plus, Loader2, Search, Trash2, FileText, Printer, Eye, X as XIcon, RefreshCw, RotateCcw, FilePlus, MoreVertical, ChevronLeft, ChevronRight } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import { listInvoices, getInvoicePeriods, createInvoice, fetchInvoicePdfBlob, getInvoiceDetail, resubmitInvoice, createCreditNote, createDebitNote, createReceipt, convertProForma } from '../api/invoices';
import PeriodFilter from '../components/PeriodFilter';
import { listProducts } from '../api/products';
import { listActivities } from '../api/activity';
import { listCustomers } from '../api/customers';
import { listServices } from '../api/services';
import { paymentTermsApi, paymentMethodsApi, documentTypesApi } from '../api/catalogs';
import useDocumentRules from '../utils/documentRules';
import { extractErrorMessage } from '../utils/errors';

const STATUS_STYLE = {
  PENDENTE: 'bg-text-muted/10 text-text-muted',
  POR_ENVIAR: 'bg-accent/10 text-accent',
  ENVIADA: 'bg-success/10 text-success',
  ERRO: 'bg-danger/10 text-danger',
};

const INVOICE_TYPE_CODE = {
  FACTURA: 'FT',
  FACTURA_RECIBO: 'FR',
  NOTA_CREDITO: 'NC',
  NOTA_DEBITO: 'ND',
  RECIBO: 'RC',
  PRO_FORMA: 'FP',
};

const PDF_BASE_URL = 'http://127.0.0.1:8001/api/v1/invoices';

// Kebab-style row action menu, rendered through a portal so it is never clipped by the
// table's horizontal scroll container (same technique as Select.jsx).
function RowActionMenu({ items }) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const btnRef = useRef(null);
  const panelRef = useRef(null);

  function toggleOpen() {
    if (!open && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      setCoords({ top: rect.bottom + 4, left: Math.max(8, rect.right - 200) });
    }
    setOpen((o) => !o);
  }

  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (
        btnRef.current && !btnRef.current.contains(e.target) &&
        panelRef.current && !panelRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={toggleOpen}
        className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer"
      >
        <MoreVertical size={15} />
      </button>
      {open && createPortal(
        <div ref={panelRef} style={{ position: 'fixed', top: coords.top, left: coords.left, width: 200, zIndex: 1000 }} className="bg-bg-elevated border border-border rounded-md shadow-xl overflow-hidden py-1">
          {items.map((item, i) => (
            <button
              key={i}
              type="button"
              onClick={() => { setOpen(false); item.onClick(); }}
              className="w-full flex items-center gap-2 px-3.5 py-2 text-sm text-left text-text-primary hover:bg-bg-inset transition-colors cursor-pointer"
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>,
        document.body
      )}
    </>
  );
}

function formatMoney(v) {
  return Number(v).toLocaleString('pt-AO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Kz';
}

function round2(v) {
  return Math.round((v + Number.EPSILON) * 100) / 100;
}

export default function Invoices() {
  const can = useCan();
  const navigate = useNavigate();
  const [invoices, setInvoices] = useState([]);
  const [products, setProducts] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  const [modalOpen, setModalOpen] = useState(false);
  const [activities, setActivities] = useState([]);
  const [services, setServices] = useState([]);
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [documentTypes, setDocumentTypes] = useState(null);
  const ruleOf = useDocumentRules();
  useEffect(() => {
    // A user who cannot read the catalog keeps the default behaviour; the server enforces the rules anyway.
    documentTypesApi.list().then(setDocumentTypes).catch(() => {});
  }, []);
  const DOC_CODES = { FACTURA: 'FT', FACTURA_RECIBO: 'FR', PRO_FORMA: 'FP' };
  // "convertible" rule of the catalog (a pro-forma by default) and the invoices a conversion can produce
  const isConvertible = (type) => {
    const d = documentTypes && documentTypes.find((x) => x.code === DOC_CODES[type]);
    return d ? d.convertible : type === 'PRO_FORMA';
  };
  const convertibleTypes = (() => {
    const all = [{ value: 'FACTURA', label: 'FT - Fatura' }, { value: 'FACTURA_RECIBO', label: 'FR - Fatura/Recibo' }];
    if (!documentTypes) return all;
    const allowed = all.filter((o) => { const d = documentTypes.find((x) => x.code === DOC_CODES[o.value]); return d && d.is_active && d.saft_section === 'INVOICES' && !d.requires_origin; });
    return allowed.length ? allowed : all;
  })();
  const [openActionMenuId, setOpenActionMenuId] = useState(null);
  const [company, setCompany] = useState(null);
  const tableScrollRef = useRef(null);

  function scrollTableBy(amount) {
    if (tableScrollRef.current) {
      tableScrollRef.current.scrollBy({ left: amount, behavior: 'smooth' });
    }
  }
  const [paymentTerms, setPaymentTerms] = useState([]);
  const [invoiceType, setInvoiceType] = useState('FACTURA');
  const [paymentTermId, setPaymentTermId] = useState('');
  const [paymentMethodId, setPaymentMethodId] = useState('');
  const [activityId, setActivityId] = useState('');
  const [customerId, setCustomerId] = useState('');
  const [lines, setLines] = useState([{ item_type: 'product', product_id: '', service_id: '', quantity: '1' }]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [resubmittingId, setResubmittingId] = useState(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailInvoice, setDetailInvoice] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');

  const [ncModalOpen, setNcModalOpen] = useState(false);
  const [ncLines, setNcLines] = useState([]);
  const [ncReason, setNcReason] = useState('ANL');
  const [ncCause, setNcCause] = useState('');
  const [ncSaving, setNcSaving] = useState(false);
  const [ncFormError, setNcFormError] = useState('');

  const [ndModalOpen, setNdModalOpen] = useState(false);
  const [ndLines, setNdLines] = useState([{ item_type: 'product', product_id: '', service_id: '', quantity: '1', discount_percent: '0' }]);
  const [ndDocumentReference, setNdDocumentReference] = useState('');
  const [ndObservations, setNdObservations] = useState('');
  const [ndSaving, setNdSaving] = useState(false);
  const [ndFormError, setNdFormError] = useState('');

  const [rcModalOpen, setRcModalOpen] = useState(false);
  const [rcAmount, setRcAmount] = useState('');
  const [rcDocumentReference, setRcDocumentReference] = useState('');
  const [rcObservations, setRcObservations] = useState('');
  const [rcPaymentMethodId, setRcPaymentMethodId] = useState('');
  const [rcSaving, setRcSaving] = useState(false);
  const [rcFormError, setRcFormError] = useState('');

  const [convertModalOpen, setConvertModalOpen] = useState(false);
  const [convertTargetType, setConvertTargetType] = useState('FACTURA');
  const [convertSaving, setConvertSaving] = useState(false);
  const [convertFormError, setConvertFormError] = useState('');

  const [pdfModalOpen, setPdfModalOpen] = useState(false);
  const [pdfBlobUrl, setPdfBlobUrl] = useState('');
  const [pdfFilename, setPdfFilename] = useState('documento.pdf');
  const [pdfViaLabel, setPdfViaLabel] = useState('Original');

  async function openPdfViewer(invoiceId, format, filename) {
    const blobUrl = await fetchInvoicePdfBlob(invoiceId, format);
    setPdfBlobUrl(blobUrl);
    setPdfFilename(filename);
    setPdfModalOpen(true);
  }

  function closePdfViewer() {
    setPdfModalOpen(false);
    if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
    setPdfBlobUrl('');
  }

  function downloadPdf() {
    const a = document.createElement('a');
    a.href = pdfBlobUrl;
    a.download = pdfFilename;
    a.click();
  }

  async function handleResubmit(invoiceId) {
    setResubmittingId(invoiceId);
    try {
      await resubmitInvoice(invoiceId);
      await loadData();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao reenviar fatura'));
    } finally {
      setResubmittingId(null);
    }
  }

  async function openDetailModal(invoiceId) {
    setDetailModalOpen(true);
    setDetailInvoice(null);
    setDetailError('');
    setDetailLoading(true);
    try {
      const data = await getInvoiceDetail(invoiceId);
      setDetailInvoice(data);
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao carregar detalhe da fatura'));
    } finally {
      setDetailLoading(false);
    }
  }

  async function openNcModalFromRow(invoiceId) {
    const data = await getInvoiceDetail(invoiceId);
    setDetailInvoice(data);
    setNcLines(data.lines.map((l) => ({
      invoice_line_id: l.id,
      product_name: l.product_name_snapshot,
      original_quantity: l.quantity,
      selected: true,
      quantity: String(l.quantity),
    })));
    setNcReason('ANL');
    setNcCause('');
    setNcFormError('');
    setNcModalOpen(true);
  }

  async function openNdModalFromRow(invoiceId) {
    const data = await getInvoiceDetail(invoiceId);
    setDetailInvoice(data);
    setNdLines([{ item_type: 'product', product_id: '', service_id: '', quantity: '1', discount_percent: '0' }]);
    setNdDocumentReference((INVOICE_TYPE_CODE[data.invoice_type] || data.invoice_type) + ' ' + data.series + '/' + data.number);
    setNdObservations('');
    setNdFormError('');
    setNdModalOpen(true);
  }

  function openNcModal() {
    if (!detailInvoice) return;
    setNcLines(detailInvoice.lines.map((l) => ({
      invoice_line_id: l.id,
      product_name: l.product_name_snapshot,
      original_quantity: l.quantity,
      selected: true,
      quantity: String(l.quantity),
    })));
    setNcReason('ANL');
    setNcCause('');
    setNcFormError('');
    setNcModalOpen(true);
  }

  function updateNcLineQuantity(lineId, quantity) {
    setNcLines((prev) => prev.map((l) => l.invoice_line_id === lineId ? { ...l, quantity } : l));
  }

  function toggleNcLineSelected(lineId) {
    setNcLines((prev) => prev.map((l) => l.invoice_line_id === lineId ? { ...l, selected: !l.selected } : l));
  }

  async function handleNcSubmit(e) {
    e.preventDefault();
    setNcFormError('');
    setNcSaving(true);
    try {
      const selectedLines = ncLines.filter((l) => l.selected && parseFloat(l.quantity) > 0);
      if (selectedLines.length === 0) {
        setNcFormError('Selecione pelo menos uma linha para creditar');
        setNcSaving(false);
        return;
      }
      await createCreditNote({
        activity_id: detailInvoice.activity_id,
        reference_invoice_id: detailInvoice.id,
        credit_note_reason: ncReason,
        credit_note_cause: ncCause,
        lines: selectedLines.map((l) => ({ invoice_line_id: l.invoice_line_id, quantity: parseFloat(l.quantity) })),
      });
      setNcModalOpen(false);
      await openDetailModal(detailInvoice.id);
      await loadData();
    } catch (err) {
      setNcFormError(extractErrorMessage(err, 'Erro ao emitir nota de credito'));
    } finally {
      setNcSaving(false);
    }
  }

  function openNdModal() {
    setNdLines([{ item_type: 'product', product_id: '', service_id: '', quantity: '1', discount_percent: '0' }]);
    setNdDocumentReference((INVOICE_TYPE_CODE[detailInvoice.invoice_type] || detailInvoice.invoice_type) + ' ' + detailInvoice.series + '/' + detailInvoice.number);
    setNdObservations('');
    setNdFormError('');
    setNdModalOpen(true);
  }

  function updateNdLine(index, field, value) {
    setNdLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));
  }

  function updateNdLineType(index, itemType) {
    setNdLines((prev) => prev.map((l, i) => (i === index ? { item_type: itemType, product_id: '', service_id: '', quantity: l.quantity, discount_percent: l.discount_percent } : l)));
  }

  function addNdLine() {
    setNdLines((prev) => [...prev, { item_type: 'product', product_id: '', service_id: '', quantity: '1', discount_percent: '0' }]);
  }

  function removeNdLine(index) {
    setNdLines((prev) => prev.filter((_, i) => i !== index));
  }

  function getNdLineItem(line) {
    return line.item_type === 'service' ? serviceById[line.service_id] : productById[line.product_id];
  }

  async function handleNdSubmit(e) {
    e.preventDefault();
    setNdFormError('');
    setNdSaving(true);
    try {
      await createDebitNote({
        activity_id: detailInvoice.activity_id,
        reference_invoice_id: detailInvoice.id,
        document_reference: ndDocumentReference || null,
        observations: ndObservations || null,
        lines: ndLines.map((l) => ({
          product_id: l.item_type === 'service' ? null : l.product_id,
          service_id: l.item_type === 'service' ? l.service_id : null,
          quantity: parseFloat(l.quantity),
          discount_percent: parseFloat(l.discount_percent) || 0,
        })),
      });
      setNdModalOpen(false);
      await openDetailModal(detailInvoice.id);
      await loadData();
    } catch (err) {
      setNdFormError(extractErrorMessage(err, 'Erro ao emitir nota de debito'));
    } finally {
      setNdSaving(false);
    }
  }

  function openRcModal() {
    setRcAmount('');
    setRcDocumentReference((INVOICE_TYPE_CODE[detailInvoice.invoice_type] || detailInvoice.invoice_type) + ' ' + detailInvoice.series + '/' + detailInvoice.number);
    setRcObservations('');
    setRcPaymentMethodId('');
    setRcFormError('');
    setRcModalOpen(true);
  }

  async function openRcModalFromRow(invoiceId) {
    const data = await getInvoiceDetail(invoiceId);
    setDetailInvoice(data);
    setRcAmount('');
    setRcDocumentReference((INVOICE_TYPE_CODE[data.invoice_type] || data.invoice_type) + ' ' + data.series + '/' + data.number);
    setRcObservations('');
    setRcPaymentMethodId('');
    setRcFormError('');
    setRcModalOpen(true);
  }

  async function handleRcSubmit(e) {
    e.preventDefault();
    setRcFormError('');
    setRcSaving(true);
    try {
      await createReceipt({
        activity_id: detailInvoice.activity_id,
        reference_invoice_id: detailInvoice.id,
        amount: parseFloat(rcAmount),
        document_reference: rcDocumentReference || null,
        observations: rcObservations || null,
        payment_method_id: rcPaymentMethodId || null,
      });
      setRcModalOpen(false);
      await openDetailModal(detailInvoice.id);
      await loadData();
    } catch (err) {
      setRcFormError(extractErrorMessage(err, 'Erro ao emitir recibo'));
    } finally {
      setRcSaving(false);
    }
  }

  function openConvertModal() {
    setConvertTargetType('FACTURA');
    setConvertFormError('');
    setConvertModalOpen(true);
  }

  async function openConvertModalFromRow(invoiceId) {
    const data = await getInvoiceDetail(invoiceId);
    setDetailInvoice(data);
    setConvertTargetType('FACTURA');
    setConvertFormError('');
    setConvertModalOpen(true);
  }

  async function handleConvertSubmit(e) {
    e.preventDefault();
    setConvertFormError('');
    setConvertSaving(true);
    try {
      await convertProForma(detailInvoice.id, {
        target_invoice_type: convertTargetType,
      });
      setConvertModalOpen(false);
      navigate('/invoices');
    } catch (err) {
      setConvertFormError(extractErrorMessage(err, 'Erro ao converter pro-forma'));
    } finally {
      setConvertSaving(false);
    }
  }

  const [periods, setPeriods] = useState([]);
  const [filters, setFilters] = useState({ year: '', month: '', dateFrom: '', dateTo: '' });
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const PAGE_SIZE = 50;

  async function loadInvoicesPage(currentFilters, currentOffset, append) {
    const data = await listInvoices({
      year: currentFilters.year || undefined,
      month: currentFilters.month || undefined,
      dateFrom: currentFilters.dateFrom || undefined,
      dateTo: currentFilters.dateTo || undefined,
      limit: PAGE_SIZE,
      offset: currentOffset,
    });
    setInvoices((prev) => (append ? [...prev, ...data] : data));
    setHasMore(data.length === PAGE_SIZE);
  }

  async function loadData() {
    setLoading(true);
    setError('');
    try {
      const [periodsData, productsData, servicesData, customersData, activitiesData, paymentTermsData, paymentMethodsData] = await Promise.all([
        getInvoicePeriods(),
        listProducts(),
        listServices(),
        listCustomers(),
        listActivities(),
        paymentTermsApi.list(),
        paymentMethodsApi.list(),
      ]);
      setPeriods(periodsData);
      const initialFilters = periodsData.length > 0
        ? { year: String(periodsData[0].year), month: '', dateFrom: '', dateTo: '' }
        : { year: '', month: '', dateFrom: '', dateTo: '' };
      setFilters(initialFilters);
      setOffset(0);
      await loadInvoicesPage(initialFilters, 0, false);
      setProducts(productsData.filter((p) => p.is_active && !p.is_raw_material));
      setServices(servicesData.filter((s) => s.is_active));
      setCustomers(customersData.filter((c) => c.is_active));
      setActivities(activitiesData.filter((a) => a.is_active));
      setPaymentTerms(paymentTermsData.filter((t) => t.is_active));
      setPaymentMethods(paymentMethodsData.filter((m) => m.is_active));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar faturas'));
    } finally {
      setLoading(false);
    }
  }

  async function handleFilterChange(newFilters) {
    setFilters(newFilters);
    setOffset(0);
    setLoading(true);
    try {
      await loadInvoicesPage(newFilters, 0, false);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar faturas'));
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadMore() {
    const nextOffset = offset + PAGE_SIZE;
    setLoadingMore(true);
    try {
      await loadInvoicesPage(filters, nextOffset, true);
      setOffset(nextOffset);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar mais faturas'));
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    loadData();
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

  const customerById = useMemo(() => {
    const map = {};
    customers.forEach((c) => { map[c.id] = c; });
    return map;
  }, [customers]);

  const paymentMethodById = useMemo(() => {
    const map = {};
    paymentMethods.forEach((m) => { map[m.id] = m; });
    return map;
  }, [paymentMethods]);

  const filteredInvoices = useMemo(() => {
    if (!search.trim()) return invoices;
    const q = search.toLowerCase();
    return invoices.filter(
      (inv) => (inv.series + '/' + inv.number).toLowerCase().includes(q) || inv.atcud.toLowerCase().includes(q)
    );
  }, [invoices, search]);

  // Debito = every document type except Nota de Credito (FT/FR/ND all increase what is owed);
  // Credito = Nota de Credito only. Used by the 3-row Total Debito/Credito/Diferenca footer.
  const footerTotals = useMemo(() => {
    const metrics = ['total', 'subtotal', 'discount_global_percent', 'vat_total', 'retention_total'];
    function sumFor(list, field) {
      return round2(list.reduce((sum, inv) => sum + (parseFloat(inv[field]) || 0), 0));
    }
    function aPagarFor(list) {
      return round2(list.reduce((sum, inv) => sum + round2((parseFloat(inv.total) || 0) - (parseFloat(inv.retention_total) || 0) - (parseFloat(inv.amount_received) || 0)), 0));
    }
    function descontosFor(list) {
      return round2(list.reduce((sum, inv) => {
        const beforeDiscount = (parseFloat(inv.subtotal) || 0) + (parseFloat(inv.vat_total) || 0);
        const pct = parseFloat(inv.discount_global_percent) || 0;
        return sum + round2(beforeDiscount * (pct / 100));
      }, 0));
    }
    const debitoList = filteredInvoices.filter((inv) => inv.invoice_type !== 'NOTA_CREDITO');
    const creditoList = filteredInvoices.filter((inv) => inv.invoice_type === 'NOTA_CREDITO');
    const build = (list) => ({
      totalDoc: sumFor(list, 'total'),
      totalIliquido: sumFor(list, 'subtotal'),
      descontos: descontosFor(list),
      iva: sumFor(list, 'vat_total'),
      total: sumFor(list, 'total'),
      retencoes: sumFor(list, 'retention_total'),
      aPagar: aPagarFor(list),
    });
    const debito = build(debitoList);
    const credito = build(creditoList);
    const diff = {
      totalDoc: round2(debito.totalDoc - credito.totalDoc),
      totalIliquido: round2(debito.totalIliquido - credito.totalIliquido),
      descontos: round2(debito.descontos - credito.descontos),
      iva: round2(debito.iva - credito.iva),
      total: round2(debito.total - credito.total),
      retencoes: round2(debito.retencoes - credito.retencoes),
      aPagar: round2(debito.aPagar - credito.aPagar),
    };
    return { debito, credito, diff };
  }, [filteredInvoices]);

  function openCreateModal() {
    setActivityId(activities.length === 1 ? activities[0].id : '');
    setCustomerId('');
    setInvoiceType('FACTURA');
    setPaymentTermId('');
    setPaymentMethodId('');
    setLines([{ item_type: 'product', product_id: '', service_id: '', quantity: '1' }]);
    setFormError('');
    setModalOpen(true);
  }

  function handleCustomerChange(newCustomerId) {
    setCustomerId(newCustomerId);
    const customer = customers.find((c) => c.id === newCustomerId);
    if (customer) {
      if (customer.payment_term_id) setPaymentTermId(customer.payment_term_id);
      if (customer.payment_method_id) setPaymentMethodId(customer.payment_method_id);
    }
  }

  function closeModal() {
    setModalOpen(false);
  }

  function updateLine(index, field, value) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));
  }

  function addLine() {
    setLines((prev) => [...prev, { item_type: 'product', product_id: '', service_id: '', quantity: '1' }]);
  }

  function updateLineType(index, itemType) {
    setLines((prev) => prev.map((l, i) => (i === index ? { item_type: itemType, product_id: '', service_id: '', quantity: l.quantity } : l)));
  }

  function removeLine(index) {
    setLines((prev) => prev.filter((_, i) => i !== index));
  }

  const preview = useMemo(() => {
    let subtotal = 0;
    for (const line of lines) {
      const item = line.item_type === 'service' ? serviceById[line.service_id] : productById[line.product_id];
      const qty = parseFloat(line.quantity) || 0;
      if (!item || qty <= 0) continue;
      subtotal += (item.price || 0) * qty;
    }
    return { subtotal };
  }, [lines, productById, serviceById]);

  const isFormValid = activityId && lines.length > 0 && lines.every((l) =>
    (l.item_type === 'service' ? l.service_id : l.product_id) && parseFloat(l.quantity) > 0
  );

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      await createInvoice({
        activity_id: activityId,
        customer_id: customerId || null,
        invoice_type: invoiceType,
        payment_term_id: paymentTermId || null,
        payment_method_id: paymentMethodId || null,
        lines: lines.map((l) => ({
          product_id: l.item_type === 'service' ? null : l.product_id,
          service_id: l.item_type === 'service' ? l.service_id : null,
          quantity: parseFloat(l.quantity),
        })),
      });
      closeModal();
      await loadData();
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao criar fatura'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Receipt size={22} className="text-accent" />
        Faturas
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Emissão de faturas conforme RGIFT 2.0 (AGT)
      </p>

      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative max-w-sm w-full sm:w-auto sm:min-w-[240px]">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              placeholder="Pesquisar por série/número ou ATCUD..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          <PeriodFilter periods={periods} onChange={handleFilterChange} />
        </div>
        <button
          onClick={() => navigate('/invoices/new')}
          // No dependency on products: a services-only company (or one that only has raw materials)
          // has none, and /invoices/new handles service lines - its own form keeps 'Criar Fatura'
          // disabled until every line has an item.
          disabled={!can('invoices:issue')}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer"
        >
          <Plus size={17} />
          Nova fatura
        </button>
      </div>

      <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
        {loading && (
          <div className="flex items-center justify-center py-16 text-text-muted text-sm">
            <Loader2 size={18} className="animate-spin mr-2" />
            A carregar...
          </div>
        )}

        {error && (
          <div className="px-6 py-4 text-danger text-sm bg-danger/10">{error}</div>
        )}

        {!loading && !error && filteredInvoices.length === 0 && (
          <div className="text-center py-16 text-text-muted text-sm flex flex-col items-center gap-3">
            <span>{search ? 'Nenhuma fatura encontrada' : 'Nenhuma fatura emitida ainda'}</span>
            <Search size={22} className="text-text-muted/40" />
          </div>
        )}

        {!loading && !error && filteredInvoices.length > 0 && (
          <>
          <div className="flex items-center justify-end gap-1.5 px-4 py-1.5 border-t border-border bg-bg-inset/30">
            <span className="text-[11px] text-text-muted mr-1">Deslocar tabela</span>
            <button type="button" onClick={() => scrollTableBy(-400)} className="inline-flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
              <ChevronLeft size={14} />
            </button>
            <button type="button" onClick={() => scrollTableBy(400)} className="inline-flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
              <ChevronRight size={14} />
            </button>
          </div>
          <div ref={tableScrollRef} className="overflow-auto max-h-[70vh] border-t border-border scrollbar-thin">
            <table className="w-full text-sm border-collapse min-w-[2600px]">
              <thead className="sticky top-0 z-20">
                <tr className="border-b border-border bg-bg-elevated">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated sticky left-0 z-30 shadow-[4px_0_6px_-2px_rgba(0,0,0,0.15)] w-[160px] min-w-[160px]">Série</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Documento</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Número</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Tp. Documento</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Entidade</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Denominação Fiscal</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">NIF</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Data Doc.</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Data Vencimento</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Estado FE</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Estado</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Estado Pagamento</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Doc. Referência</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Método Pagamento</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Total Doc.</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Total Ilíquido</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Descontos</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">IVA</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Total</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Retenções</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">A Pagar</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Pendente</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Pendente Retenções</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Modo Emissão</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">RequestID FE</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Itens</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Moeda</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Criado por</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated">Data de Criação</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3 whitespace-nowrap bg-bg-elevated sticky right-0 z-30 shadow-[-4px_0_6px_-2px_rgba(0,0,0,0.15)]">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredInvoices.map((inv) => {
                  const customer = customerById[inv.customer_id];
                  const paymentMethod = paymentMethodById[inv.payment_method_id];
                  const received = parseFloat(inv.amount_received) || 0;
                  const aPagar = round2((inv.total || 0) - (inv.retention_total || 0) - received);
                  const estadoPagamento = received >= (inv.total || 0) && (inv.total || 0) > 0 ? 'Pago' : received > 0 ? 'Parcial' : 'Pendente';
                  const estadoPagamentoStyle = estadoPagamento === 'Pago' ? 'bg-success/10 text-success' : estadoPagamento === 'Parcial' ? 'bg-accent/10 text-accent' : 'bg-text-muted/10 text-text-muted';
                  const docCode = INVOICE_TYPE_CODE[inv.invoice_type] || inv.invoice_type;
                  return (
                    <tr key={inv.id} className="border-b border-border hover:bg-bg-inset/40 transition-colors">
                      <td className="px-4 py-3 font-mono text-text-muted whitespace-nowrap sticky left-0 z-10 bg-bg-elevated group-hover:bg-bg-inset shadow-[4px_0_6px_-2px_rgba(0,0,0,0.15)] w-[160px] min-w-[160px]">{inv.series}</td>
                      <td className="px-4 py-3 font-mono font-medium text-text-primary whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          <FileText size={13} className="text-accent shrink-0" />
                          {docCode} {inv.series}/{inv.number}
                        </div>
                      </td>
                      <td className="px-4 py-3 font-mono text-text-muted whitespace-nowrap">{inv.number}</td>
                      <td className="px-4 py-3 font-mono text-text-muted whitespace-nowrap">{docCode}</td>
                      <td className="px-4 py-3 text-text-primary whitespace-nowrap">{customer ? (customer.customer_code ? customer.customer_code + ' - ' : '') + customer.name : 'Consumidor Final'}</td>
                      <td className="px-4 py-3 text-text-muted whitespace-nowrap">{customer?.fiscal_name || customer?.name || '-'}</td>
                      <td className="px-4 py-3 font-mono text-text-muted whitespace-nowrap">{customer?.nif || '999999999'}</td>
                      <td className="px-4 py-3 font-mono text-text-muted whitespace-nowrap">{inv.business_date}</td>
                      <td className="px-4 py-3 font-mono text-text-muted whitespace-nowrap">{inv.due_date || '-'}</td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {inv.invoice_type === 'PRO_FORMA' ? (
                          <span className="text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded bg-text-muted/10 text-text-muted">
                            Nao Fiscal
                          </span>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className={'text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded ' + (STATUS_STYLE[inv.status] || '')}>
                              {inv.status}
                            </span>
                            {(inv.status === 'ERRO' || inv.status === 'PENDENTE') && (
                              <button
                                type="button"
                                onClick={() => handleResubmit(inv.id)}
                                disabled={resubmittingId === inv.id || !can('invoices:resubmit')}
                                title="Reenviar para a AGT"
                                className="inline-flex items-center justify-center w-6 h-6 rounded text-text-muted hover:text-accent disabled:opacity-50 transition-colors cursor-pointer"
                              >
                                {resubmittingId === inv.id ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-text-muted text-[12px]">{inv.document_status}</td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={'text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded ' + estadoPagamentoStyle}>
                          {estadoPagamento}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-text-muted whitespace-nowrap">{inv.document_reference || '-'}</td>
                      <td className="px-4 py-3 text-text-muted whitespace-nowrap">{paymentMethod?.name || '-'}</td>
                      <td className="px-4 py-3 font-mono text-text-primary text-right whitespace-nowrap font-medium">{formatMoney(inv.total)}</td>
                      <td className="px-4 py-3 font-mono text-text-muted text-right whitespace-nowrap">{formatMoney(inv.subtotal)}</td>
                      <td className="px-4 py-3 font-mono text-text-muted text-right whitespace-nowrap">{Number(inv.discount_global_percent || 0).toFixed(2)}%</td>
                      <td className="px-4 py-3 font-mono text-text-muted text-right whitespace-nowrap">{formatMoney(inv.vat_total)}</td>
                      <td className="px-4 py-3 font-mono text-text-primary text-right whitespace-nowrap font-medium">{formatMoney(inv.total)}</td>
                      <td className="px-4 py-3 font-mono text-text-muted text-right whitespace-nowrap">{formatMoney(inv.retention_total)}</td>
                      <td className="px-4 py-3 font-mono text-accent text-right whitespace-nowrap font-medium">{formatMoney(aPagar)}</td>
                      <td className="px-4 py-3 font-mono text-accent text-right whitespace-nowrap">{formatMoney(aPagar)}</td>
                      <td className="px-4 py-3 font-mono text-text-muted text-right whitespace-nowrap">{formatMoney(inv.retention_total)}</td>
                      <td className="px-4 py-3 text-text-muted whitespace-nowrap">{inv.issuance_mode === 'ELETRONICA' ? 'Eletrônica' : 'Manual'}</td>
                      <td className="px-4 py-3 text-text-muted whitespace-nowrap">-</td>
                      <td className="px-4 py-3 text-text-muted whitespace-nowrap">{inv.item_count ?? '-'}</td>
                      <td className="px-4 py-3 text-text-muted whitespace-nowrap">AOA</td>
                      <td className="px-4 py-3 text-text-muted whitespace-nowrap">{company?.name || '-'}</td>
                      <td className="px-4 py-3 font-mono text-text-muted text-xs whitespace-nowrap">{inv.created_at ? new Date(inv.created_at).toLocaleString('pt-AO') : '-'}</td>
                      <td className="px-4 py-3 text-right sticky right-0 z-10 bg-bg-elevated shadow-[-4px_0_6px_-2px_rgba(0,0,0,0.15)]">
                        <div className="flex justify-end">
                          <RowActionMenu items={[
                            { label: 'Ver detalhe', icon: <Eye size={14} />, onClick: () => openDetailModal(inv.id) },
                            { label: 'Ticket 80mm', icon: <Receipt size={14} />, onClick: () => openPdfViewer(inv.id, 'thermal', 'RM SOFT - ' + inv.series + '-' + inv.number + ' (Ticket)') },
                            { label: 'A4', icon: <Printer size={14} />, onClick: () => openPdfViewer(inv.id, 'a4', 'RM SOFT - ' + inv.series + '-' + inv.number + ' (A4)') },
                            ...((ruleOf(inv.invoice_type, 'accepts_credit_note') || ruleOf(inv.invoice_type, 'accepts_debit_note')) && inv.document_status !== 'ANULADO' ? [
                              ...(ruleOf(inv.invoice_type, 'accepts_credit_note') ? [{ perm: 'invoices:credit_note', label: 'Emitir Nota de Credito', icon: <RotateCcw size={14} />, onClick: () => openNcModalFromRow(inv.id) }] : []),
                              ...(ruleOf(inv.invoice_type, 'accepts_debit_note') ? [{ perm: 'invoices:debit_note', label: 'Emitir Nota de Debito', icon: <FilePlus size={14} />, onClick: () => openNdModalFromRow(inv.id) }] : []),
                              ...(ruleOf(inv.invoice_type, 'accepts_receipt') && (Number(inv.total) - Number(inv.retention_total || 0) - Number(inv.amount_received || 0)) > 0.005 ? [{ perm: 'invoices:receipt', label: 'Emitir Recibo', icon: <Receipt size={14} />, onClick: () => openRcModalFromRow(inv.id) }] : []),
                            ] : []),
                            ...(isConvertible(inv.invoice_type) && !inv.converted_to_invoice_id ? [
                              { perm: 'invoices:proforma_convert', label: 'Converter em Fatura', icon: <FileText size={14} />, onClick: () => openConvertModalFromRow(inv.id) },
                            ] : []),
                          ].filter((item) => !item.perm || can(item.perm))} />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot className="sticky bottom-0 z-20 bg-bg-elevated border-t-2 border-border">
                <tr>
                  <td className="px-4 py-3 text-[12px] font-semibold text-text-primary whitespace-nowrap sticky left-0 z-30 bg-bg-elevated shadow-[4px_0_6px_-2px_rgba(0,0,0,0.15)] w-[160px] min-w-[160px]">
                    Total Débito:
                  </td>
                  <td colSpan={13} className="bg-bg-elevated"></td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.debito.totalDoc)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.debito.totalIliquido)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.debito.descontos)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.debito.iva)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.debito.total)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.debito.retencoes)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.debito.aPagar)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.debito.aPagar)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.debito.retencoes)}</td>
                  <td colSpan={6} className="bg-bg-elevated"></td>
                  <td className="sticky right-0 bg-bg-elevated shadow-[-4px_0_6px_-2px_rgba(0,0,0,0.15)]"></td>
                </tr>
                <tr>
                  <td className="px-4 py-3 text-[12px] font-semibold text-text-primary whitespace-nowrap sticky left-0 z-30 bg-bg-elevated shadow-[4px_0_6px_-2px_rgba(0,0,0,0.15)] w-[160px] min-w-[160px]">
                    Total Crédito:
                  </td>
                  <td colSpan={13} className="bg-bg-elevated"></td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.credito.totalDoc)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.credito.totalIliquido)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.credito.descontos)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.credito.iva)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.credito.total)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.credito.retencoes)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.credito.aPagar)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.credito.aPagar)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-text-primary text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.credito.retencoes)}</td>
                  <td colSpan={6} className="bg-bg-elevated"></td>
                  <td className="sticky right-0 bg-bg-elevated shadow-[-4px_0_6px_-2px_rgba(0,0,0,0.15)]"></td>
                </tr>
                <tr className="border-t border-border">
                  <td className="px-4 py-3 text-[12px] font-semibold text-text-primary whitespace-nowrap sticky left-0 z-30 bg-bg-elevated shadow-[4px_0_6px_-2px_rgba(0,0,0,0.15)] w-[160px] min-w-[160px]">
                    Total (Débito - Crédito):
                  </td>
                  <td colSpan={13} className="bg-bg-elevated"></td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.diff.totalDoc)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.diff.totalIliquido)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.diff.descontos)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.diff.iva)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.diff.total)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.diff.retencoes)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.diff.aPagar)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.diff.aPagar)}</td>
                  <td className="px-4 py-3 font-mono font-semibold text-accent text-right whitespace-nowrap bg-bg-elevated">{formatMoney(footerTotals.diff.retencoes)}</td>
                  <td colSpan={6} className="bg-bg-elevated"></td>
                  <td className="sticky right-0 bg-bg-elevated shadow-[-4px_0_6px_-2px_rgba(0,0,0,0.15)]"></td>
                </tr>
              </tfoot>
            </table>
          </div>
          </>
        )}
        {!loading && !error && invoices.length > 0 && hasMore && (
          <div className="flex justify-center py-4 border-t border-border">
            <button
              onClick={handleLoadMore}
              disabled={loadingMore}
              className="flex items-center gap-2 text-accent hover:text-accent-hover font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50"
            >
              {loadingMore && <Loader2 size={14} className="animate-spin" />}
              {loadingMore ? 'A carregar...' : 'Carregar mais'}
            </button>
          </div>
        )}
      </div>

      <Modal open={modalOpen} onClose={closeModal} title="Nova fatura" maxWidthClass="max-w-3xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">
              Atividade *
            </label>
            <Select
              value={activityId}
              onChange={setActivityId}
              options={activities.map((a) => ({ value: a.id, label: a.name + ' (' + a.series_code + ')' }))}
              placeholder="Selecionar atividade"
            />
          </div>

          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">
              Cliente (opcional)
            </label>
            <Select
              value={customerId}
              onChange={handleCustomerChange}
              options={[{ value: '', label: 'Sem cliente (venda ao balcão)' }, ...customers.map((c) => ({ value: c.id, label: c.name + ' - ' + c.nif }))]}
              placeholder="Selecionar cliente"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Tipo de documento *</label>
              <Select
                value={invoiceType}
                onChange={setInvoiceType}
                options={[{ value: 'FACTURA', label: 'FT - Fatura' }, { value: 'FACTURA_RECIBO', label: 'FR - Fatura/Recibo' }]}
              />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Condição de pagamento</label>
              <Select
                value={paymentTermId}
                onChange={setPaymentTermId}
                options={paymentTerms.map((t) => ({ value: t.id, label: t.name }))}
                placeholder="Selecionar"
              />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Método de pagamento</label>
              <Select
                value={paymentMethodId}
                onChange={setPaymentMethodId}
                options={paymentMethods.map((m) => ({ value: m.id, label: m.name }))}
                placeholder="Selecionar"
              />
            </div>
          </div>

          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">
              Produtos *
            </label>
            <div className="flex flex-col gap-2">
              {lines.map((line, idx) => {
                const product = line.item_type === 'product' ? productById[line.product_id] : null;
                const service = line.item_type === 'service' ? serviceById[line.service_id] : null;
                const item = product || service;
                return (
                  <div key={idx} className="flex items-center gap-2 bg-bg-inset/40 border border-border rounded-md p-2.5">
                    <div className="flex bg-bg-inset border border-border rounded-md overflow-hidden shrink-0">
                      <button type="button" onClick={() => updateLineType(idx, 'product')} className={'px-2.5 py-2 text-[11px] font-medium transition-colors cursor-pointer ' + (line.item_type === 'product' ? 'bg-accent text-white' : 'text-text-muted')}>Produto</button>
                      <button type="button" onClick={() => updateLineType(idx, 'service')} className={'px-2.5 py-2 text-[11px] font-medium transition-colors cursor-pointer ' + (line.item_type === 'service' ? 'bg-accent text-white' : 'text-text-muted')}>Servico</button>
                    </div>
                    <div className="flex-1">
                      {line.item_type === 'service' ? (
                        <Select
                          value={line.service_id}
                          onChange={(val) => updateLine(idx, 'service_id', val)}
                          options={services.map((s) => ({ value: s.id, label: s.code + ' - ' + s.name + ' (' + formatMoney(s.price || 0) + ')' }))}
                          placeholder="Selecionar servico"
                        />
                      ) : (
                        <Select
                          value={line.product_id}
                          onChange={(val) => updateLine(idx, 'product_id', val)}
                          options={products.map((p) => ({ value: p.id, label: p.code + ' - ' + p.name + ' (' + formatMoney(p.price) + ')' }))}
                          placeholder="Selecionar produto"
                        />
                      )}
                    </div>
                    <input
                      type="number"
                      step={product?.is_sold_by_weight ? '0.001' : '1'}
                      min={product?.is_sold_by_weight ? '0.001' : '1'}
                      value={line.quantity}
                      onChange={(e) => updateLine(idx, 'quantity', e.target.value)}
                      className="w-24 bg-bg-inset border border-border rounded-md px-2.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
                    />
                    <div className="w-28 text-right font-mono text-sm text-text-primary">
                      {item ? formatMoney((item.price || 0) * (parseFloat(line.quantity) || 0)) : '-'}
                    </div>
                    <button
                      type="button"
                      onClick={() => removeLine(idx)}
                      disabled={lines.length === 1}
                      className="text-text-muted hover:text-danger disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                );
              })}
            </div>
            <button
              type="button"
              onClick={addLine}
              className="mt-2 flex items-center gap-1.5 text-accent hover:underline text-sm cursor-pointer"
            >
              <Plus size={14} /> Adicionar linha
            </button>
          </div>

          <div className="border-t border-border pt-3 flex items-center justify-between">
            <span className="text-text-muted text-sm">Subtotal (sem IVA)</span>
            <span className="font-mono font-semibold text-text-primary">{formatMoney(preview.subtotal)}</span>
          </div>
          <p className="text-[11px] text-text-muted -mt-2">O IVA e o total final são calculados no servidor por linha, conforme a taxa de cada produto.</p>

          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
              {formError}
            </div>
          )}

          <button
            type="submit"
            disabled={saving || !isFormValid}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {saving ? 'A emitir...' : 'Emitir fatura'}
          </button>
        </form>
      </Modal>

      <Modal open={detailModalOpen} onClose={() => setDetailModalOpen(false)} title="Detalhe da fatura" maxWidthClass="max-w-3xl">
        {detailLoading && (
          <div className="flex items-center justify-center py-10 text-text-muted text-sm">
            <Loader2 size={18} className="animate-spin mr-2" />
            A carregar...
          </div>
        )}

        {detailError && (
          <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
            {detailError}
          </div>
        )}

        {!detailLoading && !detailError && detailInvoice && (
          <div className="flex flex-col gap-5">
            <div className="flex items-start justify-between flex-wrap gap-3 pb-4 border-b border-border">
              <div>
                <p className="font-display font-semibold text-lg text-text-primary">
                  {INVOICE_TYPE_CODE[detailInvoice.invoice_type] || detailInvoice.invoice_type} {detailInvoice.series}/{detailInvoice.number}
                </p>
                <p className="text-text-muted text-sm font-mono">{detailInvoice.business_date}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={'text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded ' + (STATUS_STYLE[detailInvoice.status] || '')}>
                  {detailInvoice.status}
                </span>
                <span className="text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded bg-bg-inset text-text-muted">
                  {detailInvoice.document_status}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">ATCUD</p>
                <p className="font-mono text-text-primary text-xs break-all">{detailInvoice.atcud}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">Hash</p>
                <p className="font-mono text-text-primary text-xs break-all">{detailInvoice.invoice_hash.slice(0, 30)}...</p>
              </div>
            </div>

            <div>
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide mb-2">Produtos</p>
              <div className="border border-border rounded-md overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-bg-inset/40">
                      <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2">Produto</th>
                      <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2">Qtd</th>
                      <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2">Preço</th>
                      <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2">IVA</th>
                      <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailInvoice.lines.map((l) => (
                      <tr key={l.id} className="border-b border-border last:border-0">
                        <td className="px-4 py-2.5 font-display font-medium text-text-primary">{l.product_name_snapshot}</td>
                        <td className="px-4 py-2.5 font-mono text-text-muted text-right">{l.quantity}</td>
                        <td className="px-4 py-2.5 font-mono text-text-muted text-right">{formatMoney(l.unit_price)}</td>
                        <td className="px-4 py-2.5 font-mono text-text-muted text-right">{l.vat_rate_snapshot}%</td>
                        <td className="px-4 py-2.5 font-mono text-text-primary text-right">{formatMoney(l.line_total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex flex-col gap-1.5 items-end border-t border-border pt-4">
              <div className="flex justify-between w-56 text-sm">
                <span className="text-text-muted">Subtotal</span>
                <span className="font-mono text-text-primary">{formatMoney(detailInvoice.subtotal)}</span>
              </div>
              <div className="flex justify-between w-56 text-sm">
                <span className="text-text-muted">IVA</span>
                <span className="font-mono text-text-primary">{formatMoney(detailInvoice.vat_total)}</span>
              </div>
              {Number(detailInvoice.retention_total) > 0 && (
                <div className="flex justify-between w-56 text-sm">
                  <span className="text-text-muted">{'Reten\u00e7\u00f5es'}</span>
                  <span className="font-mono text-text-primary">-{formatMoney(detailInvoice.retention_total)}</span>
                </div>
              )}
              <div className="flex justify-between w-56 text-base font-semibold">
                <span className="text-text-primary">TOTAL</span>
                <span className="font-mono text-accent">{formatMoney(detailInvoice.total)}</span>
              </div>
              {ruleOf(detailInvoice.invoice_type, 'accepts_receipt') && (Number(detailInvoice.retention_total) > 0 || Number(detailInvoice.amount_received) > 0) && (
                <>
                  {Number(detailInvoice.amount_received) > 0 && (
                    <div className="flex justify-between w-56 text-sm">
                      <span className="text-text-muted">Valor recebido</span>
                      <span className="font-mono text-text-primary">{formatMoney(detailInvoice.amount_received)}</span>
                    </div>
                  )}
                  <div className="flex justify-between w-56 text-sm">
                    <span className="text-text-muted">Valor a pagar</span>
                    <span className="font-mono text-text-primary">{formatMoney(Math.max(0, Math.round((Number(detailInvoice.total) - Number(detailInvoice.retention_total || 0) - Number(detailInvoice.amount_received || 0)) * 100) / 100))}</span>
                  </div>
                </>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => openPdfViewer(detailInvoice.id, 'thermal', 'RM SOFT - ' + detailInvoice.series + '-' + detailInvoice.number + ' (Ticket)')}
                className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-sm px-3.5 py-2 rounded-md transition-colors cursor-pointer"
              >
                <Receipt size={14} /> Ticket
              </button>
              <button
                type="button"
                onClick={() => openPdfViewer(detailInvoice.id, 'a4', 'RM SOFT - ' + detailInvoice.series + '-' + detailInvoice.number + ' (A4)')}
                className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-sm px-3.5 py-2 rounded-md transition-colors cursor-pointer"
              >
                <Printer size={14} /> A4
              </button>
              {ruleOf(detailInvoice.invoice_type, 'accepts_credit_note') && detailInvoice.document_status !== 'ANULADO' && (
                <button
                  type="button"
                  onClick={openNcModal}
                  disabled={!can('invoices:credit_note')}
                  className="flex items-center gap-1.5 border border-border hover:border-danger text-danger text-sm px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <RotateCcw size={14} /> Emitir Nota de Credito
                </button>
              )}
              {ruleOf(detailInvoice.invoice_type, 'accepts_debit_note') && detailInvoice.document_status !== 'ANULADO' && (
                <button
                  type="button"
                  onClick={openNdModal}
                  disabled={!can('invoices:debit_note')}
                  className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-sm px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <FilePlus size={14} /> Emitir Nota de Debito
                </button>
              )}
              {ruleOf(detailInvoice.invoice_type, 'accepts_receipt') && detailInvoice.document_status !== 'ANULADO' && (Number(detailInvoice.total) - Number(detailInvoice.retention_total || 0) - Number(detailInvoice.amount_received || 0)) > 0.005 && (
                <button
                  type="button"
                  onClick={openRcModal}
                  disabled={!can('invoices:receipt')}
                  className="flex items-center gap-1.5 border border-border hover:border-success text-success text-sm px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Receipt size={14} /> Emitir Recibo
                </button>
              )}
              {isConvertible(detailInvoice.invoice_type) && !detailInvoice.converted_to_invoice_id && (
                <button
                  type="button"
                  onClick={openConvertModal}
                  disabled={!can('invoices:proforma_convert')}
                  className="flex items-center gap-1.5 border border-border hover:border-accent text-accent text-sm px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <FileText size={14} /> Converter em Fatura
                </button>
              )}
            </div>
          </div>
        )}
      </Modal>

      <Modal open={ndModalOpen} onClose={() => setNdModalOpen(false)} title="Emitir Nota de Debito" maxWidthClass="max-w-3xl">
        {detailInvoice && (
          <form onSubmit={handleNdSubmit} className="flex flex-col gap-4">
            <p className="text-[12px] text-text-muted">
              Referente a <span className="font-mono text-text-primary">{INVOICE_TYPE_CODE[detailInvoice.invoice_type] || detailInvoice.invoice_type} {detailInvoice.series}/{detailInvoice.number}</span>
            </p>

            <div className="flex flex-col gap-2">
              {ndLines.map((line, idx) => {
                const item = getNdLineItem(line);
                return (
                  <div key={idx} className="flex items-center gap-2 bg-bg-inset/40 border border-border rounded-md p-2.5">
                    <div className="flex bg-bg-inset border border-border rounded-md overflow-hidden shrink-0">
                      <button type="button" onClick={() => updateNdLineType(idx, 'product')} className={'px-2.5 py-2 text-[11px] font-medium transition-colors cursor-pointer ' + (line.item_type === 'product' ? 'bg-accent text-white' : 'text-text-muted')}>Produto</button>
                      <button type="button" onClick={() => updateNdLineType(idx, 'service')} className={'px-2.5 py-2 text-[11px] font-medium transition-colors cursor-pointer ' + (line.item_type === 'service' ? 'bg-accent text-white' : 'text-text-muted')}>Servico</button>
                    </div>
                    <div className="flex-1">
                      {line.item_type === 'service' ? (
                        <Select value={line.service_id} onChange={(v) => updateNdLine(idx, 'service_id', v)} options={services.map((s) => ({ value: s.id, label: s.code + ' - ' + s.name }))} placeholder="Selecionar servico" />
                      ) : (
                        <Select value={line.product_id} onChange={(v) => updateNdLine(idx, 'product_id', v)} options={products.map((p) => ({ value: p.id, label: p.code + ' - ' + p.name }))} placeholder="Selecionar produto" />
                      )}
                    </div>
                    <input type="number" step="0.001" min="0" value={line.quantity} onChange={(e) => updateNdLine(idx, 'quantity', e.target.value)} className="w-20 bg-bg-inset border border-border rounded-md px-2.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
                    <div className="w-28 text-right font-mono text-sm text-text-primary">
                      {item ? formatMoney((item.price || 0) * (parseFloat(line.quantity) || 0)) : '-'}
                    </div>
                    <button type="button" onClick={() => removeNdLine(idx)} disabled={ndLines.length === 1} className="text-text-muted hover:text-danger disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer">
                      <Trash2 size={16} />
                    </button>
                  </div>
                );
              })}
              <button type="button" onClick={addNdLine} className="flex items-center gap-1.5 text-accent hover:text-accent-hover text-sm font-medium transition-colors cursor-pointer">
                <Plus size={15} /> Adicionar linha
              </button>
            </div>

            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Referencia</label>
              <input value={ndDocumentReference} disabled className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-muted font-mono outline-none opacity-70 cursor-not-allowed" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Observacoes</label>
              <input value={ndObservations} onChange={(e) => setNdObservations(e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
            </div>

            {ndFormError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{ndFormError}</div>
            )}

            <button
              type="submit"
              disabled={ndSaving || ndLines.some((l) => !getNdLineItem(l) || parseFloat(l.quantity) <= 0)}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              {ndSaving ? <Loader2 size={17} className="animate-spin" /> : <FilePlus size={17} />}
              {ndSaving ? 'A emitir...' : 'Emitir Nota de Debito'}
            </button>
          </form>
        )}
      </Modal>

      <Modal open={rcModalOpen} onClose={() => setRcModalOpen(false)} title="Emitir Recibo" maxWidthClass="max-w-md">
        {detailInvoice && (
          <form onSubmit={handleRcSubmit} className="flex flex-col gap-4">
            <p className="text-[12px] text-text-muted">
              Referente a <span className="font-mono text-text-primary">{INVOICE_TYPE_CODE[detailInvoice.invoice_type] || detailInvoice.invoice_type} {detailInvoice.series}/{detailInvoice.number}</span>
            </p>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Valor recebido *</label>
              <input type="number" step="0.01" min="0.01" value={rcAmount} onChange={(e) => setRcAmount(e.target.value)} required placeholder="0.00" className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{'M\u00e9todo de pagamento'}</label>
              <select value={rcPaymentMethodId} onChange={(e) => setRcPaymentMethodId(e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors">
                <option value="">{'Igual \u00e0 fatura (predefini\u00e7\u00e3o)'}</option>
                {paymentMethods.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Referencia</label>
              <input value={rcDocumentReference} disabled className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-muted font-mono outline-none opacity-70 cursor-not-allowed" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Observacoes</label>
              <input value={rcObservations} onChange={(e) => setRcObservations(e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
            </div>
            {rcFormError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{rcFormError}</div>
            )}
            <button
              type="submit"
              disabled={rcSaving || !rcAmount || parseFloat(rcAmount) <= 0}
              className="bg-success hover:opacity-90 disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              {rcSaving ? <Loader2 size={17} className="animate-spin" /> : <Receipt size={17} />}
              {rcSaving ? 'A emitir...' : 'Emitir Recibo'}
            </button>
          </form>
        )}
      </Modal>

      <Modal open={convertModalOpen} onClose={() => setConvertModalOpen(false)} title="Converter Pro-forma" maxWidthClass="max-w-md">
        {detailInvoice && (
          <form onSubmit={handleConvertSubmit} className="flex flex-col gap-4">
            <p className="text-[12px] text-text-muted">
              A converter <span className="font-mono text-text-primary">FP {detailInvoice.series}/{detailInvoice.number}</span> numa fatura real - o stock sera deduzido e o documento sera submetido a AGT.
            </p>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Converter para</label>
              <Select value={convertTargetType} onChange={setConvertTargetType} options={convertibleTypes} />
            </div>
            {convertFormError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{convertFormError}</div>
            )}
            <button
              type="submit"
              disabled={convertSaving}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              {convertSaving ? <Loader2 size={17} className="animate-spin" /> : <FileText size={17} />}
              {convertSaving ? 'A converter...' : 'Converter'}
            </button>
          </form>
        )}
      </Modal>

      <Modal open={ncModalOpen} onClose={() => setNcModalOpen(false)} title="Emitir Nota de Credito" maxWidthClass="max-w-2xl">
        {detailInvoice && (
          <form onSubmit={handleNcSubmit} className="flex flex-col gap-4">
            <p className="text-[12px] text-text-muted">
              Referente a <span className="font-mono text-text-primary">{INVOICE_TYPE_CODE[detailInvoice.invoice_type] || detailInvoice.invoice_type} {detailInvoice.series}/{detailInvoice.number}</span>
            </p>

            <div className="flex flex-col gap-2 max-h-[280px] overflow-y-auto scrollbar-thin">
              {ncLines.map((l) => (
                <div key={l.invoice_line_id} className="flex items-center gap-3 border border-border rounded-md px-3.5 py-2.5">
                  <input type="checkbox" checked={l.selected} onChange={() => toggleNcLineSelected(l.invoice_line_id)} className="w-4 h-4 accent-accent cursor-pointer shrink-0" />
                  <span className="flex-1 text-sm text-text-primary truncate">{l.product_name}</span>
                  <input
                    type="number"
                    step="0.001"
                    min="0"
                    max={l.original_quantity}
                    disabled={!l.selected}
                    value={l.quantity}
                    onChange={(e) => updateNcLineQuantity(l.invoice_line_id, e.target.value)}
                    className="w-24 bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent disabled:opacity-50 transition-colors"
                  />
                  <span className="text-[11px] text-text-muted shrink-0">/ {l.original_quantity}</span>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Motivo *</label>
                <Select value={ncReason} onChange={setNcReason} options={[{ value: 'ANL', label: 'Anulacao' }, { value: 'RTF', label: 'Rectificacao' }]} />
              </div>
              <div>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Causa * (max. 60 caracteres)</label>
                <input value={ncCause} onChange={(e) => setNcCause(e.target.value)} maxLength={60} required placeholder="Ex: Cliente desistiu da compra" className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
              </div>
            </div>

            {ncFormError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{ncFormError}</div>
            )}

            <button
              type="submit"
              disabled={ncSaving || !ncCause}
              className="bg-danger hover:opacity-90 disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              {ncSaving ? <Loader2 size={17} className="animate-spin" /> : <RotateCcw size={17} />}
              {ncSaving ? 'A emitir...' : 'Emitir Nota de Credito'}
            </button>
          </form>
        )}
      </Modal>

      {pdfModalOpen && (
        <div className="fixed inset-0 z-[1000] bg-black/80 flex items-center justify-center p-4">
          <div className="w-full max-w-[1000px] h-full max-h-[90vh] overflow-hidden bg-bg-surface rounded-lg shadow-2xl flex flex-col scrollbar-thin">
            <iframe src={pdfBlobUrl} title="Pre-visualizacao do documento" className="flex-1 w-full border-none rounded-t-lg" />
            <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-bg-elevated rounded-b-lg">
              <button
                type="button"
                onClick={closePdfViewer}
                className="flex items-center gap-1.5 text-text-primary hover:text-danger text-sm font-medium px-4 py-2 rounded-md border border-border hover:border-danger transition-colors cursor-pointer"
              >
                <XIcon size={15} /> Fechar
              </button>
              <button
                type="button"
                onClick={downloadPdf}
                className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-sm font-medium px-4 py-2 rounded-md transition-colors cursor-pointer"
              >
                Guardar
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}









