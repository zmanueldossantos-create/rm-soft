import { useState, useEffect } from 'react';
import { Boxes, Plus, Pencil, Loader2 } from 'lucide-react';
import Select from '../components/Select';
import { listActivities } from '../api/activity';
import { listResources, createResource, updateResource, toggleResourceStatus, listResourceTypes, listResourceStatuses } from '../api/booking';
import { extractErrorMessage } from '../utils/errors';
import Modal from '../components/Modal';

function ToggleSwitch({ checked, onChange, disabled }) {
  const trackClass = 'relative w-9 h-5 rounded-full transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ' + (checked ? 'bg-success' : 'bg-border');
  const knobClass = 'absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ' + (checked ? 'translate-x-4' : 'translate-x-0');
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={onChange} disabled={disabled} className={trackClass}>
      <span className={knobClass} />
    </button>
  );
}

const STATUS_LABEL = { LIVRE: 'Livre', OCUPADA: 'Ocupado', RESERVADA: 'Reservado' };
const STATUS_STYLE = {
  LIVRE: 'text-success bg-success/10',
  OCUPADA: 'text-danger bg-danger/10',
  RESERVADA: 'text-accent bg-accent/10',
};

function formatKz(value) {
  return Number(value || 0).toLocaleString('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function Recursos() {
  const [activities, setActivities] = useState([]);
  const [selectedActivityId, setSelectedActivityId] = useState('');
  const [resources, setResources] = useState([]);
  const [resourceTypes, setResourceTypes] = useState([]);
  const [statusByResource, setStatusByResource] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [togglingId, setTogglingId] = useState(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ activityId: '', resourceTypeId: '', name: '', capacity: '' });
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listActivities().then((data) => {
      const active = data.filter((a) => a.is_active);
      setActivities(active);
      if (active.length > 0) setSelectedActivityId(active[0].id);
    }).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar atividades')));
    // Resource types are managed under Configuracoes > Catalogos > Tipos de Recurso -
    // this screen only reads the catalog to populate the selector below.
    listResourceTypes().then(setResourceTypes).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar tipos de recurso')));
  }, []);

  useEffect(() => {
    if (!selectedActivityId) return;
    loadResources();
  }, [selectedActivityId]);

  async function loadResources() {
    setLoading(true);
    setError('');
    try {
      setResources(await listResources(selectedActivityId));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar recursos'));
    } finally {
      setLoading(false);
    }
    // Derived status (Livre / Ocupado / Reservado) computed by the backend from open
    // accounts and active bookings - never stored on Resource itself.
    listResourceStatuses(selectedActivityId).then((rows) => {
      setStatusByResource(Object.fromEntries(rows.map((row) => [row.resource_id, row])));
    }).catch(() => setStatusByResource({}));
  }

  function openCreateForm() {
    setEditingId(null);
    setForm({ activityId: selectedActivityId, resourceTypeId: '', name: '', capacity: '' });
    setFormError('');
    setFormOpen(true);
  }

  function openEditForm(resource) {
    setEditingId(resource.id);
    setForm({ activityId: resource.activity_id, resourceTypeId: resource.resource_type_id, name: resource.name, capacity: resource.capacity ? String(resource.capacity) : '' });
    setFormError('');
    setFormOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      const capacityValue = form.capacity ? parseInt(form.capacity, 10) : null;
      if (editingId) {
        await updateResource(editingId, form.name, capacityValue);
      } else {
        await createResource(form.activityId, form.resourceTypeId, form.name, capacityValue);
      }
      setFormOpen(false);
      if (form.activityId === selectedActivityId) {
        await loadResources();
      }
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao guardar recurso'));
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(resourceId) {
    setTogglingId(resourceId);
    try {
      await toggleResourceStatus(resourceId);
      await loadResources();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado'));
    } finally {
      setTogglingId(null);
    }
  }

  function typeName(resourceTypeId) {
    return resourceTypes.find((t) => t.id === resourceTypeId)?.name || '-';
  }

  const activeResourceTypes = resourceTypes.filter((t) => t.is_active);

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
          <Boxes size={22} className="text-accent" />
          Recursos
        </h2>
        <button
          onClick={openCreateForm}
          disabled={!selectedActivityId}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer"
        >
          <Plus size={16} />
          Novo recurso
        </button>
      </div>
      <p className="text-text-muted text-sm mb-6">
        Chambres, praticiens, mesas ou qualquer outro recurso reservavel - a base para o sistema de reservas.
        Os tipos disponiveis geram-se em Configuracoes {'>'} Catalogos {'>'} Tipos de Recurso.
      </p>

      {activities.length > 1 && (
        <div className="w-64 mb-4">
          <Select
            value={selectedActivityId}
            onChange={setSelectedActivityId}
            options={activities.map((a) => ({ value: a.id, label: a.name }))}
            placeholder="Selecionar atividade"
          />
        </div>
      )}

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : resources.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <Boxes size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium mb-1">Nenhum recurso registado</p>
          <p className="text-text-muted text-sm">Crie o primeiro recurso desta atividade para comecar a gerir reservas</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {resources.map((r) => (
            <div key={r.id} className="bg-bg-elevated border border-border rounded-lg p-4 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <p className="font-mono text-[10px] text-text-muted uppercase tracking-wide">{typeName(r.resource_type_id)}</p>
                  {r.is_active && (
                    <span className={'text-[10px] font-semibold px-1.5 py-0.5 rounded-full ' + (STATUS_STYLE[statusByResource[r.id]?.status] || STATUS_STYLE.LIVRE)}>
                      {STATUS_LABEL[statusByResource[r.id]?.status] || 'Livre'}
                    </span>
                  )}
                </div>
                <p className="font-display font-medium text-text-primary text-sm truncate">{r.name}</p>
                {r.capacity && <p className="text-text-muted text-[12px] mt-0.5">Capacidade: {r.capacity}</p>}
                {r.is_active && statusByResource[r.id]?.status === 'OCUPADA' && (
                  <p className="text-text-muted text-[12px] mt-0.5 font-mono">
                    {statusByResource[r.id].open_accounts} conta(s) - {formatKz(statusByResource[r.id].open_total)} Kz
                  </p>
                )}
                {r.is_active && statusByResource[r.id]?.status === 'RESERVADA' && (
                  <p className="text-text-muted text-[12px] mt-0.5">
                    {new Date(statusByResource[r.id].booking_starts_at).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' })}
                    {statusByResource[r.id].booking_guest_name ? ' - ' + statusByResource[r.id].booking_guest_name : ''}
                    {statusByResource[r.id].booking_party_size ? ' (' + statusByResource[r.id].booking_party_size + ' pax)' : ''}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <ToggleSwitch checked={r.is_active} disabled={togglingId === r.id} onChange={() => handleToggle(r.id)} />
                <button onClick={() => openEditForm(r)} className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                  <Pencil size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={editingId ? 'Editar recurso' : 'Novo recurso'}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {!editingId && (
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Atividade *</label>
              <Select
                value={form.activityId}
                onChange={(v) => setForm((p) => ({ ...p, activityId: v }))}
                options={activities.map((a) => ({ value: a.id, label: a.name }))}
                placeholder="Selecionar atividade"
              />
            </div>
          )}
          {!editingId && (
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Tipo de recurso *</label>
              <Select
                value={form.resourceTypeId}
                onChange={(v) => setForm((p) => ({ ...p, resourceTypeId: v }))}
                options={activeResourceTypes.map((t) => ({ value: t.id, label: t.name }))}
                placeholder="Selecionar tipo"
              />
              {activeResourceTypes.length === 0 && (
                <p className="text-[12px] text-text-muted mt-1.5">Nenhum tipo disponivel - crie um em Configuracoes {'>'} Catalogos {'>'} Tipos de Recurso.</p>
              )}
            </div>
          )}
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome *</label>
            <input
              value={form.name}
              onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="Ex: Quarto 101, Joao (cabeleireiro), Mesa 4"
              required
              autoFocus
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Capacidade (opcional)</label>
            <input
              type="number" min="1"
              value={form.capacity}
              onChange={(e) => setForm((p) => ({ ...p, capacity: e.target.value }))}
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{formError}</div>
          )}
          <button
            type="submit"
            disabled={saving || (!editingId && !form.resourceTypeId)}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {saving ? 'A guardar...' : editingId ? 'Guardar alteracoes' : 'Criar recurso'}
          </button>
        </form>
      </Modal>
    </main>
  );
}
