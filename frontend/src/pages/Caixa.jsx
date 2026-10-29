import { formatKz } from '../utils/format';
import { FREE, priceOf, levelOptions, hasPriceChoice, unitCost } from '../utils/priceLevels';
import { guessLegalPersonType, isPessoaColetiva, LEGAL_PERSON_OPTIONS } from '../utils/customerType';
import { API_ORIGIN } from '../api/config';
import DateInput from '../components/DateInput';
import { useState, useEffect, useRef, useMemo, Fragment } from 'react';
import usePosDocumentTypes from '../utils/posDocumentTypes';
import { useCan } from '../utils/permissions';
import { listDenominations, recordDenominationCount, getLatestDenominationCount } from '../api/moedeiro';
import { listProductCategories } from '../api/productCategories';
import { listServices } from '../api/services';
import { listVatRates } from '../api/vat';
import { withholdingTaxesApi, paymentTermsApi } from '../api/catalogs';
import useDocumentRules, { DOC_CODE_BY_TYPE } from '../utils/documentRules';
import { getMyCompanyBankAccounts } from '../api/company';
import { createProFormaFromPos, getPosStock } from '../api/pos';
import { listPaymentMethodPreferences } from '../api/tesouraria';
import { Wallet, Plus, Minus, Trash2, Loader2, Search, X, ShoppingCart, LogOut, CheckCircle2, FileSearch, ArrowLeftRight, Coins, Receipt, Printer, FileText, ChevronLeft, Snowflake, MonitorUp } from 'lucide-react';
import { useCustomerDisplay } from '../utils/customerDisplay';
import Modal from '../components/Modal';
import DenominationGrid, { denominationLines, denominationTotal } from '../components/DenominationGrid';
import OpenAccountsPanel from '../components/OpenAccountsPanel';
import { Wallet2 as OpenAccountsIcon, CalendarClock } from 'lucide-react';
import { ReservasPanel } from './Reservas';
import Select from '../components/Select';
import { listActivities, listPointsOfSale } from '../api/activity';
import { createCustomer } from '../api/customers';
import { listProducts } from '../api/products';
import { listCustomers } from '../api/customers';
import { openCashSession, getOpenCashSession, closeCashSession, checkout, liquidatePendingInvoice, getSessionSummary, listCashSessions, fetchClosingReportPdfBlob, getCarryForwardAmount } from '../api/pos';
import { listPendingProFormas, listRecentIssuedInvoices, fetchInvoicePdfBlob, getInvoiceDetail } from '../api/invoices';
import { listPendingReceptions, receiveCashMovement, listPendingEmissions, cancelCashMovement, getDailyReport, fetchDailyReportPdfBlob, getTransferBilletage } from '../api/tesouraria';
import DocumentActionModals from '../components/DocumentActionModals';
import {
  getMyCashPointAssociation, listCashPointAssociations,
  createCashMovement, listCashMovementReasons, listCashMovements,
} from '../api/tesouraria';
import { listUsers } from '../api/users';
import { useAuthStore } from '../store/authStore';
import { extractErrorMessage } from '../utils/errors';
import { medicineSearchText, medicineSummary, getPharmacyContext } from '../api/pharmacy';
import PrescriptionModal, { prescriptionNeedOf } from '../components/PrescriptionModal';

import { dueDateFor, isProntoTerm } from '../utils/paymentTerms';
import { useToastState } from '../components/Toaster';

// What is still owed, from the server (credit notes, deposit, receipts and refunds counted) - never recomputed here.
const balanceOf = (inv) => Number(inv.amount_due || 0);

// The cart is kept per cash point, in sessionStorage (cleared when the tab closes) - so switching between
// two of the gestor's cash points, or reloading the page, does not silently lose items in progress.
const cartStorageKey = (posId) => 'rm_caixa_cart:' + posId;
function loadStoredCart(posId) {
  if (!posId) return [];
  try {
    const raw = sessionStorage.getItem(cartStorageKey(posId));
    return raw ? JSON.parse(raw) : [];
  } catch (err) {
    return [];
  }
}

