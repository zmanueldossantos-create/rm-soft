import { useState, useEffect, useRef, Fragment } from 'react';
import { useCan } from '../utils/permissions';
import { listDenominations, recordDenominationCount, getLatestDenominationCount } from '../api/moedeiro';
import { listProductCategories } from '../api/productCategories';
import { listServices } from '../api/services';
import { listVatRates } from '../api/vat';
import { withholdingTaxesApi, paymentTermsApi } from '../api/catalogs';
import { getMyCompanyBankAccounts } from '../api/company';
import { createProFormaFromPos } from '../api/pos';
import { listPaymentMethodPreferences } from '../api/tesouraria';
import { Wallet, Plus, Minus, Trash2, Loader2, Search, X, ShoppingCart, LogOut, CheckCircle2, FileSearch, ArrowLeftRight, Link2, Unlink, Coins, Receipt, Printer, FileText } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import { listActivities, listPointsOfSale } from '../api/activity';
import { createCustomer } from '../api/customers';
import { listProducts } from '../api/products';
import { listCustomers } from '../api/customers';
import { openCashSession, getOpenCashSession, closeCashSession, checkout, liquidatePendingInvoice, getCurrentCashBalance, getCarryForwardAmount, getPosStockLevels } from '../api/pos';
import { listPendingProFormas, listRecentIssuedInvoices, fetchInvoicePdfBlob } from '../api/invoices';
import { listPendingReceptions, receiveCashMovement, listPendingEmissions, cancelCashMovement, getDailyReport } from '../api/tesouraria';
import DocumentActionModals from '../components/DocumentActionModals';
import {
  getMyCashPointAssociation, listCashPointAssociations, assignUserToCashPoint, unassignUserFromCashPoint,
  createCashMovement, listCashMovementReasons, listCashMovements,
} from '../api/tesouraria';
import { listUsers } from '../api/users';
import { useAuthStore } from '../store/authStore';
import { extractErrorMessage } from '../utils/errors';

