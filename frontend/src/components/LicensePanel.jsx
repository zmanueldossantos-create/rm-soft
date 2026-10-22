import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Copy, FileKey2, Loader2, Upload, XCircle } from 'lucide-react';
import { limitText } from '../api/plans';
import { extractErrorMessage } from '../utils/errors';
import { useToastState } from './Toaster';
import { toast } from '../store/toastStore';

// «Licença» of a client's server (LICENSE_REQUIRED): this server's code (to send to RM SOFT), the licence in force (or
// why there is none) and the import of the file RM SOFT sends. Used by the gestor (Definições da Empresa) and by the
// platform's technician (Empresas > Contrato) - load / save are the right calls for each.
// Inside forms: its buttons are never «submit».

const dateText = (value) => (value ? String(value).split('-').reverse().join('/') : '');
const BILLING = { TESTE: 'Teste gratuito', MENSAL: 'Mensal', TRIMESTRAL: 'Trimestral', SEMESTRAL: 'Semestral', ANUAL: 'Anual', VITALICIA: 'Vitalícia' };
const LIMIT_LABELS = { max_users: 'Utilizadores', max_modules: 'Módulos', max_establishments: 'Lojas', max_pos: 'Caixas', max_warehouses: 'Armazéns' };
const STATUS = {
  ATIVO: ['Em vigor', 'text-success'],
  A_EXPIRAR: ['Termina em breve', 'text-amber-500 [.light_&]:text-amber-700'],
  TOLERANCIA: ['Terminada - período de tolerância', 'text-danger'],
  BLOQUEADO: ['Terminada - só leitura', 'text-danger'],
};

export default function LicensePanel({ load, save, canImport = true }) {
  const [view, setView] = useState(null);
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useToastState('error');
  const fileRef = useRef(null);

  useEffect(() => {
    load().then(setView).catch((err) => setError(extractErrorMessage(err, 'Não foi possível carregar a licença')));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function doImport(content) {
    setSaving(true);
    setError('');
    try {
      const result = await save(content);
      setView(result);
      setText('');
      window.dispatchEvent(new Event('subscription-changed')); // the banner at the top follows at once
      toast.success('Licença importada: ' + result.plan + (result.end_date ? ' até ' + dateText(result.end_date) : ''));
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível importar a licença'));
    } finally {
      setSaving(false);
    }
  }

  function chooseFile(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    file.text().then(doImport);
  }

  async function copyCode() {
    try { await navigator.clipboard.writeText(view.installation_code); toast.success('Código copiado'); } catch { /* the code stays visible */ }
  }

  if (!view) {
    return error ? null : <div className="flex items-center justify-center py-16 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>;
  }
  const [statusLabel, statusTone] = STATUS[view.status] || STATUS.ATIVO;

  return (
    <div className="flex flex-col gap-5">
      <div className="bg-bg-elevated border border-border rounded-lg p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-text-muted">Código de instalação deste servidor</div>
          <div className="text-[22px] font-mono font-semibold text-text-primary tracking-wider">{view.installation_code}</div>
          <p className="text-[12px] text-text-muted">Envie este código à RM SOFT: a licença é emitida para este servidor e só funciona nele. Os outros computadores da rede não precisam de licença.</p>
        </div>
        <button type="button" onClick={copyCode}
          className="self-start sm:self-center flex items-center gap-2 border border-border hover:border-accent text-text-primary text-sm px-3.5 py-2 rounded-md cursor-pointer">
          <Copy size={14} /> Copiar
        </button>
      </div>

      <div className="border border-border rounded-lg p-4 flex flex-col gap-3">
        {view.valid ? (
          <>
            <div className="flex items-center gap-2 text-[15px] font-semibold text-text-primary">
              <CheckCircle2 size={17} className="text-success" /> Licença {view.plan}
              <span className={'text-[12px] font-medium ' + statusTone}>· {statusLabel}</span>
            </div>
            <div className="text-[13px] text-text-muted">
              {BILLING[view.billing] || view.billing} · desde {dateText(view.start_date)}
              {view.billing === 'VITALICIA'
                ? ' · sem fim' + (view.maintenance_until ? ' · manutenção até ' + dateText(view.maintenance_until) : '')
                : view.end_date ? ' · até ' + dateText(view.end_date) : ' · sem data de fim'}
              {view.status === 'TOLERANCIA' && view.grace_until ? ' · funciona até ' + dateText(view.grace_until) : ''}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              {Object.keys(LIMIT_LABELS).map((code) => {
                const base = view.limits?.[code];
                const extra = view.addons?.[code] || 0;
                return (
                  <div key={code} className="bg-bg-inset border border-border rounded-md px-3 py-2">
                    <div className="text-[11px] text-text-muted">{LIMIT_LABELS[code]}</div>
                    <div className="text-[15px] font-semibold font-mono text-text-primary">{base == null ? limitText(null) : base + extra}</div>
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <div className="flex items-start gap-2 text-[13px] text-danger">
            <XCircle size={17} className="shrink-0 mt-0.5" />
            <span>
              <b>Sem licença válida.</b> {view.problem}.
              {view.read_only
                ? ' O sistema está só de leitura até à importação de uma licença.'
                : view.grace_until ? ' Tudo funciona até ' + dateText(view.grace_until) + '; depois, só leitura.' : ''}
            </span>
          </div>
        )}
      </div>

      {canImport && (
        <div className="border border-border rounded-lg p-4 flex flex-col gap-3">
          <div>
            <h4 className="text-[14px] font-semibold text-text-primary flex items-center gap-2"><FileKey2 size={16} className="text-accent" /> Importar a licença</h4>
            <p className="text-[12px] text-text-muted">O ficheiro .lic enviado pela RM SOFT (uma renovação substitui a licença atual). Também pode colar o seu conteúdo.</p>
          </div>
          <input ref={fileRef} type="file" accept=".lic,.txt,text/plain" onChange={chooseFile} className="hidden" />
          <div className="flex items-start gap-3 flex-wrap">
            <button type="button" onClick={() => fileRef.current?.click()} disabled={saving}
              className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm px-4 py-2.5 rounded-md cursor-pointer">
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />} Escolher o ficheiro .lic
            </button>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} placeholder="ou cole aqui: RMSOFT-LICENCA-1...."
              className="flex-1 min-w-[260px] bg-bg-inset border border-border rounded-md px-3 py-2 text-[12px] text-text-primary font-mono outline-none focus:border-accent" />
            {text.trim() && (
              <button type="button" onClick={() => doImport(text)} disabled={saving}
                className="flex items-center gap-2 border border-border hover:border-accent text-text-primary text-sm px-4 py-2.5 rounded-md cursor-pointer disabled:opacity-50">
                Importar o texto colado
              </button>
            )}
          </div>
        </div>
      )}
      {view.issued_at && <p className="text-[11px] text-text-muted">Licença emitida pela RM SOFT em {new Date(view.issued_at).toLocaleString('pt-PT')}.</p>}
    </div>
  );
}
