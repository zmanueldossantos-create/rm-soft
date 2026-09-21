import { useState, useEffect, useRef } from 'react';
import { Building2, Loader2, Save, Lock, Image, Upload, Store, Plus, Pencil, Landmark, X, Check, Trash2, FileStack, Sparkles, ChevronDown, CreditCard, Link2, Unlink } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import { getMyCompany, updateMyCompanyContact, uploadMyCompanyLogo, removeMyCompanyLogo, getMyCompanyBankAccounts, addMyCompanyBankAccount, updateMyCompanyBankAccount, toggleMyCompanyBankAccountStatus } from '../api/company';
import { listEstablishments, createEstablishment, updateEstablishment, toggleEstablishmentStatus } from '../api/establishments';
import { countriesApi, provincesApi, municipalitiesApi, currenciesApi, banksApi, documentTypesApi } from '../api/catalogs';
import { listDocumentSeries, createDocumentSeries, updateDocumentSeries, toggleDocumentSeriesStatus } from '../api/documentSeries';
import { listActivities, createActivity, updateActivity, toggleActivityStatus, listPointsOfSale, createPointOfSale, updatePointOfSale, togglePosStatus } from '../api/activity';
import apiClient from '../api/client';
import { extractErrorMessage } from '../utils/errors';
import { useCan } from '../utils/permissions';
import { listUsers } from '../api/users';
import { listCashPointAssociations, assignUserToCashPoint, unassignUserFromCashPoint } from '../api/tesouraria';

const API_ORIGIN = 'http://127.0.0.1:8001';

