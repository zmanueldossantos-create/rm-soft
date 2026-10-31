import { API_ORIGIN } from '../api/config';
import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Building2, Loader2, Save, Lock, Image, Upload, Store, Plus, Pencil, Landmark, X, Check, Trash2, FileStack, Sparkles, ChevronDown, CreditCard, Link2, Unlink, Users, Bot, Mail, LifeBuoy, DatabaseBackup, FileKey2, BellRing, MonitorUp, Plug, RefreshCw, KeyRound, ArrowRight } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import { getMySupportSessions, getMyCompany, updateMyCompanyContact, uploadMyCompanyLogo, removeMyCompanyLogo, getMyCompanyBankAccounts, addMyCompanyBankAccount, updateMyCompanyBankAccount, toggleMyCompanyBankAccountStatus } from '../api/company';
import { listEstablishments, createEstablishment, updateEstablishment, toggleEstablishmentStatus } from '../api/establishments';
import { countriesApi, provincesApi, municipalitiesApi, currenciesApi, banksApi, documentTypesApi } from '../api/catalogs';
import { listDocumentSeries, createDocumentSeries, updateDocumentSeries, toggleDocumentSeriesStatus, getAllowedSeriesYears, syncDocumentSeriesWithAgt } from '../api/documentSeries';
import { listActivities, createActivity, updateActivity, toggleActivityStatus, listPointsOfSale, createPointOfSale, updatePointOfSale, togglePosStatus } from '../api/activity';
import apiClient from '../api/client';
import { extractErrorMessage } from '../utils/errors';
import { useCan } from '../utils/permissions';
import { getPharmacyContext } from '../api/pharmacy';
import { getMyCompanyAi } from '../api/ai';
import AiCompanySettingsTab from '../components/AiCompanySettingsTab';
import EmailSettingsTab from '../components/EmailSettingsTab';
import NotificationsTab from '../components/NotificationsTab';
import ApiKeysTab from '../components/ApiKeysTab';
import { getApiKeys } from '../api/apiKeys';
import CustomerDisplayModal from '../components/CustomerDisplayModal';
import { getCustomerDisplay } from '../api/customerDisplay';
import { getNotifications } from '../api/notifications';
import CompanyBackupsPanel from '../components/CompanyBackupsPanel';
import LicensePanel from '../components/LicensePanel';
import { getMyLicense, importMyLicense } from '../api/plans';
import SupportSessionsList from '../components/SupportSessionsList';
import { listUsers } from '../api/users';
import { listCashPointAssociations, assignUserToCashPoint, unassignUserFromCashPoint } from '../api/tesouraria';
import { Notify, useToastState } from '../components/Toaster';
import { toast } from '../store/toastStore';
import AgtCompanyPanel from '../components/AgtCompanyPanel';


function ToggleSwitch({ checked, onChange, disabled }) {
  const trackClass = 'relative w-9 h-5 rounded-full transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ' + (checked ? 'bg-success' : 'bg-border');
  const knobClass = 'absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ' + (checked ? 'translate-x-4' : 'translate-x-0');
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={onChange} disabled={disabled} className={trackClass}>
      <span className={knobClass} />
    </button>
  );
}

// A block of the «Dados da Empresa» form: a title, what it is for, its fields.
function Section({ title, hint, children }) {
  return (
    <section className="pt-6 mt-6 border-t border-border">
      <p className="text-[13px] font-medium text-text-primary mb-1">{title}</p>
      {hint && <p className="text-[12px] text-text-muted mb-3">{hint}</p>}
      {children}
    </section>
  );
}

function Field({ label, children, hint }) {
  return (
    <div>
      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-text-muted mt-1">{hint}</p>}
    </div>
  );
}

const inputClass = "w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors";
const emptyEstablishmentForm = { code: '', name: '', description: '' };
const emptyBankForm = { bankId: '', accountNumber: '', iban: '', currencyId: '' };

// The RM SOFT support accesses to this company: who entered, when, why (the platform cannot enter without leaving a trace)
function SupportTab() {
  const [sessions, setSessions] = useState(null);
  useEffect(() => {
    getMySupportSessions().then(setSessions).catch(() => setSessions([]));
  }, []);
  return (
    <div className="bg-bg-elevated border border-border rounded-lg p-5 flex flex-col gap-3">
      <p className="text-sm text-text-secondary">
        Cada vez que a equipa RM SOFT entra na sua empresa para dar suporte, fica aqui: quem, quando, porquê e até quando.
        Um acesso dura no máximo 1 hora, e o que for feito fica registado em nome de quem entrou.
      </p>
      {sessions === null
        ? <div className="flex items-center justify-center py-12 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>
        : <SupportSessionsList sessions={sessions} />}
    </div>
  );
}

