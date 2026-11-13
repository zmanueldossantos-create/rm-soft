import { useEffect, useState } from 'react';
import { Loader2, Pencil, Plus, Link2, Unlink, Users, MonitorUp, Wallet, Vault } from 'lucide-react';
import Modal from './Modal';
import Select from './Select';
import CustomerDisplayModal from './CustomerDisplayModal';
import { listActivities, updateActivity, toggleActivityStatus, listPointsOfSale, createPointOfSale, updatePointOfSale, togglePosStatus } from '../api/activity';
import { listCashPointAssociations, assignUserToCashPoint, unassignUserFromCashPoint, getTreasuryPosition } from '../api/tesouraria';
import { getCustomerDisplay } from '../api/customerDisplay';
import { listUsers } from '../api/users';
import { useCan } from '../utils/permissions';
import { extractErrorMessage } from '../utils/errors';
import { useToastState } from './Toaster';
import { toast } from '../store/toastStore';
import { formatKz } from '../utils/format';

// Tesouraria › Caixas: the caixas of the company, by activity. An activity is never created by hand: each module
// that sells gets its own when it is granted (with its warehouse and its Caixa Geral). Here the gestor renames or
// (de)activates an activity, and creates, sets up, associates and (de)activates its caixas - a caixa de venda or the
// Cofre - with the cash each one holds now.

function ToggleSwitch({ checked, onChange, disabled }) {
  const trackClass = 'relative w-9 h-5 rounded-full transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ' + (checked ? 'bg-success' : 'bg-border');
  const knobClass = 'absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ' + (checked ? 'translate-x-4' : 'translate-x-0');
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={onChange} disabled={disabled} className={trackClass}>
      <span className={knobClass} />
    </button>
  );
}

