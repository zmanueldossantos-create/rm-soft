import { useState } from 'react';
import { Bot, Loader2, Save, Check } from 'lucide-react';
import { updateMyCompanyAi } from '../api/ai';
import { extractErrorMessage } from '../utils/errors';

// The company's AI assistant, as its gestor sees it: what the platform switched on (read only) and his choice of
// confirmations - whether the assistant waits for his «Confirmar» before issuing a document or sending one.
export default function AiCompanySettingsTab({ info, onChange, canManage }) {
  const [values, setValues] = useState({ confirmDocuments: info.confirm_documents, confirmSends: info.confirm_sends });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  async function handleSave() {
    setError('');
    setSaving(true);
    try {
      onChange(await updateMyCompanyAi({ confirm_documents: values.confirmDocuments, confirm_sends: values.confirmSends }));
      setSaved(true);
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
          {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3 py-2 text-[12px] rounded-r">{error}</div>}
        </div>
      )}
    </div>
  );
}
