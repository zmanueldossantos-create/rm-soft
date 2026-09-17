import { useState, useEffect } from 'react';
import { Wallet2, Plus, Loader2, X, Trash2, CheckCircle2, Search, Minus } from 'lucide-react';
import { listActivities } from '../api/activity';
import { listPointsOfSale } from '../api/activity';
import { listResources } from '../api/booking';
import { listProducts } from '../api/products';
import { listServices } from '../api/services';
import { listPaymentMethodPreferences } from '../api/tesouraria';
import { listOpenAccounts, openAccount, getOpenAccount, listAccountLines, addAccountLine, updateAccountLineQuantity, removeAccountLine, closeAccount } from '../api/openAccount';
import { getPosStockLevels } from '../api/pos';
import { extractErrorMessage } from '../utils/errors';
import Modal from '../components/Modal';
import Select from '../components/Select';

function formatKz(value) {
  return Number(value || 0).toLocaleString('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function ContasAbertas() {
  const [activities, setActivities] = useState([]);
  const [selectedActivityId, setSelectedActivityId] = useState('');
  const [pointsOfSale, setPointsOfSale] = useState([]);
  const [resources, setResources] = useState([]);
  const [products, setProducts] = useState([]);
  const [services, setServices] = useState([]);
  const [paymentMethods, setPaymentMethods] = useState([]);

  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [newModalOpen, setNewModalOpen] = useState(false);
  const [newForm, setNewForm] = useState({ posId: '', label: '', resourceId: '', notes: '' });
  const [newError, setNewError] = useState('');
  const [newSaving, setNewSaving] = useState(false);

  const [detailAccount, setDetailAccount] = useState(null);
  const [detailLines, setDetailLines] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [stockLevels, setStockLevels] = useState({});
  const [itemTab, setItemTab] = useState('products');
  const [itemSearch, setItemSearch] = useState('');
  const [addingItemId, setAddingItemId] = useState(null);

  const [closeModalOpen, setCloseModalOpen] = useState(false);
  const [closePayments, setClosePayments] = useState([]);
  const [closeError, setCloseError] = useState('');
  const [closeSaving, setCloseSaving] = useState(false);

  useEffect(() => {
    listActivities().then((data) => {
      const active = data.filter((a) => a.is_active);
      setActivities(active);
      if (active.length > 0) setSelectedActivityId(active[0].id);
    }).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar atividades')));
    listProducts().then((data) => setProducts(data.filter((p) => p.is_active && !p.is_raw_material && !p.not_available_pos && !p.internal_use_only))).catch(() => {});
    listServices().then((data) => setServices(data.filter((s) => s.is_active))).catch(() => {});
    listPaymentMethodPreferences().then(setPaymentMethods).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedActivityId) return;
    listPointsOfSale(selectedActivityId).then((data) => setPointsOfSale(data.filter((p) => p.is_active))).catch(() => {});
    listResources(selectedActivityId).then((data) => setResources(data.filter((r) => r.is_active))).catch(() => {});
    loadAccounts();
  }, [selectedActivityId]);

  async function loadAccounts() {
    setLoading(true);
    setError('');
    try {
      setAccounts(await listOpenAccounts(selectedActivityId));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar contas'));
    } finally {
      setLoading(false);
    }
  }

  function openNewModal() {
    setNewForm({ posId: pointsOfSale[0]?.id || '', label: '', resourceId: '', notes: '' });
    setNewError('');
    setNewModalOpen(true);
  }

  async function handleNewSubmit(e) {
    e.preventDefault();
    setNewError('');
    if (!newForm.posId) {
      setNewError('Preencha todos os campos obrigatorios');
      return;
    }
    if (resources.length > 0 && !newForm.resourceId) {
      setNewError('Selecione uma mesa/recurso');
      return;
    }
    if (resources.length === 0 && !newForm.label.trim()) {
      setNewError('Preencha todos os campos obrigatorios');
      return;
    }
    setNewSaving(true);
    try {
      const resourceLabel = newForm.resourceId ? resources.find((r) => r.id === newForm.resourceId)?.name : null;
      await openAccount({
        activity_id: selectedActivityId,
        pos_id: newForm.posId,
        label: resourceLabel || newForm.label.trim(),
        resource_id: newForm.resourceId || null,
        notes: newForm.notes || null,
      });
      setNewModalOpen(false);
      await loadAccounts();
    } catch (err) {
      setNewError(extractErrorMessage(err, 'Erro ao abrir conta'));
    } finally {
      setNewSaving(false);
    }
  }

  async function openDetail(account) {
    setDetailAccount(account);
    setDetailError('');
    setItemSearch('');
    setItemTab('products');
    setDetailLoading(true);
    getPosStockLevels(account.pos_id).then(setStockLevels).catch(() => setStockLevels({}));
    try {
      setDetailLines(await listAccountLines(account.id));
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao carregar linhas'));
    } finally {
      setDetailLoading(false);
    }
  }

  async function refreshDetailLines() {
    if (!detailAccount) return;
    try {
      setDetailLines(await listAccountLines(detailAccount.id));
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao carregar linhas'));
    }
  }

  async function handleAddItem(item, isService) {
    if (!detailAccount) return;
    setAddingItemId(item.id);
    setDetailError('');
    try {
      await addAccountLine(detailAccount.id, {
        product_id: isService ? null : item.id,
        service_id: isService ? item.id : null,
        quantity: 1,
      });
      await refreshDetailLines();
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao adicionar artigo'));
    } finally {
      setAddingItemId(null);
    }
  }

  async function handleRemoveLine(lineId) {
    if (!detailAccount) return;
    try {
      await removeAccountLine(detailAccount.id, lineId);
      await refreshDetailLines();
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao remover linha'));
    }
  }

  async function handleChangeQuantity(line, delta) {
    if (!detailAccount) return;
    const newQuantity = Number(line.quantity) + delta;
    try {
      await updateAccountLineQuantity(detailAccount.id, line.id, newQuantity);
      await refreshDetailLines();
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao atualizar quantidade'));
    }
  }

  const detailTotal = detailLines.reduce((sum, l) => sum + Number(l.unit_price) * Number(l.quantity), 0);

  function openCloseModal() {
    setClosePayments([]);
    setCloseError('');
    setCloseModalOpen(true);
  }

  function toggleClosePayment(methodId) {
    setClosePayments((prev) => {
      const exists = prev.find((p) => p.payment_method_id === methodId);
      if (exists) return prev.filter((p) => p.payment_method_id !== methodId);
      return [...prev, { payment_method_id: methodId, amount: '' }];
    });
  }

  function updateClosePaymentAmount(methodId, amount) {
    setClosePayments((prev) => prev.map((p) => (p.payment_method_id === methodId ? { ...p, amount } : p)));
  }

  const closePaymentsSum = closePayments.reduce((sum, p) => sum + (parseFloat(p.amount) || 0), 0);
  const closeRemaining = Math.round((detailTotal - closePaymentsSum) * 100) / 100;

  async function handleCloseSubmit() {
    if (!detailAccount) return;
    setCloseError('');
    setCloseSaving(true);
    try {
      await closeAccount(detailAccount.id, {
        invoice_type: 'FACTURA_RECIBO',
        payments: closePayments.filter((p) => parseFloat(p.amount) > 0).map((p) => ({ payment_method_id: p.payment_method_id, amount: parseFloat(p.amount) })),
      });
      setCloseModalOpen(false);
      setDetailAccount(null);
      await loadAccounts();
    } catch (err) {
      setCloseError(extractErrorMessage(err, 'Erro ao fechar conta'));
    } finally {
      setCloseSaving(false);
    }
  }

  const posPaymentMethods = paymentMethods.filter((m) => m.available_at_pos && m.allows_receipt);

  const filteredProducts = products.filter((p) => !itemSearch.trim() || p.name.toLowerCase().includes(itemSearch.toLowerCase()) || (p.code || '').toLowerCase().includes(itemSearch.toLowerCase()));
  const filteredServices = services.filter((s) => !itemSearch.trim() || s.name.toLowerCase().includes(itemSearch.toLowerCase()));

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
          <Wallet2 size={22} className="text-accent" />
          Contas Abertas
        </h2>
        <button
          onClick={openNewModal}
          disabled={pointsOfSale.length === 0}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer"
        >
          <Plus size={16} />
          Nova conta
        </button>
      </div>
      <p className="text-text-muted text-sm mb-6">Contas em curso (mesas, tabs, quartos) - acumule artigos e feche quando o cliente pagar</p>

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
      ) : accounts.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <Wallet2 size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium mb-1">Nenhuma conta aberta</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {accounts.map((a) => (
            <button
              key={a.id}
              onClick={() => openDetail(a)}
              className="bg-bg-elevated border border-border hover:border-accent rounded-lg p-4 text-left transition-colors cursor-pointer"
            >
              <p className="font-display font-semibold text-text-primary text-sm mb-1">{a.label}</p>
              <p className="text-text-muted text-[12px] font-mono">{new Date(a.opened_at).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' })}</p>
            </button>
          ))}
        </div>
      )}

      <Modal open={newModalOpen} onClose={() => setNewModalOpen(false)} title="Nova conta">
        <form onSubmit={handleNewSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Caixa *</label>
            <Select
              value={newForm.posId}
              onChange={(v) => setNewForm((p) => ({ ...p, posId: v }))}
              options={pointsOfSale.map((p) => ({ value: p.id, label: p.name }))}
              placeholder="Selecionar"
            />
          </div>
          {resources.length > 0 ? (
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Mesa / Recurso *</label>
              <Select
                value={newForm.resourceId}
                onChange={(v) => setNewForm((p) => ({ ...p, resourceId: v }))}
                options={resources.map((r) => ({ value: r.id, label: r.name }))}
                placeholder="Selecionar"
              />
            </div>
          ) : (
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome da conta *</label>
              <input
                value={newForm.label}
                onChange={(e) => setNewForm((p) => ({ ...p, label: e.target.value }))}
                placeholder="Ex: Joao - tab"
                required
                autoFocus
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
              />
            </div>
          )}
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Comentario (opcional)</label>
            <input
              value={newForm.notes}
              onChange={(e) => setNewForm((p) => ({ ...p, notes: e.target.value }))}
              placeholder="Ex: 4 pessoas, sem gluten..."
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
            />
          </div>
          {newError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{newError}</div>
          )}
          <button
            type="submit"
            disabled={newSaving}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {newSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {newSaving ? 'A abrir...' : 'Abrir conta'}
          </button>
        </form>
      </Modal>

      <Modal open={!!detailAccount} onClose={() => setDetailAccount(null)} title={detailAccount?.label || ''} maxWidthClass="max-w-2xl">
        {detailAccount && (
          <div className="flex flex-col gap-4">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                placeholder="Pesquisar artigo..."
                value={itemSearch}
                onChange={(e) => setItemSearch(e.target.value)}
                className="w-full bg-bg-inset border border-border rounded-md pl-9 pr-3 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
              />
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setItemTab('products')}
                className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (itemTab === 'products' ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
              >
                Produtos
              </button>
              <button
                type="button"
                onClick={() => setItemTab('services')}
                className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (itemTab === 'services' ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
              >
                Servicos
              </button>
            </div>

            {itemTab === 'products' ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[160px] overflow-y-auto scrollbar-thin">
                {filteredProducts.map((p) => (
                  <button key={'p-' + p.id} onClick={() => handleAddItem(p, false)} disabled={addingItemId === p.id} className="bg-bg-inset border border-border hover:border-accent rounded-md px-2.5 py-2 text-left transition-colors cursor-pointer disabled:opacity-50">
                    <p className="font-mono text-[10px] text-text-muted mb-0.5">{p.code}</p>
                    <p className="text-[12px] text-text-primary truncate">{p.name}</p>
                    <div className="flex items-end justify-between mt-0.5">
                      <p className="text-[11px] text-accent font-mono">{formatKz(p.price)} Kz</p>
                      {p.managed_by_stock && (
                        <span className={'text-[10px] font-mono ' + ((stockLevels[p.id] ?? 0) <= 0 ? 'text-danger' : (stockLevels[p.id] ?? 0) <= (p.min_stock_threshold || 0) ? 'text-accent' : 'text-text-muted')}>
                          {stockLevels[p.id] ?? 0} {p.is_sold_by_weight ? 'Kg' : 'un'}
                        </span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[160px] overflow-y-auto scrollbar-thin">
                {filteredServices.map((s) => (
                  <button key={'s-' + s.id} onClick={() => handleAddItem(s, true)} disabled={addingItemId === s.id} className="bg-bg-inset border border-border hover:border-accent rounded-md px-2.5 py-2 text-left transition-colors cursor-pointer disabled:opacity-50">
                    <p className="font-mono text-[10px] text-text-muted mb-0.5">{s.code}</p>
                    <p className="text-[12px] text-text-primary truncate">{s.name}</p>
                    <p className="text-[11px] text-accent font-mono mt-0.5">{formatKz(s.price)} Kz</p>
                  </button>
                ))}
              </div>
            )}

            <div className="border-t border-border pt-3">
              {detailLoading ? (
                <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-accent" /></div>
              ) : detailLines.length === 0 ? (
                <p className="text-text-muted text-[13px] text-center py-6">Nenhum artigo adicionado</p>
              ) : (
                <div className="flex flex-col gap-1.5 max-h-[220px] overflow-y-auto scrollbar-thin">
                  {detailLines.map((l) => (
                    <div key={l.id} className="flex items-center justify-between bg-bg-inset border border-border rounded-md px-3 py-2">
                      <div>
                        <p className="text-[12px] text-text-primary">{l.name_snapshot}</p>
                        <p className="text-[11px] text-text-muted font-mono">{formatKz(l.unit_price)} Kz/un</p>
                      </div>
                      <div className="flex items-center gap-2.5">
                        <div className="flex items-center gap-1.5 bg-bg-elevated border border-border rounded-md px-1.5 py-1">
                          <button onClick={() => handleChangeQuantity(l, -1)} className="text-text-muted hover:text-accent cursor-pointer">
                            <Minus size={12} />
                          </button>
                          <span className="text-[12px] text-text-primary font-mono w-6 text-center">{l.quantity}</span>
                          <button onClick={() => handleChangeQuantity(l, 1)} className="text-text-muted hover:text-accent cursor-pointer">
                            <Plus size={12} />
                          </button>
                        </div>
                        <span className="font-mono text-[13px] text-text-primary font-semibold w-20 text-right">{formatKz(l.unit_price * l.quantity)} Kz</span>
                        <button onClick={() => handleRemoveLine(l.id)} className="text-text-muted hover:text-danger cursor-pointer">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {detailError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{detailError}</div>
            )}

            <div className="flex justify-between items-center bg-bg-inset border border-border rounded-md px-4 py-3">
              <span className="text-text-muted text-[13px]">Total</span>
              <span className="font-mono font-bold text-text-primary text-lg">{formatKz(detailTotal)} Kz</span>
            </div>

            <button
              onClick={openCloseModal}
              disabled={detailLines.length === 0}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              <CheckCircle2 size={17} />
              Fechar conta
            </button>
          </div>
        )}
      </Modal>

      <Modal open={closeModalOpen} onClose={() => setCloseModalOpen(false)} title="Fechar conta">
        <div className="flex flex-col gap-4">
          <div className="flex justify-between items-center bg-bg-inset border border-border rounded-md px-4 py-3">
            <span className="text-text-muted text-[13px]">Total a pagar</span>
            <span className="font-mono font-semibold text-text-primary text-lg">{formatKz(detailTotal)} Kz</span>
          </div>
          <div className="flex flex-col gap-1.5">
            {posPaymentMethods.map((m) => {
              const line = closePayments.find((p) => p.payment_method_id === m.id);
              return (
                <div key={m.id} className="flex items-center gap-2">
                  <label className="flex items-center gap-2 flex-1 cursor-pointer select-none">
                    <input type="checkbox" checked={!!line} onChange={() => toggleClosePayment(m.id)} className="w-4 h-4 accent-accent cursor-pointer" />
                    <span className="text-[13px] text-text-primary">{m.name}</span>
                  </label>
                  {line && (
                    <input
                      type="number" step="0.01" min="0"
                      value={line.amount}
                      onChange={(e) => updateClosePaymentAmount(m.id, e.target.value)}
                      placeholder="Valor"
                      className="w-28 bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
                    />
                  )}
                </div>
              );
            })}
          </div>
          {posPaymentMethods.length > 0 && (
            <div className={'text-[12px] px-3 py-2 rounded-r border-l-2 ' + (closeRemaining === 0 ? 'bg-success/10 border-success text-success' : closeRemaining > 0 ? 'bg-accent/10 border-accent text-accent' : 'bg-danger/10 border-danger text-danger')}>
              {closeRemaining === 0 ? 'Valor exato' : closeRemaining > 0 ? `Falta ${formatKz(closeRemaining)} Kz` : `Excede em ${formatKz(Math.abs(closeRemaining))} Kz`}
            </div>
          )}
          {closeError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{closeError}</div>
          )}
          <button
            onClick={handleCloseSubmit}
            disabled={closeSaving || (posPaymentMethods.length > 0 && closeRemaining !== 0)}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {closeSaving ? <Loader2 size={17} className="animate-spin" /> : <CheckCircle2 size={17} />}
            {closeSaving ? 'A fechar...' : 'Confirmar fecho'}
          </button>
        </div>
      </Modal>
    </main>
  );
}