function addDays(dateStr, days) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function Caixa() {
  const can = useCan();
  const currentUser = useAuthStore((state) => state.user);
  // can() trusts GESTOR by default while permissions is still null (avoids a menu flash) - but
  // loadInitial must know the REAL answer before deciding whether to call listProducts.
  const permissionsList = useAuthStore((state) => state.permissions);
  const canViewProductsUi = Array.isArray(permissionsList) ? permissionsList.includes('products:view') : true;
  const isGestor = currentUser?.role === 'GESTOR';
  const documentActionsRef = useRef(null);

  const [pointsOfSale, setPointsOfSale] = useState([]);
  const [allActivePos, setAllActivePos] = useState([]);
  const [holderNameByPos, setHolderNameByPos] = useState({});
  // "cash point . user . activity" - tells apart the cash points named alike (one Caixa Geral per activity)
  const posLabel = (p) => [p.name, holderNameByPos[p.id], p.activityName].filter(Boolean).join(' \u00b7 ');
  const [myAssociation, setMyAssociation] = useState(null);
  const [associationChecked, setAssociationChecked] = useState(false);
  const [selectedPosId, setSelectedPosId] = useState('');
  // The prices this till lets its cashier use (set by the gestor on the till, like the billetage); the gestor always may.
  const tillPrices = {
    levels: isGestor || !!allActivePos.find((p) => p.id === selectedPosId)?.allow_price_levels,
    free: isGestor || !!allActivePos.find((p) => p.id === selectedPosId)?.allow_free_price,
  };

  const [categories, setCategories] = useState([]);
  const [services, setServices] = useState([]);
  const [vatRates, setVatRates] = useState([]);
  const [withholdingTaxes, setWithholdingTaxes] = useState([]);
  const [activeCategoryId, setActiveCategoryId] = useState('all');
  useEffect(() => {
    if (!canViewProductsUi) setActiveCategoryId('services');
  }, [canViewProductsUi]);
  const [customersModalOpen, setCustomersModalOpen] = useState(false);
  const [customerSearchQuery, setCustomerSearchQuery] = useState('');
  const [newCustomerModalOpen, setNewCustomerModalOpen] = useState(false);
  const [newCustomerForm, setNewCustomerForm] = useState({ name: '', nif: '', phone_number: '', email: '', legal_person_type: 'FISICA', typeTouched: false });
  const [newCustomerSaving, setNewCustomerSaving] = useState(false);
  const [newCustomerError, setNewCustomerError] = useToastState('error');
  const [articlesModalOpen, setArticlesModalOpen] = useState(false);
  const [articleSearchQuery, setArticleSearchQuery] = useState('');

  const [moedeiroModalOpen, setMoedeiroModalOpen] = useState(false);
  // the drawer is counted at the closing (and for an exchange of notes) - the closing report prints that count
  const [moedeiroCountType, setMoedeiroCountType] = useState('FECHO');
  const [denominations, setDenominations] = useState([]);
  const [denominationQuantities, setDenominationQuantities] = useState({});
  const [moedeiroSaving, setMoedeiroSaving] = useState(false);
  const [moedeiroError, setMoedeiroError] = useToastState('error');
  const [moedeiroSavedTotal, setMoedeiroSavedTotal] = useState(null);

  const [movementModalOpen, setMovementModalOpen] = useState(false);
  const [movementForm, setMovementForm] = useState({ movementType: 'TRANSFERENCIA', amount: '', sourcePosId: '', otherPosId: '', reasonId: '', description: '' });
  const [movementReasons, setMovementReasons] = useState([]);
  const [movementSaving, setMovementSaving] = useState(false);
  const [movementFormError, setMovementFormError] = useToastState('error');
  const [movementHistory, setMovementHistory] = useState([]);
  const [movementHistoryLoading, setMovementHistoryLoading] = useState(false);
  const [pendingReceptions, setPendingReceptions] = useState([]);
  // billetage of a transfer: the notes sent (a sending till with billetage), and the reception being confirmed with
  // its notes (a receiving till with billetage - the sender's proposed)
  const [transferQuantities, setTransferQuantities] = useState({});
  const [receptionDraft, setReceptionDraft] = useState(null); // { movement, quantities }
  const [pendingReceptionsLoading, setPendingReceptionsLoading] = useState(false);
  const [receivingId, setReceivingId] = useState(null);
  const [pendingEmissions, setPendingEmissions] = useState([]);
  const [pendingEmissionsLoading, setPendingEmissionsLoading] = useState(false);
  const [cancellingId, setCancellingId] = useState(null);
  const [movementModalTab, setMovementModalTab] = useState('form');
  const [currentBalance, setCurrentBalance] = useState(null);
  const [sessionSummary, setSessionSummary] = useState(null); // the balance justified, by payment method
  const [balanceDetailOpen, setBalanceDetailOpen] = useState(false); // its detail: hover (mouse) or tap (touch)
  const [carryForwardAmount, setCarryForwardAmount] = useState(0);
  const [carryForwardLoading, setCarryForwardLoading] = useState(false);
  const [dailyReportModalOpen, setDailyReportModalOpen] = useState(false);
  const [dailyReportEntries, setDailyReportEntries] = useState([]);
  const [dailyReportLoading, setDailyReportLoading] = useState(false);
  const [dailyReportDateFrom, setDailyReportDateFrom] = useState('');
  const [dailyReportDateTo, setDailyReportDateTo] = useState('');
  const [reportTab, setReportTab] = useState('movimentos'); // Relatórios: the journal, or the closings
  const [reportSessions, setReportSessions] = useState([]);
  const [reportSessionsLoading, setReportSessionsLoading] = useState(false);

  const [session, setSession] = useState(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [error, setError] = useToastState('error');

  const [products, setProducts] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [cart, setCart] = useState([]);
  const [productSearch, setProductSearch] = useState('');
  const [selectedCustomerId, setSelectedCustomerId] = useState('');

  const [openModalOpen, setOpenModalOpen] = useState(false);
  const [openingAmount, setOpeningAmount] = useState('');
  const [openSaving, setOpenSaving] = useState(false);
  const [openError, setOpenError] = useToastState('error');

  const [closeModalOpen, setCloseModalOpen] = useState(false);
  const [closingAmountCounted, setClosingAmountCounted] = useState('');
  const [closingNotes, setClosingNotes] = useState('');
  const [closeSaving, setCloseSaving] = useState(false);
  const [closeError, setCloseError] = useToastState('error');
  const [closeResult, setCloseResult] = useState(null);

  const [paymentModalOpen, setPaymentModalOpen] = useState(false);
  const [payments, setPayments] = useState([]);
  // the notes the customer hands over for the cash part (only to work out the change - the payment stays the amount due)
  const [cashGiven, setCashGiven] = useState('');
  const [checkoutSaving, setCheckoutSaving] = useState(false);
  const [checkoutError, setCheckoutError] = useToastState('error');
  const [lastInvoice, setLastInvoice] = useState(null);

  const [proFormaModalOpen, setProFormaModalOpen] = useState(false);
  const [docsTab, setDocsTab] = useState('docs'); // Consultar documentos: 'docs' (issued) or 'proformas'
  // The cart starts where it sits and runs down to the footer (h-11): only its lines scroll.
  const cartRef = useRef(null);
  const [cartHeight, setCartHeight] = useState(0);
  useEffect(() => {
    function measure() {
      const el = cartRef.current;
      const next = !el || window.innerWidth < 1024 ? 0
        : Math.max(420, Math.floor(window.innerHeight - el.getBoundingClientRect().top - window.scrollY + window.scrollY - 44 - 16));
      setCartHeight((h) => (h === next ? h : next));
    }
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  });
  const [pendingProFormas, setPendingProFormas] = useState([]);
  const [proFormaLoading, setProFormaLoading] = useState(false);
  const [proFormaError, setProFormaError] = useToastState('error');
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
      // Servi?os (no STOCK capability) never gets products:view - listProducts would 403 and, if kept
      // inside this Promise.all, drag the whole page load down with it (activities, association, etc.).
      const canViewProducts = can('products:view');
      // Fired together and awaited separately where each is actually used: catalogStep below (categories,
      // services, vat...) has no dependency on activities/products/customers/association, so starting it
      // here instead of after them removes a full network round-trip from the page's critical path.
      const catalogStep = Promise.all([
        listProductCategories(), listServices(), listVatRates(), withholdingTaxesApi.list(),
        paymentTermsApi.list(), listPaymentMethodPreferences(), getMyCompanyBankAccounts(),
      ]);
      const [activitiesData, productsData, customersData, association] = await Promise.all([
        listActivities(), canViewProducts ? listProducts() : Promise.resolve([]), listCustomers(), getMyCashPointAssociation(),
      ]);
      const activeActivities = activitiesData.filter((a) => a.is_active);
      const posLists = await Promise.all(activeActivities.map((a) => listPointsOfSale(a.id)));

      const printMap = {};
      posLists.forEach((list) => (list || []).forEach((p) => {
        printMap[p.id] = { on: !!p.print_after_sale, ticket: p.print_ticket !== false, a4: !!p.print_a4, closingReport: !!p.print_closing_report };
      }));
      setPrintConfigByPos(printMap);
      const activityNameById = Object.fromEntries(activeActivities.map((a) => [a.id, a.name]));
      const activePos = posLists.flat().filter((p) => p.is_active).map((p) => ({
        ...p, activityName: activityNameById[p.activity_id],
      }));
      setAllActivePos(activePos);
      // a user who cannot read the associations still sees who operates HIS cash point: himself
      if (!can('tesouraria:associations_manage') && association?.pos_id && (currentUser?.full_name || currentUser?.name)) {
        setHolderNameByPos({ [association.pos_id]: currentUser.full_name || currentUser.name });
      }
      // who operates each cash point: only for users allowed to read the associations
      if (can('tesouraria:associations_manage')) {
        try {
          const [usersData, associationsData] = await Promise.all([listUsers(), listCashPointAssociations()]);
          const nameById = Object.fromEntries(usersData.map((u) => [u.id, u.full_name]));
          setHolderNameByPos(Object.fromEntries(associationsData.map((a) => [a.pos_id, nameById[a.user_id]]).filter(([, name]) => name)));
        } catch (err) {
          // the label simply omits the holder
        }
      }
      setMyAssociation(association);
      setAssociationChecked(true);

      // GESTOR sees/picks any POS, same as before. Any other role is locked to their
      // own associated POS - no picker, no access to other cash points at all.
      const availablePos = isGestor ? activePos : activePos.filter((p) => p.id === association?.pos_id);
      setPointsOfSale(availablePos);

      setProducts(productsData.filter((p) => p.is_active && !p.is_raw_material && !p.not_available_pos && !p.internal_use_only));
      const [categoriesData, servicesData, vatData, withholdingData, termsData, methodsData, bankData] = await catalogStep;
      setCategories(categoriesData.filter((c) => c.is_active));
      // a room rate is sold with its room (Reservas: Entrada or the stay's account), never alone in the cart
      setServices(servicesData.filter((s) => s.is_active && !s.not_available_pos && !s.is_stay_rate));
      setVatRates(vatData);
      setWithholdingTaxes(withholdingData);
      setPaymentTerms(termsData.filter((t) => t.is_active));
      setPaymentMethods(methodsData);
      setBankAccounts(bankData.filter((b) => b.is_active));
      setCustomers(customersData.filter((c) => c.is_active));
      const associatedPosStillActive = association?.pos_id && availablePos.some((p) => p.id === association.pos_id);
      const initialPosId = associatedPosStillActive ? association.pos_id : (availablePos[0]?.id || '');
      setSelectedPosId(initialPosId);
      setCart(loadStoredCart(initialPosId));
      if (initialPosId) {
        const openSession = await getOpenCashSession(initialPosId);
        setSession(openSession);
        if (openSession) await refreshBalance(initialPosId);
        refreshPosStock(initialPosId);
      }
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar caixa'));
    } finally {
      setSessionLoading(false);
    }
  }

  useEffect(() => {
    if (Array.isArray(permissionsList)) loadInitial();
  }, [Array.isArray(permissionsList)]);

  async function openMoedeiroModal(countType) {
    const resolvedType = countType || 'FECHO';
    setMoedeiroCountType(resolvedType);
    setMoedeiroError('');
    setMoedeiroSavedTotal(null);
    setClosingNotes('');
    setMoedeiroModalOpen(true);
    // the count must match the live expected balance of the drawer (see moedeiroTarget)
    refreshBalance(selectedPosId);
    try {
      const data = await listDenominations();
      setDenominations(data);
      setDenominationQuantities(Object.fromEntries(data.map((d) => [d.id, ''])));
    } catch (err) {
      setMoedeiroError(extractErrorMessage(err, 'Erro ao carregar denominações'));
    }
  }

  function changeMoedeiroCountType(countType) {
    setMoedeiroCountType(countType);
    setMoedeiroSavedTotal(null);  // another type is another count
    setMoedeiroError('');
    setDenominationQuantities(Object.fromEntries(denominations.map((d) => [d.id, ''])));
  }

  function updateDenominationQuantity(denominationId, value) {
    setDenominationQuantities((prev) => ({ ...prev, [denominationId]: value }));
  }

  const moedeiroTotal = denominationTotal(denominations, denominationQuantities);
  // Target the count must match: the live expected balance of the drawer (see get_current_expected_cash_balance) -
  // matching exactly is required to submit, per the "button only activates when the breakdown matches" requirement.
  const moedeiroTarget = currentBalance;
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
    setNewCustomerForm({ name: '', nif: '', phone_number: '', email: '', legal_person_type: 'FISICA', typeTouched: false });
    setNewCustomerError('');
    setNewCustomerModalOpen(true);
  }

  async function handleNewCustomerSubmit(e) {
    e.preventDefault();
    setNewCustomerError('');
    setNewCustomerSaving(true);
    try {
      const { name, nif, phone_number, email, legal_person_type } = newCustomerForm;
      const customer = await createCustomer({ name, nif, phone_number, email, legal_person_type });
      setCustomers((prev) => [...prev, customer]);
      setSelectedCustomerId(customer.id);
      setNewCustomerModalOpen(false);
    } catch (err) {
      setNewCustomerError(extractErrorMessage(err, 'Erro ao criar cliente'));
    } finally {
      setNewCustomerSaving(false);
    }
  }

  function openMovementModal() {
    setMovementForm({ movementType: 'TRANSFERENCIA', amount: '', sourcePosId: selectedPosId, otherPosId: '', reasonId: '', description: '' });
    setMovementFormError('');
    setMovementModalOpen(true);
    setMovementModalTab('form');
    setTransferQuantities({});
    setReceptionDraft(null);
    listCashMovementReasons().then(setMovementReasons).catch(() => {});
    if (denominations.length === 0) listDenominations().then(setDenominations).catch(() => {});
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

  // A till with billetage confirms the notes it receives: the sender's are proposed, the cashier corrects them if the
  // envelope differs (same total). Without billetage, Confirmar receives at once.
  async function startReception(movement) {
    if (!allActivePos.find((p) => p.id === selectedPosId)?.billetage_enabled) {
      handleReceiveMovement(movement.id);
      return;
    }
    setMovementFormError('');
    try {
      const sent = await getTransferBilletage(movement.id);
      setReceptionDraft({ movement, quantities: Object.fromEntries(sent.map((l) => [l.denomination_id, String(l.quantity)])) });
    } catch (err) {
      setMovementFormError(extractErrorMessage(err, 'Erro ao carregar a billetagem da transferência'));
    }
  }

  async function handleReceiveMovement(movementId, lines = null) {
    setReceivingId(movementId);
    try {
      await receiveCashMovement(movementId, selectedPosId, lines);
      setReceptionDraft(null);
      await loadPendingReceptionsList();
      refreshBalance(selectedPosId);
      refreshPosStock(selectedPosId);
    } catch (err) {
      setMovementFormError(extractErrorMessage(err, 'Erro ao confirmar receção'));
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
      refreshPosStock(selectedPosId);
    } catch (err) {
      setMovementFormError(extractErrorMessage(err, 'Erro ao cancelar transferência'));
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

  // The other till of a transfer, as the selectors name it.
  function posNameById(posId) {
    const pos = allActivePos.find((p) => p.id === posId);
    return pos ? posLabel(pos) : 'outra caixa';
  }

  // A transfer from a till with billetage: the notes sent make the amount (no amount typed apart).
  const transferSourcePos = allActivePos.find((p) => p.id === movementForm.sourcePosId);
  const transferWithBilletage = movementForm.movementType === 'TRANSFERENCIA' && !!transferSourcePos?.billetage_enabled;
  const transferTotal = denominationTotal(denominations, transferQuantities);

  async function handleMovementSubmit(e) {
    e.preventDefault();
    setMovementFormError('');
    setMovementSaving(true);
    try {
      const payload = {
        movement_type: movementForm.movementType,
        amount: transferWithBilletage ? transferTotal : parseFloat(movementForm.amount || '0'),
        reason_id: movementForm.reasonId || null,
        description: movementForm.description || null,
      };
      if (movementForm.movementType === 'TRANSFERENCIA') {
        payload.source_pos_id = movementForm.sourcePosId;
        payload.destination_pos_id = movementForm.otherPosId;
        if (transferWithBilletage) payload.denomination_lines = denominationLines(denominations, transferQuantities);
      } else if (movementForm.movementType === 'ENTRADA_EXTERNA') {
        payload.destination_pos_id = selectedPosId;
      } else {
        payload.source_pos_id = selectedPosId;
      }
      await createCashMovement(payload);
      refreshBalance(selectedPosId);
      refreshPosStock(selectedPosId);
      loadPendingEmissionsList();
      loadPendingReceptionsList();
      setMovementForm({ movementType: 'TRANSFERENCIA', amount: '', sourcePosId: selectedPosId, otherPosId: '', reasonId: '', description: '' });
      setTransferQuantities({});
    } catch (err) {
      setMovementFormError(extractErrorMessage(err, 'Erro ao registar movimento'));
    } finally {
      setMovementSaving(false);
    }
  }

  // Today's date in local time (toISOString gives the UTC day, which in Luanda is still yesterday until 1 am).
  function localToday() {
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  function openDailyReportModal() {
    // Sales are dated with the real day (never the session's), so the report opens on today.
    const defaultDate = localToday();
    setDailyReportDateFrom(defaultDate);
    setDailyReportDateTo(defaultDate);
    setDailyReportModalOpen(true);
    loadDailyReport(defaultDate, defaultDate);
    setReportTab('movimentos');
    loadReportSessions();
  }

  // The movements report (A4): the very lines of the journal shown, for the dates chosen.
  async function printDailyReport() {
    try {
      setPdfBlobUrl(await fetchDailyReportPdfBlob(selectedPosId, dailyReportDateFrom, dailyReportDateTo));
      setPdfFilename('Relatório de movimentos');
      setPdfModalOpen(true);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao gerar o relatório de movimentos'));
    }
  }

  // The closings of the till, newest first - each closed one can print its closing report again.
  async function loadReportSessions() {
    setReportSessionsLoading(true);
    try {
      setReportSessions(await listCashSessions(selectedPosId));
    } catch (err) {
      setReportSessions([]);
    } finally {
      setReportSessionsLoading(false);
    }
  }

  async function printClosingReport(sessionId) {
    try {
      setPdfBlobUrl(await fetchClosingReportPdfBlob(sessionId));
      setPdfFilename('Relatório de fecho');
      setPdfModalOpen(true);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao gerar o relatório de fecho'));
    }
  }

  const shortDateTime = (value) => (value
    ? new Date(value).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    : '-');

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
      const summary = await getSessionSummary(posId);
      setCurrentBalance(summary.balance);
      setSessionSummary(summary);
    } catch (err) {
      // silent - supplementary display, not critical path
    }
  }

  useEffect(() => {
    if (!selectedPosId) return;
    try {
      sessionStorage.setItem(cartStorageKey(selectedPosId), JSON.stringify(cart));
    } catch (err) {
      // storage full or unavailable - the cart still works, just not persisted
    }
  }, [cart, selectedPosId]);

  async function handlePosChange(posId) {
    setSelectedPosId(posId);
    setCart(loadStoredCart(posId));
    setSessionLoading(true);
    try {
      const openSession = await getOpenCashSession(posId);
      setSession(openSession);
      if (openSession) await refreshBalance(posId);
      else setCurrentBalance(null);
      refreshPosStock(posId);
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
      refreshPosStock(selectedPosId);
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
      setClosingNotes('');
      setCloseError('');
      setCloseResult(null);
      openMoedeiroModal('FECHO');
      return;
    }
    setClosingAmountCounted('');
    setClosingNotes('');
    setCloseError('');
    setCloseResult(null);
    setCloseModalOpen(true);
  }

  // The closing report (A4): proposed after the closing when the till asks for it (print_closing_report), and
  // always available - the closing window closes, then the report opens in the PDF viewer.
  const [closingReportProposed, setClosingReportProposed] = useState(false); // read fresh after each closing
  async function finishAndPrintClosingReport(sessionId) {
    finishClosing();
    await printClosingReport(sessionId);
  }

  async function handleCloseAfterBilletage() {
    setCloseSaving(true);
    setMoedeiroError('');
    try {
      const closed = await closeCashSession(session.id, null, closingNotes);
      setMoedeiroModalOpen(false);
      setCloseResult(closed);
      freshPrintConfig().then((cfg) => setClosingReportProposed(!!cfg?.closingReport));
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
      freshPrintConfig().then((cfg) => setClosingReportProposed(!!cfg?.closingReport));
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
    return p.code.toLowerCase().includes(q) || p.name.toLowerCase().includes(q) || medicineSearchText(p).includes(q)
      || (p.barcode || '').includes(q) || (p.sale_units || []).some((u) => (u.barcode || '').includes(q));
  });

  const filteredServices = services.filter((s) => {
    if (!productSearch.trim()) return true;
    const q = productSearch.toLowerCase();
    return (s.code || '').toLowerCase().includes(q) || s.name.toLowerCase().includes(q);
  });

  function imageUrl(path) {
    return path ? API_ORIGIN + path : null;
  }

  // saleUnit: one of the product's sale units (a box of 30) - the line sells that unit at its price, the server takes
  // quantity x factor out of stock. The same product in two units makes two cart lines.
  // The stock the till sells from (its activity's warehouse), reloaded after each sale: an addition beyond it is
  // refused at once when the warehouse allows no negative stock (the server's rule still decides at checkout).
  const [posStock, setPosStock] = useState(null);
  const [openAccountsModalOpen, setOpenAccountsModalOpen] = useState(false);
  const [reservasModalOpen, setReservasModalOpen] = useState(false);
  const [stayAccountId, setStayAccountId] = useState(null); // a hotel stay sent from Reservas to be paid
  const stockLevels = posStock?.stock || {}; // shown on the product cards
  function refreshPosStock(posId) {
    if (!posId) {
      setPosStock(null);
      return;
    }
    getPosStock(posId).then(setPosStock).catch(() => setPosStock(null));
  }

  // THE stock check of the cart: the cart as it would become, product by product, in base units (sale units
  // included), against the stock of the till's warehouse - unless it allows a negative stock. The server still decides.
  function cartStockRefusal(nextCart, productId) {
    const available = posStock?.stock?.[productId];
    if (!productId || available === undefined || (posStock.allow_negative_stock && !posStock.exits_blocked)) return '';
    const factorOf = (line) => Number((line.saleUnits || []).find((u) => u.id === line.saleUnitId)?.factor || 1);
    const lines = nextCart.filter((l) => l.productId === productId);
    const requested = lines.reduce((sum, l) => sum + l.quantity * factorOf(l), 0);
    if (requested <= available + 1e-9) return '';
    return 'Stock insuficiente: ' + Math.max(available, 0).toLocaleString('pt-PT', { maximumFractionDigits: 3 }) + ' ' + (lines[0]?.baseUnit || 'UN') + ' disponíveis';
  }

  function stockRefusal(item, saleUnit) {
    return cartStockRefusal([...cart, {
      productId: item.id, quantity: 1, saleUnitId: saleUnit ? saleUnit.id : null,
      saleUnits: saleUnit ? [saleUnit] : [], baseUnit: item.unit_of_measure_code || 'UN',
    }], item.id);
  }

  function addToCart(item, isService = false, saleUnit = null) {
    if (!isService) {
      const refusal = stockRefusal(item, saleUnit);
      if (refusal) {
        setError(refusal);
        return;
      }
    }
    if (isService && (item.price === null || item.price === undefined)) {
      setError('Este serviço não tem preço definido - configure um preço antes de o vender');
      return;
    }
    const itemKey = (isService ? 'service:' : 'product:') + item.id + (saleUnit ? ':' + saleUnit.id : '');
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
        price: saleUnit ? saleUnit.price : item.price,
        quantity: 1,
        discountPercent: 0,
        vatId: item.vat_id,
        withholdingTaxId: isService ? item.withholding_tax_id : null,
        unit: saleUnit ? saleUnit.unit_of_measure_code : (item.unit_of_measure_code || 'Un'),
        saleUnitId: saleUnit ? saleUnit.id : null,
        priceLevel: 1,  // Preço 1 by default - Preço 2 / 3 chosen on the line (permission)
        basePrices: isService ? null : { price: item.price, price_2: item.price_2, price_3: item.price_3 },
        cost: isService ? null : { average_cost: item.average_cost, purchase_price: item.purchase_price },  // a free price's floor
        baseUnit: item.unit_of_measure_code || 'Un',
        basePrice: item.price,
        saleUnits: isService ? [] : (item.sale_units || []),
        fractional: saleUnit ? !!saleUnit.is_fractional : (!isService && !!item.unit_is_fractional),
        baseFractional: !isService && !!item.unit_is_fractional,
      }];
    });
  }

  // Switches a cart line to another unit of the same product ('base' or one of its sale units): price and unit follow;
  // if the product already has a line in that unit, the quantities merge.
  function changeCartUnit(key, unitValue) {
    const line = cart.find((l) => l.key === key);
    if (!line || !line.productId) return;
    const saleUnit = (line.saleUnits || []).find((u) => u.id === unitValue) || null;
    const newKey = 'product:' + line.productId + (saleUnit ? ':' + saleUnit.id : '');
    if (newKey === key) return;
    const next = cart.some((l) => l.key === newKey)
      ? cart.filter((l) => l.key !== key).map((l) => (l.key === newKey ? { ...l, quantity: l.quantity + line.quantity } : l))
      : cart.map((l) => {
        if (l.key !== key) return l;
        // the price level chosen follows the unit when that unit has it, otherwise back to Preço 1
        const source = saleUnit || l.basePrices;
        const level = l.priceLevel !== FREE && priceOf(source, l.priceLevel || 1) !== null ? (l.priceLevel || 1) : 1;
        return {
          ...l, key: newKey, saleUnitId: saleUnit ? saleUnit.id : null, priceLevel: level, freePrice: '', belowCostOk: false,
          price: priceOf(source, level) ?? (saleUnit ? saleUnit.price : l.basePrice),
          unit: saleUnit ? saleUnit.unit_of_measure_code : l.baseUnit,
          fractional: saleUnit ? !!saleUnit.is_fractional : !!l.baseFractional,
        };
      });
    const refusal = cartStockRefusal(next, line.productId);
    if (refusal) {
      setError(refusal);
      return;
    }
    setCart(next);
  }

  // The price source of a cart line: its sale unit, or the product itself (its base unit).
  function priceSource(line) {
    return (line.saleUnitId ? (line.saleUnits || []).find((u) => u.id === line.saleUnitId) : null) || line.basePrices;
  }

  // Preço 1 / 2 / 3 of a cart line (the server reads the same price on the product when the sale is made).
  function changeCartLevel(key, value) {
    setCart((prev) => prev.map((l) => {
      if (l.key !== key) return l;
      if (value === FREE) return { ...l, priceLevel: FREE, freePrice: String(l.price), belowCostOk: false };  // typed next
      const level = Number(value);
      const price = priceOf(priceSource(l), level);
      return price === null ? l : { ...l, priceLevel: level, price, freePrice: '', belowCostOk: false };
    }));
  }

  // «Preço livre»: the price typed (Kz, without VAT) - the server refuses 0, and a price under the cost unconfirmed.
  function changeCartFreePrice(key, text) {
    setCart((prev) => prev.map((l) => {
      if (l.key !== key) return l;
      const value = parseFloat(String(text).replace(',', '.'));
      return { ...l, freePrice: text, price: value > 0 ? value : 0, belowCostOk: false };
    }));
  }

  // The cost of the unit sold on a cart line (null: not known).
  function lineCost(line) {
    const factor = line.saleUnitId ? Number((line.saleUnits || []).find((u) => u.id === line.saleUnitId)?.factor || 1) : 1;
    return unitCost(line.cost, factor);
  }

  // THE barcode scan: a product's own barcode adds its base unit, the barcode of one of its units or packages adds
  // that unit (through the cart's stock check). An unknown code says so. Returns whether the code was found.
  function scanCode(rawCode) {
    const code = String(rawCode || '').trim();
    if (!code) return false;
    for (const p of products) {
      if (p.barcode && p.barcode === code) {
        addToCart(p);
        return true;
      }
      const saleUnit = (p.sale_units || []).find((u) => u.barcode === code);
      if (saleUnit) {
        addToCart(p, false, saleUnit);
        return true;
      }
    }
    setError('C\u00f3digo n\u00e3o encontrado: ' + code);
    return false;
  }

  // Enter in the search field: a barcode is added; a name search that finds nothing says so; otherwise nothing.
  function scanBarcode() {
    const code = productSearch.trim();
    if (!code) return;
    const isBarcode = products.some((p) => p.barcode === code || (p.sale_units || []).some((u) => u.barcode === code));
    if (isBarcode || filteredProducts.length === 0) {
      if (scanCode(code)) setProductSearch('');
    }
  }

  // A barcode scanner types very fast and ends with Enter: caught anywhere in the till, unless the cursor is in a
  // field (quantity, discount, search...). Under 60 ms between keys, at least 4 characters.
  const scanCodeRef = useRef(scanCode);
  scanCodeRef.current = scanCode;
  const scanBuffer = useRef({ chars: '', last: 0 });
  useEffect(() => {
    function onKey(e) {
      const el = e.target;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)) return;
      const now = Date.now();
      const buf = scanBuffer.current;
      if (now - buf.last > 60) buf.chars = '';
      buf.last = now;
      if (e.key === 'Enter') {
        if (buf.chars.length >= 4) {
          e.preventDefault();
          scanCodeRef.current(buf.chars);
        }
        buf.chars = '';
        return;
      }
      if (e.key.length === 1) buf.chars += e.key;
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  function updateCartQuantity(key, quantity) {
    if (quantity <= 0) {
      setCart((prev) => prev.filter((line) => line.key !== key));
      return;
    }
    applyCartQuantity(key, quantity);
  }

  // A higher quantity must stay within the stock (cartStockRefusal); a lower one always passes.
  function applyCartQuantity(key, quantity) {
    const line = cart.find((l) => l.key === key);
    if (!line) return;
    const next = cart.map((l) => (l.key === key ? { ...l, quantity } : l));
    const refusal = quantity > line.quantity ? cartStockRefusal(next, line.productId) : '';
    if (refusal) {
      setError(refusal);
      return;
    }
    setCart(next);
  }

  // A fractional line (1.250 kg) takes its quantity typed in, committed on blur / Enter; an empty or zero entry never
  // removes the line (only the - button does).
  function setCartQuantityExact(key, value) {
    const quantity = parseFloat(String(value).replace(',', '.'));
    if (!(quantity > 0)) return;
    applyCartQuantity(key, quantity);
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
  // Farmácia: the receita of a sale holding a medicine on prescription - asked before the sale is confirmed.
  const [prescriptionPolicy, setPrescriptionPolicy] = useState('OBRIGATORIA');
  const [pharmacyEnabled, setPharmacyEnabled] = useState(false);
  useEffect(() => {
    getPharmacyContext().then((c) => { setPrescriptionPolicy(c.prescription_policy || 'OBRIGATORIA'); setPharmacyEnabled(!!c.enabled); }).catch(() => {});
  }, []);
  // Farmácia: a sale shared with an insurer (comparticipação) - the patient pays his part, the insurer gets a Fatura
  // for the rest (insurance_service). { insurerId, name, pct, medicinesOnly, cardNumber, beneficiaryName } or null.
  const [insurance, setInsurance] = useState(null);
  const [insuranceForm, setInsuranceForm] = useState(null); // the open "Seguradora" modal's fields
  const [prescription, setPrescription] = useState(null);
  const [prescriptionNeed, setPrescriptionNeed] = useState(null);
  function startConfirmation() {
    setPayments([]);
    setCashGiven('');
    const need = selectedInvoiceType === 'PRO_FORMA' ? null : prescriptionNeedOf(cart, Object.fromEntries(products.map((p) => [p.id, p])));
    if (need) { setPrescriptionNeed(need); return; }
    setPrescription(null);
    setSaleConfirmModalOpen(true);
  }
  const [selectedInvoiceType, setSelectedInvoiceType] = useState('FACTURA_RECIBO');
  const { typeOptions: posTypeOptions, liquidationOptions: posLiquidationOptions, defaultPaidType } = usePosDocumentTypes();
  const ruleOf = useDocumentRules();
  // behaviour of the selected document type, from the catalog (paid on issue: payments at the till)
  const paidOnIssue = ruleOf(selectedInvoiceType, 'paid_on_issue');
  const billsLater = !paidOnIssue && selectedInvoiceType !== 'PRO_FORMA';
  const requiresPaymentTerm = ruleOf(selectedInvoiceType, 'requires_payment_term');
  const requiresCustomer = ruleOf(selectedInvoiceType, 'requires_customer');
  // offered = the catalog allows the type here AND the user may issue it (pro-forma: pos:proforma, a sale: pos:checkout)
  const visibleTypeOptions = posTypeOptions.filter((o) => {
    if (o.value === 'PRO_FORMA') return can('pos:proforma');
    // a sale needs pos:checkout; a document billed later (a Fatura) also needs pos:checkout_ft
    return can('pos:checkout') && (ruleOf(o.value, 'paid_on_issue') || can('pos:checkout_ft'));
  });
  useEffect(() => {
    if (visibleTypeOptions.length && !visibleTypeOptions.some((o) => o.value === selectedInvoiceType)) setSelectedInvoiceType(visibleTypeOptions[0].value);
  }, [visibleTypeOptions.map((o) => o.value).join(','), selectedInvoiceType]);
  useEffect(() => {
    if (!posLiquidationOptions.some((o) => o.value === liquidationTargetType)) setLiquidationTargetType(posLiquidationOptions[0].value);
  }, [posLiquidationOptions, liquidationTargetType]);
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

  const [printConfigByPos, setPrintConfigByPos] = useState({}); // each cash point -> its printing after a sale
  const [printChoice, setPrintChoice] = useState(false); // ticket and A4 both allowed: the cashier picks one

  // a withholding for a real pessoa coletiva only - never the Consumidor final (NIF 999999999)
  const isCustomerPessoaColetiva = isPessoaColetiva(customers.find((c) => c.id === selectedCustomerId));

  // With an insurer: a covered line costs the patient his part of the price (the insurer's to the cent, as the server).
  const productsById = useMemo(() => Object.fromEntries(products.map((p) => [p.id, p])), [products]);
  function isCovered(line) {
    if (!insurance) return false;
    return !insurance.medicinesOnly || !!(line.productId && productsById[line.productId]?.is_medicine);
  }
  function insurerUnit(line) {
    return isCovered(line) ? round2(line.price * insurance.pct / 100) : 0;
  }
  const insurerShare = cart.reduce((acc, line) => {
    const vatRate = vatRates.find((v) => v.id === line.vatId)?.rate || 0;
    const sub = insurerUnit(line) * line.quantity * (1 - line.discountPercent / 100);
    return acc + sub * (1 + vatRate / 100);
  }, 0);

  const cartCalculation = cart.reduce((acc, line) => {
    const vatRate = vatRates.find((v) => v.id === line.vatId)?.rate || 0;
    const grossLine = (line.price - insurerUnit(line)) * line.quantity;
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
  // what the customer pays: the total minus the withholding he keeps (the same on the pro-forma and on the invoice it becomes)
  const paymentDueTotal = paymentMode === 'liquidation' && liquidationTarget ? round2(Number(liquidationTarget.total) - Number(liquidationTarget.retention_total || 0)) : cartTotal;

  function insurancePayload() {
    if (!insurance || selectedInvoiceType === 'PRO_FORMA') return null;
    return { insurer_id: insurance.insurerId, card_number: insurance.cardNumber, beneficiary_name: insurance.beneficiaryName || null, coverage_pct: insurance.pct };
  }

  const insurers = customers.filter((c) => c.is_insurer && c.is_active !== false);
  function openInsurance() {
    setInsuranceForm(insurance
      ? { insurerId: insurance.insurerId, pct: String(insurance.pct), cardNumber: insurance.cardNumber, beneficiaryName: insurance.beneficiaryName || '' }
      : { insurerId: '', pct: '', cardNumber: '', beneficiaryName: '' });
  }
  function applyInsurance() {
    const insurer = insurers.find((c) => c.id === insuranceForm.insurerId);
    setInsurance({
      insurerId: insurer.id, name: insurer.name, pct: parseFloat(insuranceForm.pct), medicinesOnly: insurer.insurer_medicines_only !== false,
      cardNumber: insuranceForm.cardNumber.trim(), beneficiaryName: insuranceForm.beneficiaryName.trim(),
    });
    setInsuranceForm(null);
  }

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
        { paymentTermId: ftPaymentTermId || null, dueDate: ftDueDate || null, prescription, insurance: insurancePayload() },
      );
      setLastInvoice(invoice);
      setSuccessModalOpen(true);

      afterSalePrint(invoice);
      refreshBalance(selectedPosId);
      refreshPosStock(selectedPosId);
      setCart([]);
      setSelectedCustomerId('');
      setGlobalDiscountPercent(0);
      setPrescription(null);
      setInsurance(null);
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

      afterSalePrint(proForma);
      refreshBalance(selectedPosId);
      refreshPosStock(selectedPosId);
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
    setDocsTab('docs');
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
      setRecentInvoices(await listRecentIssuedInvoices(selectedPosId));
    } catch (err) {
      // silent - the pro-forma section above already reports errors; this is a supplementary list
    } finally {
      setRecentInvoicesLoading(false);
    }
  }

  // Printing after a sale, as this cash point asks: off = nothing (as before); one format = it prints at once;
  // both = the cashier picks one in the success window.
  // The printing settings of the till are read again before each printing: a manager may change them during the
  // day, and the till follows from the next sale on - no reload of the page. On failure, the last known settings.
  async function freshPrintConfig() {
    const known = printConfigByPos[selectedPosId];
    const pos = allActivePos.find((x) => x.id === selectedPosId);
    if (!pos) return known;
    try {
      const p = ((await listPointsOfSale(pos.activity_id)) || []).find((x) => x.id === selectedPosId);
      if (!p) return known;
      const cfg = { on: !!p.print_after_sale, ticket: p.print_ticket !== false, a4: !!p.print_a4, closingReport: !!p.print_closing_report };
      setPrintConfigByPos((prev) => ({ ...prev, [selectedPosId]: cfg }));
      return cfg;
    } catch {
      return known;
    }
  }

  async function afterSalePrint(invoice) {
    const cfg = await freshPrintConfig();
    if (!invoice || !cfg || !cfg.on) return;
    if (cfg.ticket && cfg.a4) {
      setPrintChoice(true);
      return;
    }
    printDocument(invoice, cfg.ticket ? 'thermal' : 'a4');
  }

  // Opens the document in THE document viewer (the same one as 'Consultar documentos'), ready to print.
  function printDocument(invoice, format) {
    openPdfViewer(invoice.id, format, invoice.series + '-' + invoice.number + (format === 'thermal' ? ' (Ticket)' : ' (A4)'));
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
    setPaymentMode('liquidation');
    setLiquidationTarget(proForma);
    setLiquidationTargetType(posLiquidationOptions.some((o) => o.value === defaultPaidType) ? defaultPaidType : posLiquidationOptions[0].value);
    setPayments([]);
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

  // the change: what the customer handed over for the cash part, minus that cash part
  const cashPayment = payments.find((p) => posPaymentMethods.find((m) => m.id === p.paymentMethodId)?.is_cash);
  const cashPart = parseFloat(cashPayment?.amount) || 0;
  const cashHanded = parseFloat(cashGiven) || 0;
  const cashChange = cashPayment && cashHanded > cashPart ? round2(cashHanded - cashPart) : 0;

  // Ecrã do cliente: what the customer sees on the till's second monitor follows the cart and the payment
  const customerDisplay = useCustomerDisplay(selectedPosId, pointsOfSale.find((p) => p.id === selectedPosId)?.activity_id);
  const customerChange = cashChange;
  const customerView = paymentMode !== 'sale' || cart.length === 0 ? { type: 'idle' } : {
    type: 'sale',
    lines: cart.map((line) => {
      const vatRate = vatRates.find((v) => v.id === line.vatId)?.rate || 0;
      const unit = line.saleUnitId ? line.saleUnits?.find((u) => u.id === line.saleUnitId)?.unit_of_measure_code : line.baseUnit;
      const total = (line.price - insurerUnit(line)) * line.quantity * (1 - line.discountPercent / 100) * (1 + vatRate / 100);
      return { key: line.key, name: line.name, quantity: line.quantity, unit: unit || '', total: round2(total) };
    }),
    discount: round2(globalDiscountAmount),
    retention: round2(cartCalculation.retention),
    total: cartTotal,
    received: round2(paymentsTotal - cashPart + Math.max(cashHanded, cashPart)),
    change: round2(customerChange),
  };
  const customerViewKey = JSON.stringify(customerView);
  useEffect(() => {
    if (customerDisplay.allowed) customerDisplay.send(JSON.parse(customerViewKey));
  }, [customerViewKey, customerDisplay.allowed, customerDisplay.send]);

  function showSaleDoneToCustomer(invoice, change) {
    customerDisplay.send({
      type: 'done',
      document: invoice.series ? invoice.series + '/' + invoice.number : '',
      total: Number(invoice.total),
      change: round2(change),
    });
  }

  async function handleConfirmSale() {
    setCheckoutError('');
    setCheckoutSaving(true);
    try {
      const validPayments = payments.filter((p) => parseFloat(p.amount) > 0);
      if (paymentMode === 'liquidation') {
        const invoice = await liquidatePendingInvoice(selectedPosId, liquidationTarget.id, liquidationTargetType, validPayments);
        showSaleDoneToCustomer(invoice, customerChange);
        setLastInvoice(invoice);
        setPaymentModalOpen(false);
        setSuccessModalOpen(true);

        afterSalePrint(invoice);
      refreshBalance(selectedPosId);
      refreshPosStock(selectedPosId);
      listPendingProFormas().then(setPendingProFormas).catch(() => {});
      } else {
        const invoice = await checkout(
          selectedPosId, selectedCustomerId || null,
          cart,
          validPayments,
          selectedInvoiceType,
          globalDiscountPercent,
          { prescription, insurance: insurancePayload() },
        );
        showSaleDoneToCustomer(invoice, customerChange);
        setLastInvoice(invoice);
        setSuccessModalOpen(true);

        afterSalePrint(invoice);
      refreshBalance(selectedPosId);
      refreshPosStock(selectedPosId);
        setCart([]);
        setSelectedCustomerId('');
        setGlobalDiscountPercent(0);
        setPayments([]);
        setPrescription(null);
        setInsurance(null);
      }
    } catch (err) {
      setCheckoutError(extractErrorMessage(err, paymentMode === 'liquidation' ? 'Erro ao liquidar pro-forma' : 'Erro ao finalizar venda'));
    } finally {
      setCheckoutSaving(false);
    }
  }

  function closePaymentModal() {

    setPrintChoice(false);
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
          <p className="text-text-muted text-sm">Peca ao gestor para associar uma caixa a este utilizador (Atividades, definicoes da empresa) antes de operar</p>
        </div>
      </main>
    );
  }

  // Sidebar drawers: one at a time. The open one is the active icon; clicking it again closes it.
  const activeSideDrawer = proFormaModalOpen ? 'docs' : articlesModalOpen ? 'articles' : moedeiroModalOpen ? 'moedeiro'
    : movementModalOpen ? 'movement' : dailyReportModalOpen ? 'report' : openAccountsModalOpen ? 'accounts'
    : reservasModalOpen ? 'reservas' : null;
  function closeSideDrawers() {
    setProFormaModalOpen(false);
    setArticlesModalOpen(false);
    setMoedeiroModalOpen(false);
    setMovementModalOpen(false);
    setDailyReportModalOpen(false);
    setOpenAccountsModalOpen(false);
    setReservasModalOpen(false);
    setStayAccountId(null);
  }
  // A document issued outside the cart (an account closed, a passage sold at the entry) ends like a direct sale:
  // the balance, the Documento gerado window and the printing of the till.
  async function showIssuedDocument(invoiceId) {
    refreshBalance(selectedPosId);
    if (!invoiceId) return;
    try {
      const invoice = await getInvoiceDetail(invoiceId);
      setLastInvoice(invoice);
      setSuccessModalOpen(true);
      afterSalePrint(invoice);
    } catch {
      // the invoice exists all the same: Consultar documentos still shows it
    }
  }

  function toggleSideDrawer(key, open) {
    const wasActive = activeSideDrawer === key;
    closeSideDrawers();
    if (!wasActive) open();
  }

  return (
    <div className="pl-16">
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      {/* Caixa actions: a fixed icon sidebar between the navbar and the footer - labels on hover; each opens a drawer. */}
      <aside className="fixed left-0 top-14 bottom-11 z-40 w-16 bg-bg-elevated border-r border-border flex flex-col items-center gap-2 py-3">
        <button onClick={() => toggleSideDrawer('docs', openProFormaSearchModal)} className={'group relative w-11 h-11 flex items-center justify-center rounded-lg border hover:border-accent hover:bg-accent/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer ' + (activeSideDrawer === 'docs' ? 'border-accent bg-accent/5' : 'border-accent/20 bg-bg-inset')}>
          <FileSearch size={18} className="text-accent" />
          <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-md bg-bg-elevated border border-border px-2.5 py-1 text-[12px] text-text-primary shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-50">Consultar documentos</span>
        </button>
        <button onClick={() => toggleSideDrawer('articles', () => setArticlesModalOpen(true))} className={'group relative w-11 h-11 flex items-center justify-center rounded-lg border hover:border-accent hover:bg-accent/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer ' + (activeSideDrawer === 'articles' ? 'border-accent bg-accent/5' : 'border-accent/20 bg-bg-inset')}>
          <ShoppingCart size={18} className="text-accent" />
          <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-md bg-bg-elevated border border-border px-2.5 py-1 text-[12px] text-text-primary shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-50">Consultar artigos</span>
        </button>
        <button onClick={() => toggleSideDrawer('moedeiro', () => openMoedeiroModal('FECHO'))} disabled={!session || !can('moedeiro:record')} className={'group relative w-11 h-11 flex items-center justify-center rounded-lg border hover:border-accent hover:bg-accent/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer ' + (activeSideDrawer === 'moedeiro' ? 'border-accent bg-accent/5' : 'border-accent/20 bg-bg-inset')}>
          <Coins size={18} className="text-accent" />
          <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-md bg-bg-elevated border border-border px-2.5 py-1 text-[12px] text-text-primary shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-50">Moedeiro</span>
        </button>
        <button onClick={() => toggleSideDrawer('movement', openMovementModal)} disabled={!selectedPosId || !can('tesouraria:view')} className={'group relative w-11 h-11 flex items-center justify-center rounded-lg border hover:border-accent hover:bg-accent/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer ' + (activeSideDrawer === 'movement' ? 'border-accent bg-accent/5' : 'border-accent/20 bg-bg-inset')}>
          <ArrowLeftRight size={18} className="text-accent" />
          <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-md bg-bg-elevated border border-border px-2.5 py-1 text-[12px] text-text-primary shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-50">Operações de Caixa</span>
        </button>
        <button onClick={() => toggleSideDrawer('report', openDailyReportModal)} disabled={!selectedPosId || !can('tesouraria:daily_report')} className={'group relative w-11 h-11 flex items-center justify-center rounded-lg border hover:border-accent hover:bg-accent/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer ' + (activeSideDrawer === 'report' ? 'border-accent bg-accent/5' : 'border-accent/20 bg-bg-inset')}>
          <FileText size={18} className="text-accent" />
          <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-md bg-bg-elevated border border-border px-2.5 py-1 text-[12px] text-text-primary shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-50">Relatórios</span>
        </button>
        <button onClick={() => toggleSideDrawer('accounts', () => setOpenAccountsModalOpen(true))} disabled={!selectedPosId || !can('open_accounts:view')} className={'group relative w-11 h-11 flex items-center justify-center rounded-lg border hover:border-accent hover:bg-accent/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer ' + (activeSideDrawer === 'accounts' ? 'border-accent bg-accent/5' : 'border-accent/20 bg-bg-inset')}>
          <OpenAccountsIcon size={18} className="text-accent" />
          <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-md bg-bg-elevated border border-border px-2.5 py-1 text-[12px] text-text-primary shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-50">Contas abertas</span>
        </button>
        {/* Reservations of the till's activity (hotel reception, spa...): only where the sector has bookings. */}
        {can('bookings:view') && (
        <button onClick={() => toggleSideDrawer('reservas', () => setReservasModalOpen(true))} disabled={!selectedPosId} className={'group relative w-11 h-11 flex items-center justify-center rounded-lg border hover:border-accent hover:bg-accent/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer ' + (activeSideDrawer === 'reservas' ? 'border-accent bg-accent/5' : 'border-accent/20 bg-bg-inset')}>
          <CalendarClock size={18} className="text-accent" />
          <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-md bg-bg-elevated border border-border px-2.5 py-1 text-[12px] text-text-primary shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-50">Reservas</span>
        </button>
        )}
        {customerDisplay.allowed && (
        <button onClick={customerDisplay.open} disabled={!selectedPosId} className="group relative w-11 h-11 flex items-center justify-center rounded-lg border border-accent/20 bg-bg-inset hover:border-accent hover:bg-accent/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer">
          <MonitorUp size={18} className="text-accent" />
          <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-md bg-bg-elevated border border-border px-2.5 py-1 text-[12px] text-text-primary shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-50">Ecrã do cliente - arraste-o para o 2.º monitor</span>
        </button>
        )}
      </aside>
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
          <Wallet size={22} className="text-accent" />
          Caixa
        </h2>
        <div className="flex items-center gap-2 flex-wrap">
          {session && currentBalance !== null && (
            <div
              className="relative w-96 max-w-[90vw] flex items-center gap-2 bg-bg-elevated border border-border rounded-md px-4 py-2 cursor-pointer select-none"
              onPointerEnter={(e) => e.pointerType === 'mouse' && setBalanceDetailOpen(true)}
              onPointerLeave={(e) => e.pointerType === 'mouse' && setBalanceDetailOpen(false)}
              onClick={(e) => e.nativeEvent.pointerType !== 'mouse' && setBalanceDetailOpen((open) => !open)}
            >
              <Wallet size={15} className="text-accent" />
              <span className="text-text-muted text-[12px]">Numerário na gaveta</span>
              <span className="ml-auto font-mono font-semibold text-text-primary text-[15px]">{formatKz(currentBalance)} Kz</span>
              {sessionSummary?.pending_in > 0 && (
                <span title="Transferências por confirmar" className="w-2 h-2 rounded-full bg-amber-500" />
              )}
              <span className="text-text-muted text-[11px]">▾</span>
              {/* only the cash to count is shown; everything received in the session, on hover or tap */}
              {balanceDetailOpen && sessionSummary && (
                <div className="absolute left-0 right-0 top-full mt-2 z-30 bg-bg-elevated border border-border rounded-md shadow-lg p-3 flex flex-col gap-1.5 text-[12px] cursor-default">
                  <p className="text-text-muted uppercase tracking-wide text-[10px] mb-0.5">Recebido nesta sessão</p>
                  {(sessionSummary.by_method || []).length === 0 && <p className="text-text-muted">Nenhum recebimento</p>}
                  {(sessionSummary.by_method || []).map((m) => (
                    <div key={m.code} className="flex justify-between gap-3">
                      <span className="text-text-secondary">{m.label || m.name}{!m.is_cash && <span className="text-text-muted"> · fora da gaveta</span>}</span>
                      <span className="font-mono text-text-primary">{formatKz(m.amount)} Kz</span>
                    </div>
                  ))}
                  <div className="flex justify-between gap-3 border-t border-border pt-1.5 font-semibold text-text-primary">
                    <span>Total recebido</span><span className="font-mono">{formatKz(sessionSummary.total_received)} Kz</span>
                  </div>
                  <p className="text-text-muted uppercase tracking-wide text-[10px] mt-1.5 mb-0.5">Gaveta</p>
                  {[
                    ['Fundo de abertura', sessionSummary.opening_amount],
                    ['+ Numerário recebido', sessionSummary.cash_sales],
                    ['+ Transferências recebidas', sessionSummary.transfers_in],
                    ['+ Entradas', sessionSummary.entries],
                    ['- Transferências enviadas', sessionSummary.transfers_out],
                    ['- Saídas', sessionSummary.exits],
                  ].filter(([label, value], i) => i < 2 || value).map(([label, value]) => (
                    <div key={label} className="flex justify-between gap-3 text-text-secondary">
                      <span>{label}</span><span className="font-mono">{formatKz(value)} Kz</span>
                    </div>
                  ))}
                  <div className="flex justify-between gap-3 border-t border-border pt-1.5 font-semibold text-text-primary">
                    <span>Numerário na gaveta</span><span className="font-mono">{formatKz(currentBalance)} Kz</span>
                  </div>
                  {sessionSummary.pending_in > 0 && (
                    <div className="flex justify-between gap-3 text-amber-500 [.light_&]:text-amber-700">
                      <span>A receber (por confirmar)</span><span className="font-mono">{formatKz(sessionSummary.pending_in)} Kz</span>
                    </div>
                  )}
                </div>
              )}
            </div>
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
          {pointsOfSale.length > 0 && (
            <div className="w-[28rem] max-w-full">
              <Select singleLine disabled={!isGestor || pointsOfSale.length < 2}
                value={selectedPosId}
                onChange={handlePosChange}
                options={pointsOfSale.map((p) => ({ value: p.id, label: posLabel(p) }))}
                placeholder="Ponto de venda"
              />
            </div>
          )}
        </div>
      </div>


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
          {(() => {
            const time = new Date(session.opened_at).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' });
            // A session of a previous day still sells (closing is a user's choice), but a daily count is advised.
            const old = session.business_date && session.business_date < localToday();
            return (
              <p className={'text-[12px] font-mono mb-5 ' + (old ? 'text-amber-500 [.light_&]:text-amber-700' : 'text-text-muted')}>
                {old
                  ? 'Sess\u00e3o aberta desde ' + new Date(session.business_date + 'T00:00:00').toLocaleDateString('pt-PT') + ' \u00e0s ' + time + ' \u2013 recomenda-se fechar e contar a caixa'
                  : 'Sess\u00e3o aberta \u00e0s ' + time}
              </p>
            );
          })()}

          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_440px] gap-5">
            <div className="min-w-0">
              <div className="relative mb-4">
                <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
                <input
                  type="text"
                  placeholder="Pesquisar produto..."
                  value={productSearch}
                  onChange={(e) => setProductSearch(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); scanBarcode(); } }}
                  className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
                />
              </div>

              <div className="flex items-center gap-2 mb-4 overflow-x-auto scrollbar-thin pb-1">
                {canViewProductsUi && (
                  <>
                    <button
                      onClick={() => setActiveCategoryId('all')}
                      className={'shrink-0 px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (activeCategoryId === 'all' ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
                    >
                      Todos
                    </button>
                    {categories.filter((c) => products.some((p) => p.category_id === c.id)).map((c) => (
                      <button
                        key={c.id}
                        onClick={() => setActiveCategoryId(c.id)}
                        className={'shrink-0 px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (activeCategoryId === c.id ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
                      >
                        {c.name}
                      </button>
                    ))}
                  </>
                )}
                {services.length > 0 && (
                  <button
                    onClick={() => setActiveCategoryId('services')}
                    className={'shrink-0 px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (activeCategoryId === 'services' ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
                  >
                    Serviços
                  </button>
                )}
              </div>


              {activeCategoryId === 'services' ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-2.5 max-h-[520px] overflow-y-auto scrollbar-thin pr-1">
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
                <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-2.5 max-h-[520px] overflow-y-auto scrollbar-thin pr-1">
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
                        {p.is_medicine && (
                          <p className="text-[11px] text-text-muted -mt-1 mb-1.5 line-clamp-1 flex items-center gap-1" title={medicineSummary(p)}>
                            {p.cold_storage && <Snowflake size={11} className="text-sky-400 shrink-0" />}
                            {p.dispensing_regime && p.dispensing_regime !== 'LIVRE' && <span className={'font-semibold ' + (p.dispensing_regime === 'RECEITA_ESPECIAL' ? 'text-danger' : 'text-amber-500 [.light_&]:text-amber-700')}>Rx</span>}
                            <span className="truncate">{medicineSummary(p)}</span>
                          </p>
                        )}
                        <div className="flex items-end justify-between">
                          <p className="font-mono text-accent text-[13px] font-semibold">{formatKz(p.price)} Kz</p>
                          {p.managed_by_stock && (
                            <span className={'text-[10px] font-mono ' + ((stockLevels[p.id] ?? 0) <= 0 ? 'text-danger' : (stockLevels[p.id] ?? 0) <= (p.min_stock_threshold || 0) ? 'text-accent' : 'text-text-muted')}>
                              {stockLevels[p.id] ?? 0} {p.unit_of_measure_code || 'Un'}
                            </span>
                          )}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div ref={cartRef} style={cartHeight ? { height: cartHeight + 'px' } : undefined} className="bg-bg-elevated border border-border rounded-lg p-4 flex flex-col min-h-0">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <ShoppingCart size={16} className="text-accent" />
                  <div className="flex items-center gap-2"><p className="font-display font-semibold text-text-primary text-sm">Carrinho</p><button type="button" onClick={() => { setCart([]); setSelectedCustomerId(''); }} title="Nova venda" className="flex items-center gap-1 text-accent hover:text-accent-hover text-[12px] font-medium cursor-pointer"><Plus size={13} /> Novo</button></div>
                </div>
                <div className="w-64">
                  <Select
                    compact
                    value={selectedInvoiceType}
                    onChange={setSelectedInvoiceType}
                    options={visibleTypeOptions}
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

              {pharmacyEnabled && insurers.length > 0 && selectedInvoiceType !== 'PRO_FORMA' && (
                <div className="mb-3 -mt-1">
                  {insurance ? (
                    <div className="flex items-center justify-between gap-2 border border-accent/40 bg-accent/5 rounded-md px-3 py-2">
                      <button type="button" onClick={openInsurance} className="text-left text-[12px] text-text-primary cursor-pointer min-w-0">
                        <span className="font-semibold">{insurance.name} · {insurance.pct}%</span>
                        <span className="block text-text-muted truncate">Cartão n.º {insurance.cardNumber}{insurance.beneficiaryName ? ' · ' + insurance.beneficiaryName : ''}</span>
                      </button>
                      <button type="button" onClick={() => setInsurance(null)} aria-label="Retirar seguradora" className="shrink-0 text-text-muted hover:text-danger cursor-pointer"><X size={15} /></button>
                    </div>
                  ) : (
                    <button type="button" onClick={openInsurance} className="flex items-center gap-1 text-accent hover:text-accent-hover text-[12px] font-medium cursor-pointer">
                      <Plus size={13} /> Seguradora / convénio
                    </button>
                  )}
                </div>
              )}

              {cart.length === 0 ? (
                <p className="flex-1 text-text-muted text-[12px] text-center py-8">Carrinho vazio</p>
              ) : (
                <div className="mb-4 flex-1 min-h-0 overflow-y-auto scrollbar-thin border border-border rounded-md">
                  <table className="w-full text-[12px]">
                    <thead className="sticky top-0 bg-bg-inset z-10">
                      <tr className="text-[10.5px] uppercase tracking-wide text-text-muted">
                        <th className="text-left font-medium px-2.5 py-2">Artigo</th>
                        <th className="text-center font-medium px-1 py-2 w-[92px]">Qtd</th>
                        <th className="text-right font-medium px-2 py-2 w-[96px]">Preço</th>
                        <th className="text-right font-medium px-2.5 py-2 w-[104px]">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cart.map((line) => {
                        const lineTotal = line.price * line.quantity * (1 - (line.discountPercent || 0) / 100);
                        return (
                          <Fragment key={line.key}>
                            <tr className="border-t border-border">
                              <td className="px-2.5 py-2 align-top">
                                <p className="font-medium text-text-primary leading-tight">{line.name}</p>
                                <div className="flex items-center gap-2 mt-1">
                                  <button
                                    onClick={() => setExpandedDiscountKey(expandedDiscountKey === line.key ? null : line.key)}
                                    className={'text-[10px] font-semibold px-1.5 py-0.5 rounded cursor-pointer transition-colors ' + (line.discountPercent > 0 ? 'text-accent bg-accent/10' : 'text-text-muted hover:text-accent hover:bg-accent/10')}
                                    title="Aplicar desconto"
                                  >
                                    {line.discountPercent > 0 ? `-${line.discountPercent}%` : '% desc.'}
                                  </button>
                                  <button onClick={() => removeFromCart(line.key)} title="Remover" className="text-text-muted hover:text-danger cursor-pointer">
                                    <Trash2 size={12} />
                                  </button>
                                </div>

                              </td>
                              <td className="px-1 py-2 align-top">
                                <div className="flex items-center justify-center gap-1">
                                  <button onClick={() => updateCartQuantity(line.key, line.quantity - 1)} className="w-6 h-6 flex items-center justify-center rounded border border-border text-text-muted hover:text-text-primary hover:border-accent cursor-pointer">
                                    <Minus size={11} />
                                  </button>
                                  {line.fractional ? (
  <input key={line.key + ':' + line.quantity} type="text" inputMode="decimal" defaultValue={line.quantity} onBlur={(e) => setCartQuantityExact(line.key, e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }} className="w-16 bg-bg-inset border border-border rounded px-1.5 py-0.5 text-center font-mono text-[12px] text-text-primary outline-none focus:border-accent" />
) : (
  <span className="min-w-[28px] text-center font-mono text-text-primary">{line.quantity}</span>
)}
                                  <button onClick={() => updateCartQuantity(line.key, line.quantity + 1)} className="w-6 h-6 flex items-center justify-center rounded border border-border text-text-muted hover:text-text-primary hover:border-accent cursor-pointer">
                                    <Plus size={11} />
                                  </button>
                                </div>
                                {line.saleUnits && line.saleUnits.length > 0 ? (
  <div className="mt-1"><Select compact value={line.saleUnitId || 'base'} onChange={(v) => changeCartUnit(line.key, v)} options={[{ value: 'base', label: line.baseUnit }, ...line.saleUnits.map((u) => ({ value: u.id, label: u.unit_of_measure_code }))]} /></div>
) : (
  <p className="text-center text-[10px] text-text-muted mt-0.5">{line.unit}</p>
)}
                              </td>
                              <td className="px-2 py-2 align-top text-right font-mono text-text-muted whitespace-nowrap">{formatKz(line.price)}</td>
                              <td className="px-2.5 py-2 align-top text-right font-mono text-text-primary font-medium whitespace-nowrap">{formatKz(lineTotal)}</td>
                            </tr>
                            {line.productId && hasPriceChoice(priceSource(line), tillPrices) && (
                              <tr>
                                <td colSpan={4} className="px-2.5 pb-2">
                                  {/* Preço 1 / 2 / 3: the seller sees what each price is worth; «Preço livre»: typed */}
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <div className="w-[210px]">
                                      <Select compact value={String(line.priceLevel || 1)} onChange={(v) => changeCartLevel(line.key, v)} options={levelOptions(priceSource(line), tillPrices)} />
                                    </div>
                                    {line.priceLevel === FREE && (
                                      <input type="text" inputMode="decimal" value={line.freePrice} onChange={(e) => changeCartFreePrice(line.key, e.target.value)}
                                        placeholder="Preço (Kz, sem IVA)" autoFocus
                                        className="w-32 bg-bg-inset border border-border rounded px-2 py-1 text-right font-mono text-[12px] text-text-primary outline-none focus:border-accent" />
                                    )}
                                  </div>
                                  {line.priceLevel === FREE && lineCost(line) !== null && line.price > 0 && line.price < lineCost(line) && (
                                    <label className="flex items-center gap-1.5 mt-1.5 text-[11px] text-amber-500 [.light_&]:text-amber-700 cursor-pointer">
                                      <input type="checkbox" checked={!!line.belowCostOk} onChange={(e) => setCart((prev) => prev.map((l) => (l.key === line.key ? { ...l, belowCostOk: e.target.checked } : l)))} className="accent-amber-500" />
                                      Abaixo do custo ({formatKz(lineCost(line))}) - confirmo este preço
                                    </label>
                                  )}
                                </td>
                              </tr>
                            )}
                            {expandedDiscountKey === line.key && (
                              <tr className="border-t border-border/50">
                                <td colSpan={4} className="px-2.5 pb-2 pt-1">
                                  <div className="flex items-center gap-1.5">
                                    <span className="text-[11px] text-text-muted">Desconto:</span>
                                    <input
                                      type="number" min="0" max="100" step="1"
                                      value={line.discountPercent || ''}
                                      onChange={(e) => updateCartDiscount(line.key, e.target.value)}
                                      placeholder="0"
                                      autoFocus
                                      className="w-16 bg-bg-inset border border-border rounded px-1.5 py-0.5 text-[12px] text-text-primary font-mono outline-none focus:border-accent transition-colors"
                                    />
                                    <span className="text-[11px] text-text-muted">%</span>
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
                    <span className="text-text-muted text-[12px]">Retenção</span>
                    <span className="font-mono text-danger text-[12px]">-{formatKz(cartCalculation.retention)} Kz</span>
                  </div>
                )}
                {insurance && insurerShare > 0 && (
                  <div className="flex items-center justify-between">
                    <span className="text-text-muted text-[12px]">{insurance.name} ({insurance.pct}%) - Fatura à parte</span>
                    <span className="font-mono text-accent text-[12px]">{formatKz(insurerShare)} Kz</span>
                  </div>
                )}
                <div className="flex items-center justify-between pt-1.5 border-t border-border">
                  <span className="text-text-primary text-[13px] font-medium">{insurance ? 'Utente paga' : 'Total'}</span>
                  <span className="font-mono font-semibold text-text-primary text-lg">{formatKz(cartTotal)} Kz</span>
                </div>
              </div>


              <button
                onClick={startConfirmation}
                disabled={cart.length === 0 || proFormaSaving || checkoutSaving || (selectedInvoiceType === 'PRO_FORMA' ? !can('pos:proforma') : !can('pos:checkout'))}
                className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
              >
                {(proFormaSaving || checkoutSaving) && <Loader2 size={16} className="animate-spin" />}
                {selectedInvoiceType === 'PRO_FORMA' ? (proFormaSaving ? 'A gerar...' : 'Gerar pro-forma') : billsLater ? (checkoutSaving ? 'A faturar...' : 'Faturar') : (checkoutSaving ? 'A finalizar...' : 'Confirmar venda')}
              </button>
            </div>
          </div>
        </>
      )}

      <Modal open={openModalOpen} onClose={() => setOpenModalOpen(false)} title="Abrir caixa">
        <form onSubmit={handleOpenSession} className="flex flex-col gap-4">
          <div className="bg-bg-inset border border-border rounded-md px-4 py-3">
            <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1">Fundo reportado da sessão anterior</p>
            {carryForwardLoading ? (
              <div className="flex items-center gap-2 text-text-muted text-sm"><Loader2 size={14} className="animate-spin" />A calcular...</div>
            ) : (
              <p className="font-mono font-semibold text-text-primary text-lg">{formatKz(carryForwardAmount)} Kz</p>
            )}
          </div>
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
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Motivo da diferença (obrigatório se houver diferença)</label>
              <input
                value={closingNotes}
                onChange={(e) => setClosingNotes(e.target.value)}
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
              />
            </div>
            <button type="submit" disabled={closeSaving} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
              {closeSaving ? <Loader2 size={17} className="animate-spin" /> : <LogOut size={17} />}
              {closeSaving ? 'A fechar...' : 'Fechar caixa'}
            </button>
          </form>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2 bg-bg-inset border border-border rounded-md px-4 py-3">
              <div className="flex justify-between text-[13px]"><span className="text-text-muted">Esperado</span><span className="font-mono text-text-primary">{formatKz(Number(closeResult.closing_amount_expected))} Kz</span></div>
              <div className="flex justify-between text-[13px]"><span className="text-text-muted">Contado</span><span className="font-mono text-text-primary">{formatKz(Number(closeResult.closing_amount_counted))} Kz</span></div>
              <div className="flex justify-between text-[13px] border-t border-border pt-2">
                <span className="text-text-muted">Diferença</span>
                <span className={'font-mono font-semibold ' + (Number(closeResult.closing_difference) === 0 ? 'text-success' : Number(closeResult.closing_difference) > 0 ? 'text-accent' : 'text-danger')}>
                  {Number(closeResult.closing_difference) > 0 ? '+' : ''}{formatKz(Number(closeResult.closing_difference))} Kz
                </span>
              </div>
              {closeResult.closing_notes && (
                <div className="text-[12px] text-text-muted border-t border-border pt-2">
                  Motivo: <span className="text-text-primary">{closeResult.closing_notes}</span>
                </div>
              )}
            </div>
            {/* the closing report: the main button when the till proposes it, otherwise next to Concluir */}
            <div className="flex gap-2">
              <button
                onClick={() => finishAndPrintClosingReport(closeResult.id)}
                className={(closingReportProposed ? 'flex-1 bg-accent hover:bg-accent-hover text-white' : 'border border-border hover:border-accent text-text-primary')
                  + ' font-semibold text-sm rounded-md py-3 px-4 transition-colors cursor-pointer'}
              >
                Imprimir relatório de fecho
              </button>
              <button
                onClick={finishClosing}
                className={(closingReportProposed ? 'border border-border hover:border-accent text-text-primary' : 'flex-1 bg-accent hover:bg-accent-hover text-white')
                  + ' font-semibold text-sm rounded-md py-3 px-4 transition-colors cursor-pointer'}
              >
                Concluir
              </button>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={paymentModalOpen} onClose={closeLiquidationModal} title="Liquidar pro-forma" stacked={paymentMode === 'liquidation'}>
        <div className="flex flex-col gap-4">
          {liquidationTarget && (
            <div className="bg-accent/10 border-l-2 border-accent px-3.5 py-2.5 text-[13px] rounded-r">
              <p className="text-text-primary">A liquidar <span className="font-mono">FP {liquidationTarget.series}/{liquidationTarget.number}</span></p>
              <div className="mt-2">
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Converter para</label>
                <Select
                  value={liquidationTargetType}
                  onChange={setLiquidationTargetType}
                  options={posLiquidationOptions}
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
                    <span className="text-[13px] text-text-primary">{m.short_label || m.name}</span>
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


          <button
            onClick={handleConfirmSale}
            disabled={checkoutSaving || paymentsRemaining !== 0 || (paymentMode === 'liquidation' ? !can('pos:liquidate') : !can('pos:checkout'))}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {checkoutSaving ? <Loader2 size={17} className="animate-spin" /> : <CheckCircle2 size={17} />}
            {checkoutSaving ? 'A finalizar...' : 'Confirmar liquidação'}
          </button>
        </div>
      </Modal>

      <Modal variant="drawer" drawerLeftClass="left-16" open={dailyReportModalOpen} onClose={() => setDailyReportModalOpen(false)} title="Relatórios" maxWidthClass="max-w-2xl">
        <div className="flex flex-col gap-4">
          {/* Relatórios: the journal of the movements, and the closings of the till (reprint of the closing report) */}
          <div className="flex gap-1 border-b border-border">
            {[['movimentos', 'Movimentos'], ['fecho', 'Fechos de caixa']].map(([key, label]) => (
              <button
                key={key}
                onClick={() => setReportTab(key)}
                className={'px-3.5 py-2 text-sm -mb-px border-b-2 transition-colors cursor-pointer '
                  + (reportTab === key ? 'border-accent text-text-primary font-medium' : 'border-transparent text-text-muted hover:text-text-primary')}
              >
                {label}
              </button>
            ))}
          </div>
          {reportTab === 'movimentos' && (<>
          <div className="flex items-end gap-2.5">
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">De</label>
              <DateInput
                value={dailyReportDateFrom}
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
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Até</label>
              <DateInput
                value={dailyReportDateTo}
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
            <button
              onClick={printDailyReport}
              disabled={dailyReportLoading || !dailyReportDateFrom || !dailyReportDateTo}
              className="border border-border hover:border-accent text-text-primary font-medium text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Imprimir
            </button>
          </div>

          {dailyReportLoading ? (
            <div className="flex justify-center py-8"><Loader2 size={20} className="animate-spin text-accent" /></div>
          ) : dailyReportEntries.length === 0 ? (
            <p className="text-text-muted text-[13px] text-center py-8">Nenhuma operação neste período</p>
          ) : (
            <>
              <div className="flex flex-col gap-1.5 max-h-[400px] overflow-y-auto scrollbar-thin">
                {dailyReportEntries.map((e, idx) => (
                  <div key={idx} className="flex items-center justify-between bg-bg-inset border border-border rounded-md px-3.5 py-2.5">
                    <div>
                      <p className="text-[12px] text-text-primary">{e.description}</p>
                      <p className="text-[10px] text-text-muted font-mono">{new Date(e.time).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</p>
                    </div>
                    <span className={'font-mono text-[13px] font-semibold ' + (e.direction === 'saída' ? 'text-danger' : 'text-success')}>
                      {e.direction === 'saída' ? '-' : '+'}{formatKz(e.amount)} Kz
                    </span>
                  </div>
                ))}
              </div>
              <div className="flex justify-between border-t border-border pt-3">
                <span className="text-text-muted text-[13px] font-medium">Total do período</span>
                <span className="font-mono font-bold text-text-primary text-[15px]">
                  {formatKz(dailyReportEntries.reduce((sum, e) => sum + (e.direction === 'saída' ? -e.amount : e.amount), 0))} Kz
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
          </>)}
          {reportTab === 'fecho' && (reportSessionsLoading ? (
            <div className="flex justify-center py-8"><Loader2 size={20} className="animate-spin text-accent" /></div>
          ) : reportSessions.length === 0 ? (
            <p className="text-[13px] text-text-muted text-center py-8">Nenhuma sessão de caixa</p>
          ) : (
            <div className="flex flex-col divide-y divide-border border border-border rounded-md">
              {reportSessions.map((s) => {
                const closed = s.status === 'FECHADA';
                const diff = Number(s.closing_difference || 0);
                return (
                  <div key={s.id} className="flex items-center gap-3 px-3.5 py-2.5 text-[13px]">
                    <div className="flex-1 min-w-0">
                      <p className="text-text-primary">
                        Dia {new Date(s.business_date + 'T00:00:00').toLocaleDateString('pt-PT')}
                        <span className="text-text-muted"> · {shortDateTime(s.opened_at)} → {closed ? shortDateTime(s.closed_at) : 'em curso'}</span>
                      </p>
                      {closed && (
                        <p className="text-[12px] text-text-muted truncate">
                          Esperado <span className="font-mono">{formatKz(Number(s.closing_amount_expected))}</span>
                          {' · '}Contado <span className="font-mono">{formatKz(Number(s.closing_amount_counted))}</span>
                          {s.closing_notes ? ' · ' + s.closing_notes : ''}
                        </p>
                      )}
                    </div>
                    {closed ? (
                      <span className={'font-mono font-semibold whitespace-nowrap ' + (diff === 0 ? 'text-success' : diff > 0 ? 'text-accent' : 'text-danger')}>
                        {diff > 0 ? '+' : ''}{formatKz(diff)} Kz
                      </span>
                    ) : (
                      <span className="text-[11px] text-amber-500 [.light_&]:text-amber-700 whitespace-nowrap">Aberta</span>
                    )}
                    <button
                      onClick={() => printClosingReport(s.id)}
                      disabled={!closed}
                      className="border border-border hover:border-accent text-text-primary text-[12px] font-medium px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Imprimir
                    </button>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </Modal>

      <Modal open={!!insuranceForm} onClose={() => setInsuranceForm(null)} title="Seguradora / convénio" maxWidthClass="max-w-xl">
        {insuranceForm && (
          <div className="flex flex-col gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Entidade *</label>
              <Select value={insuranceForm.insurerId} onChange={(v) => {
                const insurer = insurers.find((c) => c.id === v);
                setInsuranceForm((f) => ({ ...f, insurerId: v, pct: insurer?.insurer_coverage_pct != null ? String(insurer.insurer_coverage_pct) : f.pct }));
              }} options={insurers.map((c) => ({ value: c.id, label: c.name }))} placeholder="Selecionar" />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">N.º do cartão do beneficiário *</label>
                <input value={insuranceForm.cardNumber} onChange={(e) => setInsuranceForm((f) => ({ ...f, cardNumber: e.target.value }))} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent" />
              </div>
              <div>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Taxa de comparticipação (%) *</label>
                <input type="number" min="0.01" max="100" step="0.01" value={insuranceForm.pct} onChange={(e) => setInsuranceForm((f) => ({ ...f, pct: e.target.value }))} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent" />
              </div>
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome do beneficiário</label>
              <input value={insuranceForm.beneficiaryName} onChange={(e) => setInsuranceForm((f) => ({ ...f, beneficiaryName: e.target.value }))} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent" />
            </div>
            {insurers.find((c) => c.id === insuranceForm.insurerId)?.insurer_medicines_only !== false && insuranceForm.insurerId && (
              <p className="text-[12px] text-text-muted -mt-1">Esta entidade comparticipa apenas medicamentos: os outros artigos são pagos inteiramente pelo utente.</p>
            )}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setInsuranceForm(null)} className="border border-border hover:border-accent text-text-primary text-sm font-medium rounded-md px-4 py-2.5 cursor-pointer">Cancelar</button>
              <button type="button" onClick={applyInsurance}
                disabled={!insuranceForm.insurerId || !insuranceForm.cardNumber.trim() || !(parseFloat(insuranceForm.pct) > 0 && parseFloat(insuranceForm.pct) <= 100)}
                className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-md px-5 py-2.5 cursor-pointer">Aplicar</button>
            </div>
          </div>
        )}
      </Modal>

      <PrescriptionModal
        need={prescriptionNeed}
        required={prescriptionPolicy === 'OBRIGATORIA'}
        initial={prescription}
        onCancel={() => setPrescriptionNeed(null)}
        onConfirm={(data) => { setPrescription(data); setPrescriptionNeed(null); setSaleConfirmModalOpen(true); }}
      />

      <Modal open={saleConfirmModalOpen} onClose={() => setSaleConfirmModalOpen(false)} title="Confirmar operação">
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
            {paidOnIssue && (
              <div className="flex justify-between text-[13px] pt-1.5 border-t border-border mt-1">
                <span className="text-text-muted">Pronto a pagar</span>
                <span className="text-success font-medium">Sim</span>
              </div>
            )}
          </div>
{posPaymentMethods.length > 0 && (
            <div className="flex flex-col gap-2 mb-4">
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">Formas de pagamento</p>
              <div className={'flex flex-col gap-1.5' + (!paidOnIssue ? ' opacity-40 pointer-events-none' : '')}>
                {posPaymentMethods.map((m) => {
                  const line = payments.find((p) => p.paymentMethodId === m.id);
                  return (
                    <div key={m.id} className="flex items-center gap-2">
                      <label className="flex items-center gap-2 flex-1 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={!!line}
                          onChange={() => togglePaymentMethod(m.id)}
                          disabled={!paidOnIssue}
                          className="w-4 h-4 accent-accent cursor-pointer"
                        />
                        <span className="text-[13px] text-text-primary">{m.short_label || m.name}</span>
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
              {paidOnIssue && (
                <div className={'text-[12px] px-3 py-2 rounded-r border-l-2 ' + (paymentsRemaining === 0 ? 'bg-success/10 border-success text-success' : paymentsRemaining > 0 ? 'bg-accent/10 border-accent text-accent' : 'bg-danger/10 border-danger text-danger')}>
                  {paymentsRemaining === 0 ? 'Valor exato' : paymentsRemaining > 0 ? `Falta ${formatKz(paymentsRemaining)} Kz` : `Excede em ${formatKz(Math.abs(paymentsRemaining))} Kz`}
                </div>
              )}
              {paidOnIssue && cashPart > 0 && (
                <div className="flex items-center gap-2 mt-1">
                  <label className="text-[13px] text-text-muted flex-1">Entregue pelo cliente</label>
                  <input
                    type="number" step="0.01" min="0"
                    value={cashGiven}
                    onChange={(e) => setCashGiven(e.target.value)}
                    placeholder={formatKz(cashPart)}
                    className="w-28 bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
                  />
                </div>
              )}
              {paidOnIssue && cashChange > 0 && (
                <div className="flex items-baseline justify-between text-success px-3 py-2 rounded-md bg-success/10">
                  <span className="text-[13px] font-semibold">Troco</span>
                  <span className="font-mono font-bold text-lg">{formatKz(cashChange)} Kz</span>
                </div>
              )}
            </div>
          )}

          <div className="flex flex-col gap-2.5 mb-4">
            <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">Condições de faturação (FT)</p>
            <div className={'flex flex-col gap-2.5' + (!billsLater ? ' opacity-40 pointer-events-none' : '')}>
              <Select
                value={billsLater ? ftPaymentTermId : (paymentTerms.find(isProntoTerm)?.id || '')}
                onChange={(termId) => {
                  setFtPaymentTermId(termId);
                  const term = paymentTerms.find((t) => t.id === termId);
                  setFtDueDate(term ? dueDateFor(term, new Date().toISOString().slice(0, 10)) : '');
                }}
                options={paymentTerms.map((t) => ({ value: t.id, label: t.name }))}
                placeholder="Condição de pagamento"
              />
              {ftDueDate && (
                <p className="text-[12px] text-text-muted">Data de vencimento: <span className="font-mono text-text-primary">{ftDueDate}</span></p>
              )}
            </div>
          </div>


          <p className="text-text-muted text-[13px]">Confirma a finalização desta operação?</p>
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
                else if (billsLater) handleConfirmFt();
                else handleConfirmSale();
              }}
              disabled={(selectedInvoiceType === 'PRO_FORMA' ? !can('pos:proforma') : ((!billsLater && paymentMode === 'liquidation') ? !can('pos:liquidate') : !can('pos:checkout'))) || (selectedInvoiceType !== 'PRO_FORMA' && paidOnIssue && posPaymentMethods.length > 0 && paymentsRemaining !== 0) || (requiresPaymentTerm && !ftPaymentTermId) || (requiresCustomer && !selectedCustomerId)}
              className="flex-1 bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Confirmar
            </button>
          </div>
        </div>
      </Modal>

      <Modal open={successModalOpen} onClose={closePaymentModal} title="Documento gerado" stacked={paymentMode === 'liquidation'}>
        <div className="flex flex-col items-center gap-4 py-4 text-center">
          <CheckCircle2 size={40} className="text-success" />
          <div>
            <p className="font-display font-semibold text-text-primary">
              {lastInvoice?.invoice_type === 'PRO_FORMA' ? 'Pro-forma gerada' : lastInvoice?.invoice_type === 'FACTURA' ? 'Fatura emitida' : 'Venda concluída'}
            </p>
            {lastInvoice && (
              <>
                <p className="text-text-muted text-[13px] font-mono mt-1">{lastInvoice.series}/{lastInvoice.number} - {formatKz(lastInvoice.total)} Kz</p>
                {lastInvoice.insurer_invoice_reference && lastInvoice.insurer_invoice_id !== lastInvoice.id && (
                  <div className="mt-3 flex items-center justify-center gap-2 text-[13px]">
                    <span className="text-text-muted font-mono whitespace-nowrap">{'Fatura da entidade '}{lastInvoice.insurer_invoice_reference} - {formatKz(lastInvoice.insurer_invoice_total)} Kz</span>
                    <button type="button" onClick={() => openPdfViewer(lastInvoice.insurer_invoice_id, 'a4', lastInvoice.insurer_invoice_reference.replace('/', '-') + ' (A4)')}
                      className="border border-border hover:border-accent text-text-primary text-[12px] rounded-md py-1 px-2.5 cursor-pointer whitespace-nowrap">Ver A4</button>
                  </div>
                )}
                {Number(lastInvoice.retention_total) > 0 && (
                  <p className="text-text-muted text-[12px] font-mono mt-0.5">
                    Retenção {formatKz(lastInvoice.retention_total)} Kz - recebido {formatKz(lastInvoice.total - lastInvoice.retention_total)} Kz
                  </p>
                )}
              </>
            )}
          </div>
          {printChoice && lastInvoice && (
            <div className="flex items-center gap-2">
              <span className="text-[12px] text-text-muted">Imprimir:</span>
              <button type="button" onClick={() => { printDocument(lastInvoice, 'thermal'); setPrintChoice(false); }}
                className="border border-border hover:border-accent text-text-primary text-sm rounded-md py-2 px-4 cursor-pointer">{'Tal\u00e3o'}</button>
              <button type="button" onClick={() => { printDocument(lastInvoice, 'a4'); setPrintChoice(false); }}
                className="border border-border hover:border-accent text-text-primary text-sm rounded-md py-2 px-4 cursor-pointer">A4</button>
            </div>
          )}
          <button onClick={closePaymentModal} className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md py-3 px-6 transition-colors cursor-pointer">
            Nova venda
          </button>
        </div>
      </Modal>

      <Modal variant="drawer" drawerLeftClass="left-16" open={moedeiroModalOpen} onClose={() => setMoedeiroModalOpen(false)} title="Moedeiro (billetagem)" maxWidthClass="max-w-2xl">
        <div className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Tipo de contagem</label>
            <Select
              value={moedeiroCountType}
              onChange={changeMoedeiroCountType}
              options={[
                { value: 'FECHO', label: 'Fecho de caixa' },
                { value: 'TROCA_SAIDA', label: 'Troca - saída' },
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
              {/* a closing count, from Fechar caixa or from the Moedeiro button, goes on to the closing */}
              {moedeiroCountType === 'FECHO' && (
                <>
                  {/* a difference between the count and the expected is always explained (never blocking) */}
                  <div>
                    <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Motivo da diferença (obrigatório se houver diferença)</label>
                    <input
                      value={closingNotes}
                      onChange={(e) => setClosingNotes(e.target.value)}
                      className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
                    />
                  </div>
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
              <DenominationGrid denominations={denominations} quantities={denominationQuantities} onChange={updateDenominationQuantity} />

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

      <Modal variant="drawer" drawerLeftClass="left-16" open={movementModalOpen} onClose={() => setMovementModalOpen(false)} title="Operações de Caixa" maxWidthClass="max-w-2xl">
        <div className="flex items-center gap-1.5 mb-4 border-b border-border">
          <button
            onClick={() => setMovementModalTab('form')}
            className={'px-3.5 py-2 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer ' + (movementModalTab === 'form' ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary')}
          >
            Novo movimento
          </button>
          <button
            onClick={() => { setMovementModalTab('pending'); setReceptionDraft(null); }}
            className={'px-3.5 py-2 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer flex items-center gap-1.5 ' + (movementModalTab === 'pending' ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary')}
          >
            Transferências pendentes
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
                  { value: 'TRANSFERENCIA', label: 'Transferência para outra caixa' },
                  { value: 'ENTRADA_EXTERNA', label: 'Entrada externa' },
                  { value: 'SAIDA_EXTERNA', label: 'Saída externa' },
                ]}
              />
            </div>

            {movementForm.movementType === 'TRANSFERENCIA' && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Caixa de origem *</label>
                  <Select
                    value={movementForm.sourcePosId}
                    onChange={(v) => setMovementForm((p) => ({ ...p, sourcePosId: v, otherPosId: p.otherPosId === v ? '' : p.otherPosId }))}
                    options={allActivePos.map((p) => ({ value: p.id, label: posLabel(p) }))}
                    placeholder="Selecionar"
                    disabled={!isGestor}
                  />
                </div>
                <div>
                  <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Caixa de destino *</label>
                  <Select
                    value={movementForm.otherPosId}
                    onChange={(v) => setMovementForm((p) => ({ ...p, otherPosId: v }))}
                    options={allActivePos.filter((p) => p.id !== movementForm.sourcePosId).map((p) => ({ value: p.id, label: posLabel(p) }))}
                    placeholder="Selecionar"
                  />
                </div>
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

            {transferWithBilletage ? (
              <div className="flex flex-col gap-2">
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted block">Notas e moedas enviadas *</label>
                <DenominationGrid
                  denominations={denominations}
                  quantities={transferQuantities}
                  onChange={(id, v) => setTransferQuantities((p) => ({ ...p, [id]: v }))}
                />
                <div className="flex justify-between items-center bg-bg-inset border border-border rounded-md px-4 py-2.5">
                  <span className="text-text-muted text-[13px]">Valor da transferência</span>
                  <span className="font-mono font-semibold text-lg text-text-primary">{formatKz(transferTotal)} Kz</span>
                </div>
              </div>
            ) : (
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
            )}

            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Descrição (opcional)</label>
              <input
                value={movementForm.description}
                onChange={(e) => setMovementForm((p) => ({ ...p, description: e.target.value }))}
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
              />
            </div>


            <button
              type="submit"
              disabled={movementSaving || !can('tesouraria:record') || (transferWithBilletage && transferTotal <= 0)}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              {movementSaving ? <Loader2 size={17} className="animate-spin" /> : <ArrowLeftRight size={17} />}
              {movementSaving ? 'A registar...' : 'Registar movimento'}
            </button>
          </form>
        ) : receptionDraft ? (
          // The reception of a transfer by a till with billetage: the whole drawer for it, the sender's notes proposed
          (() => {
            const m = receptionDraft.movement;
            const expected = Number(m.amount);
            const total = denominationTotal(denominations, receptionDraft.quantities);
            const gap = total - expected;
            const matches = Math.abs(gap) < 0.01;
            return (
              <div className="flex flex-col gap-4">
                <button
                  onClick={() => { setReceptionDraft(null); setMovementFormError(''); }}
                  className="self-start flex items-center gap-1 text-[12px] text-text-muted hover:text-text-primary cursor-pointer"
                >
                  <ChevronLeft size={14} /> Transferências pendentes
                </button>

                <div className="bg-bg-inset border border-border rounded-md px-4 py-3 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[11px] uppercase tracking-wide text-text-muted">Receção de transferência</p>
                    <p className="text-[13px] text-text-primary truncate mt-0.5">De {posNameById(m.source_pos_id)}</p>
                    <p className="text-[11px] text-text-muted font-mono">{new Date(m.movement_date).toLocaleDateString('pt-PT')}</p>
                  </div>
                  <span className="font-mono text-lg font-semibold text-text-primary whitespace-nowrap">{formatKz(expected)} Kz</span>
                </div>

                <p className="text-[12px] text-text-muted">
                  Conte o que recebeu. As notas e moedas indicadas pela caixa de origem já estão preenchidas - corrija-as se o envelope for diferente.
                </p>

                <DenominationGrid
                  denominations={denominations}
                  quantities={receptionDraft.quantities}
                  onChange={(id, v) => setReceptionDraft((d) => ({ ...d, quantities: { ...d.quantities, [id]: v } }))}
                />

                <div className="flex flex-col gap-1.5 bg-bg-inset border border-border rounded-md px-4 py-3">
                  <div className="flex justify-between items-center">
                    <span className="text-text-muted text-[13px]">Total contado</span>
                    <span className={'font-mono font-semibold text-lg ' + (matches ? 'text-success' : 'text-text-primary')}>{formatKz(total)} Kz</span>
                  </div>
                  <p className={'text-[12px] ' + (matches ? 'text-success' : 'text-danger')}>
                    {matches ? 'Confere com o valor enviado' : gap > 0 ? `Excede em ${formatKz(gap)} Kz` : `Falta ${formatKz(-gap)} Kz`}
                  </p>
                </div>


                <button
                  onClick={() => handleReceiveMovement(m.id, denominationLines(denominations, receptionDraft.quantities))}
                  disabled={!matches || receivingId === m.id}
                  className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
                >
                  {receivingId === m.id ? <Loader2 size={17} className="animate-spin" /> : <CheckCircle2 size={17} />}
                  {receivingId === m.id ? 'A confirmar...' : 'Confirmar receção'}
                </button>
              </div>
            );
          })()
        ) : (
          <div className="flex flex-col gap-5">
            <div>
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide mb-2">Aguardam a sua confirmação (recebidas)</p>
              {pendingReceptionsLoading ? (
                <div className="flex justify-center py-4"><Loader2 size={16} className="animate-spin text-accent" /></div>
              ) : pendingReceptions.length === 0 ? (
                <p className="text-text-muted text-[12px] text-center py-4">Nenhuma transferência pendente de receção</p>
              ) : (
                <div className="flex flex-col gap-1.5 max-h-[200px] overflow-y-auto scrollbar-thin">
                  {pendingReceptions.map((m) => (
                    <div key={m.id} className="flex items-center justify-between gap-2 bg-bg-inset border border-border rounded-md px-3 py-2">
                      <div className="min-w-0">
                        <p className="text-[12px] text-text-primary truncate">De {posNameById(m.source_pos_id)}</p>
                        <p className="text-[10px] text-text-muted font-mono">{new Date(m.movement_date).toLocaleDateString('pt-PT')}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[12px] text-text-primary font-semibold">{formatKz(m.amount)} Kz</span>
                        <button
                          onClick={() => startReception(m)}
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
                <p className="text-text-muted text-[12px] text-center py-4">Nenhuma transferência enviada por confirmar</p>
              ) : (
                <div className="flex flex-col gap-1.5 max-h-[200px] overflow-y-auto scrollbar-thin">
                  {pendingEmissions.map((m) => (
                    <div key={m.id} className="flex items-center justify-between gap-2 bg-bg-inset border border-border rounded-md px-3 py-2">
                      <div className="min-w-0">
                        <p className="text-[12px] text-text-primary truncate">Para {posNameById(m.destination_pos_id)}</p>
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
              // the type follows the NIF (a company's: 10 digits from 5) until it is chosen by hand
              onChange={(e) => setNewCustomerForm((p) => ({ ...p, nif: e.target.value, legal_person_type: p.typeTouched ? p.legal_person_type : guessLegalPersonType(e.target.value) }))}
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Tipo *</label>
            <Select value={newCustomerForm.legal_person_type} onChange={(v) => setNewCustomerForm((p) => ({ ...p, legal_person_type: v, typeTouched: true }))} options={LEGAL_PERSON_OPTIONS} />
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

      {/* Reservations of this till's activity: book, check in (billed through this till) - see ReservasPanel. */}
      <Modal variant="drawer" drawerLeftClass="left-16" open={reservasModalOpen} onClose={() => setReservasModalOpen(false)} title="Reservas" maxWidthClass="max-w-5xl">
        {reservasModalOpen && selectedPosId && (
          <ReservasPanel
            posId={selectedPosId}
            activityId={pointsOfSale.find((p) => p.id === selectedPosId)?.activity_id}
            onSale={async (invoiceId) => {
              // a passage sold at the entry: shown and printed like any sale of this till
              setReservasModalOpen(false);
              await showIssuedDocument(invoiceId);
            }}
            onPayStay={(accountId) => {
              // the check-out of a stay with something to pay: its account, opened in Contas abertas, closed with the payment
              setReservasModalOpen(false);
              setStayAccountId(accountId);
              setOpenAccountsModalOpen(true);
            }}
          />
        )}
      </Modal>

      {/* Open accounts of this till: open, add, transfer and close them without leaving the till. */}
      <Modal variant="drawer" drawerLeftClass="left-16" open={openAccountsModalOpen} onClose={() => { setOpenAccountsModalOpen(false); setStayAccountId(null); }} title="Contas abertas" maxWidthClass="max-w-5xl">
        {openAccountsModalOpen && selectedPosId && (
          <OpenAccountsPanel
            posId={selectedPosId}
            initialAccountId={stayAccountId}
            activityId={pointsOfSale.find((p) => p.id === selectedPosId)?.activity_id}
            onChange={() => refreshPosStock(selectedPosId)}
            closeOptions={{
              customers,
              typeOptions: visibleTypeOptions.filter((o) => o.value !== 'PRO_FORMA'),
              defaultType: (visibleTypeOptions.find((o) => o.value !== 'PRO_FORMA' && ruleOf(o.value, 'paid_on_issue')) || {}).value || '',
              paymentTerms,
              ruleOf,
              onNewCustomer: can('customers:create') ? openNewCustomerModal : null,
            }}
            onClosed={async (account) => {
              // An account closed at the till ends like a direct sale: balance, stock, Documento gerado, printing.
              refreshPosStock(selectedPosId);
              await showIssuedDocument(account?.invoice_id);
            }}
          />
        )}
      </Modal>

      <Modal variant="drawer" drawerLeftClass="left-16" open={articlesModalOpen} onClose={() => setArticlesModalOpen(false)} title="Consultar artigos">
        <div className="flex flex-col gap-3">
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              placeholder="Pesquisar artigo por código ou nome..."
              value={articleSearchQuery}
              onChange={(e) => setArticleSearchQuery(e.target.value)}
              autoFocus
              className="w-full bg-bg-inset border border-border rounded-md pl-9 pr-3 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
            />
          </div>
          <div className="flex flex-col gap-2 max-h-[420px] overflow-y-auto scrollbar-thin">
            {products
              .filter((p) => !articleSearchQuery.trim() || p.code.toLowerCase().includes(articleSearchQuery.toLowerCase()) || p.name.toLowerCase().includes(articleSearchQuery.toLowerCase()) || medicineSearchText(p).includes(articleSearchQuery.toLowerCase()))
              .map((p) => (
                <button
                  key={p.id}
                  onClick={() => { addToCart(p, false); setArticlesModalOpen(false); }}
                  className="flex items-center justify-between bg-bg-inset border border-border hover:border-accent rounded-md px-4 py-3 text-left transition-colors cursor-pointer"
                >
                  <div>
                    <p className="font-mono text-[10px] text-text-muted">{p.code}</p>
                    <p className="text-[13px] text-text-primary">{p.name}</p>
                    {p.is_medicine && <p className="text-[11px] text-text-muted">{medicineSummary(p)}</p>}
                  </div>
                  <span className="font-mono text-accent text-[13px] font-semibold">{Number(p.price).toFixed(2)} Kz</span>
                </button>
              ))}
          </div>
        </div>
      </Modal>


      <Modal variant="drawer" drawerLeftClass="left-16" open={proFormaModalOpen} onClose={() => setProFormaModalOpen(false)} title="Consultar documentos" maxWidthClass="max-w-6xl">
        <div className="flex flex-col gap-3">
          <div className="flex gap-1 border-b border-border">
            {[['docs', 'Documentos emitidos', recentInvoices.length], ['proformas', 'Pro-formas pendentes', pendingProFormas.length]].map(([key, label, count]) => (
              <button key={key} type="button" onClick={() => setDocsTab(key)} className={'px-3.5 py-2 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer ' + (docsTab === key ? 'border-accent text-text-primary' : 'border-transparent text-text-muted hover:text-text-primary')}>
                {label} <span className="ml-1 text-[11px] font-mono text-text-muted">{count}</span>
              </button>
            ))}
          </div>
          <div className={docsTab === 'proformas' ? '' : 'hidden'}>
          {proFormaLoading ? (
            <div className="flex justify-center py-8"><Loader2 size={20} className="animate-spin text-accent" /></div>
          ) : proFormaError ? null : pendingProFormas.length === 0 ? (
            <p className="text-text-muted text-[13px] text-center py-8">Nenhuma pro-forma pendente de liquidação</p>
          ) : (
            <div>
              <div>
              <table className="w-full text-[12px] border-collapse">
                <thead className="sticky -top-5 z-10 bg-bg-elevated">
                  <tr className="border-b border-border text-[10px] font-semibold text-text-muted uppercase tracking-wide">
                    <th className="text-left px-2.5 py-2">Documento</th>
                    <th className="text-left px-2.5 py-2">Data</th>
                    <th className="text-left px-2.5 py-2">Cliente</th>
                    <th className="text-right px-2.5 py-2">Total</th>
                    <th className="text-right px-2.5 py-2">Retenção</th>
                    <th className="text-right px-2.5 py-2">Ação</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingProFormas.map((pf) => (
                    <tr key={pf.id} className="border-b border-border last:border-0 hover:bg-bg-inset">
                      <td className="px-2.5 py-2 font-mono text-text-primary whitespace-nowrap">FP {pf.series}/{pf.number}</td>
                      <td className="px-2.5 py-2 text-text-muted whitespace-nowrap">{new Date(pf.business_date).toLocaleDateString('pt-PT')}</td>
                      <td className="px-2.5 py-2 text-text-muted whitespace-nowrap">{pf.customer_name || '-'}</td>
                      <td className="px-2.5 py-2 text-right font-mono font-semibold text-accent whitespace-nowrap">{formatKz(pf.total)} Kz</td>
                      <td className="px-2.5 py-2 text-right font-mono text-text-muted whitespace-nowrap">{Number(pf.retention_total) > 0 ? formatKz(pf.retention_total) + ' Kz' : '-'}</td>
                      <td className="px-2.5 py-2 text-right whitespace-nowrap">
                        <button
                          onClick={() => selectProFormaToLiquidate(pf)}
                          className="text-accent hover:text-accent-hover font-medium text-[12px] cursor-pointer"
                        >
                          Liquidar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          )}

          </div>
          <div className={docsTab === 'docs' ? '' : 'hidden'}>
            {recentInvoicesLoading ? (
              <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-accent" /></div>
            ) : recentInvoices.length === 0 ? (
              <p className="text-text-muted text-[13px] text-center py-6">Nenhum documento emitido ainda</p>
            ) : (
              <div>
                <table className="w-full text-[12px] border-collapse">
                  <thead className="sticky -top-5 z-10 bg-bg-elevated">
                    <tr className="border-b border-border text-[10px] font-semibold text-text-muted uppercase tracking-wide">
                      <th className="text-left px-2.5 py-2">Documento</th>
                      <th className="text-left px-2.5 py-2">Data</th>
                      <th className="text-right px-2.5 py-2">Sem IVA</th>
                      <th className="text-right px-2.5 py-2">IVA</th>
                      <th className="text-right px-2.5 py-2">Total</th>
                      <th className="text-right px-2.5 py-2">Retenção</th>
                      <th className="text-right px-2.5 py-2">Recebido</th>
                      <th className="text-right px-2.5 py-2">A pagar</th>
                      <th className="text-right px-2.5 py-2">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentInvoices.map((inv) => (
                      <tr key={inv.id} className="border-b border-border last:border-0 hover:bg-bg-inset">
                        <td className="px-2.5 py-2 font-mono text-text-primary whitespace-nowrap">{DOC_CODE_BY_TYPE[inv.invoice_type] || inv.invoice_type} {inv.series}/{inv.number}</td>
                        <td className="px-2.5 py-2 text-text-muted whitespace-nowrap">{new Date(inv.business_date).toLocaleDateString('pt-PT')}</td>
                        <td className="px-2.5 py-2 text-right font-mono text-text-muted whitespace-nowrap">{formatKz(Number(inv.total) - Number(inv.vat_total))} Kz</td>
                        <td className="px-2.5 py-2 text-right font-mono text-text-muted whitespace-nowrap">{formatKz(inv.vat_total)} Kz</td>
                        <td className="px-2.5 py-2 text-right font-mono text-text-primary whitespace-nowrap">{formatKz(inv.total)} Kz</td>
                        <td className="px-2.5 py-2 text-right font-mono text-text-muted whitespace-nowrap">{Number(inv.retention_total) > 0 ? formatKz(inv.retention_total) + ' Kz' : '-'}</td>
                        <td className={'px-2.5 py-2 text-right font-mono whitespace-nowrap ' + (Number(inv.amount_paid) < 0 ? 'text-danger' : 'text-text-muted')} title={Number(inv.amount_paid) < 0 ? 'Reembolsado' : undefined}>{Number(inv.amount_paid) > 0 ? formatKz(inv.amount_paid) + ' Kz' : Number(inv.amount_paid) < 0 ? '-' + formatKz(-Number(inv.amount_paid)) + ' Kz' : '-'}</td>
                        <td className="px-2.5 py-2 text-right font-mono whitespace-nowrap">
                          {ruleOf(inv.invoice_type, 'accepts_receipt') && balanceOf(inv) > 0.005 ? (
                            <span className="text-accent">{formatKz(balanceOf(inv))} Kz</span>
                          ) : '-'}
                        </td>
                        <td className="px-2.5 py-2">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => openPdfViewer(inv.id, 'thermal', inv.series + '-' + inv.number + ' (Ticket)')}
                              title="Reimprimir - Ticket 80mm"
                              className="flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer"
                            >
                              <Receipt size={13} />
                            </button>
                            <button
                              onClick={() => openPdfViewer(inv.id, 'a4', inv.series + '-' + inv.number + ' (A4)')}
                              title="Reimprimir - A4"
                              className="flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer"
                            >
                              <Printer size={13} />
                            </button>
                            {inv.document_status !== 'ANULADO' && ruleOf(inv.invoice_type, 'accepts_receipt') && (
                              <button
                                onClick={() => documentActionsRef.current?.openRc(inv.id)}
                                disabled={!can('invoices:receipt') || !session || !ruleOf(inv.invoice_type, 'accepts_receipt') || !(balanceOf(inv) > 0.005)}
                                title="Emitir Recibo"
                                className="flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer text-[10px] font-bold disabled:opacity-40 disabled:cursor-not-allowed"
                              >
                                RC
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
      <DocumentActionModals cashPosId={selectedPosId} ref={documentActionsRef} onSuccess={() => listRecentIssuedInvoices(selectedPosId).then(setRecentInvoices).catch(() => {})} />
    </main>
    </div>
  );
}
