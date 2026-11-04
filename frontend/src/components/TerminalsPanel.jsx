import { useEffect, useState } from 'react';
import { CreditCard, Smartphone, Pencil, Plus, Power } from 'lucide-react';
import Modal from './Modal';
import Select from './Select';
import { listTerminals, createTerminal, updateTerminal, toggleTerminal, listPaymentMethodPreferences } from '../api/tesouraria';
import { listActivities, listPointsOfSale } from '../api/activity';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Tesouraria › Bancos: the TPA and Multicaixa Express of one bank account. A card payment at the till lands on the
// account of the terminal it went through - the till takes the terminal by itself when only one fits, the cashier
// chooses when several do.

const inputCls = 'bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const KIND_LABEL = { TPA: 'TPA (cartão)', EXPRESS: 'Multicaixa Express' };

export default function TerminalsPanel({ account, canManage }) {
  const [terminals, setTerminals] = useState([]);
  const [methods, setMethods] = useState([]); // the payment methods that land on a bank account
  const [points, setPoints] = useState([]);
  const [form, setForm] = useState(null); // { id?, name, kind, posId, methodIds }
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listTerminals().then(setTerminals).catch(() => {});
    listPaymentMethodPreferences().then((list) => setMethods(list.filter((m) => m.uses_bank_account && m.allows_receipt))).catch(() => {});
    listActivities().then(async (activities) => {
      const active = activities.filter((a) => a.is_active);
      const lists = await Promise.all(active.map((a) => listPointsOfSale(a.id)));
      setPoints(lists.flatMap((list, i) => (list || []).filter((p) => p.is_active).map((p) => ({ id: p.id, label: active[i].name + ' · ' + p.name }))));
    }).catch(() => {});
  }, []);

  const mine = terminals.filter((t) => t.bank_account_id === account.id);
  const methodName = (id) => { const m = methods.find((x) => x.id === id); return m ? (m.short_label || m.name) : null; };

  // the methods a type receives by default: a TPA the cards (CC, CD), an Express the electronic money (DE)
  const defaultMethods = (kind) => methods.filter((m) => (kind === 'EXPRESS' ? ['DE'] : ['CC', 'CD']).includes(m.code)).map((m) => m.id);

  function openNew() {
    setForm({ name: '', kind: 'TPA', posId: '', methodIds: defaultMethods('TPA') });
  }

  function changeKind(kind) {
    setForm((f) => (f.kind === kind ? f : { ...f, kind, methodIds: defaultMethods(kind) }));
  }

  function openEdit(t) {
    setForm({ id: t.id, name: t.name, kind: t.kind, posId: t.pos_id || '', methodIds: t.payment_method_ids });
  }

  function toggleMethod(id) {
    setForm((f) => ({ ...f, methodIds: f.methodIds.includes(id) ? f.methodIds.filter((x) => x !== id) : [...f.methodIds, id] }));
  }

  async function save() {
    if (form.methodIds.length === 0) {
      toast.error('Escolha pelo menos uma forma de pagamento recebida pelo terminal.');
      return;
    }
    setSaving(true);
    const payload = { name: form.name, kind: form.kind, bank_account_id: account.id, pos_id: form.posId || null, payment_method_ids: form.methodIds };
    try {
      const saved = form.id ? await updateTerminal(form.id, payload) : await createTerminal(payload);
      setTerminals((list) => [...list.filter((t) => t.id !== saved.id), saved].sort((a, b) => a.name.localeCompare(b.name)));
      toast.success(form.id ? 'Terminal atualizado.' : 'Terminal criado.');
      setForm(null);
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Não foi possível guardar o terminal.'));
    } finally {
      setSaving(false);
    }
  }

  async function toggle(t) {
    try {
      const saved = await toggleTerminal(t.id);
      setTerminals((list) => list.map((x) => (x.id === saved.id ? saved : x)));
      toast.success(saved.is_active ? 'Terminal ativado.' : 'Terminal desativado.');
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Não foi possível alterar o terminal.'));
    }
  }

  return (
    <div className="bg-bg-elevated border border-border rounded-lg px-5 py-4 mb-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div>
          <p className="font-display font-semibold text-text-primary text-[14px]">Terminais desta conta</p>
          <p className="text-[12px] text-text-muted">Os pagamentos por cartão ou Express feitos num destes terminais entram nesta conta, no próprio dia.</p>
        </div>
        {canManage && account.is_active && (
          <button type="button" onClick={openNew}
            className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary hover:text-accent text-[13px] font-semibold px-3 py-2 rounded-md transition-colors cursor-pointer shrink-0">
            <Plus size={15} /> Novo terminal
          </button>
        )}
      </div>
      {mine.length === 0 ? (
        <p className="text-[13px] text-text-muted py-2">Nenhum terminal - um pagamento por cartão na caixa não sabe a que banco vai.</p>
      ) : (
        <div className="flex flex-col divide-y divide-border">
          {mine.map((t) => (
            <div key={t.id} className={'flex items-center gap-3 py-2.5 ' + (t.is_active ? '' : 'opacity-50')}>
              {t.kind === 'EXPRESS' ? <Smartphone size={16} className="text-text-muted shrink-0" /> : <CreditCard size={16} className="text-text-muted shrink-0" />}
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-medium text-text-primary truncate">{t.name} <span className="text-text-muted font-normal">· {KIND_LABEL[t.kind]}</span>{!t.is_active && <span className="text-text-muted font-normal"> · Inativo</span>}</p>
                <p className="text-[12px] text-text-muted truncate">
                  {t.pos_name ? 'Ponto de venda ' + t.pos_name : 'Todos os pontos de venda'} · {t.payment_method_ids.map(methodName).filter(Boolean).join(', ')}
                </p>
              </div>
              {canManage && (
                <>
                  <button type="button" onClick={() => openEdit(t)} title="Editar"
                    className="w-8 h-8 inline-flex items-center justify-center rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer">
                    <Pencil size={13} />
                  </button>
                  <button type="button" onClick={() => toggle(t)} title={t.is_active ? 'Desativar' : 'Ativar'}
                    className="w-8 h-8 inline-flex items-center justify-center rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer">
                    <Power size={13} />
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      <Modal open={!!form} onClose={() => setForm(null)} title={(form?.id ? 'Editar terminal' : 'Novo terminal') + ' - ' + account.bank + ' · ' + account.account_number} maxWidthClass="max-w-lg">
        {form && (
          <form onSubmit={(e) => { e.preventDefault(); save(); }} className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>Nome *</label>
                <input required maxLength={60} value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="TPA Balcão" className={inputCls + ' w-full'} />
              </div>
              <div>
                <label className={labelCls}>Tipo *</label>
                <Select value={form.kind} onChange={changeKind}
                  options={[{ value: 'TPA', label: KIND_LABEL.TPA }, { value: 'EXPRESS', label: KIND_LABEL.EXPRESS }]} />
              </div>
            </div>
            <div>
              <label className={labelCls}>Ponto de venda</label>
              <Select value={form.posId} onChange={(v) => setForm((f) => ({ ...f, posId: v }))} placeholder="Todos os pontos de venda"
                options={[{ value: '', label: 'Todos os pontos de venda' }, ...points.map((p) => ({ value: p.id, label: p.label }))]} />
              <p className="text-[12px] text-text-muted mt-1">Onde o terminal está. «Todos»: um terminal que anda de caixa em caixa.</p>
            </div>
            <div>
              <label className={labelCls}>Formas de pagamento recebidas *</label>
              {methods.length === 0
                ? <p className="text-[12px] text-danger py-1">Nenhuma forma de pagamento bancária ativa.</p>
                : (
                  <div className="flex flex-col gap-1.5">
                    {methods.map((m) => (
                      <label key={m.id} className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer select-none">
                        <input type="checkbox" checked={form.methodIds.includes(m.id)} onChange={() => toggleMethod(m.id)} className="w-4 h-4 accent-accent cursor-pointer" />
                        {m.short_label || m.name} <span className="text-text-muted">({m.code})</span>
                      </label>
                    ))}
                  </div>
                )}
            </div>
            <button type="submit" disabled={saving} className="bg-accent hover:bg-accent-hover disabled:opacity-60 text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer">
              {saving ? 'A guardar...' : 'Guardar terminal'}
            </button>
          </form>
        )}
      </Modal>
    </div>
  );
}