function ToggleSwitch({ checked, onChange, disabled }) {
  const trackClass = 'relative w-9 h-5 rounded-full transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ' + (checked ? 'bg-success' : 'bg-border');
  const knobClass = 'absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ' + (checked ? 'translate-x-4' : 'translate-x-0');
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={onChange} disabled={disabled} className={trackClass}>
      <span className={knobClass} />
    </button>
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

export default function CompanySettings() {
  const can = useCan();
  const [activeTab, setActiveTab] = useState('dados');

  const [company, setCompany] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
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
  const [allowsFutureSaleDate, setAllowsFutureSaleDate] = useState(false);
  const [suggestsLastDocumentDate, setSuggestsLastDocumentDate] = useState(false);
  const [issuanceMode, setIssuanceMode] = useState('MANUAL');
  const [electronicSignatureKey, setElectronicSignatureKey] = useState('');

  const [countries, setCountries] = useState([]);
  const [provinces, setProvinces] = useState([]);
  const [municipalities, setMunicipalities] = useState([]);
  const [currencies, setCurrencies] = useState([]);
  const [banks, setBanks] = useState([]);

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [removingLogo, setRemovingLogo] = useState(false);
  const fileInputRef = useRef(null);

  const [activities, setActivities] = useState([]);
  const [availableModules, setAvailableModules] = useState([]);
  const [activitiesLoading, setActivitiesLoading] = useState(false);
  const [activityModalOpen, setActivityModalOpen] = useState(false);
  const [editingActivityId, setEditingActivityId] = useState(null);
  const [activityForm, setActivityForm] = useState({ moduleId: '', name: '' });
  const [activitySaving, setActivitySaving] = useState(false);
  const [activityFormError, setActivityFormError] = useState('');
  const [activityTogglingId, setActivityTogglingId] = useState(null);

  const [expandedActivityId, setExpandedActivityId] = useState(null);
  const [posByActivity, setPosByActivity] = useState({});
  const [posLoadingActivityId, setPosLoadingActivityId] = useState(null);
  const [posModalOpen, setPosModalOpen] = useState(false);
  const [editingPosId, setEditingPosId] = useState(null);
  const [posForm, setPosForm] = useState({ activityId: '', name: '', billetageEnabled: false });
  const [posSaving, setPosSaving] = useState(false);
  const [posFormError, setPosFormError] = useState('');
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
  const [establishmentFormError, setEstablishmentFormError] = useState('');

  const [documentTypes, setDocumentTypes] = useState([]);
  const [seriesList, setSeriesList] = useState([]);
  const [seriesListLoading, setSeriesListLoading] = useState(false);
  const [seriesTogglingId, setSeriesTogglingId] = useState(null);
  const [seriesFormOpen, setSeriesFormOpen] = useState(false);
  const [editingSeriesId, setEditingSeriesId] = useState(null);
  const emptySeriesForm = { documentTypeId: '', establishmentId: '', seriesCode: '', description: '', contingencyIndicator: 'NORMAL', isPredefined: true, todosFacturacao: false, todosTesouraria: false, todosCompras: false };
  const [seriesForm, setSeriesForm] = useState(emptySeriesForm);
  const [seriesSaving, setSeriesSaving] = useState(false);
  const [seriesFormError, setSeriesFormError] = useState('');

  const [bankAccounts, setBankAccounts] = useState([]);
  const [bankAccountsLoading, setBankAccountsLoading] = useState(false);
  const [bankTogglingId, setBankTogglingId] = useState(null);
  const [bankModalOpen, setBankModalOpen] = useState(false);
  const [editingBankId, setEditingBankId] = useState(null);
  const [bankForm, setBankForm] = useState(emptyBankForm);
  const [bankSaving, setBankSaving] = useState(false);
  const [bankFormError, setBankFormError] = useState('');

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
      setSuggestsLastDocumentDate(data.suggests_last_document_date);
      setIssuanceMode(data.issuance_mode || 'MANUAL');
      setElectronicSignatureKey(data.electronic_signature_key || '');
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar dados da empresa'));
    } finally {
      setLoading(false);
    }
  }

  async function loadActivities() {
    setActivitiesLoading(true);
    try {
      const [activitiesData, modulesRes] = await Promise.all([
        listActivities(),
        apiClient.get('/activities/available-modules'),
      ]);
      setActivities(activitiesData);
      setAvailableModules(modulesRes.data);
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
      setError(extractErrorMessage(err, 'Erro ao carregar associacoes das caixas'));
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

  function toggleExpandActivity(activityId) {
    const next = expandedActivityId === activityId ? null : activityId;
    setExpandedActivityId(next);
    if (next && !posByActivity[activityId]) loadPointsOfSale(activityId);
  }

  function openCreatePos(activityId) {
    setEditingPosId(null);
    setPosForm({ activityId, name: '', billetageEnabled: false });
    setPosFormError('');
    setPosModalOpen(true);
  }

  function openEditPos(pos) {
    setEditingPosId(pos.id);
    setPosForm({ activityId: pos.activity_id, name: pos.name, billetageEnabled: pos.billetage_enabled || false });
    setPosFormError('');
    setPosModalOpen(true);
  }

  async function handlePosSubmit(e) {
    e.preventDefault();
    setPosFormError('');
    setPosSaving(true);
    try {
      if (editingPosId) {
        await updatePointOfSale(editingPosId, posForm.name, posForm.billetageEnabled);
      } else {
        await createPointOfSale(posForm.activityId, posForm.name, posForm.billetageEnabled);
      }
      setPosModalOpen(false);
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
      await refreshSeriesList();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado'));
    } finally {
      setSeriesTogglingId(null);
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
          contingency_indicator: seriesForm.contingencyIndicator || null,
          is_predefined: seriesForm.isPredefined,
        });
      } else {
        const isTodos = seriesForm.documentTypeId === '__TODOS__';
        await createDocumentSeries({
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
        issuance_mode: issuanceMode, electronic_signature_key: issuanceMode === 'ELETRONICA' ? (electronicSignatureKey || null) : null,
      });
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

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-sm rounded-r mb-5">
          {error}
        </div>
      )}

      <div className="flex items-center bg-bg-inset border border-border rounded-md p-0.5 self-start mb-5 w-fit flex-wrap">
        {[
          ['dados', 'Dados da Empresa', Building2],
          ['atividades', 'Atividades', Sparkles],
          ['estabelecimentos', 'Estabelecimentos', Store],
          ['bancarias', 'Coordenadas Bancárias', Landmark],
          ['series', 'Séries de Facturação', FileStack],
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
              {uploadError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-2.5 py-2 text-[11px] rounded-r mt-2">{uploadError}</div>}
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
                <Field label="Moeda principal">
                  <Select value={primaryCurrencyId} onChange={setPrimaryCurrencyId} options={currencies.filter((c) => c.id !== secondaryCurrencyId).map((c) => ({ value: c.id, label: c.code + ' - ' + c.name }))} placeholder="Selecionar" />
                </Field>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-6 border-t border-border mb-4">
            <Field label="Moeda secundária">
              <Select value={secondaryCurrencyId} onChange={setSecondaryCurrencyId} options={currencies.filter((c) => c.id !== primaryCurrencyId).map((c) => ({ value: c.id, label: c.code + ' - ' + c.name }))} placeholder="Selecionar" />
            </Field>
            <Field label="Província">
              <Select value={provinceId} onChange={handleProvinceChange} options={provincesForCountry.map((p) => ({ value: p.id, label: p.name }))} placeholder="Selecionar" />
            </Field>
            <Field label="Município">
              <Select value={municipalityId} onChange={setMunicipalityId} options={municipalities.filter((m) => m.province_id === provinceId).map((m) => ({ value: m.id, label: m.name }))} placeholder={provinceId ? 'Selecionar' : 'Selecione uma província primeiro'} />
            </Field>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            <Field label="Cidade"><input value={city} onChange={(e) => setCity(e.target.value)} className={inputClass} /></Field>
            <Field label="Endereço"><input value={address} onChange={(e) => setAddress(e.target.value)} className={inputClass} /></Field>
            <Field label="Modo de emissão">
              <Select value={issuanceMode} onChange={handleIssuanceModeChange} options={[{ value: 'MANUAL', label: 'Manual' }, { value: 'ELETRONICA', label: 'Eletrónica' }]} />
            </Field>
          </div>

          <div className="flex flex-col gap-4 pt-6 border-t border-border mt-6">
            {issuanceMode === 'ELETRONICA' && (
              <Field label="Assinatura eletrónica (chave privada AGT)">
                <input type="password" value={electronicSignatureKey} onChange={(e) => setElectronicSignatureKey(e.target.value)} className={inputClass} />
              </Field>
            )}
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
          </div>

          {saveError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mt-4">{saveError}</div>}
          {saved && <div className="bg-success/10 border-l-2 border-success text-success px-3.5 py-2.5 text-[13px] rounded-r mt-4">Alterações guardadas com sucesso</div>}

          <div className="flex items-center justify-between gap-4 flex-wrap mt-6 pt-4 border-t border-border">
            <p className="text-[11px] text-text-muted">PNG, JPG, WEBP - máx. 2MB</p>
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
                        <button type="button" onClick={() => toggleExpandActivity(a.id)} className="flex items-center gap-2 cursor-pointer">
                          <ChevronDown size={14} className={'text-text-muted transition-transform ' + (expandedActivityId === a.id ? 'rotate-180' : '')} />
                          <p className="font-display font-medium text-text-primary">{a.name}</p>
                          {!a.is_active && <span className="text-[10px] font-semibold uppercase tracking-wide text-danger bg-danger/10 px-1.5 py-0.5 rounded">Inativa</span>}
                        </button>
                        <div className="flex items-center gap-2">
                          <button onClick={() => openEditActivity(a)} aria-label="Editar atividade" className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                            <Pencil size={14} />
                          </button>
                          <ToggleSwitch checked={a.is_active} disabled={activityTogglingId === a.id} onChange={() => handleToggleActivity(a.id)} />
                        </div>
                      </div>

                      {expandedActivityId === a.id && (
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
                                <div key={p.id} className="flex items-center justify-between bg-bg-elevated border border-border rounded-md px-3 py-2">
                                  <div className="flex items-center gap-2">
                                    <p className="text-[13px] text-text-primary">{p.name}</p>
                                    {!p.is_active && <span className="text-[10px] font-semibold uppercase tracking-wide text-danger bg-danger/10 px-1.5 py-0.5 rounded">Inativo</span>}
                                    {canAssociate && <span className="text-[11px] text-text-muted">{assocUserName(p.id) ? '- ' + assocUserName(p.id) : '- sem utilizador'}</span>}
                                  </div>
                                  <div className="flex items-center gap-2">
                                    {canAssociate && (
                                      <button onClick={() => openAssociation(p)} aria-label="Associar utilizador" title="Associar utilizador" className="inline-flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                                        <Link2 size={12} />
                                      </button>
                                    )}
                                    <button onClick={() => openEditPos(p)} aria-label="Editar ponto de venda" className="inline-flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                                      <Pencil size={12} />
                                    </button>
                                    <ToggleSwitch checked={p.is_active} disabled={posTogglingId === p.id} onChange={() => handleTogglePos(p.id, a.id)} />
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
            <button onClick={openCreateSeriesForm} className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer">
              <Plus size={16} />Nova série
            </button>
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
                        <td className="px-4 py-3 font-mono text-text-primary">{s.series_code}</td>
                        <td className="px-4 py-3 font-mono text-text-muted">{s.year}</td>
                        <td className="px-4 py-3 text-text-muted">{s.issuance_mode === 'ELETRONICA' ? 'Eletrónica' : 'Manual'}</td>
                        <td className="px-4 py-3 font-mono text-text-muted text-[12px]">{s.number_start}-{s.number_end}</td>
                        <td className="px-4 py-3 font-mono text-text-muted text-[12px]">{s.date_start} a {s.date_end}</td>
                        <td className="px-4 py-3 font-mono text-text-primary">{s.current_number + 1}</td>
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
          {establishmentFormError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{establishmentFormError}</div>}
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
          {bankFormError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{bankFormError}</div>}
          <button type="submit" disabled={bankSaving || !bankForm.bankId || !bankForm.accountNumber || !bankForm.iban || !bankForm.currencyId} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
            {bankSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {bankSaving ? 'A guardar...' : editingBankId ? 'Guardar alterações' : 'Criar conta bancária'}
          </button>
        </form>
      </Modal>

      <Modal open={seriesFormOpen} onClose={() => setSeriesFormOpen(false)} title={editingSeriesId ? "Editar série de facturação" : "Nova série de facturação"}>
        <form onSubmit={handleSeriesSubmit} className="flex flex-col gap-4">
          {(() => {
            const currentYear = new Date().getFullYear();
            const isTodos = seriesForm.documentTypeId === '__TODOS__';
            // In ELETRONICA mode, restrict to the AGT electronic-submission subset (electronic_eligible)
            // ONLY for fiscal document types - non-fiscal working documents (Pro-forma, Guias, Orcamento...)
            // are never submitted to AGT regardless of the company's issuance mode, so they always need to be
            // selectable here (they still need their own sequential series). See DocumentType.is_fiscal /
            // electronic_eligible field docstrings for the SAF-T SalesInvoices vs WorkingDocuments distinction.
            const eligibleTypes = issuanceMode === 'ELETRONICA' ? documentTypes.filter((d) => d.electronic_eligible || !d.is_fiscal) : documentTypes;
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
                {issuanceMode === 'ELETRONICA' && (
                  <div>
                    <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Indicador</label>
                    <Select value={seriesForm.contingencyIndicator} onChange={(v) => setSeriesForm((p) => ({ ...p, contingencyIndicator: v }))} options={[{ value: 'NORMAL', label: 'Normal' }, { value: 'CONTINGENCIA', label: 'Contingência' }]} />
                    {!editingSeriesId && <p className="text-[11px] text-text-muted mt-1">O código de série será solicitado à AGT automaticamente.</p>}
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
                {seriesFormError && (
                  <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{seriesFormError}</div>
                )}
                <button
                  type="submit"
                  disabled={seriesSaving || (!editingSeriesId && !seriesForm.documentTypeId) || (!editingSeriesId && issuanceMode === 'MANUAL' && !autoSeriesYear && !isTodos && !seriesForm.seriesCode) || (!editingSeriesId && issuanceMode === 'ELETRONICA' && !seriesForm.establishmentId)}
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
          {activityFormError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{activityFormError}</div>
          )}
          <button
            type="submit"
            disabled={activitySaving || !activityForm.name.trim()}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {activitySaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {activitySaving ? 'A guardar...' : editingActivityId ? 'Guardar alteracoes' : 'Configurar atividade'}
          </button>
        </form>
      </Modal>

      <Modal open={!!assocPos} onClose={() => setAssocPos(null)} title={'Associacao da caixa - ' + (assocPos?.name || '')}>
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
              value={posForm.name}
              onChange={(e) => setPosForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="Ex: Caixa 1, Balcao Rua"
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
          {posFormError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{posFormError}</div>
          )}
          <button
            type="submit"
            disabled={posSaving || !posForm.name.trim()}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {posSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {posSaving ? 'A guardar...' : editingPosId ? 'Guardar alteracoes' : 'Criar ponto de venda'}
          </button>
        </form>
      </Modal>
    </main>
  );
}
