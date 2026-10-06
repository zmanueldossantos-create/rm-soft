import { useState, useEffect } from 'react';
import { Wallet2, Plus, Loader2, X, Trash2, CheckCircle2, Search, Minus, ArrowRightLeft, LayoutGrid, RefreshCw } from 'lucide-react';
import { useCan } from '../utils/permissions';
import { listActivities } from '../api/activity';
import { listPointsOfSale } from '../api/activity';
import { listResources, listResourceStatuses } from '../api/booking';
import { listProducts } from '../api/products';
import { listServices } from '../api/services';
import { listPaymentMethodPreferences } from '../api/tesouraria';
import { listOpenAccounts, openAccount, getOpenAccount, listAccountLines, addAccountLine, updateAccountLineQuantity, updateAccountLineUnit, removeAccountLine, closeAccount, transferAccountLines } from '../api/openAccount';
import { getPosStockLevels } from '../api/pos';
import { extractErrorMessage } from '../utils/errors';
import Modal from '../components/Modal';
import Select from '../components/Select';

function formatKz(value) {
  return Number(value || 0).toLocaleString('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const TABLE_STATUS_LABEL = { LIVRE: 'Livre', OCUPADA: 'Ocupado', RESERVADA: 'Reservado' };
const TABLE_BADGE_STYLE = {
  LIVRE: 'text-success bg-success/10',
  OCUPADA: 'text-danger bg-danger/10',
  RESERVADA: 'text-accent bg-accent/10',
};
const TABLE_CARD_STYLE = {
  LIVRE: 'bg-bg-elevated border-success/40 hover:border-success',
  OCUPADA: 'bg-danger/5 border-danger/40 hover:border-danger',
  RESERVADA: 'bg-accent/5 border-accent/40 hover:border-accent',
};

function formatTime(value) {
  return new Date(value).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' });
}

// The open accounts, shared by two screens:
// - the Contas Abertas page (waiters, managers): every point of sale of the activity, chosen in a list;
// - the till's side panel (cashier): posId + activityId limit it to that till's accounts, and onChange lets the
//   till refresh its own stock whenever an account changes (what sits on a table is no longer on the shelf).
// onClosed(account): an account was just closed - the till reloads its balance, as after a direct sale.
export default function OpenAccountsPanel({ posId = null, activityId = null, onChange = null, onClosed = null }) {
  const can = useCan();
  const [activities, setActivities] = useState([]);
  const [selectedActivityId, setSelectedActivityId] = useState(activityId || '');
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
  const [viewMode, setViewMode] = useState('accounts');
  const [tableStatuses, setTableStatuses] = useState([]);
  const [tablePicker, setTablePicker] = useState(null);

  // The floor plan reflects live state (accounts opened / closed, bookings about to start),
  // so it refreshes itself every 30 seconds while it is on screen.
  useEffect(() => {
    if (viewMode !== 'tables' || !selectedActivityId) return undefined;
    const timer = setInterval(() => { loadAccounts(); }, 30000);
    return () => clearInterval(timer);
  }, [viewMode, selectedActivityId]);
  const [transferModalOpen, setTransferModalOpen] = useState(false);
  const [transferSelection, setTransferSelection] = useState({});
  const [transferMode, setTransferMode] = useState('account');
  const [transferTargetAccountId, setTransferTargetAccountId] = useState('');
  const [transferTargetResourceId, setTransferTargetResourceId] = useState('');
  const [transferNewLabel, setTransferNewLabel] = useState('');
  const [transferError, setTransferError] = useState('');
  const [transferSaving, setTransferSaving] = useState(false);

  useEffect(() => {
    listActivities().then((data) => {
      const active = data.filter((a) => a.is_active);
      setActivities(active);
      // One active activity: selected for the user. Otherwise the choice stays free.
      if (!activityId && active.length === 1) setSelectedActivityId(active[0].id);
    }).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar atividades')));
    listProducts().then((data) => setProducts(data.filter((p) => p.is_active && !p.is_raw_material && !p.not_available_pos && !p.internal_use_only))).catch(() => {});
    listServices().then((data) => setServices(data.filter((s) => s.is_active))).catch(() => {});
    listPaymentMethodPreferences().then(setPaymentMethods).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedActivityId) return;
    listPointsOfSale(selectedActivityId).then((data) => setPointsOfSale(data.filter((p) => p.is_active && (!posId || p.id === posId)))).catch(() => {});
    listResources(selectedActivityId).then((data) => setResources(data.filter((r) => r.is_active))).catch(() => {});
    loadAccounts();
  }, [selectedActivityId]);

  async function loadAccounts() {
    setLoading(true);
    setError('');
    try {
      setAccounts((await listOpenAccounts(selectedActivityId)).filter((a) => !posId || a.pos_id === posId));
      if (onChange) onChange();
      await loadStatuses();
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
    // the stock shown on the cards follows every change on any account (what is left on the shelf)
    getPosStockLevels(detailAccount.pos_id).then(setStockLevels).catch(() => setStockLevels({}));
    if (onChange) onChange();
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

  // Sells a line in another unit (UN, CX...), as the till cart's unit selector - the server checks the stock.
  async function handleChangeUnit(line, value) {
    if (!detailAccount) return;
    setDetailError('');
    try {
      await updateAccountLineUnit(detailAccount.id, line.id, value === 'base' ? null : value);
      await refreshDetailLines();
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao mudar a unidade'));
    }
  }

  // The units a product line can be sold in: its base unit and its active sale units (as in the till).
  function unitPicker(line) {
    const product = line.product_id ? products.find((p) => p.id === line.product_id) : null;
    const units = (product?.sale_units || []).filter((u) => u.is_active !== false);
    if (units.length === 0) return null;
    return (
      <select value={line.sale_unit_id || 'base'} onChange={(e) => handleChangeUnit(line, e.target.value)} disabled={!can('open_accounts:edit_lines')} className="mt-1 bg-bg-elevated border border-border rounded px-1.5 py-0.5 text-[11px] font-mono text-text-primary cursor-pointer disabled:opacity-50">
        <option value="base">{product.unit_of_measure_code || 'UN'}</option>
        {units.map((u) => <option key={u.id} value={u.id}>{u.unit_of_measure_code} ({Number(u.factor)})</option>)}
      </select>
    );
  }

  // Each line's amounts come from the server, computed as the invoice will (VAT per line, same rounding):
  // the total asked for at closing is exactly what the invoice charges.
  const round2 = (v) => Math.round((v + Number.EPSILON) * 100) / 100;
  const detailSubtotal = round2(detailLines.reduce((sum, l) => sum + Number(l.line_subtotal || 0), 0));
  const detailVat = round2(detailLines.reduce((sum, l) => sum + Number(l.line_vat || 0), 0));
  const detailTotal = round2(detailSubtotal + detailVat);

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
      const closed = await closeAccount(detailAccount.id, {
        payments: closePayments.filter((p) => parseFloat(p.amount) > 0).map((p) => ({ payment_method_id: p.payment_method_id, amount: parseFloat(p.amount) })),
      });
      setCloseModalOpen(false);
      setDetailAccount(null);
      await loadAccounts();
      if (onClosed) onClosed(closed);
    } catch (err) {
      setCloseError(extractErrorMessage(err, 'Erro ao fechar conta'));
    } finally {
      setCloseSaving(false);
    }
  }

  // ---- Floor plan (derived table status, see resource_status_service) ----
  const showTables = viewMode === 'tables' && resources.length > 0;

  async function loadStatuses() {
    if (!selectedActivityId) return;
    try {
      setTableStatuses(await listResourceStatuses(selectedActivityId));
    } catch {
      setTableStatuses([]);
    }
  }

  function openNewModalForResource(resourceId, notes = '') {
    if (pointsOfSale.length === 0) {
      setError('Nenhum ponto de venda ativo nesta atividade');
      return;
    }
    setNewForm({ posId: pointsOfSale[0]?.id || '', label: '', resourceId, notes });
    setNewError('');
    setNewModalOpen(true);
  }

  function handleTableClick(table) {
    if (table.status === 'OCUPADA') {
      const tableAccounts = accounts.filter((a) => a.resource_id === table.resource_id);
      if (tableAccounts.length === 1) openDetail(tableAccounts[0]);
      else if (tableAccounts.length > 1) setTablePicker({ resourceId: table.resource_id, name: table.name, accounts: tableAccounts });
      return;
    }
    if (!can('open_accounts:open')) return;
    const guest = [table.booking_guest_name, table.booking_party_size ? table.booking_party_size + ' pax' : null].filter(Boolean).join(' - ');
    openNewModalForResource(table.resource_id, table.status === 'RESERVADA' && guest ? 'Reserva: ' + guest : '');
  }

  // ---- Transfer / split (see open_account_service.transfer_lines) ----
  const transferAccountOptions = detailAccount
    ? accounts.filter((a) => a.id !== detailAccount.id && a.pos_id === detailAccount.pos_id && !a.booking_id).map((a) => ({ value: a.id, label: a.label }))
    : [];
  const occupiedResourceIds = new Set(accounts.filter((a) => a.resource_id).map((a) => a.resource_id));
  const freeResourceOptions = resources.filter((r) => !occupiedResourceIds.has(r.id)).map((r) => ({ value: r.id, label: r.name }));
  const transferTotal = detailLines.reduce((sum, l) => sum + (transferSelection[l.id] !== undefined ? Number(l.unit_price) * (parseFloat(transferSelection[l.id]) || 0) : 0), 0);

  function openTransferModal() {
    setTransferSelection({});
    setTransferMode(transferAccountOptions.length > 0 ? 'account' : 'split');
    setTransferTargetAccountId('');
    setTransferTargetResourceId('');
    setTransferNewLabel((detailAccount?.label || '') + ' - B');
    setTransferError('');
    setTransferModalOpen(true);
  }

  function toggleTransferLine(line) {
    setTransferSelection((prev) => {
      const next = { ...prev };
      if (next[line.id] !== undefined) delete next[line.id];
      else next[line.id] = String(line.quantity);
      return next;
    });
  }

  function updateTransferQuantity(lineId, value) {
    setTransferSelection((prev) => ({ ...prev, [lineId]: value }));
  }

  async function handleTransferSubmit() {
    if (!detailAccount) return;
    setTransferError('');
    const items = detailLines
      .filter((l) => transferSelection[l.id] !== undefined)
      .map((l) => ({ line_id: l.id, quantity: parseFloat(transferSelection[l.id]), available: Number(l.quantity) }));
    if (items.length === 0) {
      setTransferError('Selecione pelo menos um artigo');
      return;
    }
    if (items.some((i) => !(i.quantity > 0) || i.quantity > i.available + 1e-9)) {
      setTransferError('Indique quantidades validas (superiores a zero e nao superiores as existentes)');
      return;
    }
    const payload = { items: items.map((i) => ({ line_id: i.line_id, quantity: i.quantity })) };
    if (transferMode === 'account') {
      if (!transferTargetAccountId) { setTransferError('Selecione a conta de destino'); return; }
      payload.target_account_id = transferTargetAccountId;
    } else if (transferMode === 'table') {
      if (!transferTargetResourceId) { setTransferError('Selecione a mesa de destino'); return; }
      payload.target_resource_id = transferTargetResourceId;
    } else {
      if (!transferNewLabel.trim()) { setTransferError('Indique um nome para a nova conta'); return; }
      payload.new_label = transferNewLabel.trim();
    }
    setTransferSaving(true);
    try {
      const result = await transferAccountLines(detailAccount.id, payload);
      setTransferModalOpen(false);
      await loadAccounts();
      if (result.source_closed) setDetailAccount(null);
      else await refreshDetailLines();
    } catch (err) {
      setTransferError(extractErrorMessage(err, 'Erro ao transferir'));
    } finally {
      setTransferSaving(false);
    }
  }

  const posPaymentMethods = paymentMethods.filter((m) => m.available_at_pos && m.allows_receipt);

  const filteredProducts = products.filter((p) => !itemSearch.trim() || p.name.toLowerCase().includes(itemSearch.toLowerCase()) || (p.code || '').toLowerCase().includes(itemSearch.toLowerCase()));
  const filteredServices = services.filter((s) => !itemSearch.trim() || s.name.toLowerCase().includes(itemSearch.toLowerCase()));

  return (
    <main className={posId ? '' : 'max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9'}>
      {(!posId || resources.length === 0) && (
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        {posId ? <span /> : (
          <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
            <Wallet2 size={22} className="text-accent" />
            Contas Abertas
          </h2>
        )}
        <button
          onClick={openNewModal}
          disabled={pointsOfSale.length === 0 || !can('open_accounts:open')}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer"
        >
          <Plus size={16} />
          Nova conta
        </button>
      </div>
      )}
      {posId ? <div className={resources.length === 0 ? 'mb-4' : ''} /> : (
        <p className="text-text-muted text-sm mb-6">Contas em curso (mesas, tabs, quartos) - acumule artigos e feche quando o cliente pagar</p>
      )}

      {!posId && activities.length > 1 && (
        <div className="w-64 mb-4">
          <Select
            value={selectedActivityId}
            onChange={setSelectedActivityId}
            options={activities.map((a) => ({ value: a.id, label: a.name }))}
            placeholder="Selecionar atividade"
          />
        </div>
      )}

      {resources.length > 0 && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <button
            type="button"
            onClick={() => setViewMode('accounts')}
            className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (viewMode === 'accounts' ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
          >
            Contas
          </button>
          <button
            type="button"
            onClick={() => { setViewMode('tables'); loadAccounts(); }}
            className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (viewMode === 'tables' ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
          >
            <span className="inline-flex items-center gap-1.5">
              <LayoutGrid size={14} />
              Mesas / Recursos
            </span>
          </button>
          {showTables && (
            <button
              type="button"
              onClick={() => loadAccounts()}
              aria-label="Atualizar"
              title="Atualizar"
              className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer"
            >
              <RefreshCw size={14} />
            </button>
          )}
          {posId && (
            <button
              onClick={openNewModal}
              disabled={pointsOfSale.length === 0 || !can('open_accounts:open')}
              className="ml-auto flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer"
            >
              <Plus size={16} />
              Nova conta
            </button>
          )}
        </div>
      )}

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {showTables ? (
        tableStatuses.length === 0 ? (
          <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
            <LayoutGrid size={28} className="text-text-muted mx-auto mb-3" />
            <p className="text-text-primary font-medium mb-1">Nenhuma mesa ativa nesta atividade</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {tableStatuses.map((tb) => (
              <button
                key={tb.resource_id}
                type="button"
                onClick={() => handleTableClick(tb)}
                disabled={tb.status !== 'OCUPADA' && !can('open_accounts:open')}
                className={'rounded-lg border p-4 text-left transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed ' + (TABLE_CARD_STYLE[tb.status] || TABLE_CARD_STYLE.LIVRE)}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <p className="font-display font-semibold text-text-primary text-sm truncate">{tb.name}</p>
                  <span className={'text-[10px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ' + (TABLE_BADGE_STYLE[tb.status] || TABLE_BADGE_STYLE.LIVRE)}>
                    {TABLE_STATUS_LABEL[tb.status] || 'Livre'}
                  </span>
                </div>
                {tb.capacity ? <p className="text-text-muted text-[12px]">{tb.capacity} lugares</p> : null}
                {tb.status === 'OCUPADA' && (
                  <p className="text-text-primary text-[12px] font-mono mt-1">
                    {tb.open_accounts} conta(s) - {formatKz(tb.open_total)} Kz
                  </p>
                )}
                {tb.status === 'OCUPADA' && tb.opened_at && (
                  <p className="text-text-muted text-[11px] font-mono">desde {formatTime(tb.opened_at)}</p>
                )}
                {tb.booking_id && (
                  <p className={'text-[11px] mt-1 ' + (tb.status === 'RESERVADA' ? 'text-accent font-medium' : 'text-text-muted')}>
                    Reserva {formatTime(tb.booking_starts_at)}
                    {tb.booking_guest_name ? ' - ' + tb.booking_guest_name : ''}
                    {tb.booking_party_size ? ' (' + tb.booking_party_size + ' pax)' : ''}
                  </p>
                )}
              </button>
            ))}
          </div>
        )
      ) : loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : accounts.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <Wallet2 size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium mb-1">{!selectedActivityId ? (activities.length === 0 ? 'Nenhuma atividade ativa' : 'Selecione uma atividade') : 'Nenhuma conta aberta'}</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
          {accounts.map((a) => (
            <button
              key={a.id}
              onClick={() => openDetail(a)}
              className="bg-bg-elevated border border-border hover:border-accent rounded-lg p-4 text-left transition-colors cursor-pointer"
            >
              <p className="font-display font-semibold text-text-primary text-sm mb-1">{a.label}</p>
              <p className="text-text-primary text-[14px] font-mono font-semibold whitespace-nowrap">{formatKz(a.total)} Kz</p>
              <p className="text-text-muted text-[11px] font-mono">{a.line_count || 0} artigo(s) - desde {formatTime(a.opened_at)}</p>
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
                  <button key={'p-' + p.id} onClick={() => handleAddItem(p, false)} disabled={addingItemId === p.id || !can('open_accounts:edit_lines')} className="bg-bg-inset border border-border hover:border-accent rounded-md px-2.5 py-2 text-left transition-colors cursor-pointer disabled:opacity-50">
                    <p className="font-mono text-[10px] text-text-muted mb-0.5">{p.code}</p>
                    <p className="text-[12px] text-text-primary truncate">{p.name}</p>
                    <div className="flex items-end justify-between mt-0.5">
                      <p className="text-[11px] text-accent font-mono">{formatKz(p.price)} Kz</p>
                      {p.managed_by_stock && (
                        <span className={'text-[10px] font-mono ' + ((stockLevels[p.id] ?? 0) <= 0 ? 'text-danger' : (stockLevels[p.id] ?? 0) <= (p.min_stock_threshold || 0) ? 'text-accent' : 'text-text-muted')}>
                          {stockLevels[p.id] ?? 0} {p.unit_of_measure_code || 'Un'}
                        </span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[160px] overflow-y-auto scrollbar-thin">
                {filteredServices.map((s) => (
                  <button key={'s-' + s.id} onClick={() => handleAddItem(s, true)} disabled={addingItemId === s.id || !can('open_accounts:edit_lines')} className="bg-bg-inset border border-border hover:border-accent rounded-md px-2.5 py-2 text-left transition-colors cursor-pointer disabled:opacity-50">
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
                        <p className="text-[11px] text-text-muted font-mono">{formatKz(l.unit_price)} Kz/{(l.unit_code_snapshot || 'un').toLowerCase()}</p>{unitPicker(l)}
                      </div>
                      <div className="flex items-center gap-2.5">
                        <div className="flex items-center gap-1.5 bg-bg-elevated border border-border rounded-md px-1.5 py-1">
                          <button onClick={() => handleChangeQuantity(l, -1)} disabled={!can('open_accounts:edit_lines')} className="text-text-muted hover:text-accent cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
                            <Minus size={12} />
                          </button>
                          <span className="text-[12px] text-text-primary font-mono w-6 text-center">{l.quantity}</span>
                          <button onClick={() => handleChangeQuantity(l, 1)} disabled={!can('open_accounts:edit_lines')} className="text-text-muted hover:text-accent cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
                            <Plus size={12} />
                          </button>
                        </div>
                        <span className="font-mono text-[13px] text-text-primary font-semibold min-w-20 whitespace-nowrap text-right">{formatKz(l.unit_price * l.quantity)} Kz</span>
                        <button onClick={() => handleRemoveLine(l.id)} disabled={!can('open_accounts:edit_lines')} className="text-text-muted hover:text-danger cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
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

            {can('open_accounts:transfer') && !detailAccount.booking_id && (
              <button
                type="button"
                onClick={openTransferModal}
                disabled={detailLines.length === 0}
                className="border border-border hover:border-accent text-text-primary font-medium text-sm rounded-md py-2.5 flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ArrowRightLeft size={16} />
                Transferir / Dividir
              </button>
            )}
            <button
              onClick={openCloseModal}
              disabled={detailLines.length === 0 || !can('open_accounts:close')}
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
      <Modal open={transferModalOpen} onClose={() => setTransferModalOpen(false)} title={'Transferir / Dividir - ' + (detailAccount?.label || '')} maxWidthClass="max-w-2xl">
        <div className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Artigos a mover</label>
            <div className="flex flex-col gap-1.5 max-h-[220px] overflow-y-auto scrollbar-thin">
              {detailLines.map((l) => {
                const selected = transferSelection[l.id] !== undefined;
                return (
                  <div key={l.id} className="flex items-center gap-3 bg-bg-inset border border-border rounded-md px-3 py-2">
                    <input type="checkbox" checked={selected} onChange={() => toggleTransferLine(l)} className="w-4 h-4 accent-accent cursor-pointer" />
                    <div className="flex-1 min-w-0">
                      <p className="text-[12px] text-text-primary truncate">{l.name_snapshot}</p>
                      <p className="text-[11px] text-text-muted font-mono">{formatKz(l.unit_price)} Kz/un - na conta: {l.quantity}</p>
                    </div>
                    {selected && (
                      <input
                        type="number" step="any" min="0" max={l.quantity}
                        value={transferSelection[l.id]}
                        onChange={(e) => updateTransferQuantity(l.id, e.target.value)}
                        className="w-24 bg-bg-elevated border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Destino</label>
            <div className="flex items-center gap-2 flex-wrap mb-3">
              {[
                { key: 'account', label: 'Outra conta' },
                ...(resources.length > 0 ? [{ key: 'table', label: 'Outra mesa livre' }] : []),
                { key: 'split', label: 'Dividir (nova conta)' },
              ].map((m) => (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => setTransferMode(m.key)}
                  className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (transferMode === m.key ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
                >
                  {m.label}
                </button>
              ))}
            </div>
            {transferMode === 'account' && (
              <Select value={transferTargetAccountId} onChange={setTransferTargetAccountId} options={transferAccountOptions} placeholder="Selecionar conta" />
            )}
            {transferMode === 'table' && (
              <Select value={transferTargetResourceId} onChange={setTransferTargetResourceId} options={freeResourceOptions} placeholder="Selecionar mesa livre" />
            )}
            {transferMode === 'split' && (
              <div className="flex flex-col gap-1.5">
                <input
                  value={transferNewLabel}
                  onChange={(e) => setTransferNewLabel(e.target.value)}
                  placeholder="Nome da nova conta"
                  className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
                />
                <p className="text-text-muted text-[12px]">A nova conta fica na mesma mesa e no mesmo ponto de venda - feche cada conta com o seu pagamento.</p>
              </div>
            )}
          </div>

          <div className="flex justify-between items-center bg-bg-inset border border-border rounded-md px-4 py-3">
            <span className="text-text-muted text-[13px]">Total a mover</span>
            <span className="font-mono font-semibold text-text-primary text-lg">{formatKz(transferTotal)} Kz</span>
          </div>

          {transferError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{transferError}</div>
          )}
          <button
            type="button"
            onClick={handleTransferSubmit}
            disabled={transferSaving}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {transferSaving ? <Loader2 size={17} className="animate-spin" /> : <ArrowRightLeft size={17} />}
            {transferSaving ? 'A transferir...' : 'Confirmar'}
          </button>
        </div>
      </Modal>
      <Modal open={!!tablePicker} onClose={() => setTablePicker(null)} title={'Contas - ' + (tablePicker?.name || '')}>
        <div className="flex flex-col gap-2">
          {tablePicker?.accounts.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => { setTablePicker(null); openDetail(a); }}
              className="flex items-center justify-between bg-bg-inset border border-border hover:border-accent rounded-md px-3.5 py-2.5 text-left transition-colors cursor-pointer"
            >
              <span className="text-[13px] text-text-primary">{a.label}</span>
              <span className="text-[12px] text-text-muted font-mono">{formatTime(a.opened_at)}</span>
            </button>
          ))}
          {can('open_accounts:open') && (
            <button
              type="button"
              onClick={() => { const resourceId = tablePicker?.resourceId; setTablePicker(null); if (resourceId) openNewModalForResource(resourceId); }}
              className="flex items-center justify-center gap-2 border border-border hover:border-accent text-text-primary font-medium text-sm rounded-md py-2.5 transition-colors cursor-pointer"
            >
              <Plus size={15} />
              Nova conta nesta mesa
            </button>
          )}
        </div>
      </Modal>
    </main>
  );
}
