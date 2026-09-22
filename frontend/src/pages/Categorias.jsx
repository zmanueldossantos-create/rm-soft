import { useState, useEffect } from 'react';
import { Tags, Wrench, Plus, Pencil, Loader2, X, PiggyBank, CreditCard, Boxes, PackageMinus } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import { listProductCategories, createProductCategory, updateProductCategory, toggleProductCategoryStatus } from '../api/productCategories';
import { listServiceTypes, createServiceType, updateServiceType, toggleServiceTypeStatus } from '../api/serviceTypes';
import { listCashMovementReasons, createCashMovementReason, updateCashMovementReason, toggleCashMovementReasonStatus, listPaymentMethodPreferences, setPaymentMethodPreference, listDocumentTypePaymentTermPreferences, setDocumentTypePaymentTermPreference } from '../api/tesouraria';
import { listResourceTypes, createResourceType, updateResourceType, toggleResourceTypeStatus } from '../api/booking';
import { listConsumptionReasons, createConsumptionReason, updateConsumptionReason, toggleConsumptionReasonStatus } from '../api/internalConsumption';
import { extractErrorMessage } from '../utils/errors';
import { useCan } from '../utils/permissions';

function ToggleSwitch({ checked, onChange, disabled }) {
  const trackClass = 'relative w-9 h-5 rounded-full transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ' + (checked ? 'bg-success' : 'bg-border');
  const knobClass = 'absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ' + (checked ? 'translate-x-4' : 'translate-x-0');
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={onChange} disabled={disabled} className={trackClass}>
      <span className={knobClass} />
    </button>
  );
}

const inputClass = "w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors";

const CATALOGS = [
  { key: 'product_categories', label: 'Categorias de Produto', icon: Tags, api: { list: listProductCategories, create: createProductCategory, update: updateProductCategory, toggle: toggleProductCategoryStatus } },
  { key: 'service_types', label: 'Tipos de Serviço', icon: Wrench, api: { list: listServiceTypes, create: createServiceType, update: updateServiceType, toggle: toggleServiceTypeStatus } },
  { key: 'cash_movement_reasons', label: 'Motivos de Movimento de Caixa', icon: PiggyBank, api: {
    list: () => listCashMovementReasons(),
    create: (p) => createCashMovementReason(p.name, p.direction),
    update: (id, p) => updateCashMovementReason(id, p.name, p.direction),
    toggle: (id) => toggleCashMovementReasonStatus(id),
  } },
  { key: 'resource_types', label: 'Tipos de Recurso', icon: Boxes, api: {
    list: () => listResourceTypes(),
    create: (p) => createResourceType(p.name, p.requires_service),
    update: (id, p) => updateResourceType(id, p.name, p.requires_service),
    toggle: (id) => toggleResourceTypeStatus(id),
  } },
  { key: 'consumption_reasons', label: 'Motivos de Consumo Interno', icon: PackageMinus, api: {
    list: () => listConsumptionReasons(),
    create: (p) => createConsumptionReason(p.name),
    update: (id, p) => updateConsumptionReason(id, p.name),
    toggle: (id) => toggleConsumptionReasonStatus(id),
  } },
];

// Permission codes per catalog: 'view' decides whether its card is shown, 'manage' whether
// create / edit / toggle are enabled inside it.
const CATALOG_PERMS = {
  product_categories: { view: 'product_categories:view', manage: 'product_categories:manage' },
  service_types: { view: 'service_types:view', manage: 'service_types:manage' },
  cash_movement_reasons: { view: 'tesouraria:reasons_view', manage: 'tesouraria:reasons_manage' },
  resource_types: { view: 'resource_types:view', manage: 'resource_types:manage' },
  consumption_reasons: { view: 'consumption_reasons:view', manage: 'consumption_reasons:manage' },
};

const emptyForm = { name: '', not_available_purchases: false, not_available_pos: false, not_available_sales: false };
const emptyNameOnlyForm = { name: '', requires_service: false };
const emptyReasonForm = { name: '', direction: 'SAIDA' };