export default function CompanySettings() {
  const can = useCan();
  // The AI assistant: its tab only when the platform switched it on for the company
  const [aiInfo, setAiInfo] = useState(null);
  useEffect(() => {
    getMyCompanyAi().then(setAiInfo).catch(() => setAiInfo(null));
  }, []);
  // Notificações: its tab only when the plan has the option (and for whoever manages the company)
  const [notificationsAllowed, setNotificationsAllowed] = useState(false);
  const canManageCompany = can('company:manage'); // the permissions arrive after the first render
  useEffect(() => {
    if (canManageCompany) getNotifications().then((d) => setNotificationsAllowed(!!d.allowed)).catch(() => setNotificationsAllowed(false));
  }, [canManageCompany]);
  // Integração API: its tab only when the plan has the option (the gestor)
  const [apiAllowed, setApiAllowed] = useState(false);
  useEffect(() => {
    if (canManageCompany) getApiKeys().then((d) => setApiAllowed(!!d.allowed)).catch(() => setApiAllowed(false));
  }, [canManageCompany]);
  // Ecrã do cliente: its button on each activity only when the plan has the option
  const [displayAllowed, setDisplayAllowed] = useState(false);
  const [displayActivity, setDisplayActivity] = useState(null);
  // The licence: its tab only on a client's server (LICENSE_REQUIRED)
  const [licenseRequired, setLicenseRequired] = useState(false);
  useEffect(() => {
    getMyLicense().then((v) => setLicenseRequired(!!v.required)).catch(() => setLicenseRequired(false));
  }, []);
  // ?tab=series (from the Configuração inicial "Ir" buttons) opens that tab directly
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'dados');
  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab) setActiveTab(tab);
  }, [searchParams]);

  const [company, setCompany] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useToastState('error');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useToastState('error');
  const [saved, setSaved] = useState(false);

  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [shortName, setShortName] = useState('');
  const [phone2, setPhone2] = useState('');
  const [website, setWebsite] = useState('');
  const [city, setCity] = useState('');
  const [countryId, setCountryId] = useState('');
  const [provinceId, setProvinceId] = useState('');
  const [municipalityId, setMunicipalityId] = useState('');
  const [primaryCurrencyId, setPrimaryCurrencyId] = useState('');
  const [secondaryCurrencyId, setSecondaryCurrencyId] = useState('');
  const [usesInvoicing, setUsesInvoicing] = useState(true);
  const [autoSeriesYear, setAutoSeriesYear] = useState(true);
  const [allowedSeriesYears, setAllowedSeriesYears] = useState([]); // AGT: the next year too after 15 December
  useEffect(() => {
    getAllowedSeriesYears().then((d) => setAllowedSeriesYears(d.years || [])).catch(() => setAllowedSeriesYears([]));
  }, []);
  const [allowsFutureSaleDate, setAllowsFutureSaleDate] = useState(false);
  const [stockPeriodClosing, setStockPeriodClosing] = useState(false); // Fecho de stock por período
  const [stockCheckAtPeriodEnd, setStockCheckAtPeriodEnd] = useState(false); // Stock à data (late exits)
  const [inventoryBeforeClose, setInventoryBeforeClose] = useState(false); // Inventário obrigatório antes do fecho
  const [expiryAlertDays, setExpiryAlertDays] = useState('30'); // lots: days of warning before an expiry date
  // Farmácia (only with the Farmácia sector): is the prescription's number required at the sale?
  const [pharmacyEnabled, setPharmacyEnabled] = useState(false);
  const [prescriptionPolicy, setPrescriptionPolicy] = useState('OBRIGATORIA');
  useEffect(() => { getPharmacyContext().then((c) => setPharmacyEnabled(!!c.enabled)).catch(() => setPharmacyEnabled(false)); }, []);
  const [saleUnitChecks, setSaleUnitChecks] = useState({ sale_unit_check_above_base: 'warn', sale_unit_check_below_cost: 'warn', sale_unit_check_same_factor: 'warn' });
  const [suggestsLastDocumentDate, setSuggestsLastDocumentDate] = useState(false);
  const [issuanceMode, setIssuanceMode] = useState('MANUAL');

  const [countries, setCountries] = useState([]);
  const [provinces, setProvinces] = useState([]);
  const [municipalities, setMunicipalities] = useState([]);
  const [currencies, setCurrencies] = useState([]);
  const [banks, setBanks] = useState([]);

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useToastState('error');
  const [removingLogo, setRemovingLogo] = useState(false);
  const fileInputRef = useRef(null);

  const [activities, setActivities] = useState([]);
  const [availableModules, setAvailableModules] = useState([]);
  const [activitiesLoading, setActivitiesLoading] = useState(false);
  const [activityModalOpen, setActivityModalOpen] = useState(false);
  const [editingActivityId, setEditingActivityId] = useState(null);
  const [activityForm, setActivityForm] = useState({ moduleId: '', name: '' });
  const [activitySaving, setActivitySaving] = useState(false);
  const [activityFormError, setActivityFormError] = useToastState('error');
  const [activityTogglingId, setActivityTogglingId] = useState(null);

  const [posByActivity, setPosByActivity] = useState({});
  const [posLoadingActivityId, setPosLoadingActivityId] = useState(null);
  const [posModalOpen, setPosModalOpen] = useState(false);
  const [editingPosId, setEditingPosId] = useState(null);
  const [posForm, setPosForm] = useState({ activityId: '', name: '', billetageEnabled: false, acceptClosingDifference: true, printClosingReport: false, printAfterSale: false, printTicket: true, printA4: false, allowPriceLevels: false, allowFreePrice: false });
  const [posSaving, setPosSaving] = useState(false);
  const [posFormError, setPosFormError] = useToastState('error');
  const [assocByPos, setAssocByPos] = useState({});
  const [assocUsers, setAssocUsers] = useState([]);
  const [assocPos, setAssocPos] = useState(null);
  const [assocSelection, setAssocSelection] = useState('');
  const [assocSaving, setAssocSaving] = useState(false);
  const [assocError, setAssocError] = useState('');
  const [posTogglingId, setPosTogglingId] = useState(null);

  const [establishments, setEstablishments] = useState([]);
  const [establishmentsLoading, setEstablishmentsLoading] = useState(false);
  const [establishmentTogglingId, setEstablishmentTogglingId] = useState(null);
  const [establishmentModalOpen, setEstablishmentModalOpen] = useState(false);
  const [editingEstablishmentId, setEditingEstablishmentId] = useState(null);
  const [establishmentForm, setEstablishmentForm] = useState(emptyEstablishmentForm);
  const [establishmentSaving, setEstablishmentSaving] = useState(false);
  const [establishmentFormError, setEstablishmentFormError] = useToastState('error');

  const [documentTypes, setDocumentTypes] = useState([]);
  const [seriesList, setSeriesList] = useState([]);
  const [seriesListLoading, setSeriesListLoading] = useState(false);
  const [seriesTogglingId, setSeriesTogglingId] = useState(null);
  const [seriesFormOpen, setSeriesFormOpen] = useState(false);
  const [editingSeriesId, setEditingSeriesId] = useState(null);
  const emptySeriesForm = { year: '', documentTypeId: '', establishmentId: '', seriesCode: '', description: '', contingencyIndicator: 'NORMAL', isPredefined: true, todosFacturacao: false, todosTesouraria: false, todosCompras: false };
  const [seriesForm, setSeriesForm] = useState(emptySeriesForm);
  const [seriesSaving, setSeriesSaving] = useState(false);
  const [seriesFormError, setSeriesFormError] = useToastState('error');

  const [bankAccounts, setBankAccounts] = useState([]);
  const [bankAccountsLoading, setBankAccountsLoading] = useState(false);
  const [bankTogglingId, setBankTogglingId] = useState(null);
  const [bankModalOpen, setBankModalOpen] = useState(false);
  const [editingBankId, setEditingBankId] = useState(null);
  const [bankForm, setBankForm] = useState(emptyBankForm);
  const [bankSaving, setBankSaving] = useState(false);
  const [bankFormError, setBankFormError] = useToastState('error');

  function formatIbanRest(raw) {
    const alnum = raw.replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 21);
    return alnum.match(/.{1,4}/g)?.join('.') || '';
  }

  async function loadCompany() {
    setLoading(true);
    setError('');
    try {
      const data = await getMyCompany();
      setCompany(data);
      setEmail(data.email);
      setPhone(data.phone_number.replace('+244', ''));
      setAddress(data.address || '');
      setShortName(data.short_name || '');
      setPhone2((data.phone_number_2 || '').replace('+244', ''));
      setWebsite(data.website || '');
      setCity(data.city || '');
      setProvinceId(data.province_id || '');
      setMunicipalityId(data.municipality_id || '');
      setPrimaryCurrencyId(data.primary_currency_id || '');
      setSecondaryCurrencyId(data.secondary_currency_id || '');
      setUsesInvoicing(data.uses_invoicing);
      setAutoSeriesYear(data.auto_series_year);
      setAllowsFutureSaleDate(data.allows_future_sale_date);
      setSaleUnitChecks({
        sale_unit_check_above_base: data.sale_unit_check_above_base || 'warn',
        sale_unit_check_below_cost: data.sale_unit_check_below_cost || 'warn',
        sale_unit_check_same_factor: data.sale_unit_check_same_factor || 'warn',
      });
      setSuggestsLastDocumentDate(data.suggests_last_document_date);
      setStockPeriodClosing(!!data.stock_period_closing);
      setStockCheckAtPeriodEnd(!!data.stock_check_at_period_end);
      setInventoryBeforeClose(!!data.inventory_before_close);
      setExpiryAlertDays(String(data.expiry_alert_days ?? 30));
      setPrescriptionPolicy(data.prescription_policy || 'OBRIGATORIA');
      setIssuanceMode(data.issuance_mode || 'MANUAL');
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar dados da empresa'));
    } finally {
      setLoading(false);
    }
  }

  const firstActivityId = activities[0]?.id;
  useEffect(() => {
    if (canManageCompany && firstActivityId) {
      getCustomerDisplay(firstActivityId).then((d) => setDisplayAllowed(!!d.allowed)).catch(() => setDisplayAllowed(false));
    }
  }, [canManageCompany, firstActivityId]);

  async function loadActivities() {
    setActivitiesLoading(true);
    try {
      const [activitiesData, modulesRes] = await Promise.all([
        listActivities(),
        apiClient.get('/activities/available-modules'),
      ]);
      setActivities(activitiesData);
      setAvailableModules(modulesRes.data);
      activitiesData.forEach((a) => loadPointsOfSale(a.id));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar atividades'));
    } finally {
      setActivitiesLoading(false);
    }
  }

  function openActivateModule(module) {
    setEditingActivityId(null);
    setActivityForm({ moduleId: module.id, name: module.name });
    setActivityFormError('');
    setActivityModalOpen(true);
  }

  function openEditActivity(activity) {
    setEditingActivityId(activity.id);
    setActivityForm({ moduleId: activity.module_id, name: activity.name });
    setActivityFormError('');
    setActivityModalOpen(true);
  }

  async function handleActivitySubmit(e) {
    e.preventDefault();
    setActivityFormError('');
    setActivitySaving(true);
    try {
      if (editingActivityId) {
        await updateActivity(editingActivityId, activityForm.name);
      } else {
        await createActivity(activityForm.moduleId, activityForm.name);
      }
      setActivityModalOpen(false);
      toast.success(editingActivityId ? 'Atividade atualizada' : 'Atividade criada');
      await loadActivities();
    } catch (err) {
      setActivityFormError(extractErrorMessage(err, 'Erro ao guardar atividade'));
    } finally {
      setActivitySaving(false);
    }
  }

  async function handleToggleActivity(activityId) {
    setActivityTogglingId(activityId);
    try {
      await toggleActivityStatus(activityId);
      toast.success('Estado da atividade atualizado');
      await loadActivities();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado da atividade'));
    } finally {
      setActivityTogglingId(null);
    }
  }

  // Which user operates each cash point: managed here, where the cash points are created.
  const canAssociate = can('tesouraria:associations_manage');
  const assocUserName = (posId) => assocUsers.find((u) => u.id === assocByPos[posId])?.full_name;

  async function loadAssociations() {
    try {
      const [users, associations] = await Promise.all([listUsers(), listCashPointAssociations()]);
      setAssocUsers(users);
      const map = {};
      associations.forEach((a) => { map[a.pos_id] = a.user_id; });
      setAssocByPos(map);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar associações das caixas'));
    }
  }

  useEffect(() => {
    if (activeTab === 'atividades' && canAssociate) loadAssociations();
  }, [activeTab]);

  function openAssociation(pos) {
    setAssocPos(pos);
    setAssocSelection('');
    setAssocError('');
  }

  async function handleAssociate() {
    if (!assocSelection || !assocPos) return;
    setAssocSaving(true);
    setAssocError('');
    try {
      await assignUserToCashPoint(assocSelection, assocPos.id);
      toast.success('Utilizador associado à caixa');
      setAssocSelection('');
      await loadAssociations();
    } catch (err) {
      setAssocError(extractErrorMessage(err, 'Erro ao associar caixa'));
    } finally {
      setAssocSaving(false);
    }
  }

  async function handleUnassign() {
    const holderId = assocPos && assocByPos[assocPos.id];
    if (!holderId) return;
    setAssocSaving(true);
    setAssocError('');
    try {
      await unassignUserFromCashPoint(holderId);
      toast.success('Utilizador desassociado da caixa');
      await loadAssociations();
    } catch (err) {
      setAssocError(extractErrorMessage(err, 'Erro ao desassociar caixa'));
    } finally {
      setAssocSaving(false);
    }
  }

  async function loadPointsOfSale(activityId) {
    setPosLoadingActivityId(activityId);
    try {
      const data = await listPointsOfSale(activityId);
      setPosByActivity((prev) => ({ ...prev, [activityId]: data }));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar pontos de venda'));
    } finally {
      setPosLoadingActivityId(null);
    }
  }

  function openCreatePos(activityId) {
    setEditingPosId(null);
    setPosForm({ activityId, name: '', billetageEnabled: false, acceptClosingDifference: true, printClosingReport: false, isDefault: false, printAfterSale: false, printTicket: true, printA4: false, allowPriceLevels: false, allowFreePrice: false });
    setPosFormError('');
    setPosModalOpen(true);
  }

  function openEditPos(pos) {
    setEditingPosId(pos.id);
    setPosForm({ activityId: pos.activity_id, name: pos.name, billetageEnabled: pos.billetage_enabled || false, acceptClosingDifference: pos.accept_closing_difference !== false, printClosingReport: !!pos.print_closing_report, printAfterSale: !!pos.print_after_sale, printTicket: pos.print_ticket !== false, printA4: !!pos.print_a4, isDefault: !!pos.is_default, allowPriceLevels: !!pos.allow_price_levels, allowFreePrice: !!pos.allow_free_price });
    setPosFormError('');
    setPosModalOpen(true);
  }

  async function handlePosSubmit(e) {
    e.preventDefault();
    setPosFormError('');
    setPosSaving(true);
    try {
      if (editingPosId) {
        await updatePointOfSale(editingPosId, posForm.name, posForm.billetageEnabled, { print_after_sale: posForm.printAfterSale, print_ticket: posForm.printTicket, print_a4: posForm.printA4, accept_closing_difference: posForm.acceptClosingDifference, print_closing_report: posForm.printClosingReport, allow_price_levels: posForm.allowPriceLevels, allow_free_price: posForm.allowFreePrice });
      } else {
        await createPointOfSale(posForm.activityId, posForm.name, posForm.billetageEnabled, { print_after_sale: posForm.printAfterSale, print_ticket: posForm.printTicket, print_a4: posForm.printA4, accept_closing_difference: posForm.acceptClosingDifference, print_closing_report: posForm.printClosingReport, allow_price_levels: posForm.allowPriceLevels, allow_free_price: posForm.allowFreePrice });
      }
      setPosModalOpen(false);
      toast.success(editingPosId ? 'Ponto de venda atualizado' : 'Ponto de venda criado');
      await loadPointsOfSale(posForm.activityId);
    } catch (err) {
      setPosFormError(extractErrorMessage(err, 'Erro ao guardar ponto de venda'));
    } finally {
      setPosSaving(false);
    }
  }

  async function handleTogglePos(posId, activityId) {
    setPosTogglingId(posId);
    try {
      await togglePosStatus(posId);
      toast.success('Estado do ponto de venda atualizado');
      await loadPointsOfSale(activityId);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado do ponto de venda'));
    } finally {
      setPosTogglingId(null);
    }
  }

  async function loadEstablishments() {
    setEstablishmentsLoading(true);
    try {
      setEstablishments(await listEstablishments());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar estabelecimentos'));
    } finally {
      setEstablishmentsLoading(false);
    }
  }

  async function loadSeries() {
    setSeriesListLoading(true);
    try {
      setSeriesList(await listDocumentSeries());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar séries'));
    } finally {
      setSeriesListLoading(false);
    }
  }

  async function refreshSeriesList() {
    setSeriesList(await listDocumentSeries());
  }

  async function handleToggleSeries(id) {
    setSeriesTogglingId(id);
    try {
      await toggleDocumentSeriesStatus(id);
      toast.success('Estado da série atualizado');
      await refreshSeriesList();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado'));
    } finally {
      setSeriesTogglingId(null);
    }
  }

  const [seriesSyncing, setSeriesSyncing] = useState(false);
  async function handleSyncSeries() {
    setSeriesSyncing(true);
    try {
      const result = await syncDocumentSeriesWithAgt();
      setSeriesList(result.series);
      const parts = [result.updated + ' atualizada(s)', result.added + ' importada(s)'];
      if (result.unknown.length) parts.push('desconhecida(s): ' + result.unknown.join(', '));
      toast.success('Séries sincronizadas com a AGT - ' + parts.join(' · '));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao sincronizar com a AGT'));
    } finally {
      setSeriesSyncing(false);
    }
  }

  function openCreateSeriesForm() {
    setEditingSeriesId(null);
    setSeriesForm(emptySeriesForm);
    setSeriesFormError('');
    setSeriesFormOpen(true);
  }

  function openEditSeriesForm(s) {
    setEditingSeriesId(s.id);
    setSeriesForm({ ...emptySeriesForm, description: s.description || '', contingencyIndicator: s.contingency_indicator || 'NORMAL', isPredefined: s.is_predefined });
    setSeriesFormError('');
    setSeriesFormOpen(true);
  }

  async function handleSeriesSubmit(e) {
    e.preventDefault();
    setSeriesFormError('');
    setSeriesSaving(true);
    try {
      if (editingSeriesId) {
        await updateDocumentSeries(editingSeriesId, {
          description: seriesForm.description || null,
          is_predefined: seriesForm.isPredefined,
        });
      } else {
        const isTodos = seriesForm.documentTypeId === '__TODOS__';
        await createDocumentSeries({
          year: seriesForm.year ? Number(seriesForm.year) : null,
          document_type_id: isTodos ? null : seriesForm.documentTypeId,
          establishment_id: issuanceMode === 'ELETRONICA' ? (seriesForm.establishmentId || null) : null,
          series_code: issuanceMode === 'MANUAL' && !autoSeriesYear ? seriesForm.seriesCode : null,
          description: seriesForm.description || null,
          contingency_indicator: issuanceMode === 'ELETRONICA' ? seriesForm.contingencyIndicator : null,
          is_predefined: seriesForm.isPredefined,
          todos_facturacao: isTodos ? seriesForm.todosFacturacao : false,
          todos_tesouraria: isTodos ? seriesForm.todosTesouraria : false,
          todos_compras: isTodos ? seriesForm.todosCompras : false,
        });
      }
      setSeriesFormOpen(false);
      toast.success(editingSeriesId ? 'Série atualizada' : 'Série criada');
      await refreshSeriesList();
    } catch (err) {
      setSeriesFormError(extractErrorMessage(err, 'Erro ao criar série'));
    } finally {
      setSeriesSaving(false);
    }
  }

  async function loadBankAccounts() {
    setBankAccountsLoading(true);
    try {
      setBankAccounts(await getMyCompanyBankAccounts());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar contas bancárias'));
    } finally {
      setBankAccountsLoading(false);
    }
  }

  useEffect(() => {
    loadCompany();
    countriesApi.list().then((data) => setCountries(data.filter((c) => c.is_active))).catch(() => {});
    provincesApi.list().then((data) => setProvinces(data.filter((p) => p.is_active))).catch(() => {});
    municipalitiesApi.list().then((data) => setMunicipalities(data.filter((m) => m.is_active))).catch(() => {});
    currenciesApi.list().then((data) => setCurrencies(data.filter((c) => c.is_active))).catch(() => {});
    banksApi.list().then((data) => setBanks(data.filter((b) => b.is_active))).catch(() => {});
    documentTypesApi.list().then((data) => setDocumentTypes(data.filter((d) => d.is_active))).catch(() => {});
  }, []);

  useEffect(() => {
    if (activeTab === 'atividades' && activities.length === 0) loadActivities();
    if (activeTab === 'estabelecimentos' && establishments.length === 0) loadEstablishments();
    if (activeTab === 'bancarias' && bankAccounts.length === 0) loadBankAccounts();
    if (activeTab === 'series') {
      if (seriesList.length === 0) loadSeries();
      if (establishments.length === 0) loadEstablishments();
    }
  }, [activeTab]);

  const provincesForCountry = useMemoProvinces(provinces, countryId);

  function useMemoProvinces(list, cId) {
    // Provinces aren't yet linked to a selectable country field here (company has no country_id
    // field of its own - province already implies the country) - show all active provinces.
    return list;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaveError('');
    setSaved(false);
    setSaving(true);
    try {
      const fullPhone = phone.startsWith('+') ? phone : '+244' + phone.replace(/\s/g, '');
      const fullPhone2 = phone2 ? (phone2.startsWith('+') ? phone2 : '+244' + phone2.replace(/\s/g, '')) : null;
      await updateMyCompanyContact({
        email, phone_number: fullPhone, address: address || null,
        short_name: shortName || null, phone_number_2: fullPhone2, website: website || null,
        city: city || null, province_id: provinceId || null, municipality_id: municipalityId || null,
        primary_currency_id: primaryCurrencyId || null, secondary_currency_id: secondaryCurrencyId || null,
        uses_invoicing: usesInvoicing, auto_series_year: autoSeriesYear,
        allows_future_sale_date: allowsFutureSaleDate, suggests_last_document_date: suggestsLastDocumentDate,
        ...saleUnitChecks,
        stock_period_closing: stockPeriodClosing,
        stock_check_at_period_end: stockCheckAtPeriodEnd,
        inventory_before_close: inventoryBeforeClose,
        expiry_alert_days: parseInt(expiryAlertDays, 10) || 30,
        ...(pharmacyEnabled ? { prescription_policy: prescriptionPolicy } : {}),
        issuance_mode: issuanceMode,
      });
      setCompany((c) => ({ ...c, issuance_mode: issuanceMode }));  // the «Faturação Eletrónica» tab follows the saved mode
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setSaveError(extractErrorMessage(err, 'Erro ao guardar alterações'));
    } finally {
      setSaving(false);
    }
  }

  function handleUsesInvoicingChange(checked) {
    setUsesInvoicing(checked);
    if (!checked) {
      setAutoSeriesYear(false);
      setAllowsFutureSaleDate(false);
      setSuggestsLastDocumentDate(false);
    }
  }

  function handleIssuanceModeChange(mode) {
    setIssuanceMode(mode);
    if (mode === 'ELETRONICA') setAutoSeriesYear(false);
  }

  function handleProvinceChange(v) {
    setProvinceId(v);
    setMunicipalityId('');
  }

  async function handleRemoveLogo() {
    setUploadError('');
    setRemovingLogo(true);
    try {
      const updated = await removeMyCompanyLogo();
      setCompany(updated);
      toast.success('Logotipo removido');
    } catch (err) {
      setUploadError(extractErrorMessage(err, 'Erro ao remover logotipo'));
    } finally {
      setRemovingLogo(false);
    }
  }

  async function handleLogoChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError('');
    setUploading(true);
    try {
      const updated = await uploadMyCompanyLogo(file);
      setCompany(updated);
      toast.success('Logotipo atualizado');
    } catch (err) {
      setUploadError(extractErrorMessage(err, 'Erro ao carregar logotipo'));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  function openCreateEstablishment() {
    setEditingEstablishmentId(null);
    setEstablishmentForm(emptyEstablishmentForm);
    setEstablishmentFormError('');
    setEstablishmentModalOpen(true);
  }

  function openEditEstablishment(item) {
    setEditingEstablishmentId(item.id);
    setEstablishmentForm({ code: item.code, name: item.name, description: item.description || '' });
    setEstablishmentFormError('');
    setEstablishmentModalOpen(true);
  }

  async function handleEstablishmentSubmit(e) {
    e.preventDefault();
    setEstablishmentFormError('');
    setEstablishmentSaving(true);
    try {
      if (editingEstablishmentId) {
        await updateEstablishment(editingEstablishmentId, establishmentForm);
      } else {
        await createEstablishment(establishmentForm);
      }
      setEstablishmentModalOpen(false);
      toast.success(editingEstablishmentId ? 'Estabelecimento atualizado' : 'Estabelecimento criado');
      await loadEstablishments();
    } catch (err) {
      setEstablishmentFormError(extractErrorMessage(err, 'Erro ao guardar estabelecimento'));
    } finally {
      setEstablishmentSaving(false);
    }
  }

  async function handleToggleEstablishment(id) {
    setEstablishmentTogglingId(id);
    try {
      await toggleEstablishmentStatus(id);
      toast.success('Estado do estabelecimento atualizado');
      await loadEstablishments();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado'));
    } finally {
      setEstablishmentTogglingId(null);
    }
  }

  function openCreateBank() {
    setEditingBankId(null);
    setBankForm(emptyBankForm);
    setBankFormError('');
    setBankModalOpen(true);
  }

  function openEditBank(item) {
    setEditingBankId(item.id);
    setBankForm({ bankId: item.bank_id, accountNumber: item.account_number, iban: item.iban.replace(/^AO\d{2}\.?/, ''), currencyId: item.currency_id });
    setBankFormError('');
    setBankModalOpen(true);
  }

  async function handleBankSubmit(e) {
    e.preventDefault();
    setBankFormError('');
    setBankSaving(true);
    try {
      const payload = { bank_id: bankForm.bankId, account_number: bankForm.accountNumber, iban: 'AO06' + bankForm.iban, currency_id: bankForm.currencyId };
      if (editingBankId) {
        await updateMyCompanyBankAccount(editingBankId, payload);
      } else {
        await addMyCompanyBankAccount(payload);
      }
      setBankModalOpen(false);
      toast.success(editingBankId ? 'Conta bancária atualizada' : 'Conta bancária adicionada');
      await loadBankAccounts();
    } catch (err) {
      setBankFormError(extractErrorMessage(err, 'Erro ao guardar conta bancária'));
    } finally {
      setBankSaving(false);
    }
  }

  async function handleToggleBank(id) {
    setBankTogglingId(id);
    try {
      await toggleMyCompanyBankAccountStatus(id);
      toast.success('Estado da conta bancária atualizado');
      await loadBankAccounts();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado'));
    } finally {
      setBankTogglingId(null);
    }
  }

  if (loading) {
    return (
      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
        <div className="flex justify-center items-center h-64">
          <Loader2 size={24} className="animate-spin text-accent" />
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Building2 size={22} className="text-accent" />
        Definições da Empresa
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Atualize o logotipo, os contactos, os estabelecimentos e as contas bancárias da sua empresa
      </p>


      <div className="flex items-center bg-bg-inset border border-border rounded-md p-0.5 self-start mb-5 w-fit flex-wrap">
        {[
          ['dados', 'Dados da Empresa', Building2],
          ['atividades', 'Atividades', Sparkles],
          ['estabelecimentos', 'Estabelecimentos', Store],
          ['bancarias', 'Coordenadas Bancárias', Landmark],
          ['series', 'Séries de Facturação', FileStack],
          ...(company?.issuance_mode === 'ELETRONICA' ? [['agt', 'Faturação Eletrónica', KeyRound]] : []),
          ['email', 'Email', Mail],
          ...(notificationsAllowed ? [['notificacoes', 'Notificações', BellRing]] : []),
          ...(apiAllowed ? [['api', 'Integração API', Plug]] : []),
          ...(can('company:backup') ? [['copias', 'Cópias de segurança', DatabaseBackup]] : []),
          ...(can('company:manage') ? [['suporte', 'Acessos de suporte', LifeBuoy]] : []),
          ...(aiInfo?.ai_enabled ? [['ia', 'Assistente IA', Bot]] : []),
          ...(licenseRequired ? [['licenca', 'Licença', FileKey2]] : []),
        ].map(([key, label, Icon]) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveTab(key)}
            className={'flex items-center gap-1.5 px-3.5 py-2 rounded text-[12px] font-medium transition-colors cursor-pointer ' + (activeTab === key ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'dados' && company && (
        <form onSubmit={handleSubmit} className="bg-bg-elevated border border-border rounded-lg p-6 sm:p-8">
          <div className="flex items-center gap-4 flex-wrap pb-6 border-b border-border mb-6">
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-text-muted uppercase tracking-wide">
              <Lock size={11} />
              Identidade fiscal
            </span>
            <span className="text-[11px] text-text-muted">Denominação fiscal:</span>
            <p className="font-display font-medium text-text-primary">{company.name}</p>
            <span className="text-border">&middot;</span>
            <p className="font-mono text-text-primary">{company.nif}</p>
            <p className="text-[11px] text-text-muted">
              Só o administrador da plataforma pode alterar estes dados.
            </p>
          </div>

          <div className="flex flex-col md:flex-row gap-8 mb-6">
            <div className="md:w-[110px] shrink-0">
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide mb-3 flex items-center gap-1.5">
                <Image size={12} />
                Logotipo
              </p>
              <input ref={fileInputRef} type="file" accept=".png,.jpg,.jpeg,.webp" onChange={handleLogoChange} className="hidden" id="logo-upload" />
              <label
                htmlFor="logo-upload"
                className="relative group w-full aspect-square bg-bg-inset border border-dashed border-border hover:border-accent rounded-lg flex items-center justify-center overflow-hidden cursor-pointer transition-colors"
              >
                {company.logo_path ? (
                  <img src={API_ORIGIN + company.logo_path} alt="Logotipo" className="w-full h-full object-contain" />
                ) : (
                  <Image size={24} className="text-text-muted/40" />
                )}
                {uploading && (
                  <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                    <Loader2 size={18} className="animate-spin text-white" />
                  </div>
                )}
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100">
                  <Upload size={16} className="text-white" />
                </div>
              </label>
              {company.logo_path && (
                <button
                  type="button"
                  onClick={handleRemoveLogo}
                  disabled={removingLogo}
                  className="flex items-center justify-center gap-1.5 w-full text-danger hover:bg-danger/10 text-[12px] px-2 py-1.5 rounded-md transition-colors cursor-pointer mt-1.5 disabled:opacity-50"
                >
                  {removingLogo ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                  Remover
                </button>
              )}
              <p className="text-[10px] text-text-muted mt-1.5 text-center">PNG, JPG, WEBP - máx. 2MB</p>
            </div>

            <div className="flex-1 flex flex-col gap-4">
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">Contactos</p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Field label="Nome curto"><input value={shortName} onChange={(e) => setShortName(e.target.value)} className={inputClass} /></Field>
                <Field label="Website"><input value={website} onChange={(e) => setWebsite(e.target.value)} className={inputClass} /></Field>
                <Field label="Email *"><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className={inputClass} /></Field>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Field label="Telefone 1 *">
                  <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent transition-colors">
                    <span className="px-3 py-2.5 text-text-muted border-r border-border font-mono text-sm">+244</span>
                    <input value={phone} onChange={(e) => setPhone(e.target.value)} required className="flex-1 bg-transparent border-none px-3 py-2.5 text-sm text-text-primary font-mono outline-none" />
                  </div>
                </Field>
                <Field label="Telefone 2">
                  <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent transition-colors">
                    <span className="px-3 py-2.5 text-text-muted border-r border-border font-mono text-sm">+244</span>
                    <input value={phone2} onChange={(e) => setPhone2(e.target.value)} className="flex-1 bg-transparent border-none px-3 py-2.5 text-sm text-text-primary font-mono outline-none" />
                  </div>
                </Field>
              </div>
            </div>
          </div>

          <Section title="Morada e moeda" hint="Onde a empresa está e em que moeda trabalha - aparecem nos documentos.">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
              <Field label="Província">
                <Select value={provinceId} onChange={handleProvinceChange} options={provincesForCountry.map((p) => ({ value: p.id, label: p.name }))} placeholder="Selecionar" />
              </Field>
              <Field label="Município">
                <Select value={municipalityId} onChange={setMunicipalityId} options={municipalities.filter((m) => m.province_id === provinceId).map((m) => ({ value: m.id, label: m.name }))} placeholder={provinceId ? 'Selecionar' : 'Selecione uma província primeiro'} />
              </Field>
              <Field label="Cidade"><input value={city} onChange={(e) => setCity(e.target.value)} className={inputClass} /></Field>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Field label="Endereço"><input value={address} onChange={(e) => setAddress(e.target.value)} className={inputClass} /></Field>
              <Field label="Moeda principal">
                <Select value={primaryCurrencyId} onChange={setPrimaryCurrencyId} options={currencies.filter((c) => c.id !== secondaryCurrencyId).map((c) => ({ value: c.id, label: c.code + ' - ' + c.name }))} placeholder="Selecionar" />
              </Field>
              <Field label="Moeda secundária">
                <Select value={secondaryCurrencyId} onChange={setSecondaryCurrencyId} options={currencies.filter((c) => c.id !== primaryCurrencyId).map((c) => ({ value: c.id, label: c.code + ' - ' + c.name }))} placeholder="Selecionar" />
              </Field>
            </div>
          </Section>

          <Section title="Faturação" hint="Como a empresa emite os seus documentos.">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4 items-end">
              <Field label="Modo de emissão">
                <Select value={issuanceMode} onChange={handleIssuanceModeChange} options={[{ value: 'MANUAL', label: 'Manual' }, { value: 'ELETRONICA', label: 'Eletrónica' }]} />
              </Field>
              {issuanceMode === 'ELETRONICA' && (company.issuance_mode === 'ELETRONICA' ? (
                <button type="button" onClick={() => setActiveTab('agt')}
                  className="sm:col-span-2 justify-self-start flex items-center gap-1.5 text-sm font-medium px-3.5 py-2.5 rounded-md border border-border hover:border-accent text-text-primary transition-colors cursor-pointer">
                  <KeyRound size={15} className="text-accent" />
                  Ligação à AGT (chave, testes, contingência)
                  <ArrowRight size={14} />
                </button>
              ) : (
                <p className="sm:col-span-2 text-[12px] text-text-muted pb-2.5">Guarde as alterações: a ligação à AGT configura-se depois no separador «Faturação Eletrónica».</p>
              ))}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              <label className="flex items-center gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                <input type="checkbox" checked={usesInvoicing} onChange={(e) => handleUsesInvoicingChange(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                <span className="text-sm text-text-primary">Usa Facturação</span>
              </label>
              <label className="flex items-center gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                <input type="checkbox" checked={autoSeriesYear} disabled={!usesInvoicing || issuanceMode === 'ELETRONICA'} onChange={(e) => setAutoSeriesYear(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer disabled:opacity-50" />
                <span className="text-sm text-text-primary">Série automática por ano</span>
              </label>
              <label className="flex items-center gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                <input type="checkbox" checked={allowsFutureSaleDate} disabled={!usesInvoicing} onChange={(e) => setAllowsFutureSaleDate(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer disabled:opacity-50" />
                <span className="text-sm text-text-primary">Permite venda com data futura</span>
              </label>
              <label className="flex items-center gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                <input type="checkbox" checked={suggestsLastDocumentDate} disabled={!usesInvoicing} onChange={(e) => setSuggestsLastDocumentDate(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer disabled:opacity-50" />
                <span className="text-sm text-text-primary">Sugere data do último documento</span>
              </label>
            </div>
          </Section>

          <Section title="Controlos das unidades e embalagens" hint="O que o sistema faz quando uma unidade ou embalagem de um produto parece incoerente.">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[['sale_unit_check_above_base', 'Mais cara que a unidade base'], ['sale_unit_check_below_cost', 'Abaixo do preço de compra'], ['sale_unit_check_same_factor', 'Mesmo conteudo que outra unidade']].map(([field, label]) => (
                <div key={field}>
                  <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{label}</label>
                  <Select value={saleUnitChecks[field]} onChange={(v) => setSaleUnitChecks((s) => ({ ...s, [field]: v }))} options={[{ value: 'off', label: 'Não verificar' }, { value: 'warn', label: 'Avisar e pedir confirmação' }, { value: 'block', label: 'Bloquear' }]} />
                </div>
              ))}
            </div>
          </Section>

          <Section title="Controlos de stock" hint="Regras do stock ligadas aos períodos contabilísticos.">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              <label className="flex items-start gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                <input type="checkbox" checked={stockPeriodClosing} onChange={(e) => setStockPeriodClosing(e.target.checked)} className="w-4 h-4 mt-0.5 accent-accent cursor-pointer" />
                <span>
                  <span className="text-sm text-text-primary block">Fecho de stock por período</span>
                  <span className="text-[12px] text-text-muted block">Ao fechar um período definitivamente, o stock de cada produto e armazém (inicial, entradas, saídas, final e valor ao custo médio) fica congelado. Consulta em Stock → Resumo de Stock → Movimento do período.</span>
                </span>
              </label>
              <label className="flex items-start gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                <input type="checkbox" checked={stockCheckAtPeriodEnd} onChange={(e) => setStockCheckAtPeriodEnd(e.target.checked)} className="w-4 h-4 mt-0.5 accent-accent cursor-pointer" />
                <span>
                  <span className="text-sm text-text-primary block">Stock à data nos lançamentos tardios</span>
                  <span className="text-[12px] text-text-muted block">Uma saída lançada no período fechado parcialmente (perda, saída, transferência, ajuste, produção, consumo interno) não pode usar mais do que o stock no fim desse período - nunca o que entrou depois.</span>
                </span>
              </label>
              <label className="flex items-start gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                <input type="checkbox" checked={inventoryBeforeClose} onChange={(e) => setInventoryBeforeClose(e.target.checked)} className="w-4 h-4 mt-0.5 accent-accent cursor-pointer" />
                <span>
                  <span className="text-sm text-text-primary block">Inventário obrigatório antes do fecho</span>
                  <span className="text-[12px] text-text-muted block">Um período só pode ser fechado definitivamente depois de um inventário validado, nesse período, em cada armazém com stock (Stock → Armazéns e Stock → Inventário).</span>
                </span>
              </label>
              <div className="flex items-start gap-3 border border-border rounded-md px-3.5 py-3">
                <input type="number" min="1" max="365" step="1" value={expiryAlertDays} onChange={(e) => setExpiryAlertDays(e.target.value)}
                  className="w-20 shrink-0 bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono text-right outline-none focus:border-accent" />
                <span>
                  <span className="text-sm text-text-primary block">Alerta de validade (dias)</span>
                  <span className="text-[12px] text-text-muted block">Um lote passa a «a expirar» este número de dias antes da sua validade (Stock → Validades e Resumo de Stock). Os lotes expirados nunca são vendidos.</span>
                </span>
              </div>
              {pharmacyEnabled && (
                <div className="md:col-span-2 flex flex-col gap-2.5 border border-border rounded-md px-3.5 py-3">
                  <span>
                    <span className="text-sm text-text-primary block">Farmácia - receita médica</span>
                    <span className="text-[12px] text-text-muted block">Na venda de um medicamento sujeito a receita médica. A receita especial (psicotrópicos e estupefacientes) é sempre obrigatória, com o utente e o documento de identificação.</span>
                  </span>
                  {[['OBRIGATORIA', 'Obrigatória', 'Sem o n.º da receita, a venda é recusada.'],
                    ['SE_APRESENTADA', 'Registar se apresentada', 'A receita é pedida e registada se o cliente a tiver; a venda nunca é bloqueada.']].map(([value, label, hint]) => (
                    <label key={value} className="flex items-start gap-2.5 cursor-pointer select-none">
                      <input type="radio" name="prescription_policy" checked={prescriptionPolicy === value} onChange={() => setPrescriptionPolicy(value)} className="w-4 h-4 mt-0.5 accent-accent cursor-pointer" />
                      <span>
                        <span className="text-[13px] text-text-primary block">{label}</span>
                        <span className="text-[12px] text-text-muted block">{hint}</span>
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </Section>

          {saved && <Notify success="Alterações guardadas com sucesso" />}

          <div className="flex items-center justify-end gap-4 flex-wrap mt-6 pt-4 border-t border-border">
            <button
              type="submit"
              disabled={saving || !email || !phone}
              className="shrink-0 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md px-6 py-3 flex items-center justify-center gap-2 transition-colors"
            >
              {saving ? <Loader2 size={17} className="animate-spin" /> : <Save size={17} />}
              {saving ? 'A guardar...' : 'Guardar alterações'}
            </button>
          </div>
        </form>
      )}

      {activeTab === 'atividades' && (
        <div className="bg-bg-elevated border border-border rounded-lg p-6 sm:p-8">
          <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5 mb-5"><Sparkles size={12} />Atividades</p>

          {activitiesLoading ? (
            <div className="flex justify-center py-12"><Loader2 size={20} className="animate-spin text-accent" /></div>
          ) : (
            <>
              {availableModules.filter((m) => !activities.some((a) => a.module_id === m.id)).length > 0 && (
                <div className="mb-6">
                  <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide mb-2.5">Modulos por configurar</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {availableModules.filter((m) => !activities.some((a) => a.module_id === m.id)).map((m) => (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => openActivateModule(m)}
                        className="text-left bg-bg-inset border border-dashed border-accent/50 hover:border-accent rounded-lg px-4 py-3.5 transition-colors cursor-pointer"
                      >
                        <p className="font-display font-medium text-text-primary">{m.name}</p>
                        <p className="text-[12px] text-text-muted mt-0.5">{m.description || 'Clique para configurar'}</p>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {activities.length === 0 ? (
                <p className="text-text-muted text-[13px] text-center py-12">Nenhuma atividade configurada ainda</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {activities.map((a) => (
                    <div key={a.id} className="border border-border rounded-md">
                      <div className="flex items-center justify-between px-4 py-3">
                        <p className="font-display font-medium text-text-primary">{a.name}</p>
                        <div className="flex items-center gap-2">
                          {!a.is_active && <span className="text-[10px] font-semibold uppercase tracking-wide text-danger bg-danger/10 px-1.5 py-0.5 rounded">Inativa</span>}
                          {displayAllowed && (
                            <button onClick={() => setDisplayActivity(a)} title="Ecrã do cliente: mensagem e imagens" className="flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent text-[12px] font-medium transition-colors cursor-pointer">
                              <MonitorUp size={14} />Ecrã do cliente
                            </button>
                          )}
                          <button onClick={() => openEditActivity(a)} aria-label="Editar atividade" className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                            <Pencil size={14} />
                          </button>
                          <ToggleSwitch checked={a.is_active} disabled={activityTogglingId === a.id} onChange={() => handleToggleActivity(a.id)} />
                        </div>
                      </div>

                      {(
                        <div className="border-t border-border px-4 py-3 bg-bg-inset/40">
                          <div className="flex items-center justify-between mb-2.5">
                            <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5"><CreditCard size={12} />Pontos de venda</p>
                            <button type="button" onClick={() => openCreatePos(a.id)} className="flex items-center gap-1.5 text-accent hover:text-accent-hover text-[12px] font-medium cursor-pointer">
                              <Plus size={13} />Novo ponto de venda
                            </button>
                          </div>
                          {posLoadingActivityId === a.id ? (
                            <div className="flex justify-center py-4"><Loader2 size={16} className="animate-spin text-accent" /></div>
                          ) : !posByActivity[a.id] || posByActivity[a.id].length === 0 ? (
                            <p className="text-text-muted text-[12px] py-2">Nenhum ponto de venda configurado</p>
                          ) : (
                            <div className="flex flex-col gap-1.5">
                              {posByActivity[a.id].map((p) => (
                                <div key={p.id} className="flex items-center justify-between bg-bg-elevated border border-border rounded-lg px-3.5 py-3">
                                  <div className="flex items-center gap-3">
                                    <p className="text-sm font-medium text-text-primary">{p.name}</p>
                                    {!p.is_active && <span className="text-[10px] font-semibold uppercase tracking-wide text-danger bg-danger/10 px-1.5 py-0.5 rounded">Inativo</span>}
                                    {canAssociate && (
                                      assocUserName(p.id) ? (
                                        <span className="flex items-center gap-1.5 bg-accent/10 text-accent text-[12px] font-medium rounded-md px-2.5 py-1">
                                          <Users size={12} />{assocUserName(p.id)}
                                        </span>
                                      ) : (
                                        <span className="text-[11px] text-text-muted">sem utilizador</span>
                                      )
                                    )}
                                  </div>
                                  <div className="flex items-center gap-2.5">
                                    {canAssociate && (
                                      <button onClick={() => openAssociation(p)} aria-label="Associar utilizador" title="Associar utilizador" className="inline-flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                                        <Link2 size={14} />
                                      </button>
                                    )}
                                    <button onClick={() => openEditPos(p)} aria-label="Editar ponto de venda" className="inline-flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                                      <Pencil size={14} />
                                    </button>
                                    <span title={p.is_default ? 'A caixa por defeito da atividade não pode ser desativada' : undefined}><ToggleSwitch checked={p.is_active} disabled={posTogglingId === p.id || !!p.is_default} onChange={() => handleTogglePos(p.id, a.id)} /></span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      <CustomerDisplayModal activity={displayActivity} onClose={() => setDisplayActivity(null)} />

      {activeTab === 'estabelecimentos' && (
        <div className="bg-bg-elevated border border-border rounded-lg p-6 sm:p-8">
          <div className="flex items-center justify-between mb-5">
            <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5"><Store size={12} />Estabelecimentos</p>
            <button onClick={openCreateEstablishment} className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer">
              <Plus size={16} />Novo estabelecimento
            </button>
          </div>
          {establishmentsLoading ? (
            <div className="flex items-center justify-center py-12 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>
          ) : establishments.length === 0 ? (
            <p className="text-text-muted text-[13px] text-center py-12">Nenhum estabelecimento registado ainda</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Código</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Nome</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Descrição</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Estado</th>
                    <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {establishments.map((item) => (
                    <tr key={item.id} className="border-b border-border last:border-0">
                      <td className="px-4 py-3 font-mono text-text-muted">{item.code}</td>
                      <td className="px-4 py-3 font-display font-medium text-text-primary">{item.name}</td>
                      <td className="px-4 py-3 text-text-muted">{item.description || '-'}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <ToggleSwitch checked={item.is_active} disabled={establishmentTogglingId === item.id} onChange={() => handleToggleEstablishment(item.id)} />
                          <span className={'text-[12px] font-medium ' + (item.is_active ? 'text-success' : 'text-text-muted')}>{item.is_active ? 'Ativo' : 'Inativo'}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button onClick={() => openEditEstablishment(item)} aria-label="Editar estabelecimento" className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                          <Pencil size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'agt' && company?.issuance_mode === 'ELETRONICA' && (
        <div className="bg-bg-elevated border border-border rounded-lg p-6 sm:p-8">
          <AgtCompanyPanel />
        </div>
      )}

      {activeTab === 'email' && <EmailSettingsTab canManage={can('company:manage')} />}
      {activeTab === 'notificacoes' && notificationsAllowed && <NotificationsTab canManage={can('company:manage')} onAllowed={setNotificationsAllowed} />}
      {activeTab === 'api' && apiAllowed && <ApiKeysTab onAllowed={setApiAllowed} />}

      {activeTab === 'suporte' && <SupportTab />}

      {activeTab === 'copias' && can('company:backup') && <CompanyBackupsPanel canManage={can('company:backup')} />}
      {activeTab === 'licenca' && licenseRequired && <LicensePanel load={getMyLicense} save={importMyLicense} canImport={can('company:manage')} />}

      {activeTab === 'ia' && aiInfo?.ai_enabled && (
        <AiCompanySettingsTab info={aiInfo} onChange={setAiInfo} canManage={can('company:manage')} />
      )}

      {activeTab === 'bancarias' && (
        <div className="bg-bg-elevated border border-border rounded-lg p-6 sm:p-8">
          <div className="flex items-center justify-between mb-5">
            <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5"><Landmark size={12} />Coordenadas Bancárias</p>
            <button onClick={openCreateBank} className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer">
              <Plus size={16} />Nova conta bancária
            </button>
          </div>
          {bankAccountsLoading ? (
            <div className="flex items-center justify-center py-12 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>
          ) : bankAccounts.length === 0 ? (
            <p className="text-text-muted text-[13px] text-center py-12">Nenhuma conta bancária registada ainda</p>
          ) : (
            <div className="flex flex-col gap-2">
              {bankAccounts.map((acc) => {
                const bank = banks.find((b) => b.id === acc.bank_id);
                const currency = currencies.find((c) => c.id === acc.currency_id);
                return (
                  <div key={acc.id} className="flex items-center justify-between gap-2 border border-border rounded-md px-4 py-3">
                    <div className="text-[13px] text-text-primary">
                      <span className="font-medium">{bank ? bank.acronym : '...'}</span>
                      <span className="text-text-muted font-mono ml-2">{acc.account_number} · {acc.iban.replace(/^(AO\d{2})(?!\.)/, '$1.')} · {currency?.code}</span>
                    </div>
                    <div className="flex items-center gap-2.5 shrink-0">
                      <ToggleSwitch checked={acc.is_active} disabled={bankTogglingId === acc.id} onChange={() => handleToggleBank(acc.id)} />
                      <button onClick={() => openEditBank(acc)} aria-label="Editar conta" className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                        <Pencil size={14} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {activeTab === 'series' && (
        <div className="bg-bg-elevated border border-border rounded-lg p-6 sm:p-8">
          <div className="flex items-center justify-between mb-5">
            <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5">
              <FileStack size={12} />
              Séries de Facturação
            </p>
            <div className="flex items-center gap-2">
              {issuanceMode === 'ELETRONICA' && (
                <button onClick={handleSyncSeries} disabled={seriesSyncing} className="flex items-center gap-2 border border-border hover:border-accent disabled:opacity-50 text-text-primary font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer">
                  {seriesSyncing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}Sincronizar com a AGT
                </button>
              )}
              <button onClick={openCreateSeriesForm} className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer">
                <Plus size={16} />{issuanceMode === 'ELETRONICA' ? 'Pedir série à AGT' : 'Nova série'}
              </button>
            </div>
          </div>
          <p className="text-[12px] text-text-muted mb-4">
            Modo actual: <span className="font-semibold text-text-primary">{issuanceMode === 'ELETRONICA' ? 'Eletrónica' : 'Manual'}</span>
            {issuanceMode === 'MANUAL' && (autoSeriesYear ? ' - série automática por ano' : ' - código de série livre')}
          </p>
          {seriesListLoading ? (
            <div className="flex items-center justify-center py-12 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>
          ) : seriesList.length === 0 ? (
            <p className="text-text-muted text-[13px] text-center py-12">Nenhuma série registada ainda</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Área</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Tipo</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Código</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Ano</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Modo Emissão</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Números</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Válido</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Próximo Nº</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">AGT</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Predefinida</th>
                    <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Estado</th>
                    <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-3">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {[...seriesList].sort((a, b) => {
                    const areaOf = (x) => x.is_facturacao ? 0 : x.is_tesouraria ? 1 : x.is_compras ? 2 : 3;
                    return areaOf(a) - areaOf(b);
                  }).map((s) => {
                    const docType = documentTypes.find((d) => d.id === s.document_type_id);
                    const areaLabel = s.is_facturacao ? 'Facturação' : s.is_tesouraria ? 'Tesouraria' : s.is_compras ? 'Compras' : '-';
                    const areaColor = s.is_facturacao ? 'text-accent' : s.is_tesouraria ? 'text-success' : s.is_compras ? 'text-purple-400' : 'text-text-muted';
                    return (
                      <tr key={s.id} className="border-b border-border last:border-0">
                        <td className={'px-4 py-3 text-[12px] font-medium ' + areaColor}>{areaLabel}</td>
                        <td className="px-4 py-3 font-mono text-text-muted">{docType ? docType.code : '?'}</td>
                        <td className="px-4 py-3 font-mono text-text-primary whitespace-nowrap">
                          {s.series_code}
                          {s.contingency_indicator === 'CONTINGENCIA' && <span className="ml-2 font-sans text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-500" title="Série de contingência: usada quando a AGT não está acessível">Contingência</span>}
                        </td>
                        <td className="px-4 py-3 font-mono text-text-muted">{s.year}</td>
                        <td className="px-4 py-3 text-text-muted">{s.issuance_mode === 'ELETRONICA' ? 'Eletrónica' : s.issuance_mode === 'FORMACAO' ? 'Formação' : 'Manual'}</td>
                        <td className="px-4 py-3 font-mono text-text-muted text-[12px]">{s.number_start}-{s.number_end}</td>
                        <td className="px-4 py-3 font-mono text-text-muted text-[12px]">
                          {s.series_start_ts ? new Date(s.series_start_ts).toLocaleString('pt-PT') + ' a ' + (s.series_end_ts ? new Date(s.series_end_ts).toLocaleString('pt-PT') : '...') : s.date_start + ' a ' + s.date_end}
                        </td>
                        <td className="px-4 py-3 font-mono text-text-primary">{s.current_number + 1}</td>
                        <td className="px-4 py-3 text-[12px] whitespace-nowrap">
                          {s.agt_status ? <span className={s.agt_status === 'F' ? 'text-danger' : 'text-success'}>{{ A: 'Aberta', U: 'Em utilização', F: 'Fechada' }[s.agt_status] || s.agt_status}</span> : <span className="text-text-muted">-</span>}
                        </td>
                        <td className="px-4 py-3 text-[12px] text-text-muted">{s.is_predefined ? 'Sim' : 'Não'}</td>
                        <td className="px-4 py-3">
                          <ToggleSwitch checked={s.is_active} disabled={seriesTogglingId === s.id} onChange={() => handleToggleSeries(s.id)} />
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button onClick={() => openEditSeriesForm(s)} aria-label="Editar série" className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                            <Pencil size={14} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <Modal open={establishmentModalOpen} onClose={() => setEstablishmentModalOpen(false)} title={editingEstablishmentId ? 'Editar estabelecimento' : 'Novo estabelecimento'}>
        <form onSubmit={handleEstablishmentSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Código *"><input value={establishmentForm.code} onChange={(e) => setEstablishmentForm((p) => ({ ...p, code: e.target.value }))} required className={inputClass} /></Field>
            <Field label="Nome *"><input value={establishmentForm.name} onChange={(e) => setEstablishmentForm((p) => ({ ...p, name: e.target.value }))} required className={inputClass} /></Field>
          </div>
          <Field label="Descrição"><input value={establishmentForm.description} onChange={(e) => setEstablishmentForm((p) => ({ ...p, description: e.target.value }))} className={inputClass} /></Field>
          <button type="submit" disabled={establishmentSaving || !establishmentForm.code || !establishmentForm.name} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
            {establishmentSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {establishmentSaving ? 'A guardar...' : editingEstablishmentId ? 'Guardar alterações' : 'Criar estabelecimento'}
          </button>
        </form>
      </Modal>

      <Modal open={bankModalOpen} onClose={() => setBankModalOpen(false)} title={editingBankId ? 'Editar conta bancária' : 'Nova conta bancária'}>
        <form onSubmit={handleBankSubmit} className="flex flex-col gap-4">
          <Field label="Banco *">
            <Select value={bankForm.bankId} onChange={(v) => setBankForm((p) => ({ ...p, bankId: v }))} options={banks.map((b) => ({ value: b.id, label: b.acronym + ' - ' + b.full_name }))} placeholder="Selecionar" />
          </Field>
          <Field label="Nº conta *"><input value={bankForm.accountNumber} onChange={(e) => setBankForm((p) => ({ ...p, accountNumber: e.target.value }))} required className={inputClass} /></Field>
          <Field label="IBAN *">
            <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent transition-colors">
              <span className="px-3 py-2.5 text-text-muted border-r border-border font-mono text-sm">AO06</span>
              <input value={bankForm.iban} onChange={(e) => setBankForm((p) => ({ ...p, iban: formatIbanRest(e.target.value) }))} required className="flex-1 bg-transparent border-none px-3 py-2.5 text-sm text-text-primary font-mono outline-none" />
            </div>
          </Field>
          <Field label="Moeda *">
            <Select value={bankForm.currencyId} onChange={(v) => setBankForm((p) => ({ ...p, currencyId: v }))} options={currencies.map((c) => ({ value: c.id, label: c.code }))} placeholder="Selecionar" />
          </Field>
          <button type="submit" disabled={bankSaving || !bankForm.bankId || !bankForm.accountNumber || !bankForm.iban || !bankForm.currencyId} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
            {bankSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {bankSaving ? 'A guardar...' : editingBankId ? 'Guardar alterações' : 'Criar conta bancária'}
          </button>
        </form>
      </Modal>

      <Modal open={seriesFormOpen} onClose={() => setSeriesFormOpen(false)} title={editingSeriesId ? "Editar série de facturação" : "Nova série de facturação"}>
        <form onSubmit={handleSeriesSubmit} className="flex flex-col gap-4">
          {allowedSeriesYears.length > 1 && !editingSeriesId && (
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Ano da serie *</label>
              <Select value={seriesForm.year || ''} onChange={(v) => setSeriesForm((p) => ({ ...p, year: v }))} options={allowedSeriesYears.map((y) => ({ value: String(y), label: String(y) }))} placeholder="Selecionar" />
            </div>
          )}
          {(() => {
            const currentYear = new Date().getFullYear();
            const isTodos = seriesForm.documentTypeId === '__TODOS__';
            // In ELETRONICA mode, restrict to the AGT electronic-submission subset (electronic_eligible)
            // ONLY for fiscal document types - non-fiscal working documents (Pro-forma, Guias, Orcamento...)
            // are never submitted to AGT regardless of the company's issuance mode, so they always need to be
            // selectable here (they still need their own sequential series). See DocumentType.is_fiscal /
            // electronic_eligible field docstrings for the SAF-T SalesInvoices vs WorkingDocuments distinction.
            // ELETRONICA: only the types sent to the AGT - a working document (pro-forma, guias...) keeps its series, made
            // automatically at its first document
            const eligibleTypes = issuanceMode === 'ELETRONICA' ? documentTypes.filter((d) => d.electronic_eligible && d.sent_to_agt) : documentTypes;
            const typeOptions = [
              ...(issuanceMode === 'MANUAL' ? [{ value: '__TODOS__', label: 'Todos' }] : []),
              ...eligibleTypes.map((d) => ({ value: d.id, label: d.code + ' - ' + d.name })),
            ];
            const selectedType = documentTypes.find((d) => d.id === seriesForm.documentTypeId);
            const derivedFacturacao = selectedType?.area === 'FACTURACAO';
            const derivedTesouraria = selectedType?.area === 'TESOURARIA';
            const derivedCompras = selectedType?.area === 'COMPRAS';

            return (
              <>
                {!editingSeriesId && (
                  <>
                    <div>
                      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Tipo de documento *</label>
                      <Select value={seriesForm.documentTypeId} onChange={(v) => setSeriesForm((p) => ({ ...p, documentTypeId: v }))} options={typeOptions} placeholder="Selecionar" />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Ano</label>
                        <input value={currentYear} disabled className={inputClass + ' opacity-60 cursor-not-allowed'} />
                      </div>
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Números</label>
                        <input value={'1 até 999999999'} disabled className={inputClass + ' opacity-60 cursor-not-allowed'} />
                      </div>
                    </div>
                    <p className="text-[11px] text-text-muted -mt-2">Válida de 01/01/{currentYear} até 31/12/{currentYear}</p>

                    <div className="grid grid-cols-3 gap-2">
                      <div className="flex items-center justify-between gap-2 border border-border rounded-md px-2.5 py-2 text-[12px]">
                        <span className={isTodos ? '' : 'opacity-60'}>Facturação</span>
                        <ToggleSwitch checked={isTodos ? seriesForm.todosFacturacao : derivedFacturacao} disabled={!isTodos} onChange={() => setSeriesForm((p) => ({ ...p, todosFacturacao: !p.todosFacturacao }))} />
                      </div>
                      <div className="flex items-center justify-between gap-2 border border-border rounded-md px-2.5 py-2 text-[12px]">
                        <span className={isTodos ? '' : 'opacity-60'}>Tesouraria</span>
                        <ToggleSwitch checked={isTodos ? seriesForm.todosTesouraria : derivedTesouraria} disabled={!isTodos} onChange={() => setSeriesForm((p) => ({ ...p, todosTesouraria: !p.todosTesouraria }))} />
                      </div>
                      <div className="flex items-center justify-between gap-2 border border-border rounded-md px-2.5 py-2 text-[12px]">
                        <span className={isTodos ? '' : 'opacity-60'}>Compras</span>
                        <ToggleSwitch checked={isTodos ? seriesForm.todosCompras : derivedCompras} disabled={!isTodos} onChange={() => setSeriesForm((p) => ({ ...p, todosCompras: !p.todosCompras }))} />
                      </div>
                    </div>
                    {isTodos && <p className="text-[11px] text-text-muted -mt-2">Uma série será criada para cada tipo de documento nas áreas selecionadas.</p>}

                    {issuanceMode === 'MANUAL' && !autoSeriesYear && !isTodos && (
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Código de série *</label>
                        <input value={seriesForm.seriesCode} onChange={(e) => setSeriesForm((p) => ({ ...p, seriesCode: e.target.value }))} required placeholder="Ex: S001" className={inputClass} />
                      </div>
                    )}
                    {issuanceMode === 'ELETRONICA' && (
                      <div>
                        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Estabelecimento *</label>
                        <Select value={seriesForm.establishmentId} onChange={(v) => setSeriesForm((p) => ({ ...p, establishmentId: v }))} options={establishments.map((e) => ({ value: e.id, label: e.code + ' - ' + e.name }))} placeholder="Selecionar" />
                      </div>
                    )}
                  </>
                )}
                {issuanceMode === 'ELETRONICA' && !editingSeriesId && (
                  <div>
                    <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Indicador</label>
                    <Select value={seriesForm.contingencyIndicator} onChange={(v) => setSeriesForm((p) => ({ ...p, contingencyIndicator: v }))} options={[{ value: 'NORMAL', label: 'Normal (N)' }, { value: 'CONTINGENCIA', label: 'Contingência (C) - usada quando a AGT não está acessível' }]} />
                    <p className="text-[11px] text-text-muted mt-1">
                      O código da série é pedido à AGT agora (é preciso ligação à internet). Peça também a série de contingência, enquanto há ligação. Os documentos não enviados à AGT (pró-forma, guias...) têm a sua série criada automaticamente.
                    </p>
                  </div>
                )}
                <div>
                  <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Descrição</label>
                  <input value={seriesForm.description} onChange={(e) => setSeriesForm((p) => ({ ...p, description: e.target.value }))} className={inputClass} />
                </div>
                <label className="flex items-center gap-2.5 cursor-pointer select-none">
                  <input type="checkbox" checked={seriesForm.isPredefined} onChange={(e) => setSeriesForm((p) => ({ ...p, isPredefined: e.target.checked }))} className="w-4 h-4 accent-accent cursor-pointer" />
                  <span className="text-sm text-text-primary">Predefinida</span>
                </label>
                <button
                  type="submit"
                  disabled={seriesSaving || (allowedSeriesYears.length > 1 && !editingSeriesId && !seriesForm.year) || (!editingSeriesId && !seriesForm.documentTypeId) || (!editingSeriesId && issuanceMode === 'MANUAL' && !autoSeriesYear && !isTodos && !seriesForm.seriesCode) || (!editingSeriesId && issuanceMode === 'ELETRONICA' && !seriesForm.establishmentId)}
                  className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
                >
                  {seriesSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
                  {seriesSaving ? 'A guardar...' : 'Criar série'}
                </button>
              </>
            );
          })()}
        </form>
      </Modal>

      <Modal open={activityModalOpen} onClose={() => setActivityModalOpen(false)} title={editingActivityId ? 'Editar atividade' : 'Configurar modulo'}>
        <form onSubmit={handleActivitySubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome *</label>
            <input
              value={activityForm.name}
              onChange={(e) => setActivityForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="Ex: Padaria, Bar Central, Hotel"
              required
              autoFocus
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
            />
          </div>
          <button
            type="submit"
            disabled={activitySaving || !activityForm.name.trim()}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {activitySaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {activitySaving ? 'A guardar...' : editingActivityId ? 'Guardar alterações' : 'Configurar atividade'}
          </button>
        </form>
      </Modal>

      <Modal open={!!assocPos} onClose={() => setAssocPos(null)} title={'Associação da caixa - ' + (assocPos?.name || '')}>
        <div className="flex flex-col gap-3">
          <p className="text-[13px] text-text-muted">Define qual utilizador esta autorizado a operar esta caixa.</p>
          {assocPos && assocUserName(assocPos.id) ? (
            <div className="flex items-center justify-between bg-bg-inset border border-border rounded-md px-3 py-2.5">
              <span className="text-[13px] text-text-primary">{assocUserName(assocPos.id)}</span>
              <button type="button" onClick={handleUnassign} disabled={assocSaving} className="flex items-center gap-1.5 text-danger text-[12px] cursor-pointer disabled:opacity-50">
                <Unlink size={12} />Desassociar
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <Select value={assocSelection} onChange={setAssocSelection} options={assocUsers.map((u) => ({ value: u.id, label: u.full_name }))} placeholder="Selecionar utilizador" />
              </div>
              <button type="button" onClick={handleAssociate} disabled={assocSaving || !assocSelection} className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-[12px] font-medium px-3 py-2 rounded-md cursor-pointer">
                <Link2 size={12} />Associar
              </button>
            </div>
          )}
          {assocError && <p className="text-danger text-[12px]">{assocError}</p>}
        </div>
      </Modal>

      <Modal open={posModalOpen} onClose={() => setPosModalOpen(false)} title={editingPosId ? 'Editar ponto de venda' : 'Novo ponto de venda'}>
        <form onSubmit={handlePosSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome *</label>
            <input
              value={posForm.name} readOnly={posForm.isDefault} style={posForm.isDefault ? { opacity: 0.6, cursor: 'not-allowed' } : undefined}
              onChange={(e) => setPosForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="Ex: Caixa 1, Balcão Rua"
              required
              autoFocus
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
            />
          </div>
          <label className="flex items-center gap-2.5 text-[13px] text-text-primary cursor-pointer">
            <input
              type="checkbox"
              checked={posForm.billetageEnabled}
              onChange={(e) => setPosForm((p) => ({ ...p, billetageEnabled: e.target.checked }))}
              className="w-4 h-4 accent-accent cursor-pointer"
            />
            Exigir billetagem no fecho de caixa
          </label>
          {/* the prices the cashier of this till may use (the gestor always may) */}
          <label className="flex items-center gap-2.5 text-[13px] text-text-primary cursor-pointer">
            <input type="checkbox" checked={posForm.allowPriceLevels} onChange={(e) => setPosForm((p) => ({ ...p, allowPriceLevels: e.target.checked }))} className="w-4 h-4 accent-accent cursor-pointer" />
            Permitir escolher o Preço 2 / Preço 3
          </label>
          <label className="flex items-center gap-2.5 text-[13px] text-text-primary cursor-pointer">
            <input type="checkbox" checked={posForm.allowFreePrice} onChange={(e) => setPosForm((p) => ({ ...p, allowFreePrice: e.target.checked }))} className="w-4 h-4 accent-accent cursor-pointer" />
            Permitir alterar o preço (preço livre)
          </label>
            {/* closing: accept a difference (always with a reason) or refuse it; propose the A4 closing report */}
            <label className="flex items-center gap-2 text-[13px] text-text-secondary cursor-pointer">
              <input type="checkbox" checked={posForm.acceptClosingDifference} onChange={(e) => setPosForm((p) => ({ ...p, acceptClosingDifference: e.target.checked }))} />
              Aceitar diferença no fecho (com motivo obrigatório)
            </label>
            {!posForm.acceptClosingDifference && (
              <p className="text-[11px] text-text-muted -mt-1 ml-6">O fecho só é aceite se o contado for igual ao esperado.</p>
            )}
            <label className="flex items-center gap-2 text-[13px] text-text-secondary cursor-pointer">
              <input type="checkbox" checked={posForm.printClosingReport} onChange={(e) => setPosForm((p) => ({ ...p, printClosingReport: e.target.checked }))} />
              Propor a impressão do relatório de fecho (A4)
            </label>
          <div className="rounded-md border border-border px-3.5 py-3 flex flex-col gap-2.5">
            <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer">
              <input type="checkbox" checked={posForm.printAfterSale} onChange={(e) => setPosForm((p) => ({ ...p, printAfterSale: e.target.checked }))} />
              {'Imprimir ap\u00f3s a venda'}
            </label>
            {posForm.printAfterSale && (
              <div className="flex items-center gap-5 pl-6 text-[13px] text-text-primary">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={posForm.printTicket} onChange={(e) => setPosForm((p) => ({ ...p, printTicket: e.target.checked }))} />
                  {'Tal\u00e3o'}
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={posForm.printA4} onChange={(e) => setPosForm((p) => ({ ...p, printA4: e.target.checked }))} />
                  A4
                </label>
              </div>
            )}
            <p className="text-[11px] text-text-muted">
              {!posForm.printAfterSale ? 'Desativado: nada \u00e9 impresso automaticamente.'
                : posForm.printTicket && posForm.printA4 ? 'Tal\u00e3o e A4: o caixa escolhe ap\u00f3s cada venda.'
                  : posForm.printTicket || posForm.printA4 ? 'Imprime diretamente ap\u00f3s cada venda.'
                    : 'Escolha pelo menos um formato.'}
            </p>
          </div>
          <button
            type="submit"
            disabled={posSaving || !posForm.name.trim()}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {posSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {posSaving ? 'A guardar...' : editingPosId ? 'Guardar alterações' : 'Criar ponto de venda'}
          </button>
        </form>
      </Modal>
    </main>
  );
}