export default function CaixasPanel() {
  const can = useCan();
  const canManage = can('pos_terminals:manage');
  const canManageActivity = can('activities:manage');
  const canAssociate = can('tesouraria:associations_manage');
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [posByActivity, setPosByActivity] = useState({});
  const [cashByPos, setCashByPos] = useState({});
  const [displayAllowed, setDisplayAllowed] = useState(false);
  const [displayActivity, setDisplayActivity] = useState(null);
  const [activityForm, setActivityForm] = useState(null); // { id, name }
  const [activitySaving, setActivitySaving] = useState(false);
  const [activityTogglingId, setActivityTogglingId] = useState(null);
  const [posModalOpen, setPosModalOpen] = useState(false);
  const [editingPosId, setEditingPosId] = useState(null);
  const [posForm, setPosForm] = useState({ activityId: '', name: '', kind: 'CAIXA', billetageEnabled: false, acceptClosingDifference: true, printClosingReport: false, printAfterSale: false, printTicket: true, printA4: false, allowPriceLevels: false, allowFreePrice: false });
  const [posSaving, setPosSaving] = useState(false);
  const [posFormError, setPosFormError] = useToastState('error');
  const [posTogglingId, setPosTogglingId] = useState(null);
  const [assocByPos, setAssocByPos] = useState({});
  const [assocUsers, setAssocUsers] = useState([]);
  const [assocPos, setAssocPos] = useState(null);
  const [assocSelection, setAssocSelection] = useState('');
  const [assocSaving, setAssocSaving] = useState(false);
  const [assocError, setAssocError] = useState('');

  async function loadPointsOfSale(activityId) {
    try {
      const data = await listPointsOfSale(activityId);
      setPosByActivity((prev) => ({ ...prev, [activityId]: data }));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar as caixas'));
    }
  }

  async function loadCash() {
    try {
      const position = await getTreasuryPosition();
      setCashByPos(Object.fromEntries((position.tills || []).map((t) => [t.pos_id, t])));
    } catch (err) {
      setCashByPos({});  // without the Tesouraria view: no balances
    }
  }

  async function load() {
    setLoading(true);
    try {
      const data = await listActivities();
      setActivities(data);
      await Promise.all(data.map((a) => loadPointsOfSale(a.id)));
      if (data[0]) getCustomerDisplay(data[0].id).then((d) => setDisplayAllowed(!!d.allowed)).catch(() => setDisplayAllowed(false));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar as atividades'));
    } finally {
      setLoading(false);
    }
    loadCash();
  }

  async function loadAssociations() {
    try {
      const [users, associations] = await Promise.all([listUsers(), listCashPointAssociations()]);
      setAssocUsers(users);
      const map = {};
      associations.forEach((a) => { map[a.pos_id] = a.user_id; });
      setAssocByPos(map);
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar as associações das caixas'));
    }
  }

  useEffect(() => { load(); if (canAssociate) loadAssociations(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const assocUserName = (posId) => assocUsers.find((u) => u.id === assocByPos[posId])?.full_name;

  async function saveActivity(e) {
    e.preventDefault();
    setActivitySaving(true);
    try {
      await updateActivity(activityForm.id, activityForm.name);
      toast.success('Atividade renomeada');
      setActivityForm(null);
      setActivities(await listActivities());
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao renomear a atividade'));
    } finally {
      setActivitySaving(false);
    }
  }

  async function handleToggleActivity(activityId) {
    setActivityTogglingId(activityId);
    try {
      await toggleActivityStatus(activityId);
      toast.success('Estado da atividade atualizado');
      setActivities(await listActivities());
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao atualizar o estado da atividade'));
    } finally {
      setActivityTogglingId(null);
    }
  }

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
      setAssocError(extractErrorMessage(err, 'Erro ao associar a caixa'));
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
      setAssocError(extractErrorMessage(err, 'Erro ao desassociar a caixa'));
    } finally {
      setAssocSaving(false);
    }
  }

  function openCreatePos(activityId) {
    setEditingPosId(null);
    setPosForm({ activityId, name: '', kind: 'CAIXA', billetageEnabled: false, acceptClosingDifference: true, printClosingReport: false, isDefault: false, printAfterSale: false, printTicket: true, printA4: false, allowPriceLevels: false, allowFreePrice: false });
    setPosFormError('');
    setPosModalOpen(true);
  }

  function openEditPos(pos) {
    setEditingPosId(pos.id);
    setPosForm({ activityId: pos.activity_id, name: pos.name, kind: pos.kind || 'CAIXA', billetageEnabled: pos.billetage_enabled || false, acceptClosingDifference: pos.accept_closing_difference !== false, printClosingReport: !!pos.print_closing_report, printAfterSale: !!pos.print_after_sale, printTicket: pos.print_ticket !== false, printA4: !!pos.print_a4, isDefault: !!pos.is_default, allowPriceLevels: !!pos.allow_price_levels, allowFreePrice: !!pos.allow_free_price });
    setPosFormError('');
    setPosModalOpen(true);
  }

  async function handlePosSubmit(e) {
    e.preventDefault();
    setPosFormError('');
    setPosSaving(true);
    try {
      if (editingPosId) {
        await updatePointOfSale(editingPosId, posForm.name, posForm.billetageEnabled, { print_after_sale: posForm.printAfterSale, print_ticket: posForm.printTicket, print_a4: posForm.printA4, accept_closing_difference: posForm.acceptClosingDifference, print_closing_report: posForm.printClosingReport, allow_price_levels: posForm.allowPriceLevels, allow_free_price: posForm.allowFreePrice, kind: posForm.kind });
      } else {
        await createPointOfSale(posForm.activityId, posForm.name, posForm.billetageEnabled, { print_after_sale: posForm.printAfterSale, print_ticket: posForm.printTicket, print_a4: posForm.printA4, accept_closing_difference: posForm.acceptClosingDifference, print_closing_report: posForm.printClosingReport, allow_price_levels: posForm.allowPriceLevels, allow_free_price: posForm.allowFreePrice, kind: posForm.kind });
      }
      setPosModalOpen(false);
      toast.success(editingPosId ? 'Caixa atualizada' : 'Caixa criada');
      await loadPointsOfSale(posForm.activityId);
    } catch (err) {
      setPosFormError(extractErrorMessage(err, 'Erro ao guardar a caixa'));
    } finally {
      setPosSaving(false);
    }
  }

  async function handleTogglePos(posId, activityId) {
    setPosTogglingId(posId);
    try {
      await togglePosStatus(posId);
      toast.success('Estado da caixa atualizado');
      await loadPointsOfSale(activityId);
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao atualizar o estado da caixa'));
    } finally {
      setPosTogglingId(null);
    }
  }

  if (loading) return <div className="flex justify-center py-12"><Loader2 size={20} className="animate-spin text-accent" /></div>;

  return (
    <>
      <p className="text-text-muted text-[13px] mb-4">
        Cada módulo de venda tem a sua atividade, criada pelo sistema, com a Caixa Geral. Acrescente aqui as outras caixas e o Cofre, associe os caixas e ajuste as definições de cada caixa.
      </p>
      {activities.length === 0 ? (
        <p className="text-text-muted text-[13px] text-center py-12">Nenhuma atividade - a empresa ainda não tem nenhum módulo de venda</p>
      ) : (
        <div className="flex flex-col gap-4">
          {activities.map((a) => (
            <div key={a.id} className="bg-bg-elevated border border-border rounded-lg">
              <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-border flex-wrap">
                <div className="flex items-center gap-2.5">
                  <p className="font-display font-semibold text-text-primary">{a.name}</p>
                  {!a.is_active && <span className="text-[10px] font-semibold uppercase tracking-wide text-danger bg-danger/10 px-1.5 py-0.5 rounded">Inativa</span>}
                </div>
                <div className="flex items-center gap-2">
                  {displayAllowed && canManageActivity && (
                    <button onClick={() => setDisplayActivity(a)} title="Ecrã do cliente: mensagem e imagens" className="flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent text-[12px] font-medium transition-colors cursor-pointer">
                      <MonitorUp size={14} />Ecrã do cliente
                    </button>
                  )}
                  {canManageActivity && (
                    <>
                      <button onClick={() => setActivityForm({ id: a.id, name: a.name })} title="Renomear a atividade" className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                        <Pencil size={14} />
                      </button>
                      <ToggleSwitch checked={a.is_active} disabled={activityTogglingId === a.id} onChange={() => handleToggleActivity(a.id)} />
                    </>
                  )}
                </div>
              </div>
              <div className="px-5 py-3 flex flex-col gap-1.5">
                {(posByActivity[a.id] || []).length === 0 && <p className="text-text-muted text-[12px] py-2">Nenhuma caixa</p>}
                {(posByActivity[a.id] || []).map((p) => {
                  const till = cashByPos[p.id];
                  return (
                    <div key={p.id} className={'flex items-center justify-between gap-3 bg-bg-inset/50 border border-border rounded-lg px-3.5 py-2.5 flex-wrap' + (p.is_active ? '' : ' opacity-60')}>
                      <div className="flex items-center gap-3 flex-wrap">
                        {p.kind === 'COFRE' ? <Vault size={15} className="text-amber-500" /> : <Wallet size={15} className="text-accent" />}
                        <p className="text-sm font-medium text-text-primary">{p.name}</p>
                        {p.kind === 'COFRE' && <span className="text-[10px] font-semibold uppercase tracking-wide text-amber-500 bg-amber-500/10 px-1.5 py-0.5 rounded">Cofre</span>}
                        {p.is_default && <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted bg-bg-inset px-1.5 py-0.5 rounded">Por defeito</span>}
                        {!p.is_active && <span className="text-[10px] font-semibold uppercase tracking-wide text-danger bg-danger/10 px-1.5 py-0.5 rounded">Inativa</span>}
                        {canAssociate && (assocUserName(p.id)
                          ? <span className="flex items-center gap-1.5 bg-accent/10 text-accent text-[12px] font-medium rounded-md px-2.5 py-1"><Users size={12} />{assocUserName(p.id)}</span>
                          : <span className="text-[11px] text-text-muted">sem utilizador</span>)}
                      </div>
                      <div className="flex items-center gap-2.5">
                        {till && (
                          <span className="text-[12px] text-text-muted" title={till.is_open ? 'Sessão aberta' : 'Fechada'}>
                            <span className={'inline-block w-1.5 h-1.5 rounded-full mr-1.5 ' + (till.is_open ? 'bg-success' : 'bg-text-muted/50')} />
                            <span className="font-mono text-text-primary">{formatKz(till.cash)} Kz</span>
                          </span>
                        )}
                        {canAssociate && (
                          <button onClick={() => openAssociation(p)} title="Associar utilizador" className="inline-flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                            <Link2 size={14} />
                          </button>
                        )}
                        {canManage && (
                          <>
                            <button onClick={() => openEditPos(p)} title="Editar a caixa" className="inline-flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                              <Pencil size={14} />
                            </button>
                            <span title={p.is_default ? 'A caixa por defeito da atividade não pode ser desativada' : undefined}>
                              <ToggleSwitch checked={p.is_active} disabled={posTogglingId === p.id || !!p.is_default} onChange={() => handleTogglePos(p.id, a.id)} />
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
                {canManage && (
                  <button type="button" onClick={() => openCreatePos(a.id)}
                    className="self-start mt-1 flex items-center gap-1.5 border border-dashed border-accent/60 hover:border-accent hover:bg-accent/5 text-accent text-[13px] font-medium rounded-md px-3.5 py-2 transition-colors cursor-pointer">
                    <Plus size={15} /> Caixa
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <CustomerDisplayModal activity={displayActivity} onClose={() => setDisplayActivity(null)} />

      <Modal open={!!activityForm} onClose={() => setActivityForm(null)} title="Renomear a atividade">
        {activityForm && (
          <form onSubmit={saveActivity} className="flex flex-col gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome *</label>
              <input value={activityForm.name} required autoFocus maxLength={100} onChange={(e) => setActivityForm((f) => ({ ...f, name: e.target.value }))}
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
            <button type="submit" disabled={activitySaving || !activityForm.name.trim()} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 cursor-pointer">
              {activitySaving ? 'A guardar...' : 'Guardar'}
            </button>
          </form>
        )}
      </Modal>

      <Modal open={!!assocPos} onClose={() => setAssocPos(null)} title={'Associação da caixa - ' + (assocPos?.name || '')}>
        <div className="flex flex-col gap-3">
          <p className="text-[13px] text-text-muted">O utilizador autorizado a operar esta caixa.</p>
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

      <Modal open={posModalOpen} onClose={() => setPosModalOpen(false)} title={editingPosId ? 'Editar caixa' : 'Nova caixa'}>
        <form onSubmit={handlePosSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome *</label>
            <input
              value={posForm.name}
              onChange={(e) => setPosForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="Ex: Caixa 1, Balcão Rua"
              required
              autoFocus
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
            />
          </div>
          {/* one point of sale = one cash drawer: a till that sells, or the company's safe (never sells) */}
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Tipo *</label>
            <div className="grid grid-cols-2 gap-2">
              {[['CAIXA', 'Caixa de venda', 'Vende, abre e fecha a sessão'], ['COFRE', 'Cofre', 'Não vende: guarda o dinheiro entre as caixas e o banco']].map(([value, label, hint]) => (
                <button key={value} type="button" disabled={posForm.isDefault}
                  onClick={() => setPosForm((p) => ({ ...p, kind: value }))}
                  className={'text-left rounded-md border px-3 py-2.5 transition-colors ' + (posForm.kind === value ? 'border-accent bg-accent/10' : 'border-border hover:border-accent/60') + (posForm.isDefault ? ' opacity-60 cursor-not-allowed' : ' cursor-pointer')}>
                  <span className="block text-[13px] font-semibold text-text-primary">{label}</span>
                  <span className="block text-[11px] text-text-muted">{hint}</span>
                </button>
              ))}
            </div>
            {posForm.isDefault && <p className="text-[11px] text-text-muted mt-1">A caixa por defeito da atividade é sempre uma caixa de venda.</p>}
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
          {posForm.kind !== 'COFRE' && <>
          <label className="flex items-center gap-2.5 text-[13px] text-text-primary cursor-pointer">
            <input type="checkbox" checked={posForm.allowPriceLevels} onChange={(e) => setPosForm((p) => ({ ...p, allowPriceLevels: e.target.checked }))} className="w-4 h-4 accent-accent cursor-pointer" />
            Permitir escolher o Preço 2 / Preço 3
          </label>
          <label className="flex items-center gap-2.5 text-[13px] text-text-primary cursor-pointer">
            <input type="checkbox" checked={posForm.allowFreePrice} onChange={(e) => setPosForm((p) => ({ ...p, allowFreePrice: e.target.checked }))} className="w-4 h-4 accent-accent cursor-pointer" />
            Permitir alterar o preço (preço livre)
          </label>
          </>}
            {/* closing: accept a difference (always with a reason) or refuse it; propose the A4 closing report */}
            <label className="flex items-center gap-2.5 text-[13px] text-text-primary cursor-pointer">
              <input type="checkbox" checked={posForm.acceptClosingDifference} onChange={(e) => setPosForm((p) => ({ ...p, acceptClosingDifference: e.target.checked }))} className="w-4 h-4 accent-accent cursor-pointer" />
              Aceitar diferença no fecho (com motivo obrigatório)
            </label>
            {!posForm.acceptClosingDifference && (
              <p className="text-[11px] text-text-muted -mt-1 ml-6">O fecho só é aceite se o contado for igual ao esperado.</p>
            )}
            <label className="flex items-center gap-2.5 text-[13px] text-text-primary cursor-pointer">
              <input type="checkbox" checked={posForm.printClosingReport} onChange={(e) => setPosForm((p) => ({ ...p, printClosingReport: e.target.checked }))} className="w-4 h-4 accent-accent cursor-pointer" />
              Propor a impressão do relatório de fecho (A4)
            </label>
          {posForm.kind !== 'COFRE' && <div className="rounded-md border border-border px-3.5 py-3 flex flex-col gap-2.5">
            <label className="flex items-center gap-2.5 text-[13px] text-text-primary cursor-pointer">
              <input type="checkbox" checked={posForm.printAfterSale} onChange={(e) => setPosForm((p) => ({ ...p, printAfterSale: e.target.checked }))} className="w-4 h-4 accent-accent cursor-pointer" />
              {'Imprimir ap\u00f3s a venda'}
            </label>
            {posForm.printAfterSale && (
              <div className="flex items-center gap-5 pl-6 text-[13px] text-text-primary">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={posForm.printTicket} onChange={(e) => setPosForm((p) => ({ ...p, printTicket: e.target.checked }))} className="w-4 h-4 accent-accent cursor-pointer" />
                  {'Tal\u00e3o'}
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={posForm.printA4} onChange={(e) => setPosForm((p) => ({ ...p, printA4: e.target.checked }))} className="w-4 h-4 accent-accent cursor-pointer" />
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
          </div>}
          <button
            type="submit"
            disabled={posSaving || !posForm.name.trim()}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {posSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {posSaving ? 'A guardar...' : editingPosId ? 'Guardar alterações' : 'Criar caixa'}
          </button>
        </form>
      </Modal>
    </>
  );
}
