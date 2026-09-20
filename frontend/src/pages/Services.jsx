import { useState, useEffect, useMemo } from 'react';
import { Wrench, Plus, Loader2, Search, Pencil } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import { listServices, createService, updateService, toggleServiceStatus } from '../api/services';
import { listServiceTypes, createServiceType } from '../api/serviceTypes';
import { listResourceTypes } from '../api/booking';
import { listVatRates } from '../api/vat';
import { unitsApi, withholdingTaxesApi, vatCodesApi } from '../api/catalogs';
import { extractErrorMessage } from '../utils/errors';

function ToggleSwitch({ checked, onChange, disabled }) {
  const trackClass = 'relative w-10 h-5.5 rounded-full transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ' + (checked ? 'bg-success' : 'bg-border');
  const knobClass = 'absolute top-0.5 left-0.5 w-4.5 h-4.5 bg-white rounded-full transition-transform ' + (checked ? 'translate-x-4.5' : 'translate-x-0');
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

const emptyForm = {
  code: '', name: '', serviceTypeId: '', resourceTypeId: '', description: '', unitOfMeasureId: '',
  price: '', brand: '', vatId: '', withholdingTaxId: '',
  subjectToReturn: false, notAvailablePos: false, status: 'ACTIVO',
  exemptionReasonId: '',
  durationMinutes: '',
};

export default function Services() {
  const [services, setServices] = useState([]);
  const [serviceTypes, setServiceTypes] = useState([]);
  const [resourceTypes, setResourceTypes] = useState([]);
  const [vatRates, setVatRates] = useState([]);
  const [units, setUnits] = useState([]);
  const [withholdingTaxes, setWithholdingTaxes] = useState([]);
  const [vatCodes, setVatCodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [togglingId, setTogglingId] = useState(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [typeModalOpen, setTypeModalOpen] = useState(false);
  const [typeName, setTypeName] = useState('');
  const [typeSaving, setTypeSaving] = useState(false);
  const [typeFormError, setTypeFormError] = useState('');

  async function loadData() {
    setLoading(true);
    setError('');
    try {
      const [servicesData, typesData, resourceTypesData, vatData, unitsData, taxesData, vatCodesData] = await Promise.all([
        listServices(), listServiceTypes(), listResourceTypes(), listVatRates(), unitsApi.list(), withholdingTaxesApi.list(), vatCodesApi.list(),
      ]);
      setServices(servicesData);
      setServiceTypes(typesData.filter((t) => t.is_active));
      setResourceTypes(resourceTypesData.filter((t) => t.is_active));
      setVatRates(vatData);
      setUnits(unitsData.filter((u) => u.is_active));
      setWithholdingTaxes(taxesData.filter((w) => w.is_active));
      setVatCodes(vatCodesData.filter((v) => v.is_active));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar serviços'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const vatById = useMemo(() => {
    const map = {};
    vatRates.forEach((v) => { map[v.id] = v; });
    return map;
  }, [vatRates]);

  const filteredServices = useMemo(() => {
    if (!search.trim()) return services;
    const q = search.toLowerCase();
    return services.filter((s) => s.code.toLowerCase().includes(q) || s.name.toLowerCase().includes(q));
  }, [services, search]);

  function openCreateModal() {
    setEditingId(null);
    setForm({ ...emptyForm });
    setFormError('');
    setModalOpen(true);
  }

  function openEditModal(service) {
    setEditingId(service.id);
    setForm({
      code: service.code,
      name: service.name,
      serviceTypeId: service.service_type_id || '',
      resourceTypeId: service.resource_type_id || '',
      description: service.description || '',
      unitOfMeasureId: service.unit_of_measure_id || '',
      price: service.price != null ? String(service.price) : '',
      durationMinutes: service.duration_minutes != null ? String(service.duration_minutes) : '',
      brand: service.brand || '',
      vatId: service.vat_id,
      withholdingTaxId: service.withholding_tax_id || '',
      subjectToReturn: service.subject_to_return,
      notAvailablePos: service.not_available_pos,
      status: service.status,
      exemptionReasonId: service.exemption_reason_id || '',
    });
    setFormError('');
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setEditingId(null);
    setForm(emptyForm);
    setFormError('');
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleCreateType(e) {
    e.preventDefault();
    setTypeFormError('');
    setTypeSaving(true);
    try {
      const created = await createServiceType({ name: typeName, not_available_purchases: false, not_available_pos: false, not_available_sales: false });
      setServiceTypes((prev) => [...prev, created]);
      updateField('serviceTypeId', created.id);
      setTypeModalOpen(false);
      setTypeName('');
    } catch (err) {
      setTypeFormError(extractErrorMessage(err, 'Erro ao criar tipo de serviço'));
    } finally {
      setTypeSaving(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);

    const payload = {
      code: form.code,
      name: form.name,
      service_type_id: form.serviceTypeId || null,
      resource_type_id: form.resourceTypeId || null,
      description: form.description || null,
      unit_of_measure_id: form.unitOfMeasureId || null,
      price: form.price !== '' ? parseFloat(form.price) : null,
      brand: form.brand || null,
      vat_id: form.vatId,
      withholding_tax_id: form.withholdingTaxId || null,
      subject_to_return: form.subjectToReturn,
      not_available_pos: form.notAvailablePos,
      status: form.status,
      exemption_reason_id: form.exemptionReasonId || null,
      duration_minutes: form.durationMinutes !== '' ? parseInt(form.durationMinutes, 10) : null,
    };

    try {
      if (editingId) {
        await updateService(editingId, payload);
      } else {
        await createService(payload);
      }
      closeModal();
      await loadData();
    } catch (err) {
      setFormError(extractErrorMessage(err, editingId ? 'Erro ao atualizar serviço' : 'Erro ao criar serviço'));
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(serviceId) {
    setTogglingId(serviceId);
    try {
      await toggleServiceStatus(serviceId);
      await loadData();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado do serviço'));
    } finally {
      setTogglingId(null);
    }
  }

  const selectedVat = vatRates.find((v) => v.id === form.vatId);
  const isExemptVat = selectedVat && Number(selectedVat.rate) === 0;

  const isFormValid = form.code && form.name && form.vatId && (!isExemptVat || form.exemptionReasonId);

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Wrench size={22} className="text-accent" />
        Serviços
      </h2>
      <p className="text-text-muted text-sm mb-6">Gerir a ficha de serviços da sua empresa</p>

      {vatRates.length === 0 && !loading && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-4 py-3 text-sm rounded-r mb-5">
          Nenhuma taxa de IVA disponível - contacte o administrador da plataforma.
        </div>
      )}

      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="relative max-w-sm w-full sm:w-auto sm:min-w-[260px]">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Pesquisar por código ou nome..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
          />
        </div>
        <button
          onClick={openCreateModal}
          disabled={vatRates.length === 0}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer"
        >
          <Plus size={17} />
          Novo serviço
        </button>
      </div>

      <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
        {loading && (
          <div className="flex items-center justify-center py-16 text-text-muted text-sm">
            <Loader2 size={18} className="animate-spin mr-2" />
            A carregar...
          </div>
        )}
        {error && <div className="px-6 py-4 text-danger text-sm bg-danger/10">{error}</div>}
        {!loading && !error && filteredServices.length === 0 && (
          <div className="text-center py-16 text-text-muted text-sm">
            <span className="flex flex-col items-center gap-3">{search ? 'Nenhum serviço encontrado' : 'Nenhum serviço registado ainda'}<Search size={22} className="text-text-muted/40 mt-1" /></span>
          </div>
        )}
        {!loading && !error && filteredServices.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[760px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Código</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Designação</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Tipo</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Preço</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">IVA</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Estado</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredServices.map((s) => {
                  const type = serviceTypes.find((t) => t.id === s.service_type_id);
                  return (
                    <tr key={s.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                      <td className="px-6 py-4 font-mono text-text-muted">{s.code}</td>
                      <td className="px-6 py-4 font-display font-medium text-text-primary">{s.name}</td>
                      <td className="px-6 py-4 font-mono text-text-muted">{type?.name || '-'}</td>
                      <td className="px-6 py-4 font-mono text-text-primary">{s.price != null ? Number(s.price).toFixed(2) + ' Kz' : '-'}</td>
                      <td className="px-6 py-4 font-mono text-text-muted">{vatById[s.vat_id] ? vatById[s.vat_id].rate + '%' : '-'}</td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2.5">
                          <ToggleSwitch checked={s.is_active} disabled={togglingId === s.id} onChange={() => handleToggle(s.id)} />
                          <span className={'text-[12px] font-medium ' + (s.is_active ? 'text-success' : 'text-text-muted')}>
                            {s.is_active ? 'Ativo' : 'Inativo'}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => openEditModal(s)}
                          aria-label="Editar serviço"
                          className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer"
                        >
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

      <Modal open={modalOpen} onClose={closeModal} title={editingId ? 'Editar serviço' : 'Novo serviço'} maxWidthClass="max-w-3xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 max-h-[70vh] overflow-y-auto scrollbar-thin pr-1">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label="Código *">
              <input value={form.code} onChange={(e) => updateField('code', e.target.value)} required className={inputClass} />
            </Field>
            <Field label="Designação *">
              <input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} />
            </Field>
            <Field label="Marca">
              <input value={form.brand} onChange={(e) => updateField('brand', e.target.value)} className={inputClass} />
            </Field>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label="Tipo de serviço">
              <div className="flex items-center gap-1.5">
                <div className="flex-1">
                  <Select value={form.serviceTypeId} onChange={(v) => updateField('serviceTypeId', v)} options={serviceTypes.map((t) => ({ value: t.id, label: t.name }))} placeholder="Selecionar" />
                </div>
                <button type="button" onClick={() => setTypeModalOpen(true)} className="flex items-center justify-center w-10 h-10 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer shrink-0">
                  <Plus size={15} />
                </button>
              </div>
            </Field>
            <Field label="Unidade de medida">
              <Select value={form.unitOfMeasureId} onChange={(v) => updateField('unitOfMeasureId', v)} options={units.map((u) => ({ value: u.id, label: u.code + ' - ' + u.name }))} placeholder="Selecionar" />
            </Field>
            <Field label="IVA *">
              <Select value={form.vatId} onChange={(v) => updateField('vatId', v)} options={vatRates.map((v) => ({ value: v.id, label: v.name + ' (' + v.rate + '%)' }))} placeholder="Selecionar IVA" />
            </Field>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label="Tipo de recurso associado (opcional)">
              <Select value={form.resourceTypeId} onChange={(v) => updateField('resourceTypeId', v)} options={resourceTypes.map((t) => ({ value: t.id, label: t.name }))} placeholder="Nenhum - servico generico" />
            </Field>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label="Preço (Kz)">
              <input type="number" step="0.01" min="0" value={form.price} onChange={(e) => updateField('price', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Duração (minutos)" hint="Opcional - preenche a hora de fim nas reservas">
              <input type="number" step="1" min="5" max="1440" value={form.durationMinutes} onChange={(e) => updateField('durationMinutes', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Retenção">
              <Select value={form.withholdingTaxId} onChange={(v) => updateField('withholdingTaxId', v)} options={withholdingTaxes.map((w) => ({ value: w.id, label: w.name }))} placeholder="Sem retenção" />
            </Field>
            {isExemptVat && (
              <Field label="Motivo de isenção *">
                <Select value={form.exemptionReasonId} onChange={(v) => updateField('exemptionReasonId', v)} options={vatCodes.map((c) => ({ value: c.id, label: c.code + ' - ' + c.name }))} placeholder="Selecionar motivo" />
              </Field>
            )}
            {editingId && (
              <Field label="Estado">
                <Select value={form.status} onChange={(v) => updateField('status', v)} options={[{ value: 'ACTIVO', label: 'Activo' }, { value: 'INACTIVO', label: 'Inactivo' }]} />
              </Field>
            )}
          </div>

          <Field label="Descrição">
            <textarea value={form.description} onChange={(e) => updateField('description', e.target.value)} rows={2} className={inputClass} />
          </Field>

          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border">
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.notAvailablePos} onChange={(e) => updateField('notAvailablePos', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Não disponível POS</span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.subjectToReturn} onChange={(e) => updateField('subjectToReturn', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Sujeito a devolução</span>
            </label>
          </div>

          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{formError}</div>
          )}

          <button
            type="submit"
            disabled={saving || !isFormValid}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {saving ? 'A guardar...' : editingId ? 'Guardar alterações' : 'Criar serviço'}
          </button>
        </form>
      </Modal>

      <Modal open={typeModalOpen} onClose={() => { setTypeModalOpen(false); setTypeFormError(''); }} title="Novo tipo de serviço">
        <form onSubmit={handleCreateType} className="flex flex-col gap-4">
          <Field label="Nome *">
            <input value={typeName} onChange={(e) => setTypeName(e.target.value)} required className={inputClass} />
          </Field>
          {typeFormError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{typeFormError}</div>
          )}
          <button
            type="submit"
            disabled={typeSaving || !typeName}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {typeSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            Criar tipo de serviço
          </button>
        </form>
      </Modal>
    </main>
  );
}
