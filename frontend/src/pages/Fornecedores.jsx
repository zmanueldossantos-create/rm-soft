import { useState, useEffect, useMemo } from 'react';
import { Truck, Plus, Pencil, Loader2, Search } from 'lucide-react';
import { listSuppliers, createSupplier, updateSupplier, toggleSupplierStatus } from '../api/suppliers';
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

const emptyForm = { name: '', nif: '', phoneNumber: '', email: '', address: '', paymentTerms: '', notes: '' };

export default function Fornecedores() {
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [togglingId, setTogglingId] = useState(null);
  const [search, setSearch] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadSuppliers();
  }, []);

  async function loadSuppliers() {
    setLoading(true);
    setError('');
    try {
      setSuppliers(await listSuppliers());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar fornecedores'));
    } finally {
      setLoading(false);
    }
  }

  const filteredSuppliers = useMemo(() => {
    if (!search.trim()) return suppliers;
    const q = search.toLowerCase();
    return suppliers.filter((s) => s.name.toLowerCase().includes(q) || (s.nif || '').toLowerCase().includes(q));
  }, [suppliers, search]);

  function openCreateForm() {
    setEditingId(null);
    setForm(emptyForm);
    setFormError('');
    setFormOpen(true);
  }

  function openEditForm(supplier) {
    setEditingId(supplier.id);
    setForm({
      name: supplier.name,
      nif: supplier.nif || '',
      phoneNumber: supplier.phone_number || '',
      email: supplier.email || '',
      address: supplier.address || '',
      paymentTerms: supplier.payment_terms || '',
      notes: supplier.notes || '',
    });
    setFormError('');
    setFormOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        nif: form.nif || null,
        phone_number: form.phoneNumber || null,
        email: form.email || null,
        address: form.address || null,
        payment_terms: form.paymentTerms || null,
        notes: form.notes || null,
      };
      if (editingId) {
        await updateSupplier(editingId, payload);
      } else {
        await createSupplier(payload);
      }
      setFormOpen(false);
      await loadSuppliers();
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao guardar fornecedor'));
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(supplierId) {
    setTogglingId(supplierId);
    try {
      await toggleSupplierStatus(supplierId);
      await loadSuppliers();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado'));
    } finally {
      setTogglingId(null);
    }
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Truck size={22} className="text-accent" />
        Fornecedores
      </h2>
      <p className="text-text-muted text-sm mb-5">Entidades externas de quem a empresa compra stock</p>

      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="relative max-w-sm w-full sm:w-auto sm:min-w-[260px]">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Pesquisar por nome ou NIF..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
          />
        </div>
        <button
          onClick={openCreateForm}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer"
        >
          <Plus size={16} />
          Novo fornecedor
        </button>
      </div>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : filteredSuppliers.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <Truck size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium mb-1">{search ? 'Nenhum fornecedor encontrado' : 'Nenhum fornecedor registado'}</p>
        </div>
      ) : (
        <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
                <th className="text-left px-4 py-2.5">Nome</th>
                <th className="text-left px-4 py-2.5">NIF</th>
                <th className="text-left px-4 py-2.5">Telefone</th>
                <th className="text-left px-4 py-2.5">Condicoes de pagamento</th>
                <th className="text-left px-4 py-2.5">Estado</th>
                <th className="text-right px-4 py-2.5">Acoes</th>
              </tr>
            </thead>
            <tbody>
              {filteredSuppliers.map((s) => (
                <tr key={s.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                  <td className="px-4 py-2.5 text-text-primary font-medium">{s.name}</td>
                  <td className="px-4 py-2.5 text-text-muted font-mono text-[12px]">{s.nif || '-'}</td>
                  <td className="px-4 py-2.5 text-text-muted">{s.phone_number || '-'}</td>
                  <td className="px-4 py-2.5 text-text-muted">{s.payment_terms || '-'}</td>
                  <td className="px-4 py-2.5">
                    <ToggleSwitch checked={s.is_active} disabled={togglingId === s.id} onChange={() => handleToggle(s.id)} />
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => openEditForm(s)} className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                      <Pencil size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={editingId ? 'Editar fornecedor' : 'Novo fornecedor'} maxWidthClass="max-w-xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome *</label>
              <input value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} required autoFocus className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">NIF (opcional)</label>
              <input value={form.nif} onChange={(e) => setForm((p) => ({ ...p, nif: e.target.value }))} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Telefone (opcional)</label>
              <input value={form.phoneNumber} onChange={(e) => setForm((p) => ({ ...p, phoneNumber: e.target.value }))} placeholder="+244..." className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Email (opcional)</label>
              <input type="email" value={form.email} onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Morada (opcional)</label>
            <input value={form.address} onChange={(e) => setForm((p) => ({ ...p, address: e.target.value }))} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Condicoes de pagamento (opcional)</label>
            <input value={form.paymentTerms} onChange={(e) => setForm((p) => ({ ...p, paymentTerms: e.target.value }))} placeholder="Ex: 30 dias, a vista" className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Notas (opcional)</label>
            <textarea value={form.notes} onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))} rows={2} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
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
            {saving ? 'A guardar...' : editingId ? 'Guardar alteracoes' : 'Criar fornecedor'}
          </button>
        </form>
      </Modal>
    </main>
  );
}
