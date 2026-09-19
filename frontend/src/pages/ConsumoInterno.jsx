import { useState, useEffect } from 'react';
import { PackageMinus, Plus, Loader2 } from 'lucide-react';
import { listActivities } from '../api/activity';
import { listProducts } from '../api/products';
import { listResources } from '../api/booking';
import { listConsumptionReasons, recordConsumption, listInternalConsumption } from '../api/internalConsumption';
import { getMyPermissions } from '../api/permissions';
import { extractErrorMessage } from '../utils/errors';
import Modal from '../components/Modal';
import Select from '../components/Select';

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function formatDateTime(iso) {
  return new Date(iso).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Luanda' });
}

export default function ConsumoInterno() {
  const [activities, setActivities] = useState([]);
  const [selectedActivityId, setSelectedActivityId] = useState('');
  const [products, setProducts] = useState([]);
  const [resources, setResources] = useState([]);
  const [reasons, setReasons] = useState([]);
  const [entries, setEntries] = useState([]);
  const [canRecord, setCanRecord] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [dateFrom, setDateFrom] = useState(todayIso());
  const [dateTo, setDateTo] = useState(todayIso());

  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({ productId: '', quantity: '', reasonId: '', resourceId: '', notes: '' });
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listActivities().then((data) => {
      const active = data.filter((a) => a.is_active);
      setActivities(active);
      if (active.length > 0) setSelectedActivityId(active[0].id);
    }).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar atividades')));
    listProducts().then((data) => setProducts(data.filter((p) => p.is_active && p.internal_use_only))).catch(() => {});
    listConsumptionReasons().then((data) => setReasons(data.filter((r) => r.is_active))).catch(() => {});
    getMyPermissions().then((perms) => setCanRecord(perms.includes('internal_consumption:record'))).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedActivityId) return;
    listResources(selectedActivityId).then((data) => setResources(data.filter((r) => r.is_active))).catch(() => {});
    loadHistory();
  }, [selectedActivityId, dateFrom, dateTo]);

  async function loadHistory() {
    setLoading(true);
    setError('');
    try {
      const filters = { activityId: selectedActivityId };
      if (dateFrom) filters.dateFrom = dateFrom + 'T00:00:00';
      if (dateTo) filters.dateTo = dateTo + 'T23:59:59';
      setEntries(await listInternalConsumption(filters));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar historico'));
    } finally {
      setLoading(false);
    }
  }

  function handleDateFromChange(value) {
    setDateFrom(value);
    setDateTo((prevTo) => (prevTo && prevTo < value ? value : prevTo));
  }

  function openCreateForm() {
    setForm({ productId: '', quantity: '', reasonId: '', resourceId: '', notes: '' });
    setFormError('');
    setFormOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    if (!form.productId || !form.quantity || !form.reasonId) {
      setFormError('Preencha os campos obrigatorios');
      return;
    }
    setSaving(true);
    try {
      await recordConsumption({
        activity_id: selectedActivityId,
        product_id: form.productId,
        quantity: parseFloat(form.quantity),
        reason_id: form.reasonId,
        resource_id: form.resourceId || null,
        notes: form.notes || null,
      });
      setFormOpen(false);
      await loadHistory();
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao registar consumo'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
          <PackageMinus size={22} className="text-accent" />
          Consumo Interno
        </h2>
        {canRecord && (
          <button
            onClick={openCreateForm}
            disabled={!selectedActivityId}
            className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer"
          >
            <Plus size={16} />
            Registar consumo
          </button>
        )}
      </div>
      <p className="text-text-muted text-sm mb-6">Consumiveis usados internamente (limpeza, amenities...) - nao gera fatura, apenas deduz stock</p>

      {activities.length > 1 && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          {activities.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelectedActivityId(a.id)}
              className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (selectedActivityId === a.id ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
            >
              {a.name}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2.5 mb-5 flex-wrap">
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">De</label>
          <input type="date" value={dateFrom} onChange={(e) => handleDateFromChange(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Ate</label>
          <input type="date" value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
        </div>
      </div>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : entries.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <PackageMinus size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium mb-1">Nenhum consumo registado neste periodo</p>
        </div>
      ) : (
        <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
                <th className="text-left px-4 py-2.5">Produto</th>
                <th className="text-right px-4 py-2.5">Qtd</th>
                <th className="text-left px-4 py-2.5">Recurso</th>
                <th className="text-left px-4 py-2.5">Registado por</th>
                <th className="text-left px-4 py-2.5">Data</th>
                <th className="text-left px-4 py-2.5">Notas</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                  <td className="px-4 py-2.5 text-text-primary font-medium">{e.product_name}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-text-primary">{e.quantity}</td>
                  <td className="px-4 py-2.5 text-text-muted">{e.resource_name || '-'}</td>
                  <td className="px-4 py-2.5 text-text-muted">{e.consumed_by_name}</td>
                  <td className="px-4 py-2.5 font-mono text-[12px] text-text-muted">{formatDateTime(e.created_at)}</td>
                  <td className="px-4 py-2.5 text-text-muted text-[12px]">{e.notes || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title="Registar consumo interno" maxWidthClass="max-w-xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Produto *</label>
              <Select
                value={form.productId}
                onChange={(v) => setForm((p) => ({ ...p, productId: v }))}
                options={products.map((p) => ({ value: p.id, label: p.code + ' - ' + p.name }))}
                placeholder="Selecionar"
              />
              {products.length === 0 && (
                <p className="text-[12px] text-text-muted mt-1.5">Nenhum produto de uso interno - marque "Uso interno apenas" num produto em Produtos.</p>
              )}
            </div>
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Quantidade *</label>
              <input type="number" step="0.001" min="0.001" value={form.quantity} onChange={(e) => setForm((p) => ({ ...p, quantity: e.target.value }))} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
            </div>
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Motivo *</label>
              <Select
                value={form.reasonId}
                onChange={(v) => setForm((p) => ({ ...p, reasonId: v }))}
                options={reasons.map((r) => ({ value: r.id, label: r.name }))}
                placeholder="Selecionar"
              />
              {reasons.length === 0 && (
                <p className="text-[12px] text-text-muted mt-1.5">Nenhum motivo disponivel - crie um em Configuracoes {'>'} Catalogos {'>'} Motivos de Consumo Interno.</p>
              )}
            </div>
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Recurso (opcional)</label>
              <Select
                value={form.resourceId}
                onChange={(v) => setForm((p) => ({ ...p, resourceId: v }))}
                options={resources.map((r) => ({ value: r.id, label: r.name }))}
                placeholder="Nenhum"
              />
            </div>
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Notas (opcional)</label>
            <input value={form.notes} onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
          </div>
          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{formError}</div>
          )}
          <button
            type="submit"
            disabled={saving}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {saving ? 'A registar...' : 'Registar consumo'}
          </button>
        </form>
      </Modal>
    </main>
  );
}