export default function Categorias() {
  const can = useCan();
  const visibleCatalogs = CATALOGS.filter((c) => can(CATALOG_PERMS[c.key].view));
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [activeCatalog, setActiveCatalog] = useState(null);
  const canManage = activeCatalog ? can(CATALOG_PERMS[activeCatalog.key].manage) : false;
  const [items, setItems] = useState([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [togglingId, setTogglingId] = useState(null);

  const [paymentMethods, setPaymentMethods] = useState([]);
  const [paymentMethodsModalOpen, setPaymentMethodsModalOpen] = useState(false);
  const [paymentMethodsLoading, setPaymentMethodsLoading] = useState(false);
  const [togglingPaymentMethodId, setTogglingPaymentMethodId] = useState(null);
  const [paymentTermPrefs, setPaymentTermPrefs] = useState([]);
  const [paymentTermPrefsModalOpen, setPaymentTermPrefsModalOpen] = useState(false);
  const [paymentTermPrefsLoading, setPaymentTermPrefsLoading] = useState(false);
  const [togglingPaymentTermPrefId, setTogglingPaymentTermPrefId] = useState(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  async function loadCounts() {
    setLoading(true);
    setError('');
    try {
      const results = await Promise.allSettled(visibleCatalogs.map((c) => c.api.list()));
      const newCounts = {};
      visibleCatalogs.forEach((c, i) => { if (results[i].status === 'fulfilled') newCounts[c.key] = results[i].value.length; });
      setCounts(newCounts);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar categorias'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCounts();
    listPaymentMethodPreferences().then(setPaymentMethods).catch(() => {});
    listDocumentTypePaymentTermPreferences().then(setPaymentTermPrefs).catch(() => {});
  }, []);

  async function openCatalog(catalog) {
    setActiveCatalog(catalog);
    setItemsLoading(true);
    try {
      setItems(await catalog.api.list());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar itens'));
    } finally {
      setItemsLoading(false);
    }
  }

  function closeCatalogModal() {
    setActiveCatalog(null);
    setItems([]);
  }

  async function refreshItems() {
    if (!activeCatalog) return;
    const data = await activeCatalog.api.list();
    setItems(data);
    setCounts((prev) => ({ ...prev, [activeCatalog.key]: data.length }));
  }

  async function openPaymentMethodsModal() {
    setPaymentMethodsModalOpen(true);
    setPaymentMethodsLoading(true);
    try {
      setPaymentMethods(await listPaymentMethodPreferences());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar metodos de pagamento'));
    } finally {
      setPaymentMethodsLoading(false);
    }
  }

  async function handleTogglePaymentMethod(method) {
    setTogglingPaymentMethodId(method.id);
    try {
      await setPaymentMethodPreference(method.id, !method.available_at_pos);
      setPaymentMethods(await listPaymentMethodPreferences());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar preferencia'));
    } finally {
      setTogglingPaymentMethodId(null);
    }
  }

  async function openPaymentTermPrefsModal() {
    setPaymentTermPrefsModalOpen(true);
    setPaymentTermPrefsLoading(true);
    try {
      setPaymentTermPrefs(await listDocumentTypePaymentTermPreferences());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar condicoes de pagamento'));
    } finally {
      setPaymentTermPrefsLoading(false);
    }
  }

  async function handleTogglePaymentTermPref(docType) {
    setTogglingPaymentTermPrefId(docType.id);
    try {
      await setDocumentTypePaymentTermPreference(docType.id, !docType.requires_payment_term);
      setPaymentTermPrefs(await listDocumentTypePaymentTermPreferences());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar preferencia'));
    } finally {
      setTogglingPaymentTermPrefId(null);
    }
  }

  async function handleToggle(id) {
    setTogglingId(id);
    try {
      await activeCatalog.api.toggle(id);
      await refreshItems();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado'));
    } finally {
      setTogglingId(null);
    }
  }

  function openCreateForm() {
    setEditingId(null);
    if (activeCatalog?.key === 'cash_movement_reasons') setForm(emptyReasonForm);
    else if (activeCatalog?.key === 'resource_types' || activeCatalog?.key === 'consumption_reasons') setForm(emptyNameOnlyForm);
    else setForm(emptyForm);
    setFormError('');
    setFormOpen(true);
  }

  function openEditForm(item) {
    setEditingId(item.id);
    if (activeCatalog?.key === 'cash_movement_reasons') {
      setForm({ name: item.name, direction: item.direction });
    } else if (activeCatalog?.key === 'resource_types') {
      setForm({ name: item.name, requires_service: item.requires_service });
    } else if (activeCatalog?.key === 'consumption_reasons') {
      setForm({ name: item.name });
    } else {
      setForm({
        name: item.name,
        not_available_purchases: item.not_available_purchases,
        not_available_pos: item.not_available_pos,
        not_available_sales: item.not_available_sales,
      });
    }
    setFormError('');
    setFormOpen(true);
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      if (editingId) {
        await activeCatalog.api.update(editingId, form);
      } else {
        await activeCatalog.api.create(form);
      }
      setFormOpen(false);
      await refreshItems();
    } catch (err) {
      setFormError(extractErrorMessage(err, editingId ? 'Erro ao atualizar' : 'Erro ao criar'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Tags size={22} className="text-accent" />
        Catálogos
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Categorias de produto e tipos de serviço - próprios da sua empresa
      </p>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {visibleCatalogs.map((c) => (
            <button
              key={c.key}
              onClick={() => openCatalog(c)}
              className="bg-bg-elevated border border-border hover:border-accent rounded-lg p-5 text-left transition-colors cursor-pointer"
            >
              <c.icon size={20} className="text-accent mb-3" />
              <p className="font-display font-semibold text-text-primary text-sm mb-1">{c.label}</p>
              <p className="text-text-muted text-[12px] font-mono">{counts[c.key] ?? 0} itens</p>
            </button>
          ))}
          {can('tesouraria:payment_prefs_view') && (
          <button
            onClick={openPaymentMethodsModal}
            className="bg-bg-elevated border border-border hover:border-accent rounded-lg p-5 text-left transition-colors cursor-pointer"
          >
            <CreditCard size={20} className="text-accent mb-3" />
            <p className="font-display font-semibold text-text-primary text-sm mb-1">Métodos de Pagamento</p>
            <p className="text-text-muted text-[12px] font-mono">{paymentMethods.length} itens</p>
          </button>
          )}
          {can('documents:payment_term_prefs_view') && (
          <button
            onClick={openPaymentTermPrefsModal}
            className="bg-bg-elevated border border-border hover:border-accent rounded-lg p-5 text-left transition-colors cursor-pointer"
          >
            <CreditCard size={20} className="text-accent mb-3" />
            <p className="font-display font-semibold text-text-primary text-sm mb-1">Condições de Pagamento Obrigatórias</p>
            <p className="text-text-muted text-[12px] font-mono">{paymentTermPrefs.length} itens</p>
          </button>
          )}
        </div>
      )}

      <Modal open={!!activeCatalog} onClose={closeCatalogModal} title={activeCatalog?.label || ''} maxWidthClass="max-w-2xl">
        <div className="flex flex-col gap-4">
          {canManage && (
          <button
            onClick={openCreateForm}
            className="flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer self-start"
          >
            <Plus size={16} />
            Novo
          </button>
          )}

          {itemsLoading ? (
            <div className="flex items-center justify-center py-8 text-text-muted text-sm">
              <Loader2 size={16} className="animate-spin mr-2" />
              A carregar...
            </div>
          ) : (
            <div className="flex flex-col gap-1.5 max-h-[420px] overflow-y-auto scrollbar-thin">
              {items.length === 0 && <p className="text-text-muted text-[13px] text-center py-6">Nenhum item registado</p>}
              {items.map((item) => (
                <div key={item.id} className="flex items-center justify-between gap-2 border border-border rounded-md px-3.5 py-2.5">
                  <span className="text-[13px] text-text-primary truncate">{item.name}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    <ToggleSwitch checked={item.is_active} disabled={togglingId === item.id || !canManage} onChange={() => handleToggle(item.id)} />
                    <button onClick={() => openEditForm(item)} disabled={!canManage} className="flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
                      <Pencil size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      <Modal open={paymentMethodsModalOpen} onClose={() => setPaymentMethodsModalOpen(false)} title="Metodos de Pagamento" maxWidthClass="max-w-2xl">
        <div className="flex flex-col gap-4">
          <p className="text-text-muted text-[13px]">Escolha quais os 12 meios de pagamento oficiais da AGT vao aparecer para seleccao na Caixa</p>
          {paymentMethodsLoading ? (
            <div className="flex items-center justify-center py-8 text-text-muted text-sm">
              <Loader2 size={16} className="animate-spin mr-2" />
              A carregar...
            </div>
          ) : (
            <div className="flex flex-col gap-1.5 max-h-[420px] overflow-y-auto scrollbar-thin">
              {paymentMethods.map((m) => (
                <div key={m.id} className="flex items-center justify-between gap-2 border border-border rounded-md px-3.5 py-2.5">
                  <div className="flex items-center gap-2.5">
                    <span className="font-mono text-[11px] text-text-muted bg-bg-inset px-1.5 py-0.5 rounded">{m.code}</span>
                    <span className="text-[13px] text-text-primary">{m.name}</span>
                    {m.is_cash && <span className="text-[10px] font-semibold uppercase tracking-wide text-success bg-success/10 px-1.5 py-0.5 rounded">Numerario</span>}
                  </div>
                  <ToggleSwitch checked={m.available_at_pos} disabled={togglingPaymentMethodId === m.id || !can('tesouraria:payment_prefs_manage')} onChange={() => handleTogglePaymentMethod(m)} />
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      <Modal open={paymentTermPrefsModalOpen} onClose={() => setPaymentTermPrefsModalOpen(false)} title="Condicoes de Pagamento Obrigatorias" maxWidthClass="max-w-2xl">
        <div className="flex flex-col gap-4">
          <p className="text-text-muted text-[13px]">Escolha para quais tipos de documento e obrigatorio escolher uma condicao de pagamento (o catalogo da plataforma define o padrao)</p>
          {paymentTermPrefsLoading ? (
            <div className="flex items-center justify-center py-8 text-text-muted text-sm">
              <Loader2 size={16} className="animate-spin mr-2" />
              A carregar...
            </div>
          ) : (
            <div className="flex flex-col gap-1.5 max-h-[420px] overflow-y-auto scrollbar-thin">
              {paymentTermPrefs.map((d) => (
                <div key={d.id} className="flex items-center justify-between gap-2 border border-border rounded-md px-3.5 py-2.5">
                  <div className="flex items-center gap-2.5">
                    <span className="font-mono text-[11px] text-text-muted bg-bg-inset px-1.5 py-0.5 rounded">{d.code}</span>
                    <span className="text-[13px] text-text-primary">{d.name}</span>
                  </div>
                  <ToggleSwitch checked={d.requires_payment_term} disabled={togglingPaymentTermPrefId === d.id || !can('documents:payment_term_prefs_manage')} onChange={() => handleTogglePaymentTermPref(d)} />
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={(editingId ? 'Editar' : 'Novo') + ' - ' + (activeCatalog?.label || '')}>
        {activeCatalog && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome *</label>
              <input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} />
            </div>
            {activeCatalog?.key === 'cash_movement_reasons' ? (
              <div>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Direção *</label>
                <Select
                  value={form.direction}
                  onChange={(v) => updateField('direction', v)}
                  options={[{ value: 'ENTRADA', label: 'Entrada' }, { value: 'SAIDA', label: 'Saída' }]}
                />
              </div>
            ) : activeCatalog?.key === 'resource_types' ? (
              <label className="flex items-center gap-2.5 cursor-pointer select-none">
                <input type="checkbox" checked={form.requires_service} onChange={(e) => updateField('requires_service', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                <span className="text-sm text-text-primary">Exige servico na reserva</span>
              </label>
            ) : activeCatalog?.key === 'consumption_reasons' ? null : (
              <div className="flex flex-col gap-2">
                <label className="flex items-center gap-2.5 cursor-pointer select-none">
                  <input type="checkbox" checked={form.not_available_purchases} onChange={(e) => updateField('not_available_purchases', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                  <span className="text-sm text-text-primary">Não disponível em compras</span>
                </label>
                <label className="flex items-center gap-2.5 cursor-pointer select-none">
                  <input type="checkbox" checked={form.not_available_pos} onChange={(e) => updateField('not_available_pos', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                  <span className="text-sm text-text-primary">Não disponível no POS</span>
                </label>
                <label className="flex items-center gap-2.5 cursor-pointer select-none">
                  <input type="checkbox" checked={form.not_available_sales} onChange={(e) => updateField('not_available_sales', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                  <span className="text-sm text-text-primary">Não disponível em vendas</span>
                </label>
              </div>
            )}
            {formError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{formError}</div>
            )}
            <button
              type="submit"
              disabled={saving}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
              {saving ? 'A guardar...' : editingId ? 'Guardar alterações' : 'Criar'}
            </button>
          </form>
        )}
      </Modal>
    </main>
  );
}