function addDays(dateStr, days) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function formatKz(value) {
  return Number(value).toLocaleString('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function Caixa() {
  const can = useCan();
  const currentUser = useAuthStore((state) => state.user);
  const isGestor = currentUser?.role === 'GESTOR';
  const documentActionsRef = useRef(null);

  const [pointsOfSale, setPointsOfSale] = useState([]);
  const [allActivePos, setAllActivePos] = useState([]);
  const [myAssociation, setMyAssociation] = useState(null);
  const [associationChecked, setAssociationChecked] = useState(false);
  const [selectedPosId, setSelectedPosId] = useState('');

  const [categories, setCategories] = useState([]);
  const [services, setServices] = useState([]);
  const [vatRates, setVatRates] = useState([]);
  const [withholdingTaxes, setWithholdingTaxes] = useState([]);
  const [activeCategoryId, setActiveCategoryId] = useState('all');
  const [customersModalOpen, setCustomersModalOpen] = useState(false);
  const [customerSearchQuery, setCustomerSearchQuery] = useState('');
  const [newCustomerModalOpen, setNewCustomerModalOpen] = useState(false);
  const [newCustomerForm, setNewCustomerForm] = useState({ name: '', nif: '', phone_number: '', email: '' });
  const [newCustomerSaving, setNewCustomerSaving] = useState(false);
  const [newCustomerError, setNewCustomerError] = useState('');
  const [articlesModalOpen, setArticlesModalOpen] = useState(false);
  const [articleSearchQuery, setArticleSearchQuery] = useState('');

  const [moedeiroModalOpen, setMoedeiroModalOpen] = useState(false);
  const [moedeiroCountType, setMoedeiroCountType] = useState('ABERTURA');
  const [denominations, setDenominations] = useState([]);
  const [denominationQuantities, setDenominationQuantities] = useState({});
  const [moedeiroSaving, setMoedeiroSaving] = useState(false);
  const [moedeiroError, setMoedeiroError] = useState('');
  const [moedeiroSavedTotal, setMoedeiroSavedTotal] = useState(null);

  const [movementModalOpen, setMovementModalOpen] = useState(false);
  const [movementForm, setMovementForm] = useState({ movementType: 'TRANSFERENCIA', amount: '', otherPosId: '', reasonId: '', description: '' });
  const [movementReasons, setMovementReasons] = useState([]);
  const [movementSaving, setMovementSaving] = useState(false);
  const [movementFormError, setMovementFormError] = useState('');
  const [movementHistory, setMovementHistory] = useState([]);
  const [movementHistoryLoading, setMovementHistoryLoading] = useState(false);
  const [pendingReceptions, setPendingReceptions] = useState([]);
  const [pendingReceptionsLoading, setPendingReceptionsLoading] = useState(false);
  const [receivingId, setReceivingId] = useState(null);
  const [pendingEmissions, setPendingEmissions] = useState([]);
  const [pendingEmissionsLoading, setPendingEmissionsLoading] = useState(false);
  const [cancellingId, setCancellingId] = useState(null);
  const [movementModalTab, setMovementModalTab] = useState('form');
  const [currentBalance, setCurrentBalance] = useState(null);
  const [carryForwardAmount, setCarryForwardAmount] = useState(0);
  const [carryForwardLoading, setCarryForwardLoading] = useState(false);
  const [stockLevels, setStockLevels] = useState({});
  const [dailyReportModalOpen, setDailyReportModalOpen] = useState(false);
  const [dailyReportEntries, setDailyReportEntries] = useState([]);
  const [dailyReportLoading, setDailyReportLoading] = useState(false);
  const [dailyReportDateFrom, setDailyReportDateFrom] = useState('');
  const [dailyReportDateTo, setDailyReportDateTo] = useState('');
  const [closingViaBilletage, setClosingViaBilletage] = useState(false);

  const [posHolder, setPosHolder] = useState(null);
  const [assignableUsers, setAssignableUsers] = useState([]);
  const [assignSelection, setAssignSelection] = useState('');
  const [assignSaving, setAssignSaving] = useState(false);
  const [assignError, setAssignError] = useState('');
  const [associationModalOpen, setAssociationModalOpen] = useState(false);
  const [session, setSession] = useState(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [error, setError] = useState('');

  const [products, setProducts] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [cart, setCart] = useState([]);
  const [productSearch, setProductSearch] = useState('');
  const [selectedCustomerId, setSelectedCustomerId] = useState('');

  const [openModalOpen, setOpenModalOpen] = useState(false);
  const [openingAmount, setOpeningAmount] = useState('');
  const [openSaving, setOpenSaving] = useState(false);
  const [openError, setOpenError] = useState('');

  const [closeModalOpen, setCloseModalOpen] = useState(false);
  const [closingAmountCounted, setClosingAmountCounted] = useState('');
  const [closingNotes, setClosingNotes] = useState('');
  const [closeSaving, setCloseSaving] = useState(false);
  const [closeError, setCloseError] = useState('');
  const [closeResult, setCloseResult] = useState(null);

  const [paymentModalOpen, setPaymentModalOpen] = useState(false);
  const [payments, setPayments] = useState([{ paymentMethod: 'NUMERARIO', amount: '' }]);
  const [checkoutSaving, setCheckoutSaving] = useState(false);
  const [checkoutError, setCheckoutError] = useState('');
  const [lastInvoice, setLastInvoice] = useState(null);

  const [proFormaModalOpen, setProFormaModalOpen] = useState(false);
  const [pendingProFormas, setPendingProFormas] = useState([]);
  const [proFormaLoading, setProFormaLoading] = useState(false);
  const [proFormaError, setProFormaError] = useState('');
  const [recentInvoices, setRecentInvoices] = useState([]);
  const [recentInvoicesLoading, setRecentInvoicesLoading] = useState(false);
  const [pdfModalOpen, setPdfModalOpen] = useState(false);
  const [pdfBlobUrl, setPdfBlobUrl] = useState('');
  const [pdfFilename, setPdfFilename] = useState('');

  const [paymentMode, setPaymentMode] = useState('sale');
  const [liquidationTarget, setLiquidationTarget] = useState(null);
  const [liquidationTargetType, setLiquidationTargetType] = useState('FACTURA_RECIBO');

  async function loadInitial() {
    setSessionLoading(true);
    setError('');
    try {
      const [activitiesData, productsData, customersData, association] = await Promise.all([
        listActivities(), listProducts(), listCustomers(), getMyCashPointAssociation(),
      ]);
      const activeActivities = activitiesData.filter((a) => a.is_active);
      const posLists = await Promise.all(activeActivities.map((a) => listPointsOfSale(a.id)));
      const activityNameById = Object.fromEntries(activeActivities.map((a) => [a.id, a.name]));
      const activePos = posLists.flat().filter((p) => p.is_active).map((p) => ({
        ...p, activityName: activityNameById[p.activity_id],
      }));
      setAllActivePos(activePos);
      setMyAssociation(association);
      setAssociationChecked(true);

      // GESTOR sees/picks any POS, same as before. Any other role is locked to their
      // own associated POS - no picker, no access to other cash points at all.
      const availablePos = isGestor ? activePos : activePos.filter((p) => p.id === association?.pos_id);
      setPointsOfSale(availablePos);

      setProducts(productsData.filter((p) => p.is_active && !p.is_raw_material && !p.not_available_pos && !p.internal_use_only));
      const [categoriesData, servicesData, vatData, withholdingData, termsData, methodsData, bankData] = await Promise.all([
        listProductCategories(), listServices(), listVatRates(), withholdingTaxesApi.list(),
        paymentTermsApi.list(), listPaymentMethodPreferences(), getMyCompanyBankAccounts(),
      ]);
      setCategories(categoriesData.filter((c) => c.is_active));
      setServices(servicesData.filter((s) => s.is_active));
      setVatRates(vatData);
      setWithholdingTaxes(withholdingData);
      setPaymentTerms(termsData.filter((t) => t.is_active));
      setPaymentMethods(methodsData);
      setBankAccounts(bankData.filter((b) => b.is_active));
      setCustomers(customersData.filter((c) => c.is_active));
      const associatedPosStillActive = association?.pos_id && availablePos.some((p) => p.id === association.pos_id);
      const initialPosId = associatedPosStillActive ? association.pos_id : (availablePos[0]?.id || '');
      setSelectedPosId(initialPosId);
      if (initialPosId) {
        const openSession = await getOpenCashSession(initialPosId);
        setSession(openSession);
        if (isGestor) await loadPosHolder(initialPosId);
        if (openSession) await refreshBalance(initialPosId);
        getPosStockLevels(initialPosId).then(setStockLevels).catch(() => setStockLevels({}));
      }
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar caixa'));
    } finally {
      setSessionLoading(false);
    }
  }

  useEffect(() => {
    loadInitial();
  }, []);

  async function openMoedeiroModal(countType) {
    const resolvedType = countType || 'ABERTURA';
    setMoedeiroCountType(resolvedType);
    setMoedeiroError('');
    setMoedeiroSavedTotal(null);
    setMoedeiroModalOpen(true);
    // Ensure the target balance (see moedeiroTarget) is available regardless of
    // which entry point opened this modal - the "Moedeiro" card jumps straight
    // here without going through openCloseModal/handlePosChange first.
    if (resolvedType === 'ABERTURA') {
      getCarryForwardAmount(selectedPosId).then(setCarryForwardAmount).catch(() => setCarryForwardAmount(0));
    } else {
      refreshBalance(selectedPosId);
    }
    try {
      const data = await listDenominations();
      setDenominations(data);
      const initialQuantities = Object.fromEntries(data.map((d) => [d.id, '']));
      setDenominationQuantities(initialQuantities);
    } catch (err) {
      setMoedeiroError(extractErrorMessage(err, 'Erro ao carregar denominacoes'));
    }
  }

  function updateDenominationQuantity(denominationId, value) {
    setDenominationQuantities((prev) => ({ ...prev, [denominationId]: value }));
  }

  const moedeiroTotal = denominations.reduce((sum, d) => {
    const qty = parseInt(denominationQuantities[d.id] || '0', 10);
    return sum + qty * Number(d.value);
  }, 0);
  // Target the count must match: the carried-over float for ABERTURA (before the
  // session even has sales), or the live expected balance for FECHO (see
  // get_current_expected_cash_balance) - matching exactly is required to submit,
  // per the "button only activates when the breakdown matches" requirement.
  const moedeiroTarget = moedeiroCountType === 'ABERTURA' ? carryForwardAmount : currentBalance;
  const moedeiroMatches = moedeiroTarget !== null && Math.abs(moedeiroTotal - moedeiroTarget) < 0.01;

  async function handleMoedeiroSubmit() {
    if (!session) return;
    setMoedeiroSaving(true);
    setMoedeiroError('');
    try {
      const lines = denominations
        .map((d) => ({ denominationId: d.id, quantity: parseInt(denominationQuantities[d.id] || '0', 10) }))
        .filter((l) => l.quantity > 0);
      const result = await recordDenominationCount(session.id, moedeiroCountType, lines);
      setMoedeiroSavedTotal(result.total);
    } catch (err) {
      setMoedeiroError(extractErrorMessage(err, 'Erro ao registar contagem'));
    } finally {
      setMoedeiroSaving(false);
    }
  }

  function openNewCustomerModal() {
    setNewCustomerForm({ name: '', nif: '', phone_number: '', email: '' });
    setNewCustomerError('');
    setNewCustomerModalOpen(true);
  }

  async function handleNewCustomerSubmit(e) {
    e.preventDefault();
    setNewCustomerError('');
    setNewCustomerSaving(true);
    try {
      const customer = await createCustomer(newCustomerForm);
      setCustomers((prev) => [...prev, customer]);
      setSelectedCustomerId(customer.id);
      setNewCustomerModalOpen(false);
    } catch (err) {
      setNewCustomerError(extractErrorMessage(err, 'Erro ao criar cliente'));
    } finally {
      setNewCustomerSaving(false);
    }
  }

  async function loadPosHolder(posId) {
    if (!isGestor || !posId) { setPosHolder(null); return; }
    try {
      const [usersData, associationsData] = await Promise.all([listUsers(), listCashPointAssociations()]);
      setAssignableUsers(usersData);
      const holderAccess = associationsData.find((a) => a.pos_id === posId);
      const holderUser = holderAccess ? usersData.find((u) => u.id === holderAccess.user_id) : null;
      setPosHolder(holderUser || null);
    } catch (err) {
      setAssignError(extractErrorMessage(err, 'Erro ao carregar associacao da caixa'));
    }
  }

  async function handleAssignPos() {
    if (!assignSelection || !selectedPosId) return;
    setAssignSaving(true);
    setAssignError('');
    try {
      await assignUserToCashPoint(assignSelection, selectedPosId);
      setAssignSelection('');
      await loadPosHolder(selectedPosId);
    } catch (err) {
      setAssignError(extractErrorMessage(err, 'Erro ao associar caixa'));
    } finally {
      setAssignSaving(false);
    }
  }

  async function handleUnassignPos() {
    if (!posHolder) return;
    setAssignSaving(true);
    setAssignError('');
    try {
      await unassignUserFromCashPoint(posHolder.id);
      await loadPosHolder(selectedPosId);
    } catch (err) {
      setAssignError(extractErrorMessage(err, 'Erro ao desassociar caixa'));
    } finally {
      setAssignSaving(false);
    }
  }

  function openMovementModal() {
    setMovementForm({ movementType: 'TRANSFERENCIA', amount: '', otherPosId: '', reasonId: '', description: '' });
    setMovementFormError('');
    setMovementModalOpen(true);
    setMovementModalTab('form');
    listCashMovementReasons().then(setMovementReasons).catch(() => {});
    loadPendingReceptionsList();
    loadPendingEmissionsList();
  }

  async function loadPendingReceptionsList() {
    if (!selectedPosId) return;
    setPendingReceptionsLoading(true);
    try {
      setPendingReceptions(await listPendingReceptions(selectedPosId));
    } catch (err) {
      // silent - supplementary section
    } finally {
      setPendingReceptionsLoading(false);
    }
  }

  async function loadPendingEmissionsList() {
    if (!selectedPosId) return;
    setPendingEmissionsLoading(true);
    try {
      setPendingEmissions(await listPendingEmissions(selectedPosId));
    } catch (err) {
      // silent - supplementary section
    } finally {
      setPendingEmissionsLoading(false);
    }
  }

  async function handleReceiveMovement(movementId) {
    setReceivingId(movementId);
    try {
      await receiveCashMovement(movementId, selectedPosId);
      await loadPendingReceptionsList();
      refreshBalance(selectedPosId);
      getPosStockLevels(selectedPosId).then(setStockLevels).catch(() => {});
    } catch (err) {
      setMovementFormError(extractErrorMessage(err, 'Erro ao confirmar recepcao'));
    } finally {
      setReceivingId(null);
    }
  }

  async function handleCancelMovement(movementId) {
    setCancellingId(movementId);
    try {
      await cancelCashMovement(movementId, selectedPosId);
      await loadPendingEmissionsList();
      refreshBalance(selectedPosId);
      getPosStockLevels(selectedPosId).then(setStockLevels).catch(() => {});
    } catch (err) {
      setMovementFormError(extractErrorMessage(err, 'Erro ao cancelar transferencia'));
    } finally {
      setCancellingId(null);
    }
  }

  async function loadMovementHistory() {
    if (!selectedPosId) return;
    setMovementHistoryLoading(true);
    try {
      const data = await listCashMovements({ posId: selectedPosId });
      setMovementHistory(data);
    } catch (err) {
      // silent - history is supplementary, not critical to the form itself
    } finally {
      setMovementHistoryLoading(false);
    }
  }

  async function handleMovementSubmit(e) {
    e.preventDefault();
    setMovementFormError('');
    setMovementSaving(true);
    try {
      const payload = {
        movement_type: movementForm.movementType,
        amount: parseFloat(movementForm.amount || '0'),
        reason_id: movementForm.reasonId || null,
        description: movementForm.description || null,
      };
      if (movementForm.movementType === 'TRANSFERENCIA') {
        payload.source_pos_id = selectedPosId;
        payload.destination_pos_id = movementForm.otherPosId;
      } else if (movementForm.movementType === 'ENTRADA_EXTERNA') {
        payload.destination_pos_id = selectedPosId;
      } else {
        payload.source_pos_id = selectedPosId;
      }
      await createCashMovement(payload);
      refreshBalance(selectedPosId);
      getPosStockLevels(selectedPosId).then(setStockLevels).catch(() => {});
      loadPendingEmissionsList();
      loadPendingReceptionsList();
      setMovementForm({ movementType: 'TRANSFERENCIA', amount: '', otherPosId: '', reasonId: '', description: '' });
    } catch (err) {
      setMovementFormError(extractErrorMessage(err, 'Erro ao registar movimento'));
    } finally {
      setMovementSaving(false);
    }
  }

  function openDailyReportModal() {
    // Default to the OPEN SESSION's business_date (the accounting day), not the
    // real calendar date - a session opened yesterday and never closed still
    // records today's sales under yesterday's business_date (see discussion on
    // the "sale made today doesn't show in the report" confusion). Falls back to
    // the real calendar date when there's no open session.
    const defaultDate = session ? session.business_date : new Date().toISOString().slice(0, 10);
    setDailyReportDateFrom(defaultDate);
    setDailyReportDateTo(defaultDate);
    setDailyReportModalOpen(true);
    loadDailyReport(defaultDate, defaultDate);
  }

  async function loadDailyReport(dateFrom, dateTo) {
    setDailyReportLoading(true);
    try {
      setDailyReportEntries(await getDailyReport(selectedPosId, dateFrom, dateTo));
    } catch (err) {
      setDailyReportEntries([]);
    } finally {
      setDailyReportLoading(false);
    }
  }

  async function refreshBalance(posId) {
    if (!posId) return;
    try {
      setCurrentBalance(await getCurrentCashBalance(posId));
    } catch (err) {
      // silent - supplementary display, not critical path
    }
  }

  async function handlePosChange(posId) {
    setSelectedPosId(posId);
    setCart([]);
    setSessionLoading(true);
    try {
      const openSession = await getOpenCashSession(posId);
      setSession(openSession);
      await loadPosHolder(posId);
      if (openSession) await refreshBalance(posId);
      else setCurrentBalance(null);
      getPosStockLevels(posId).then(setStockLevels).catch(() => setStockLevels({}));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar sessão de caixa'));
    } finally {
      setSessionLoading(false);
    }
  }

  async function openOpenModal() {
    setOpenError('');
    setOpenModalOpen(true);
    setCarryForwardLoading(true);
    try {
      setCarryForwardAmount(await getCarryForwardAmount(selectedPosId));
    } catch (err) {
      setCarryForwardAmount(0);
    } finally {
      setCarryForwardLoading(false);
    }
  }

  async function handleOpenSession(e) {
    e.preventDefault();
    setOpenError('');
    setOpenSaving(true);
    try {
      const newSession = await openCashSession(selectedPosId);
      setSession(newSession);
      setOpenModalOpen(false);
      refreshBalance(selectedPosId);
      getPosStockLevels(selectedPosId).then(setStockLevels).catch(() => {});
    } catch (err) {
      setOpenError(extractErrorMessage(err, 'Erro ao abrir caixa'));
    } finally {
      setOpenSaving(false);
    }
  }

  function openCloseModal() {
    // A POS with billetage_enabled must count its drawer by denomination before
    // closing (see cash_session_service.close_session's BilletageRequiredError) -
    // rather than let the cashier discover this only after a failed manual close,
    // go straight to the Moedeiro FECHO count and finish closing from there
    // (see handleCloseAfterBilletage) - see discussion on presenting billetage
    // proactively at close time.
    const selectedPos = allActivePos.find((p) => p.id === selectedPosId);
    if (selectedPos?.billetage_enabled) {
      setClosingViaBilletage(true);
      setClosingNotes('');
      setCloseError('');
      setCloseResult(null);
      openMoedeiroModal('FECHO');
      return;
    }
    setClosingViaBilletage(false);
    setClosingAmountCounted('');
    setClosingNotes('');
    setCloseError('');
    setCloseResult(null);
    setCloseModalOpen(true);
  }

  async function handleCloseAfterBilletage() {
    setCloseSaving(true);
    setMoedeiroError('');
    try {
      const closed = await closeCashSession(session.id, null, closingNotes);
      setMoedeiroModalOpen(false);
      setCloseResult(closed);
      setCloseModalOpen(true);
    } catch (err) {
      setMoedeiroError(extractErrorMessage(err, 'Erro ao fechar caixa'));
    } finally {
      setCloseSaving(false);
    }
  }

  async function handleCloseSession(e) {
    e.preventDefault();
    setCloseError('');
    setCloseSaving(true);
    try {
      const closed = await closeCashSession(session.id, parseFloat(closingAmountCounted || '0'), closingNotes);
      setCloseResult(closed);
    } catch (err) {
      setCloseError(extractErrorMessage(err, 'Erro ao fechar caixa'));
    } finally {
      setCloseSaving(false);
    }
  }

  function finishClosing() {
    setCloseModalOpen(false);
    setSession(null);
    setCart([]);
  }

  const filteredProducts = products.filter((p) => {
    if (activeCategoryId !== 'all' && activeCategoryId !== 'services' && p.category_id !== activeCategoryId) return false;
    if (!productSearch.trim()) return true;
    const q = productSearch.toLowerCase();
    return p.code.toLowerCase().includes(q) || p.name.toLowerCase().includes(q);
  });

  const filteredServices = services.filter((s) => {
    if (!productSearch.trim()) return true;
    const q = productSearch.toLowerCase();
    return (s.code || '').toLowerCase().includes(q) || s.name.toLowerCase().includes(q);
  });

  function imageUrl(path) {
    return path ? 'http://127.0.0.1:8001' + path : null;
  }

  function addToCart(item, isService = false) {
    if (isService && (item.price === null || item.price === undefined)) {
      setError('Este servico nao tem preco definido - configure um preco antes de o vender');
      return;
    }
    const itemKey = (isService ? 'service:' : 'product:') + item.id;
    setCart((prev) => {
      const existing = prev.find((line) => line.key === itemKey);
      if (existing) {
        return prev.map((line) => (line.key === itemKey ? { ...line, quantity: line.quantity + 1 } : line));
      }
      return [...prev, {
        key: itemKey,
        productId: isService ? null : item.id,
        serviceId: isService ? item.id : null,
        code: item.code,
        name: item.name,
        price: item.price,
        quantity: 1,
        discountPercent: 0,
        vatId: item.vat_id,
        withholdingTaxId: isService ? item.withholding_tax_id : null,
        unit: isService ? 'Un' : (item.is_sold_by_weight ? 'Kg' : 'Un'),
      }];
    });
  }

  function updateCartQuantity(key, quantity) {
    if (quantity <= 0) {
      setCart((prev) => prev.filter((line) => line.key !== key));
      return;
    }
    setCart((prev) => prev.map((line) => (line.key === key ? { ...line, quantity } : line)));
  }

  function updateCartDiscount(key, discountPercent) {
    setCart((prev) => prev.map((line) => (line.key === key ? { ...line, discountPercent: parseFloat(discountPercent) || 0 } : line)));
  }

  function removeFromCart(key) {
    setCart((prev) => prev.filter((line) => line.key !== key));
  }

  const [globalDiscountPercent, setGlobalDiscountPercent] = useState(0);
  const [expandedDiscountKey, setExpandedDiscountKey] = useState(null);
  const [saleConfirmModalOpen, setSaleConfirmModalOpen] = useState(false);
  const [selectedInvoiceType, setSelectedInvoiceType] = useState('FACTURA_RECIBO');
  const [paymentTerms, setPaymentTerms] = useState([]);
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [ftPaymentTermId, setFtPaymentTermId] = useState('');
  const [ftPaymentMethodId, setFtPaymentMethodId] = useState('');
  const [ftBankAccountId, setFtBankAccountId] = useState('');
  const [ftDueDate, setFtDueDate] = useState('');
  const [proFormaSaving, setProFormaSaving] = useState(false);
  const [ftModalOpen, setFtModalOpen] = useState(false);
  const [successModalOpen, setSuccessModalOpen] = useState(false);

  const isCustomerPessoaColetiva = customers.find((c) => c.id === selectedCustomerId)?.legal_person_type === 'JURIDICA';

  const cartCalculation = cart.reduce((acc, line) => {
    const vatRate = vatRates.find((v) => v.id === line.vatId)?.rate || 0;
    const grossLine = line.price * line.quantity;
    const lineDiscountAmount = grossLine * (line.discountPercent / 100);
    const lineSubtotal = grossLine - lineDiscountAmount;
    const lineVat = lineSubtotal * (vatRate / 100);

    let lineRetention = 0;
    if (line.serviceId && line.withholdingTaxId && isCustomerPessoaColetiva) {
      const whRate = withholdingTaxes.find((w) => w.id === line.withholdingTaxId)?.rate || 0;
      lineRetention = lineSubtotal * (whRate / 100);
    }

    acc.subtotal += lineSubtotal;
    acc.vat += lineVat;
    acc.retention += lineRetention;
    return acc;
  }, { subtotal: 0, vat: 0, retention: 0 });

  const grossTotal = cartCalculation.subtotal + cartCalculation.vat;
  const globalDiscountAmount = grossTotal * (globalDiscountPercent / 100);
  const cartTotal = round2(grossTotal - globalDiscountAmount - cartCalculation.retention);
  const paymentDueTotal = paymentMode === 'liquidation' && liquidationTarget ? Number(liquidationTarget.total) : cartTotal;

  async function handleConfirmFt() {
    setCheckoutError('');
    setCheckoutSaving(true);
    try {
      const invoice = await checkout(
        selectedPosId, selectedCustomerId || null,
        cart,
        [],
        'FACTURA',
        globalDiscountPercent,
        { paymentTermId: ftPaymentTermId || null, dueDate: ftDueDate || null },
      );
      setLastInvoice(invoice);
      setSuccessModalOpen(true);
      refreshBalance(selectedPosId);
      getPosStockLevels(selectedPosId).then(setStockLevels).catch(() => {});
      setCart([]);
      setSelectedCustomerId('');
      setGlobalDiscountPercent(0);
      setFtModalOpen(false);
    } catch (err) {
      setCheckoutError(extractErrorMessage(err, 'Erro ao faturar'));
    } finally {
      setCheckoutSaving(false);
    }
  }

  async function handleCreateProForma() {
    setError('');
    setProFormaSaving(true);
    try {
      const proForma = await createProFormaFromPos(selectedPosId, selectedCustomerId || null, cart, globalDiscountPercent);
      setLastInvoice(proForma);
      setSuccessModalOpen(true);
      refreshBalance(selectedPosId);
      getPosStockLevels(selectedPosId).then(setStockLevels).catch(() => {});
      setCart([]);
      setSelectedCustomerId('');
      setGlobalDiscountPercent(0);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao gerar pro-forma'));
    } finally {
      setProFormaSaving(false);
    }
  }

  async function openProFormaSearchModal() {
    setProFormaError('');
    setProFormaModalOpen(true);
    setProFormaLoading(true);
    setRecentInvoicesLoading(true);
    try {
      const data = await listPendingProFormas();
      setPendingProFormas(data);
    } catch (err) {
      setProFormaError(extractErrorMessage(err, 'Erro ao carregar pro-formas pendentes'));
    } finally {
      setProFormaLoading(false);
    }
    try {
      setRecentInvoices(await listRecentIssuedInvoices());
    } catch (err) {
      // silent - the pro-forma section above already reports errors; this is a supplementary list
    } finally {
      setRecentInvoicesLoading(false);
    }
  }

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

  function selectProFormaToLiquidate(proForma) {
    setProFormaModalOpen(false);
    setPaymentMode('liquidation');
    setLiquidationTarget(proForma);
    setLiquidationTargetType('FACTURA_RECIBO');
    setPayments([{ paymentMethod: 'NUMERARIO', amount: String(Number(proForma.total).toFixed(2)) }]);
    setCheckoutError('');
    setLastInvoice(null);
    setPaymentModalOpen(true);
  }

  function closeLiquidationModal() {
    setPaymentModalOpen(false);
    setPayments([]);
    setLiquidationTarget(null);
    setPaymentMode('sale');
  }

  const posPaymentMethods = paymentMethods.filter((m) => m.available_at_pos && m.allows_receipt);

  function togglePaymentMethod(paymentMethodId) {
    setPayments((prev) => {
      const exists = prev.find((p) => p.paymentMethodId === paymentMethodId);
      if (exists) return prev.filter((p) => p.paymentMethodId !== paymentMethodId);
      return [...prev, { paymentMethodId, amount: '' }];
    });
  }

  function updatePaymentAmount(paymentMethodId, amount) {
    setPayments((prev) => prev.map((p) => (p.paymentMethodId === paymentMethodId ? { ...p, amount } : p)));
  }

  const paymentsTotal = payments.reduce((sum, p) => sum + (parseFloat(p.amount) || 0), 0);
  const paymentsRemaining = round2(paymentDueTotal - paymentsTotal);

  function round2(n) {
    return Math.round(n * 100) / 100;
  }

  async function handleConfirmSale() {
    setCheckoutError('');
    setCheckoutSaving(true);
    try {
      const validPayments = payments.filter((p) => parseFloat(p.amount) > 0);
      if (paymentMode === 'liquidation') {
        const invoice = await liquidatePendingInvoice(selectedPosId, liquidationTarget.id, liquidationTargetType, validPayments);
        setLastInvoice(invoice);
        setSuccessModalOpen(true);
      refreshBalance(selectedPosId);
      getPosStockLevels(selectedPosId).then(setStockLevels).catch(() => {});
      } else {
        const invoice = await checkout(
          selectedPosId, selectedCustomerId || null,
          cart,
          validPayments,
          selectedInvoiceType,
          globalDiscountPercent,
        );
        setLastInvoice(invoice);
        setSuccessModalOpen(true);
      refreshBalance(selectedPosId);
      getPosStockLevels(selectedPosId).then(setStockLevels).catch(() => {});
        setCart([]);
        setSelectedCustomerId('');
        setGlobalDiscountPercent(0);
        setPayments([]);
      }
    } catch (err) {
      setCheckoutError(extractErrorMessage(err, paymentMode === 'liquidation' ? 'Erro ao liquidar pro-forma' : 'Erro ao finalizar venda'));
    } finally {
      setCheckoutSaving(false);
    }
  }

  function closePaymentModal() {
    setPaymentModalOpen(false);
    setSuccessModalOpen(false);
    setLastInvoice(null);
    setPayments([]);
  }

  if (associationChecked && !isGestor && pointsOfSale.length === 0) {
    return (
      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <Wallet size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium mb-1">Nenhuma caixa associada</p>
          <p className="text-text-muted text-sm">Contacte o gestor para associar uma caixa a este utilizador antes de operar</p>
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
          <Wallet size={22} className="text-accent" />
          Caixa
        </h2>
        <div className="flex items-center gap-2 flex-wrap">
          {session && currentBalance !== null && (
            <div className="flex items-center gap-2 bg-bg-elevated border border-border rounded-md px-4 py-2">
              <Wallet size={15} className="text-accent" />
              <span className="text-text-muted text-[12px]">Saldo actual</span>
              <span className="font-mono font-semibold text-text-primary text-[15px]">{formatKz(currentBalance)} Kz</span>
            </div>
          )}
          {isGestor && (
            <button
              onClick={() => setAssociationModalOpen(true)}
              className="flex items-center gap-2 border border-border hover:border-accent hover:text-accent text-text-primary font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer"
            >
              <Link2 size={15} />
              Associação
            </button>
          )}
          {session && (
            <button
              onClick={openCloseModal}
              disabled={!can('pos:close_session')}
              className="flex items-center gap-2 border border-border hover:border-danger hover:text-danger text-text-primary font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <LogOut size={15} />
              Fechar caixa
            </button>
          )}
          {pointsOfSale.length > 1 && (
            <div className="w-64">
              <Select
                value={selectedPosId}
                onChange={handlePosChange}
                options={pointsOfSale.map((p) => ({ value: p.id, label: p.name + ' - ' + p.activityName }))}
                placeholder="Ponto de venda"
              />
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">
          {error}
        </div>
      )}

      {sessionLoading && (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      )}

      {!sessionLoading && !session && (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <Wallet size={32} className="text-text-muted/40 mx-auto mb-4" />
          <p className="text-text-muted text-sm mb-5">Não há nenhuma sessão de caixa aberta para este ponto de venda</p>
          <button
            onClick={openOpenModal}
            disabled={!selectedPosId || !can('pos:open_session')}
            className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm px-5 py-3 rounded-md transition-colors cursor-pointer"
          >
            <Wallet size={17} />
            Abrir caixa
          </button>
        </div>
      )}

      {!sessionLoading && session && (
        <>
          <p className="text-[12px] text-text-muted font-mono mb-5">
            Sessão aberta às {new Date(session.opened_at).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' })}
          </p>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <div className="lg:col-span-2">
              <div className="relative mb-4">
                <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
                <input
                  type="text"
                  placeholder="Pesquisar produto..."
                  value={productSearch}
                  onChange={(e) => setProductSearch(e.target.value)}
                  className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
                />
              </div>

              <div className="flex items-center gap-2 mb-4 overflow-x-auto scrollbar-thin pb-1">
                <button
                  onClick={() => setActiveCategoryId('all')}
                  className={'shrink-0 px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (activeCategoryId === 'all' ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
                >
                  Todos
                </button>
                {categories.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setActiveCategoryId(c.id)}
                    className={'shrink-0 px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (activeCategoryId === c.id ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
                  >
                    {c.name}
                  </button>
                ))}
                {services.length > 0 && (
                  <button
                    onClick={() => setActiveCategoryId('services')}
                    className={'shrink-0 px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (activeCategoryId === 'services' ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
                  >
                    Servicos
                  </button>
                )}
              </div>

              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2.5 mb-4">
                <button
                  onClick={openProFormaSearchModal}
                  className="flex flex-col items-center justify-center gap-1.5 bg-bg-inset border border-accent/20 hover:border-accent hover:bg-accent/5 rounded-lg py-3.5 text-center transition-colors cursor-pointer"
                >
                  <FileSearch size={18} className="text-accent" />
                  <span className="text-[11px] font-medium text-text-primary leading-tight">Consultar<br />documentos</span>
                </button>
                <button
                  onClick={() => setArticlesModalOpen(true)}
                  className="flex flex-col items-center justify-center gap-1.5 bg-bg-inset border border-accent/20 hover:border-accent hover:bg-accent/5 rounded-lg py-3.5 text-center transition-colors cursor-pointer"
                >
                  <ShoppingCart size={18} className="text-accent" />
                  <span className="text-[11px] font-medium text-text-primary leading-tight">Consultar<br />artigos</span>
                </button>
                <button
                  onClick={() => openMoedeiroModal('ABERTURA')}
                  disabled={!session || !can('moedeiro:record')}
                  className="flex flex-col items-center justify-center gap-1.5 bg-bg-inset border border-accent/20 hover:border-accent hover:bg-accent/5 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg py-3.5 text-center transition-colors cursor-pointer"
                >
                  <Coins size={18} className="text-accent" />
                  <span className="text-[11px] font-medium text-text-primary leading-tight">Moedeiro</span>
                </button>
                <button
                  onClick={openMovementModal}
                  disabled={!selectedPosId || !can('tesouraria:view')}
                  className="flex flex-col items-center justify-center gap-1.5 bg-bg-inset border border-accent/20 hover:border-accent hover:bg-accent/5 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg py-3.5 text-center transition-colors cursor-pointer"
                >
                  <ArrowLeftRight size={18} className="text-accent" />
                  <span className="text-[11px] font-medium text-text-primary leading-tight">Operacoes<br />de Caixa</span>
                </button>
                <button
                  onClick={openDailyReportModal}
                  disabled={!selectedPosId || !can('tesouraria:daily_report')}
                  className="flex flex-col items-center justify-center gap-1.5 bg-bg-inset border border-accent/20 hover:border-accent hover:bg-accent/5 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg py-3.5 text-center transition-colors cursor-pointer"
                >
                  <FileText size={18} className="text-accent" />
                  <span className="text-[11px] font-medium text-text-primary leading-tight">Relatorio<br />do dia</span>
                </button>
                <button
                  onClick={() => { setCart([]); setSelectedCustomerId(''); }}
                  className="flex flex-col items-center justify-center gap-1.5 bg-bg-inset border border-accent/20 hover:border-accent hover:bg-accent/5 rounded-lg py-3.5 text-center transition-colors cursor-pointer"
                >
                  <Plus size={18} className="text-accent" />
                  <span className="text-[11px] font-medium text-text-primary leading-tight">Novo</span>
                </button>
              </div>

              {activeCategoryId === 'services' ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 max-h-[520px] overflow-y-auto scrollbar-thin pr-1">
                  {filteredServices.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => addToCart(s, true)}
                      className="bg-bg-elevated border border-border hover:border-accent rounded-lg p-3.5 text-left transition-colors cursor-pointer"
                    >
                      <p className="font-mono text-[10px] text-text-muted mb-1">{s.code}</p>
                      <p className="font-display font-medium text-[13px] text-text-primary mb-1.5 line-clamp-2">{s.name}</p>
                      <p className="font-mono text-accent text-[13px] font-semibold">{formatKz(s.price)} Kz</p>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 max-h-[520px] overflow-y-auto scrollbar-thin pr-1">
                  {filteredProducts.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => addToCart(p, false)}
                      className="bg-bg-elevated border border-border hover:border-accent rounded-lg overflow-hidden text-left transition-colors cursor-pointer"
                    >
                      <div className="w-full aspect-square bg-bg-inset flex items-center justify-center overflow-hidden">
                        {p.image_path ? (
                          <img src={imageUrl(p.image_path)} alt={p.name} className="w-full h-full object-cover" />
                        ) : (
                          <ShoppingCart size={22} className="text-text-muted" />
                        )}
                      </div>
                      <div className="p-3 relative">
                        <p className="font-mono text-[10px] text-text-muted mb-1">{p.code}</p>
                        <p className="font-display font-medium text-[13px] text-text-primary mb-1.5 line-clamp-2">{p.name}</p>
                        <div className="flex items-end justify-between">
                          <p className="font-mono text-accent text-[13px] font-semibold">{formatKz(p.price)} Kz</p>
                          {p.managed_by_stock && (
                            <span className={'text-[10px] font-mono ' + ((stockLevels[p.id] ?? 0) <= 0 ? 'text-danger' : (stockLevels[p.id] ?? 0) <= (p.min_stock_threshold || 0) ? 'text-accent' : 'text-text-muted')}>
                              {stockLevels[p.id] ?? 0} {p.is_sold_by_weight ? 'Kg' : 'un'}
                            </span>
                          )}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-bg-elevated border border-border rounded-lg p-4 flex flex-col h-fit sticky top-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <ShoppingCart size={16} className="text-accent" />
                  <p className="font-display font-semibold text-text-primary text-sm">Carrinho</p>
                </div>
                <div className="w-44">
                  <Select
                    compact
                    value={selectedInvoiceType}
                    onChange={setSelectedInvoiceType}
                    options={[
                      { value: 'FACTURA_RECIBO', label: 'Fatura/Recibo' },
                      { value: 'FACTURA', label: 'Fatura' },
                      { value: 'PRO_FORMA', label: 'Pro-forma' },
                    ]}
                  />
                </div>
              </div>

              <div className="mb-3 flex items-center gap-2">
                <div className="flex-1">
                  <Select
                    value={selectedCustomerId}
                    onChange={setSelectedCustomerId}
                    options={customers.map((c) => ({ value: c.id, label: c.name }))}
                    placeholder="Cliente (opcional)"
                  />
                </div>
                <button
                  onClick={openNewCustomerModal}
                  disabled={!can('customers:create')}
                  aria-label="Novo cliente"
                  className="shrink-0 flex items-center justify-center w-9 h-9 bg-accent hover:bg-accent-hover text-white rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Plus size={16} />
                </button>
                <button
                  onClick={() => setCustomersModalOpen(true)}
                  aria-label="Consultar clientes"
                  className="shrink-0 flex items-center justify-center w-9 h-9 border border-border hover:border-accent hover:text-accent text-text-muted rounded-md transition-colors cursor-pointer"
                >
                  <Search size={16} />
                </button>
              </div>

              {cart.length === 0 ? (
                <p className="text-text-muted text-[12px] text-center py-8">Carrinho vazio</p>
              ) : (
                <div className="mb-4 max-h-[340px] overflow-y-auto scrollbar-thin border border-border rounded-md">
                  <table className="w-full text-[11px]">
                    <thead className="sticky top-0 bg-bg-inset">
                      <tr className="text-text-muted">
                        <th className="text-left font-medium px-2 py-1.5">Artigo</th>
                        <th className="text-center font-medium px-1 py-1.5 w-16">Qtd</th>
                        <th className="text-center font-medium px-1 py-1.5 w-9">Un</th>
                        <th className="text-right font-medium px-2 py-1.5">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cart.map((line) => {
                        const lineTotal = line.price * line.quantity * (1 - (line.discountPercent || 0) / 100);
                        return (
                          <Fragment key={line.key}>
                            <tr key={line.key} className="border-t border-border">
                              <td className="px-2 py-1.5 align-top">
                                <p className="font-medium text-text-primary truncate max-w-[110px]">{line.name}</p>
                                <div className="flex items-center gap-1.5 mt-0.5">
                                  <button
                                    onClick={() => setExpandedDiscountKey(expandedDiscountKey === line.key ? null : line.key)}
                                    className={'text-[9px] font-semibold px-1 py-0.5 rounded cursor-pointer transition-colors ' + (line.discountPercent > 0 ? 'text-accent bg-accent/10' : 'text-text-muted hover:text-accent hover:bg-accent/10')}
                                    title="Aplicar desconto"
                                  >
                                    {line.discountPercent > 0 ? `-${line.discountPercent}%` : '%'}
                                  </button>
                                  <button onClick={() => removeFromCart(line.key)} className="text-text-muted hover:text-danger cursor-pointer">
                                    <Trash2 size={10} />
                                  </button>
                                </div>
                              </td>
                              <td className="px-1 py-1.5 align-top">
                                <div className="flex items-center justify-center gap-0.5">
                                  <button onClick={() => updateCartQuantity(line.key, line.quantity - 1)} className="w-5 h-5 flex items-center justify-center rounded border border-border text-text-muted hover:text-text-primary cursor-pointer">
                                    <Minus size={9} />
                                  </button>
                                  <span className="w-5 text-center font-mono text-text-primary">{line.quantity}</span>
                                  <button onClick={() => updateCartQuantity(line.key, line.quantity + 1)} className="w-5 h-5 flex items-center justify-center rounded border border-border text-text-muted hover:text-text-primary cursor-pointer">
                                    <Plus size={9} />
                                  </button>
                                </div>
                              </td>
                              <td className="px-1 py-1.5 align-top text-center text-text-muted">{line.unit}</td>
                              <td className="px-2 py-1.5 align-top text-right font-mono text-text-primary">{formatKz(lineTotal)}</td>
                            </tr>
                            {expandedDiscountKey === line.key && (
                              <tr key={line.key + '-discount'} className="border-t border-border/50">
                                <td colSpan={4} className="px-2 pb-1.5 pt-0.5">
                                  <div className="flex items-center gap-1.5">
                                    <span className="text-[10px] text-text-muted">Desconto:</span>
                                    <input
                                      type="number" min="0" max="100" step="1"
                                      value={line.discountPercent || ''}
                                      onChange={(e) => updateCartDiscount(line.key, e.target.value)}
                                      placeholder="0"
                                      autoFocus
                                      className="w-14 bg-bg-inset border border-border rounded px-1.5 py-0.5 text-[11px] text-text-primary font-mono outline-none focus:border-accent transition-colors"
                                    />
                                    <span className="text-[10px] text-text-muted">%</span>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="border-t border-border pt-3 mb-3 flex flex-col gap-1.5">
                <div className="flex items-center gap-1.5 justify-end mb-1">
                  <span className="text-[11px] text-text-muted">Desconto global:</span>
                  <input
                    type="number" min="0" max="100" step="1"
                    value={globalDiscountPercent || ''}
                    onChange={(e) => setGlobalDiscountPercent(parseFloat(e.target.value) || 0)}
                    placeholder="0"
                    className="w-14 bg-bg-inset border border-border rounded px-1.5 py-0.5 text-[11px] text-text-primary font-mono outline-none focus:border-accent transition-colors"
                  />
                  <span className="text-[11px] text-text-muted">%</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-text-muted text-[12px]">Iliquido</span>
                  <span className="font-mono text-text-primary text-[12px]">{formatKz(cartCalculation.subtotal)} Kz</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-text-muted text-[12px]">IVA</span>
                  <span className="font-mono text-text-primary text-[12px]">{formatKz(cartCalculation.vat)} Kz</span>
                </div>
                {globalDiscountAmount > 0 && (
                  <div className="flex items-center justify-between">
                    <span className="text-text-muted text-[12px]">Desconto</span>
                    <span className="font-mono text-danger text-[12px]">-{formatKz(globalDiscountAmount)} Kz</span>
                  </div>
                )}
                {cartCalculation.retention > 0 && (
                  <div className="flex items-center justify-between">
                    <span className="text-text-muted text-[12px]">Retencao</span>
                    <span className="font-mono text-danger text-[12px]">-{formatKz(cartCalculation.retention)} Kz</span>
                  </div>
                )}
                <div className="flex items-center justify-between pt-1.5 border-t border-border">
                  <span className="text-text-primary text-[13px] font-medium">Total</span>
                  <span className="font-mono font-semibold text-text-primary text-lg">{formatKz(cartTotal)} Kz</span>
                </div>
              </div>

              {posPaymentMethods.length > 0 && (
                <div className="flex flex-col gap-2 mb-4">
                  <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">Formas de pagamento</p>
                  <div className={'flex flex-col gap-1.5' + (selectedInvoiceType !== 'FACTURA_RECIBO' ? ' opacity-40 pointer-events-none' : '')}>
                    {posPaymentMethods.map((m) => {
                      const line = payments.find((p) => p.paymentMethodId === m.id);
                      return (
                        <div key={m.id} className="flex items-center gap-2">
                          <label className="flex items-center gap-2 flex-1 cursor-pointer select-none">
                            <input
                              type="checkbox"
                              checked={!!line}
                              onChange={() => togglePaymentMethod(m.id)}
                              disabled={selectedInvoiceType !== 'FACTURA_RECIBO'}
                              className="w-4 h-4 accent-accent cursor-pointer"
                            />
                            <span className="text-[13px] text-text-primary">{m.name}</span>
                          </label>
                          {line && (
                            <input
                              type="number" step="0.01" min="0"
                              value={line.amount}
                              onChange={(e) => updatePaymentAmount(m.id, e.target.value)}
                              placeholder="Valor"
                              className="w-28 bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {selectedInvoiceType === 'FACTURA_RECIBO' && (
                    <div className={'text-[12px] px-3 py-2 rounded-r border-l-2 ' + (paymentsRemaining === 0 ? 'bg-success/10 border-success text-success' : paymentsRemaining > 0 ? 'bg-accent/10 border-accent text-accent' : 'bg-danger/10 border-danger text-danger')}>
                      {paymentsRemaining === 0 ? 'Valor exato' : paymentsRemaining > 0 ? `Falta ${formatKz(paymentsRemaining)} Kz` : `Excede em ${formatKz(Math.abs(paymentsRemaining))} Kz`}
                    </div>
                  )}
                </div>
              )}

              <div className="flex flex-col gap-2.5 mb-4">
                <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">Condicoes de faturacao (FT)</p>
                <div className={'flex flex-col gap-2.5' + (selectedInvoiceType !== 'FACTURA' ? ' opacity-40 pointer-events-none' : '')}>
                  <Select
                    value={ftPaymentTermId}
                    onChange={(termId) => {
                      setFtPaymentTermId(termId);
                      const term = paymentTerms.find((t) => t.id === termId);
                      if (term && term.days > 0) {
                        setFtDueDate(addDays(new Date().toISOString().slice(0, 10), term.days));
                      } else {
                        setFtDueDate('');
                      }
                    }}
                    options={paymentTerms.map((t) => ({ value: t.id, label: t.name }))}
                    placeholder="Condicao de pagamento"
                  />
                  {ftDueDate && (
                    <p className="text-[12px] text-text-muted">Data de vencimento: <span className="font-mono text-text-primary">{ftDueDate}</span></p>
                  )}
                </div>
              </div>

              {checkoutError && (
                <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-3">{checkoutError}</div>
              )}

              <button
                onClick={() => setSaleConfirmModalOpen(true)}
                disabled={cart.length === 0 || proFormaSaving || checkoutSaving || (selectedInvoiceType === 'FACTURA_RECIBO' && posPaymentMethods.length > 0 && paymentsRemaining !== 0)}
                className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
              >
                {(proFormaSaving || checkoutSaving) && <Loader2 size={16} className="animate-spin" />}
                {selectedInvoiceType === 'PRO_FORMA' ? (proFormaSaving ? 'A gerar...' : 'Gerar pro-forma') : selectedInvoiceType === 'FACTURA' ? (checkoutSaving ? 'A faturar...' : 'Faturar') : (checkoutSaving ? 'A finalizar...' : 'Confirmar venda')}
              </button>
            </div>
          </div>
        </>
      )}

      <Modal open={openModalOpen} onClose={() => setOpenModalOpen(false)} title="Abrir caixa">
        <form onSubmit={handleOpenSession} className="flex flex-col gap-4">
          <div className="bg-bg-inset border border-border rounded-md px-4 py-3">
            <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1">Fundo reportado da sessao anterior</p>
            {carryForwardLoading ? (
              <div className="flex items-center gap-2 text-text-muted text-sm"><Loader2 size={14} className="animate-spin" />A calcular...</div>
            ) : (
              <p className="font-mono font-semibold text-text-primary text-lg">{formatKz(carryForwardAmount)} Kz</p>
            )}
          </div>
          {openError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{openError}</div>
          )}
          <button type="submit" disabled={openSaving} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
            {openSaving ? <Loader2 size={17} className="animate-spin" /> : <Wallet size={17} />}
            {openSaving ? 'A abrir...' : 'Abrir caixa'}
          </button>
        </form>
      </Modal>

      <Modal open={closeModalOpen} onClose={() => setCloseModalOpen(false)} title="Fechar caixa">
        {!closeResult ? (
          <form onSubmit={handleCloseSession} className="flex flex-col gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Valor contado na gaveta *</label>
              <input
                type="number" step="0.01" min="0"
                value={closingAmountCounted}
                onChange={(e) => setClosingAmountCounted(e.target.value)}
                required
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
              />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Notas (opcional)</label>
              <input
                value={closingNotes}
                onChange={(e) => setClosingNotes(e.target.value)}
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
              />
            </div>
            {closeError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{closeError}</div>
            )}
            <button type="submit" disabled={closeSaving} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
              {closeSaving ? <Loader2 size={17} className="animate-spin" /> : <LogOut size={17} />}
              {closeSaving ? 'A fechar...' : 'Fechar caixa'}
            </button>
          </form>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2 bg-bg-inset border border-border rounded-md px-4 py-3">
              <div className="flex justify-between text-[13px]"><span className="text-text-muted">Esperado</span><span className="font-mono text-text-primary">{Number(closeResult.closing_amount_expected).toFixed(2)} Kz</span></div>
              <div className="flex justify-between text-[13px]"><span className="text-text-muted">Contado</span><span className="font-mono text-text-primary">{Number(closeResult.closing_amount_counted).toFixed(2)} Kz</span></div>
              <div className="flex justify-between text-[13px] border-t border-border pt-2">
                <span className="text-text-muted">Diferença</span>
                <span className={'font-mono font-semibold ' + (Number(closeResult.closing_difference) === 0 ? 'text-success' : Number(closeResult.closing_difference) > 0 ? 'text-accent' : 'text-danger')}>
                  {Number(closeResult.closing_difference) > 0 ? '+' : ''}{Number(closeResult.closing_difference).toFixed(2)} Kz
                </span>
              </div>
            </div>
            <button onClick={finishClosing} className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer">
              Concluir
            </button>
          </div>
        )}
      </Modal>

      <Modal open={paymentModalOpen} onClose={closeLiquidationModal} title="Liquidar pro-forma">
        <div className="flex flex-col gap-4">
          {liquidationTarget && (
            <div className="bg-accent/10 border-l-2 border-accent px-3.5 py-2.5 text-[13px] rounded-r">
              <p className="text-text-primary">A liquidar <span className="font-mono">FP {liquidationTarget.series}/{liquidationTarget.number}</span></p>
              <div className="mt-2">
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Converter para</label>
                <Select
                  value={liquidationTargetType}
                  onChange={setLiquidationTargetType}
                  options={[{ value: 'FACTURA', label: 'Fatura' }, { value: 'FACTURA_RECIBO', label: 'Fatura/Recibo' }]}
                />
              </div>
            </div>
          )}

          <div className="flex justify-between items-center bg-bg-inset border border-border rounded-md px-4 py-3">
            <span className="text-text-muted text-[13px]">Total a pagar</span>
            <span className="font-mono font-semibold text-text-primary text-lg">{formatKz(paymentDueTotal)} Kz</span>
          </div>

          <div className="flex flex-col gap-1.5">
            {posPaymentMethods.map((m) => {
              const line = payments.find((p) => p.paymentMethodId === m.id);
              return (
                <div key={m.id} className="flex items-center gap-2">
                  <label className="flex items-center gap-2 flex-1 cursor-pointer select-none">
                    <input type="checkbox" checked={!!line} onChange={() => togglePaymentMethod(m.id)} className="w-4 h-4 accent-accent cursor-pointer" />
                    <span className="text-[13px] text-text-primary">{m.name}</span>
                  </label>
                  {line && (
                    <input
                      type="number" step="0.01" min="0"
                      value={line.amount}
                      onChange={(e) => updatePaymentAmount(m.id, e.target.value)}
                      placeholder="Valor"
                      className="w-28 bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
                    />
                  )}
                </div>
              );
            })}
          </div>

          <div className={'text-[13px] px-3.5 py-2.5 rounded-r border-l-2 ' + (paymentsRemaining === 0 ? 'bg-success/10 border-success text-success' : paymentsRemaining > 0 ? 'bg-accent/10 border-accent text-accent' : 'bg-danger/10 border-danger text-danger')}>
            {paymentsRemaining === 0 ? 'Valor exato' : paymentsRemaining > 0 ? `Falta ${formatKz(paymentsRemaining)} Kz` : `Excede em ${formatKz(Math.abs(paymentsRemaining))} Kz`}
          </div>

          {checkoutError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{checkoutError}</div>
          )}

          <button
            onClick={handleConfirmSale}
            disabled={checkoutSaving || paymentsRemaining !== 0 || (paymentMode === 'liquidation' ? !can('pos:liquidate') : !can('pos:checkout'))}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {checkoutSaving ? <Loader2 size={17} className="animate-spin" /> : <CheckCircle2 size={17} />}
            {checkoutSaving ? 'A finalizar...' : 'Confirmar liquidacao'}
          </button>
        </div>
      </Modal>

      <Modal open={dailyReportModalOpen} onClose={() => setDailyReportModalOpen(false)} title="Relatorio do dia" maxWidthClass="max-w-2xl">
        <div className="flex flex-col gap-4">
          <div className="flex items-end gap-2.5">
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">De</label>
              <input
                type="date" value={dailyReportDateFrom}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => {
                  const newFrom = e.target.value;
                  setDailyReportDateFrom(newFrom);
                  if (dailyReportDateTo && dailyReportDateTo < newFrom) setDailyReportDateTo(newFrom);
                }}
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
              />
            </div>
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Ate</label>
              <input
                type="date" value={dailyReportDateTo}
                min={dailyReportDateFrom || undefined}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setDailyReportDateTo(e.target.value)}
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
              />
            </div>
            <button
              onClick={() => loadDailyReport(dailyReportDateFrom, dailyReportDateTo)}
              className="bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer"
            >
              Filtrar
            </button>
          </div>

          {dailyReportLoading ? (
            <div className="flex justify-center py-8"><Loader2 size={20} className="animate-spin text-accent" /></div>
          ) : dailyReportEntries.length === 0 ? (
            <p className="text-text-muted text-[13px] text-center py-8">Nenhuma operacao neste periodo</p>
          ) : (
            <>
              <div className="flex flex-col gap-1.5 max-h-[400px] overflow-y-auto scrollbar-thin">
                {dailyReportEntries.map((e, idx) => (
                  <div key={idx} className="flex items-center justify-between bg-bg-inset border border-border rounded-md px-3.5 py-2.5">
                    <div>
                      <p className="text-[12px] text-text-primary">{e.description}</p>
                      <p className="text-[10px] text-text-muted font-mono">{new Date(e.time).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</p>
                    </div>
                    <span className={'font-mono text-[13px] font-semibold ' + (e.direction === 'saida' ? 'text-danger' : 'text-success')}>
                      {e.direction === 'saida' ? '-' : '+'}{formatKz(e.amount)} Kz
                    </span>
                  </div>
                ))}
              </div>
              <div className="flex justify-between border-t border-border pt-3">
                <span className="text-text-muted text-[13px] font-medium">Total do periodo</span>
                <span className="font-mono font-bold text-text-primary text-[15px]">
                  {formatKz(dailyReportEntries.reduce((sum, e) => sum + (e.direction === 'saida' ? -e.amount : e.amount), 0))} Kz
                </span>
              </div>
              <button
                onClick={() => window.print()}
                className="flex items-center justify-center gap-2 border border-border hover:border-accent text-text-primary font-medium text-sm rounded-md py-3 transition-colors cursor-pointer"
              >
                <Printer size={16} />
                Imprimir
              </button>
            </>
          )}
        </div>
      </Modal>

      <Modal open={saleConfirmModalOpen} onClose={() => setSaleConfirmModalOpen(false)} title="Confirmar operacao">
        <div className="flex flex-col gap-4">
          <div className="bg-bg-inset border border-border rounded-md px-4 py-3 flex flex-col gap-1.5">
            <div className="flex justify-between text-[13px]">
              <span className="text-text-muted">Tipo de documento</span>
              <span className="text-text-primary font-medium">{selectedInvoiceType === 'PRO_FORMA' ? 'Pro-forma' : selectedInvoiceType === 'FACTURA' ? 'Fatura' : 'Fatura/Recibo'}</span>
            </div>
            <div className="flex justify-between text-[13px]">
              <span className="text-text-muted">Artigos</span>
              <span className="text-text-primary font-medium">{cart.length}</span>
            </div>
            <div className="flex justify-between text-[15px] pt-1.5 border-t border-border mt-1">
              <span className="text-text-primary font-semibold">Total</span>
              <span className="text-text-primary font-mono font-bold">{formatKz(cartTotal)} Kz</span>
            </div>
          </div>
          <p className="text-text-muted text-[13px]">Confirma a finalizacao desta operacao?</p>
          <div className="flex gap-2.5">
            <button
              onClick={() => setSaleConfirmModalOpen(false)}
              className="flex-1 border border-border hover:border-accent text-text-primary font-medium text-sm rounded-md py-3 transition-colors cursor-pointer"
            >
              Cancelar
            </button>
            <button
              onClick={() => {
                setSaleConfirmModalOpen(false);
                if (selectedInvoiceType === 'PRO_FORMA') handleCreateProForma();
                else if (selectedInvoiceType === 'FACTURA') handleConfirmFt();
                else handleConfirmSale();
              }}
              className="flex-1 bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer"
            >
              Confirmar
            </button>
          </div>
        </div>
      </Modal>

      <Modal open={successModalOpen} onClose={closePaymentModal} title="Documento gerado">
        <div className="flex flex-col items-center gap-4 py-4 text-center">
          <CheckCircle2 size={40} className="text-success" />
          <div>
            <p className="font-display font-semibold text-text-primary">
              {lastInvoice?.invoice_type === 'PRO_FORMA' ? 'Pro-forma gerada' : lastInvoice?.invoice_type === 'FACTURA' ? 'Fatura emitida' : 'Venda concluida'}
            </p>
            {lastInvoice && (
              <p className="text-text-muted text-[13px] font-mono mt-1">{lastInvoice.series}/{String(lastInvoice.number).padStart(lastInvoice.number_digits, '0')} - {formatKz(lastInvoice.total)} Kz</p>
            )}
          </div>
          <button onClick={closePaymentModal} className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md py-3 px-6 transition-colors cursor-pointer">
            Nova venda
          </button>
        </div>
      </Modal>

      <Modal open={moedeiroModalOpen} onClose={() => setMoedeiroModalOpen(false)} title="Moedeiro (billetagem)" maxWidthClass="max-w-md">
        <div className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Tipo de contagem</label>
            <Select
              value={moedeiroCountType}
              onChange={(v) => setMoedeiroCountType(v)}
              options={[
                { value: 'ABERTURA', label: 'Abertura de caixa' },
                { value: 'FECHO', label: 'Fecho de caixa' },
                { value: 'TROCA_SAIDA', label: 'Troca - saida' },
                { value: 'TROCA_ENTRADA', label: 'Troca - entrada' },
              ]}
            />
          </div>

          {moedeiroSavedTotal !== null ? (
            <div className="flex flex-col gap-3">
              <div className="bg-success/10 border-l-2 border-success text-success px-3.5 py-3 text-[13px] rounded-r flex items-center gap-2">
                <CheckCircle2 size={16} />
                Contagem registada: {formatKz(moedeiroSavedTotal)} Kz
              </div>
              {closingViaBilletage && (
                <>
                  {moedeiroError && (
                    <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{moedeiroError}</div>
                  )}
                  <button
                    onClick={handleCloseAfterBilletage}
                    disabled={closeSaving}
                    className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
                  >
                    {closeSaving ? <Loader2 size={17} className="animate-spin" /> : <LogOut size={17} />}
                    {closeSaving ? 'A fechar...' : 'Fechar caixa'}
                  </button>
                </>
              )}
            </div>
          ) : (
            <>
              <div className="max-h-[360px] overflow-y-auto scrollbar-thin flex flex-col gap-2">
                <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">Notas</p>
                {denominations.filter((d) => d.denomination_type === 'NOTA').map((d) => (
                  <div key={d.id} className="flex items-center justify-between gap-3">
                    <span className="text-[13px] text-text-primary font-mono w-24">{formatKz(d.value)} Kz</span>
                    <input
                      type="number" min="0" step="1"
                      value={denominationQuantities[d.id] || ''}
                      onChange={(e) => updateDenominationQuantity(d.id, e.target.value)}
                      placeholder="0"
                      className="w-32 bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
                    />
                    <span className="text-[12px] text-text-muted w-20 text-right">
                      {formatKz(parseInt(denominationQuantities[d.id] || '0', 10) * Number(d.value))}
                    </span>
                  </div>
                ))}
                <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide mt-2">Moedas</p>
                {denominations.filter((d) => d.denomination_type === 'MOEDA').map((d) => (
                  <div key={d.id} className="flex items-center justify-between gap-3">
                    <span className="text-[13px] text-text-primary font-mono w-24">{formatKz(d.value)} Kz</span>
                    <input
                      type="number" min="0" step="1"
                      value={denominationQuantities[d.id] || ''}
                      onChange={(e) => updateDenominationQuantity(d.id, e.target.value)}
                      placeholder="0"
                      className="w-32 bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
                    />
                    <span className="text-[12px] text-text-muted w-20 text-right">
                      {formatKz(parseInt(denominationQuantities[d.id] || '0', 10) * Number(d.value))}
                    </span>
                  </div>
                ))}
              </div>

              <div className="flex flex-col gap-1.5 bg-bg-inset border border-border rounded-md px-4 py-3">
                <div className="flex justify-between items-center">
                  <span className="text-text-muted text-[13px]">Saldo da caixa</span>
                  <span className="font-mono text-text-primary text-[13px]">{moedeiroTarget !== null ? formatKz(moedeiroTarget) + ' Kz' : '...'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-text-muted text-[13px]">Total contado</span>
                  <span className={'font-mono font-semibold text-lg ' + (moedeiroMatches ? 'text-success' : 'text-text-primary')}>{formatKz(moedeiroTotal)} Kz</span>
                </div>
                {!moedeiroMatches && moedeiroTarget !== null && (
                  <p className="text-[11px] text-danger">
                    {moedeiroTotal > moedeiroTarget ? `Excede em ${formatKz(moedeiroTotal - moedeiroTarget)} Kz` : `Falta ${formatKz(moedeiroTarget - moedeiroTotal)} Kz`}
                  </p>
                )}
              </div>

              {moedeiroError && (
                <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{moedeiroError}</div>
              )}

              <button
                onClick={handleMoedeiroSubmit}
                disabled={moedeiroSaving || !moedeiroMatches}
                className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
              >
                {moedeiroSaving ? <Loader2 size={17} className="animate-spin" /> : <Coins size={17} />}
                {moedeiroSaving ? 'A registar...' : 'Registar contagem'}
              </button>
            </>
          )}
        </div>
      </Modal>

      <Modal open={associationModalOpen} onClose={() => setAssociationModalOpen(false)} title="Associacao da caixa">
        <div className="flex flex-col gap-3">
          <p className="text-[13px] text-text-muted">Define qual utilizador esta autorizado a operar esta caixa.</p>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Caixa</label>
            <Select
              value={selectedPosId}
              onChange={handlePosChange}
              options={allActivePos.map((p) => ({ value: p.id, label: p.name + ' - ' + p.activityName }))}
              placeholder="Selecionar caixa"
            />
          </div>
          {posHolder ? (
            <div className="flex items-center justify-between bg-bg-inset border border-border rounded-md px-3 py-2.5">
              <span className="text-[13px] text-text-primary">{posHolder.full_name}</span>
              <button type="button" onClick={handleUnassignPos} disabled={assignSaving} className="flex items-center gap-1.5 text-danger text-[12px] cursor-pointer disabled:opacity-50">
                <Unlink size={12} />Desassociar
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <Select
                  value={assignSelection}
                  onChange={setAssignSelection}
                  options={assignableUsers.map((u) => ({ value: u.id, label: u.full_name }))}
                  placeholder="Selecionar utilizador"
                />
              </div>
              <button type="button" onClick={handleAssignPos} disabled={assignSaving || !assignSelection} className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-[12px] font-medium px-3 py-2 rounded-md cursor-pointer">
                <Link2 size={12} />Associar
              </button>
            </div>
          )}
          {assignError && <p className="text-danger text-[12px]">{assignError}</p>}
        </div>
      </Modal>

      <Modal open={movementModalOpen} onClose={() => setMovementModalOpen(false)} title="Operacoes de Caixa">
        <div className="flex items-center gap-1.5 mb-4 border-b border-border">
          <button
            onClick={() => setMovementModalTab('form')}
            className={'px-3.5 py-2 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer ' + (movementModalTab === 'form' ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary')}
          >
            Novo movimento
          </button>
          <button
            onClick={() => setMovementModalTab('pending')}
            className={'px-3.5 py-2 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer flex items-center gap-1.5 ' + (movementModalTab === 'pending' ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary')}
          >
            Transferencias pendentes
            {(pendingReceptions.length + pendingEmissions.length) > 0 && (
              <span className="bg-accent text-white text-[10px] font-semibold px-1.5 py-0.5 rounded-full">{pendingReceptions.length + pendingEmissions.length}</span>
            )}
          </button>
        </div>

        {movementModalTab === 'form' ? (
          <form onSubmit={handleMovementSubmit} className="flex flex-col gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Tipo</label>
              <Select
                value={movementForm.movementType}
                onChange={(v) => setMovementForm((p) => ({ ...p, movementType: v, otherPosId: '', reasonId: '' }))}
                options={[
                  { value: 'TRANSFERENCIA', label: 'Transferencia para outra caixa' },
                  { value: 'ENTRADA_EXTERNA', label: 'Entrada externa' },
                  { value: 'SAIDA_EXTERNA', label: 'Saida externa' },
                ]}
              />
            </div>

            {movementForm.movementType === 'TRANSFERENCIA' && (
              <div>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Caixa de destino *</label>
                <Select
                  value={movementForm.otherPosId}
                  onChange={(v) => setMovementForm((p) => ({ ...p, otherPosId: v }))}
                  options={allActivePos.filter((p) => p.id !== selectedPosId).map((p) => ({ value: p.id, label: p.name + ' - ' + p.activityName }))}
                  placeholder="Selecionar"
                />
              </div>
            )}
            {movementForm.movementType !== 'TRANSFERENCIA' && (
              <div>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Motivo *</label>
                <Select
                  value={movementForm.reasonId}
                  onChange={(v) => setMovementForm((p) => ({ ...p, reasonId: v }))}
                  options={movementReasons
                    .filter((r) => r.is_active && r.direction === (movementForm.movementType === 'ENTRADA_EXTERNA' ? 'ENTRADA' : 'SAIDA'))
                    .map((r) => ({ value: r.id, label: r.name }))}
                  placeholder="Selecionar"
                />
              </div>
            )}

            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Valor *</label>
              <input
                type="number" step="0.01" min="0.01"
                value={movementForm.amount}
                onChange={(e) => setMovementForm((p) => ({ ...p, amount: e.target.value }))}
                required
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
              />
            </div>

            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Descricao (opcional)</label>
              <input
                value={movementForm.description}
                onChange={(e) => setMovementForm((p) => ({ ...p, description: e.target.value }))}
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
              />
            </div>

            {movementFormError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{movementFormError}</div>
            )}

            <button
              type="submit"
              disabled={movementSaving}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              {movementSaving ? <Loader2 size={17} className="animate-spin" /> : <ArrowLeftRight size={17} />}
              {movementSaving ? 'A registar...' : 'Registar movimento'}
            </button>
          </form>
        ) : (
          <div className="flex flex-col gap-5">
            <div>
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide mb-2">Aguardam a sua confirmacao (recebidas)</p>
              {pendingReceptionsLoading ? (
                <div className="flex justify-center py-4"><Loader2 size={16} className="animate-spin text-accent" /></div>
              ) : pendingReceptions.length === 0 ? (
                <p className="text-text-muted text-[12px] text-center py-4">Nenhuma transferencia pendente de recepcao</p>
              ) : (
                <div className="flex flex-col gap-1.5 max-h-[200px] overflow-y-auto scrollbar-thin">
                  {pendingReceptions.map((m) => (
                    <div key={m.id} className="flex items-center justify-between bg-bg-inset border border-border rounded-md px-3 py-2">
                      <div>
                        <p className="text-[12px] text-text-primary">Transferencia recebida</p>
                        <p className="text-[10px] text-text-muted font-mono">{new Date(m.movement_date).toLocaleDateString('pt-PT')}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[12px] text-text-primary font-semibold">{formatKz(m.amount)} Kz</span>
                        <button
                          onClick={() => handleReceiveMovement(m.id)}
                          disabled={receivingId === m.id || !can('tesouraria:receive')}
                          className="flex items-center gap-1 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-[11px] font-medium px-2.5 py-1.5 rounded-md cursor-pointer"
                        >
                          {receivingId === m.id ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />}
                          Confirmar
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide mb-2">Enviadas por si (aguardam a outra caixa)</p>
              {pendingEmissionsLoading ? (
                <div className="flex justify-center py-4"><Loader2 size={16} className="animate-spin text-accent" /></div>
              ) : pendingEmissions.length === 0 ? (
                <p className="text-text-muted text-[12px] text-center py-4">Nenhuma transferencia enviada por confirmar</p>
              ) : (
                <div className="flex flex-col gap-1.5 max-h-[200px] overflow-y-auto scrollbar-thin">
                  {pendingEmissions.map((m) => (
                    <div key={m.id} className="flex items-center justify-between bg-bg-inset border border-border rounded-md px-3 py-2">
                      <div>
                        <p className="text-[12px] text-text-primary">Transferencia enviada</p>
                        <p className="text-[10px] text-text-muted font-mono">{new Date(m.movement_date).toLocaleDateString('pt-PT')}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[12px] text-text-primary font-semibold">{formatKz(m.amount)} Kz</span>
                        <button
                          onClick={() => handleCancelMovement(m.id)}
                          disabled={cancellingId === m.id || !can('tesouraria:cancel_movement')}
                          className="flex items-center gap-1 border border-border hover:border-danger hover:text-danger text-text-muted disabled:opacity-50 text-[11px] font-medium px-2.5 py-1.5 rounded-md cursor-pointer"
                        >
                          {cancellingId === m.id ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />}
                          Cancelar
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {movementFormError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{movementFormError}</div>
            )}
          </div>
        )}
      </Modal>

      <Modal open={newCustomerModalOpen} onClose={() => setNewCustomerModalOpen(false)} title="Novo cliente">
        <form onSubmit={handleNewCustomerSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome *</label>
            <input
              value={newCustomerForm.name}
              onChange={(e) => setNewCustomerForm((p) => ({ ...p, name: e.target.value }))}
              required
              autoFocus
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">NIF</label>
            <input
              value={newCustomerForm.nif}
              onChange={(e) => setNewCustomerForm((p) => ({ ...p, nif: e.target.value }))}
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Telefone *</label>
            <input
              value={newCustomerForm.phone_number}
              onChange={(e) => setNewCustomerForm((p) => ({ ...p, phone_number: e.target.value }))}
              required
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Email</label>
            <input
              type="email"
              value={newCustomerForm.email}
              onChange={(e) => setNewCustomerForm((p) => ({ ...p, email: e.target.value }))}
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
            />
          </div>
          {newCustomerError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{newCustomerError}</div>
          )}
          <button
            type="submit"
            disabled={newCustomerSaving || !newCustomerForm.name.trim() || !newCustomerForm.phone_number.trim()}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {newCustomerSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {newCustomerSaving ? 'A guardar...' : 'Criar cliente'}
          </button>
        </form>
      </Modal>

      <Modal open={customersModalOpen} onClose={() => setCustomersModalOpen(false)} title="Consultar clientes">
        <div className="flex flex-col gap-3">
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              placeholder="Pesquisar cliente..."
              value={customerSearchQuery}
              onChange={(e) => setCustomerSearchQuery(e.target.value)}
              autoFocus
              className="w-full bg-bg-inset border border-border rounded-md pl-9 pr-3 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
            />
          </div>
          <div className="flex flex-col gap-2 max-h-[420px] overflow-y-auto scrollbar-thin">
            {customers
              .filter((c) => !customerSearchQuery.trim() || c.name.toLowerCase().includes(customerSearchQuery.toLowerCase()) || (c.nif || '').includes(customerSearchQuery))
              .map((c) => (
                <button
                  key={c.id}
                  onClick={() => { setSelectedCustomerId(c.id); setCustomersModalOpen(false); }}
                  className="flex items-center justify-between bg-bg-inset border border-border hover:border-accent rounded-md px-4 py-3 text-left transition-colors cursor-pointer"
                >
                  <div>
                    <p className="text-[13px] text-text-primary">{c.name}</p>
                    <p className="text-[11px] text-text-muted">{c.phone_number || 'Sem telefone'}{c.email ? ' - ' + c.email : ''}</p>
                  </div>
                  <span className="text-[11px] text-text-muted font-mono">{c.nif}</span>
                </button>
              ))}
          </div>
        </div>
      </Modal>

      <Modal open={articlesModalOpen} onClose={() => setArticlesModalOpen(false)} title="Consultar artigos">
        <div className="flex flex-col gap-3">
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              placeholder="Pesquisar artigo por codigo ou nome..."
              value={articleSearchQuery}
              onChange={(e) => setArticleSearchQuery(e.target.value)}
              autoFocus
              className="w-full bg-bg-inset border border-border rounded-md pl-9 pr-3 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
            />
          </div>
          <div className="flex flex-col gap-2 max-h-[420px] overflow-y-auto scrollbar-thin">
            {products
              .filter((p) => !articleSearchQuery.trim() || p.code.toLowerCase().includes(articleSearchQuery.toLowerCase()) || p.name.toLowerCase().includes(articleSearchQuery.toLowerCase()))
              .map((p) => (
                <button
                  key={p.id}
                  onClick={() => { addToCart(p, false); setArticlesModalOpen(false); }}
                  className="flex items-center justify-between bg-bg-inset border border-border hover:border-accent rounded-md px-4 py-3 text-left transition-colors cursor-pointer"
                >
                  <div>
                    <p className="font-mono text-[10px] text-text-muted">{p.code}</p>
                    <p className="text-[13px] text-text-primary">{p.name}</p>
                  </div>
                  <span className="font-mono text-accent text-[13px] font-semibold">{Number(p.price).toFixed(2)} Kz</span>
                </button>
              ))}
          </div>
        </div>
      </Modal>


      <Modal open={proFormaModalOpen} onClose={() => setProFormaModalOpen(false)} title="Consultar documentos">
        <div className="flex flex-col gap-3">
          {proFormaLoading ? (
            <div className="flex justify-center py-8"><Loader2 size={20} className="animate-spin text-accent" /></div>
          ) : proFormaError ? (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{proFormaError}</div>
          ) : pendingProFormas.length === 0 ? (
            <p className="text-text-muted text-[13px] text-center py-8">Nenhuma pro-forma pendente de liquidacao</p>
          ) : (
            <div className="flex flex-col gap-2 max-h-[420px] overflow-y-auto scrollbar-thin">
              {pendingProFormas.map((pf) => (
                <button
                  key={pf.id}
                  onClick={() => selectProFormaToLiquidate(pf)}
                  className="flex items-center justify-between bg-bg-inset border border-border hover:border-accent rounded-md px-4 py-3 text-left transition-colors cursor-pointer"
                >
                  <div>
                    <p className="font-mono text-[12px] text-text-primary">FP {pf.series}/{pf.number}</p>
                    <p className="text-[11px] text-text-muted">{new Date(pf.business_date).toLocaleDateString('pt-PT')}</p>
                  </div>
                  <span className="font-mono font-semibold text-accent text-[13px]">{formatKz(pf.total)} Kz</span>
                </button>
              ))}
            </div>
          )}

          <div className="border-t border-border pt-3 mt-1">
            <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide mb-2">Documentos emitidos</p>
            {recentInvoicesLoading ? (
              <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-accent" /></div>
            ) : recentInvoices.length === 0 ? (
              <p className="text-text-muted text-[13px] text-center py-6">Nenhum documento emitido ainda</p>
            ) : (
              <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto scrollbar-thin">
                {recentInvoices.map((inv) => (
                  <div key={inv.id} className="flex items-center justify-between bg-bg-inset border border-border rounded-md px-4 py-2.5">
                    <div>
                      <p className="font-mono text-[12px] text-text-primary">{inv.invoice_type === 'FACTURA' ? 'FT' : inv.invoice_type === 'FACTURA_RECIBO' ? 'FR' : inv.invoice_type} {inv.series}/{inv.number}</p>
                      <p className="text-[11px] text-text-muted">{new Date(inv.business_date).toLocaleDateString('pt-PT')} - {formatKz(inv.total)} Kz</p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => openPdfViewer(inv.id, 'thermal', inv.series + '-' + inv.number + ' (Ticket)')}
                        title="Reimprimir - Ticket 80mm"
                        className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer"
                      >
                        <Receipt size={14} />
                      </button>
                      <button
                        onClick={() => openPdfViewer(inv.id, 'a4', inv.series + '-' + inv.number + ' (A4)')}
                        title="Reimprimir - A4"
                        className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer"
                      >
                        <Printer size={14} />
                      </button>
                      {(inv.invoice_type === 'FACTURA' || inv.invoice_type === 'FACTURA_RECIBO') && inv.document_status !== 'ANULADO' && (
                        <>
                          <button
                            onClick={() => documentActionsRef.current?.openNc(inv.id)}
                            disabled={!can('invoices:credit_note')}
                            title="Emitir Nota de Credito"
                            className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer text-[10px] font-bold disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            NC
                          </button>
                          <button
                            onClick={() => documentActionsRef.current?.openNd(inv.id)}
                            disabled={!can('invoices:debit_note')}
                            title="Emitir Nota de Debito"
                            className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer text-[10px] font-bold disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            ND
                          </button>
                          <button
                            onClick={() => documentActionsRef.current?.openRc(inv.id)}
                            disabled={!can('invoices:receipt')}
                            title="Emitir Recibo"
                            className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer text-[10px] font-bold disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            RC
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </Modal>

      <Modal open={pdfModalOpen} onClose={closePdfViewer} title={pdfFilename} maxWidthClass="max-w-3xl">
        <div className="flex flex-col gap-3">
          {pdfBlobUrl && (
            <iframe src={pdfBlobUrl} title={pdfFilename} className="w-full h-[70vh] rounded-md border border-border" />
          )}
          <a
            href={pdfBlobUrl}
            download={pdfFilename + '.pdf'}
            className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer no-underline"
          >
            Descarregar PDF
          </a>
        </div>
      </Modal>
      <DocumentActionModals ref={documentActionsRef} onSuccess={() => listRecentIssuedInvoices().then(setRecentInvoices).catch(() => {})} />
    </main>
  );
}
