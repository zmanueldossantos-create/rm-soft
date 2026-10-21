import { useState, useEffect } from 'react';
import { Mail, Loader2, Save, Check, Send } from 'lucide-react';
import Select from './Select';
import { getEmailSettings, updateEmailSettings, testEmailSettings } from '../api/ai';
import { extractErrorMessage } from '../utils/errors';
import { useToastState } from './Toaster';
import { toast } from '../store/toastStore';

const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors disabled:opacity-60';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';

// The company's own email account: its documents (sent by the AI assistant, later from Faturas) always leave from
// this address. The password is kept encrypted and never shown back.
export default function EmailSettingsTab({ canManage }) {
  const [form, setForm] = useState(null);
  const [info, setInfo] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useToastState('error');
  const [testTo, setTestTo] = useState('');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useToastState('success');

  function load(data) {
    setInfo(data);
    setForm({ smtpHost: data.smtp_host, smtpPort: String(data.smtp_port), security: data.security, username: data.username,
      password: '', fromEmail: data.from_email, fromName: data.from_name });
  }

  useEffect(() => {
    getEmailSettings().then(load).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar')));
  }, []);

  function update(field, value) {
    setForm((p) => ({ ...p, [field]: value }));
    setSaved(false);
  }

  function chooseSecurity(value) {
    setForm((p) => ({ ...p, security: value, smtpPort: value === 'SSL' ? '465' : value === 'STARTTLS' ? '587' : '25' }));
    setSaved(false);
  }

  async function handleSave() {
    setError('');
    setTestResult('');
    setSaving(true);
    try {
      load(await updateEmailSettings({
        smtp_host: form.smtpHost.trim(), smtp_port: parseInt(form.smtpPort, 10) || 0, security: form.security,
        username: form.username.trim() || null, password: form.password ? form.password : null,
        from_email: form.fromEmail.trim(), from_name: form.fromName.trim() || null, is_active: true,
      }));
      setSaved(true);
      toast.success('Alterações guardadas');
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setError('');
    setTestResult('');
    setTesting(true);
    try {
      await testEmailSettings(testTo.trim());
      setTestResult('Email de teste enviado para ' + testTo.trim() + ' - verifique a caixa de entrada');
    } catch (err) {
      setError(extractErrorMessage(err, 'O envio falhou'));
    } finally {
      setTesting(false);
    }
  }

  if (!form) {
    return (
      <div className="bg-bg-elevated border border-border rounded-lg p-8 flex items-center justify-center text-text-muted text-sm">
        {error || <><Loader2 size={16} className="animate-spin mr-2" />A carregar...</>}
      </div>
    );
  }

  return (
    <div className="bg-bg-elevated border border-border rounded-lg p-6 sm:p-8 flex flex-col gap-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5"><Mail size={12} />Email da empresa</p>
        <span className={'text-[12px] font-medium ' + (info.configured ? 'text-success' : 'text-text-muted')}>{info.configured ? 'Configurado' : 'Não configurado'}</span>
      </div>
      <p className="text-[12px] text-text-muted -mt-2">Os documentos enviados por email (pelo Assistente IA) partem deste endereço. Com o Gmail, use uma «palavra-passe de aplicação» (Conta Google → Segurança), não a palavra-passe normal.</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="sm:col-span-2">
          <label className={labelClass}>Servidor de envio (SMTP) *</label>
          <input value={form.smtpHost} disabled={!canManage} onChange={(e) => update('smtpHost', e.target.value)} placeholder="Ex.: smtp.gmail.com" className={inputClass} />
        </div>
        <div>
          <label className={labelClass}>Segurança</label>
          <Select value={form.security} onChange={chooseSecurity} disabled={!canManage}
            options={[{ value: 'STARTTLS', label: 'STARTTLS (587)' }, { value: 'SSL', label: 'SSL (465)' }, { value: 'NONE', label: 'Nenhuma' }]} />
        </div>
        <div>
          <label className={labelClass}>Porta *</label>
          <input type="number" value={form.smtpPort} disabled={!canManage} onChange={(e) => update('smtpPort', e.target.value)} className={inputClass} />
        </div>
        <div>
          <label className={labelClass}>Utilizador</label>
          <input value={form.username} disabled={!canManage} onChange={(e) => update('username', e.target.value)} placeholder="Normalmente o email" autoComplete="off" className={inputClass} />
        </div>
        <div>
          <label className={labelClass}>Palavra-passe</label>
          <input type="password" value={form.password} disabled={!canManage} onChange={(e) => update('password', e.target.value)} placeholder={info.password_hint || ''} autoComplete="new-password" className={inputClass} />
          {info.has_password && <p className="text-[11px] text-text-muted mt-1">Vazio = manter a atual</p>}
        </div>
        <div>
          <label className={labelClass}>Email de envio *</label>
          <input value={form.fromEmail} disabled={!canManage} onChange={(e) => update('fromEmail', e.target.value)} placeholder="geral@empresa.ao" className={inputClass} />
        </div>
        <div>
          <label className={labelClass}>Nome do remetente</label>
          <input value={form.fromName} disabled={!canManage} onChange={(e) => update('fromName', e.target.value)} placeholder="Nome da empresa" className={inputClass} />
        </div>
      </div>

      {canManage && (
        <div className="flex items-end gap-3 flex-wrap">
          <button onClick={handleSave} disabled={saving} className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium px-4 py-2.5 rounded-md transition-colors cursor-pointer">
            {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <Check size={14} /> : <Save size={14} />}
            {saved ? 'Guardado' : 'Guardar'}
          </button>
          <div className="flex items-end gap-2 ml-auto">
            <div>
              <label className={labelClass}>Enviar um teste para</label>
              <input value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder="o-seu@email.ao" className={inputClass + ' w-64'} />
            </div>
            <button onClick={handleTest} disabled={testing || !info.configured || !testTo.trim()}
              title={!info.configured ? 'Guarde primeiro a configuração' : undefined}
              className="flex items-center gap-1.5 border border-border hover:border-accent disabled:opacity-50 disabled:cursor-not-allowed text-text-primary text-sm font-medium px-4 py-2.5 rounded-md transition-colors cursor-pointer">
              {testing ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}Enviar teste
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
