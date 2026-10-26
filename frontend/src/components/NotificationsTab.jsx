import { useEffect, useState } from 'react';
import { BellRing, Check, Copy, ExternalLink, Loader2, Mail, Pencil, Plus, Save, Send, Trash2 } from 'lucide-react';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';
import { createRecipient, deleteRecipient, getNotifications, saveNotificationSettings, testRecipient, updateRecipient } from '../api/notifications';
import { extractErrorMessage } from '../utils/errors';
import { useToastState } from './Toaster';
import { toast } from '../store/toastStore';

// Notificações: the gestor types who receives what (an email, a Telegram), each recipient with its own events.
// The messages wait in the server's outbox and are sent in the background - a sale never waits for them.

const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const STATUS = { PENDENTE: ['Por enviar', 'bg-accent/15 text-accent'], ENVIADA: ['Enviada', 'bg-success/15 text-success'], ERRO: ['Erro', 'bg-danger/15 text-danger'] };
const when = (iso) => (iso ? new Date(iso).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '');

function Toggle({ checked, onChange, disabled, label }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={() => onChange(!checked)}
      className={'relative w-10 h-[22px] rounded-full transition-colors shrink-0 cursor-pointer disabled:opacity-50 ' + (checked ? 'bg-accent' : 'bg-border')}>
      <span className={'absolute top-[3px] w-4 h-4 rounded-full bg-white transition-all ' + (checked ? 'left-[21px]' : 'left-[3px]')} />
    </button>
  );
}

