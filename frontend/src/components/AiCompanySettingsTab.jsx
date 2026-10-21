import { useState, useEffect } from 'react';
import { Bot, Loader2, Save, Check, Send, Link2, Unlink } from 'lucide-react';
import { updateMyCompanyAi, getMyChannels, newChannelCode, unlinkChannel } from '../api/ai';
import { useCan } from '../utils/permissions';
import { extractErrorMessage } from '../utils/errors';
import { useToastState } from './Toaster';
import { toast } from '../store/toastStore';

const CHANNEL_LABELS = { TELEGRAM: 'Telegram', WHATSAPP: 'WhatsApp' };

// The user's own chats with the assistant: linked by a 6-digit code sent from the phone (10 minutes).
function ChannelLinks() {
  const [data, setData] = useState(null);
  const [codes, setCodes] = useState({});
  const [busy, setBusy] = useState(null);
  const [error, setError] = useToastState('error');

  function load() {
    getMyChannels().then(setData).catch(() => setData(null));
  }

  useEffect(load, []);

  async function link(channel) {
    setError('');
    setBusy(channel);
    try {
      const code = await newChannelCode(channel);
      setCodes((p) => ({ ...p, [channel]: code }));
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível gerar o código'));
    } finally {
      setBusy(null);
    }
  }

  async function unlink(channel) {
    setBusy(channel);
    try {
      await unlinkChannel(channel);
      setCodes((p) => ({ ...p, [channel]: null }));
      load();
    } finally {
      setBusy(null);
    }
  }

  if (!data) return null;
  const shown = Object.entries(data.channels).filter(([, c]) => c.enabled);
  if (shown.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[11px] uppercase tracking-wide text-text-muted">O assistente no seu telefone</p>
      {shown.map(([channel, c]) => {
        const code = codes[channel];
        const unavailable = (channel === 'TELEGRAM' && !data.telegram_bot_username) || (channel === 'WHATSAPP' && !data.whatsapp_configured);
        return (
          <div key={channel} className="border border-border rounded-md px-3.5 py-3 flex flex-col gap-2">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm font-medium text-text-primary w-24">{CHANNEL_LABELS[channel]}</span>
              <span className={'text-[12px] flex-1 ' + (c.linked ? 'text-success' : 'text-text-muted')}>
                {c.linked ? 'Ligado' + (c.name ? ' (' + c.name + ')' : '') : unavailable ? 'A aguardar configuração da plataforma' : 'Não ligado'}
              </span>
              {!unavailable && (
                <button type="button" onClick={() => link(channel)} disabled={busy === channel}
                  className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[12px] rounded-md px-3 py-1.5 cursor-pointer disabled:opacity-50">
                  {busy === channel ? <Loader2 size={13} className="animate-spin" /> : <Link2 size={13} />}{c.linked ? 'Ligar outro telefone' : 'Ligar'}
                </button>
              )}
              {c.linked && (
                <button type="button" onClick={() => unlink(channel)} disabled={busy === channel}
                  className="flex items-center gap-1.5 border border-border hover:border-danger hover:text-danger text-text-primary text-[12px] rounded-md px-3 py-1.5 cursor-pointer disabled:opacity-50">
                  <Unlink size={13} />Desligar
                </button>
              )}
            </div>
            {code && (
              <div className="bg-bg-inset border border-border rounded-md px-3 py-2.5 flex items-center gap-3 flex-wrap">
                <span className="font-mono text-xl tracking-[0.3em] text-text-primary">{code.code}</span>
                <span className="text-[12px] text-text-muted flex-1 min-w-[200px]">
                  {channel === 'TELEGRAM'
                    ? 'Abra o bot @' + data.telegram_bot_username + ' e envie este código (ou clique em «Abrir no Telegram»). Válido 10 minutos.'
                    : 'Envie «LIGAR ' + code.code + '» para o WhatsApp RM SOFT ' + (data.whatsapp_number || '') + ' (ou clique em «Abrir no WhatsApp»). Válido 10 minutos.'}
                </span>
                {code.link && (
                  <a href={code.link} target="_blank" rel="noreferrer"
                    className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[12px] font-semibold rounded-md px-3 py-1.5">
                    <Send size={13} />Abrir no {CHANNEL_LABELS[channel]}
                  </a>
                )}
                <button type="button" onClick={load} className="text-[12px] text-text-muted hover:text-text-primary cursor-pointer">Atualizar estado</button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// The company's AI assistant, as its gestor sees it: what the platform switched on (read only) and his choice of
// confirmations - whether the assistant waits for his «Confirmar» before issuing a document or sending one.
export default function AiCompanySettingsTab({ info, onChange, canManage }) {
  const canUse = useCan()('assistant:use');
  const [values, setValues] = useState({ confirmDocuments: info.confirm_documents, confirmSends: info.confirm_sends });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useToastState('error');

  async function handleSave() {
    setError('');
    setSaving(true);
    try {
      onChange(await updateMyCompanyAi({ confirm_documents: values.confirmDocuments, confirm_sends: values.confirmSends }));
      setSaved(true);
      toast.success('Alterações guardadas');
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setSaving(false);
    }
  }

  const channels = [['whatsapp_enabled', 'WhatsApp'], ['telegram_enabled', 'Telegram'], ['email_enabled', 'Email']];
  const options = [
    ['confirmDocuments', 'Confirmar antes de emitir documentos', 'O assistente prepara a fatura, pró-forma ou recibo e mostra-a; só é emitida depois de clicar em «Confirmar». Sem confirmação, é emitida logo que pedida.'],
    ['confirmSends', 'Confirmar antes de enviar documentos', 'Antes de enviar um documento por WhatsApp ou email, o assistente mostra o destinatário e espera a sua confirmação.'],
  ];

  return (
    <div className="bg-bg-elevated border border-border rounded-lg p-6 sm:p-8 flex flex-col gap-5">
      <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5"><Bot size={12} />Assistente IA</p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="border border-border rounded-md px-3.5 py-3">
          <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">Estado</p>
          <p className={'text-sm font-medium ' + (info.platform_configured ? 'text-success' : 'text-amber-500 [.light_&]:text-amber-700')}>
            {info.platform_configured ? 'Ativo' : 'Ativo - a aguardar configuração da plataforma'}
          </p>
        </div>
        <div className="border border-border rounded-md px-3.5 py-3">
          <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">Canais</p>
          <p className="text-sm text-text-primary">{['Aplicação', ...channels.filter(([k]) => info[k]).map(([, l]) => l)].join(' · ')}</p>
        </div>
        <div className="border border-border rounded-md px-3.5 py-3">
          <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">Mensagens por mês</p>
          <p className="text-sm text-text-primary font-mono">{info.effective_monthly_limit}</p>
        </div>
      </div>

      {canUse && <ChannelLinks />}

      <div className="flex flex-col gap-2">
        {options.map(([key, label, hint]) => (
          <label key={key} className={'flex items-start gap-3 border border-border rounded-md px-3.5 py-3 select-none ' + (canManage ? 'cursor-pointer hover:border-accent' : 'opacity-60 cursor-not-allowed')}>
            <input type="checkbox" checked={values[key]} disabled={!canManage} onChange={(e) => { setValues((p) => ({ ...p, [key]: e.target.checked })); setSaved(false); }} className="w-4 h-4 mt-0.5 accent-accent cursor-pointer" />
            <span>
              <span className="block text-sm font-medium text-text-primary">{label}</span>
              <span className="block text-[12px] text-text-muted mt-0.5">{hint}</span>
            </span>
          </label>
        ))}
      </div>

      {canManage && (
        <div className="flex items-center gap-3">
          <button onClick={handleSave} disabled={saving} className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium px-4 py-2.5 rounded-md transition-colors cursor-pointer">
            {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <Check size={14} /> : <Save size={14} />}
            {saved ? 'Guardado' : 'Guardar'}
          </button>
        </div>
      )}
    </div>
  );
}