export default function NotificationsTab({ canManage, onAllowed }) {
  const [data, setData] = useState(null);
  const [settings, setSettings] = useState(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [editing, setEditing] = useState(null); // null closed, {} new, a recipient
  const [removing, setRemoving] = useState(null);
  const [, setError] = useToastState('error');

  async function load() {
    try {
      const d = await getNotifications();
      onAllowed?.(d.allowed);
      setData(d);
      if (d.allowed) setSettings({ ...d.settings, sale_min_amount: d.settings.sale_min_amount ?? '' });
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível carregar as notificações'));
    }
  }
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveSettings() {
    setSavingSettings(true);
    try {
      await saveNotificationSettings({ ...settings, sale_min_amount: settings.sale_min_amount === '' ? null : Number(settings.sale_min_amount) });
      toast.success('Definições das notificações guardadas');
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setSavingSettings(false);
    }
  }

  async function sendTest(r) {
    try {
      await testRecipient(r.id);
      toast.success('Mensagem de teste enviada para ' + r.name + ' - veja o resultado no histórico');
      setTimeout(load, 4000);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível enviar o teste'));
    }
  }

  async function toggleActive(r) {
    try {
      await updateRecipient(r.id, { name: r.name, address: r.address, events: r.events, is_active: !r.is_active });
      toast.success(r.name + (r.is_active ? ': notificações suspensas' : ': notificações ativas'));
      load();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao guardar'));
    }
  }

  async function confirmRemove() {
    try {
      await deleteRecipient(removing.id);
      toast.success(removing.name + ' já não recebe notificações');
      setRemoving(null);
      load();
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível apagar'));
    }
  }

  async function copyLink(link) {
    try { await navigator.clipboard.writeText(link); toast.success('Link copiado - envie-o ao destinatário'); } catch { /* the link stays visible */ }
  }

  if (!data) return <div className="flex items-center justify-center py-16 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>;
  if (!data.allowed) {
    return <div className="bg-bg-elevated border border-border rounded-lg p-6 text-sm text-text-muted">As notificações automáticas não estão incluídas no seu plano. Para as ter, contacte a RM SOFT.</div>;
  }
  const eventLabel = Object.fromEntries(data.events.map((e) => [e.code, e.label]));
  const showSaleMin = data.events.some((e) => e.code === 'VENDA');

  return (
    <div className="flex flex-col gap-5">
      {/* ------------------------------------------------------------------------------------------------ settings */}
      <div className="bg-bg-elevated border border-border rounded-lg p-5 sm:p-6">
        <div className="flex items-center gap-2.5 mb-1">
          <BellRing size={18} className="text-accent" />
          <h3 className="font-display font-semibold text-[16px] text-text-primary">Notificações automáticas</h3>
        </div>
        <p className="text-sm text-text-muted mb-5">Avisos por email ou Telegram quando acontece algo na empresa: um quarto ocupado, uma mesa aberta, uma venda, o fecho de uma caixa, um produto em stock baixo.</p>
        <div className="flex flex-col gap-4">
          <label className="flex items-center gap-3 text-sm text-text-primary">
            <Toggle checked={settings.enabled} onChange={(v) => setSettings((s) => ({ ...s, enabled: v }))} disabled={!canManage} label="Notificações ativas" />
            Notificações ativas
          </label>
          <label className="flex items-start gap-3 text-sm text-text-primary">
            <Toggle checked={settings.include_gestor_actions} onChange={(v) => setSettings((s) => ({ ...s, include_gestor_actions: v }))} disabled={!canManage} label="Notificar também o que o gestor faz" />
            <span>Notificar também o que o gestor faz<span className="block text-[12px] text-text-muted">Desligado: só se avisa o que a equipa faz (caixa, receção, sala). O stock baixo é sempre avisado.</span></span>
          </label>
          {showSaleMin && (
            <div className="max-w-xs">
              <label className={labelClass}>Vendas: só acima de (Kz)</label>
              <input type="number" min="0" value={settings.sale_min_amount} onChange={(e) => setSettings((s) => ({ ...s, sale_min_amount: e.target.value }))}
                disabled={!canManage} placeholder="Todas as vendas" className={inputClass + ' font-mono'} />
            </div>
          )}
          {canManage && (
            <button type="button" onClick={saveSettings} disabled={savingSettings}
              className="self-start flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm px-4 py-2.5 rounded-md cursor-pointer">
              {savingSettings ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Guardar
            </button>
          )}
        </div>
      </div>

      {/* ---------------------------------------------------------------------------------------------- recipients */}
      <div className="bg-bg-elevated border border-border rounded-lg p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
          <div>
            <h3 className="font-display font-semibold text-[16px] text-text-primary">Destinatários</h3>
            <p className="text-sm text-text-muted">Quem recebe, por que canal, e que avisos.</p>
          </div>
          {canManage && (
            <button type="button" onClick={() => setEditing({})}
              className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md cursor-pointer">
              <Plus size={15} /> Novo destinatário
            </button>
          )}
        </div>
        {!data.channels.EMAIL && <p className="text-[13px] text-amber-500 [.light_&]:text-amber-700 mb-2">Email: configure primeiro o email da empresa (separador Email).</p>}
        {!data.channels.TELEGRAM && <p className="text-[13px] text-amber-500 [.light_&]:text-amber-700 mb-2">Telegram: o bot ainda não está configurado neste servidor - contacte a RM SOFT.</p>}
        {data.recipients.length === 0 ? (
          <div className="border border-dashed border-border rounded-md py-10 text-center text-sm text-text-muted">Ainda nenhum destinatário. Adicione o seu email ou o seu Telegram.</div>
        ) : (
          <ul className="flex flex-col divide-y divide-border border border-border rounded-md">
            {data.recipients.map((r) => (
              <li key={r.id} className={'px-4 py-3.5 flex flex-col lg:flex-row lg:items-center gap-3 ' + (r.is_active ? '' : 'opacity-60')}>
                <div className="min-w-0 lg:w-64 shrink-0">
                  <div className="text-sm font-semibold text-text-primary flex items-center gap-2">
                    {r.channel === 'EMAIL' ? <Mail size={14} className="text-accent" /> : <Send size={14} className="text-accent" />}
                    {r.name}
                  </div>
                  <div className="text-[12px] text-text-muted truncate">
                    {r.channel === 'EMAIL' ? r.address : r.linked ? 'Telegram ligado' + (r.telegram_name ? ' · ' + r.telegram_name : '') : 'À espera: o destinatário tem de abrir o link'}
                  </div>
                </div>
                <div className="flex-1 flex flex-wrap gap-1.5">
                  {r.events.length === 0 ? <span className="text-[12px] text-text-muted">Nenhum aviso escolhido</span>
                    : r.events.map((code) => <span key={code} className="text-[12px] bg-bg-inset border border-border rounded px-2 py-0.5 text-text-primary">{eventLabel[code] || code}</span>)}
                </div>
                {canManage && (
                  <div className="flex items-center gap-2 flex-wrap">
                    {r.channel === 'TELEGRAM' && !r.linked && r.link && (
                      <>
                        <button type="button" onClick={() => copyLink(r.link)} className="flex items-center gap-1.5 border border-accent text-accent text-[13px] px-3 py-1.5 rounded-md cursor-pointer"><Copy size={13} /> Copiar link</button>
                        <a href={r.link} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[13px] px-3 py-1.5 rounded-md"><ExternalLink size={13} /> Abrir</a>
                      </>
                    )}
                    {r.linked && <button type="button" onClick={() => sendTest(r)} className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[13px] px-3 py-1.5 rounded-md cursor-pointer"><Send size={13} /> Testar</button>}
                    <Toggle checked={r.is_active} onChange={() => toggleActive(r)} label={r.is_active ? 'Suspender' : 'Ativar'} />
                    <button type="button" onClick={() => setEditing(r)} aria-label="Editar" className="w-8 h-8 flex items-center justify-center rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent cursor-pointer"><Pencil size={14} /></button>
                    <button type="button" onClick={() => setRemoving(r)} aria-label="Apagar" className="w-8 h-8 flex items-center justify-center rounded-md border border-border text-text-muted hover:text-danger hover:border-danger cursor-pointer"><Trash2 size={14} /></button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ------------------------------------------------------------------------------------------------- history */}
      <div className="bg-bg-elevated border border-border rounded-lg p-5 sm:p-6">
        <h3 className="font-display font-semibold text-[16px] text-text-primary mb-1">Histórico</h3>
        <p className="text-sm text-text-muted mb-4">As últimas 50 mensagens. Uma mensagem que falha é tentada de novo 3 vezes antes de ficar em erro.</p>
        {data.history.length === 0 ? <p className="text-sm text-text-muted">Ainda nenhuma mensagem.</p> : (
          <div className="overflow-x-auto border border-border rounded-md">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted border-b border-border">
                  <th className="px-3 py-2.5 font-medium">Data</th><th className="px-3 py-2.5 font-medium">Destinatário</th>
                  <th className="px-3 py-2.5 font-medium">Aviso</th><th className="px-3 py-2.5 font-medium">Assunto</th><th className="px-3 py-2.5 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {data.history.map((h) => (
                  <tr key={h.id} className="border-b border-border last:border-0">
                    <td className="px-3 py-2.5 font-mono text-[12px] text-text-muted whitespace-nowrap">{when(h.created_at)}</td>
                    <td className="px-3 py-2.5 text-text-primary whitespace-nowrap">{h.recipient} <span className="text-text-muted text-[12px]">· {h.channel === 'EMAIL' ? 'Email' : 'Telegram'}</span></td>
                    <td className="px-3 py-2.5 text-text-muted">{h.event}</td>
                    <td className="px-3 py-2.5 text-text-primary">{h.subject}</td>
                    <td className="px-3 py-2.5" title={h.error || ''}>
                      <span className={'text-[12px] font-semibold px-2 py-0.5 rounded ' + STATUS[h.status][1]}>{STATUS[h.status][0]}</span>
                      {h.error && <span className="block text-[11px] text-danger mt-0.5 max-w-[260px] truncate">{h.error}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing && <RecipientModal recipient={editing.id ? editing : null} events={data.events} channels={data.channels}
        onClose={() => setEditing(null)} onSaved={(r, created) => { setEditing(null); load();
          toast.success(created ? (r.channel === 'TELEGRAM' ? r.name + ' criado - copie o link e envie-o ao destinatário' : r.name + ' vai receber as notificações escolhidas') : r.name + ' atualizado'); }} />}
      <ConfirmDialog open={!!removing} danger title="Apagar destinatário" confirmLabel="Apagar"
        message={removing ? removing.name + ' deixa de receber as notificações. O histórico fica.' : ''}
        onConfirm={confirmRemove} onCancel={() => setRemoving(null)} />
    </div>
  );
}

function RecipientModal({ recipient, events, channels, onClose, onSaved }) {
  const [form, setForm] = useState(() => ({
    name: recipient?.name || '', channel: recipient?.channel || 'EMAIL',
    address: recipient?.address || '', events: recipient?.events || events.map((e) => e.code), is_active: recipient?.is_active ?? true,
  }));
  const [saving, setSaving] = useState(false);
  const [, setError] = useToastState('error');
  const set = (field, value) => setForm((f) => ({ ...f, [field]: value }));
  const toggleEvent = (code) => set('events', form.events.includes(code) ? form.events.filter((c) => c !== code) : [...form.events, code]);

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const saved = recipient ? await updateRecipient(recipient.id, form) : await createRecipient(form);
      onSaved(saved, !recipient);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível guardar'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={recipient ? 'Editar destinatário' : 'Novo destinatário'} maxWidthClass="max-w-2xl">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label><span className={labelClass}>Nome *</span><input value={form.name} onChange={(e) => set('name', e.target.value)} maxLength={100} placeholder="Ex.: Dono, Gerente da sala" className={inputClass} /></label>
          <div>
            <span className={labelClass}>Canal</span>
            <div className="flex gap-2">
              {[['EMAIL', 'Email'], ['TELEGRAM', 'Telegram'], ['WHATSAPP', 'WhatsApp']].map(([code, label]) => (
                <button key={code} type="button" disabled={!!recipient || code === 'WHATSAPP' || (code === 'TELEGRAM' && !channels.TELEGRAM)}
                  onClick={() => set('channel', code)}
                  title={code === 'WHATSAPP' ? 'Em breve' : code === 'TELEGRAM' && !channels.TELEGRAM ? 'O bot Telegram não está configurado' : undefined}
                  className={'flex-1 px-3 py-2.5 rounded-md text-sm font-medium border cursor-pointer disabled:cursor-not-allowed ' + (form.channel === code
                    ? 'bg-accent border-accent text-white' : 'border-border text-text-muted hover:text-text-primary disabled:opacity-50')}>
                  {label}{code === 'WHATSAPP' && <span className="block text-[10px] font-normal">em breve</span>}
                </button>
              ))}
            </div>
          </div>
        </div>
        {form.channel === 'EMAIL' ? (
          <label><span className={labelClass}>Email *</span><input type="email" value={form.address} onChange={(e) => set('address', e.target.value)} placeholder="dono@empresa.ao" className={inputClass} /></label>
        ) : !recipient && (
          <p className="text-[13px] text-text-muted bg-bg-inset border border-border rounded-md px-3 py-2.5">Depois de guardar, aparece um link: o destinatário abre-o uma vez no telemóvel (Telegram) e carrega em «Iniciar». Fica ligado.</p>
        )}
        <div>
          <span className={labelClass}>Avisos que recebe</span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {events.map((ev) => {
              const on = form.events.includes(ev.code);
              return (
                <button key={ev.code} type="button" onClick={() => toggleEvent(ev.code)} aria-pressed={on}
                  className={'text-left px-3 py-2.5 rounded-md border cursor-pointer flex gap-2.5 ' + (on ? 'border-accent bg-accent/10' : 'border-border hover:border-accent')}>
                  <span className={'mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0 ' + (on ? 'bg-accent border-accent' : 'border-border')}>{on && <Check size={12} className="text-white" />}</span>
                  <span><span className="block text-sm font-medium text-text-primary">{ev.label}</span><span className="block text-[12px] text-text-muted">{ev.description}</span></span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="border border-border hover:border-accent text-text-primary text-sm px-4 py-2.5 rounded-md cursor-pointer">Cancelar</button>
          <button type="submit" disabled={saving} className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm px-4 py-2.5 rounded-md cursor-pointer">
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Guardar
          </button>
        </div>
      </form>
    </Modal>
  );
}
