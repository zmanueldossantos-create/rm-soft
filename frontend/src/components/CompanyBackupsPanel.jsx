import { useEffect, useState } from 'react';
import { CheckCircle2, Clock, DatabaseBackup, Download, Loader2, Plus, Save, Trash2, XCircle } from 'lucide-react';
import { downloadMyBackup, getMyBackups, makeMyBackup, saveMyBackupSettings } from '../api/company';
import { downloadCompanyBackupCopy, getCompanyBackups, makeCompanyBackup } from '../api/admin';
import { extractErrorMessage } from '../utils/errors';
import { Notify, useToastState } from './Toaster';

// Cópias de segurança of a company. The gestor (no companyId) chooses automatic (1 to 3 hours a day) or manual, makes a
// copy now and downloads its copies; the platform (companyId given) sees the same, without changing the gestor's
// choice. Restoring is the platform's only («Restaurar empresa» in Empresas).

const KIND_LABELS = { AUTOMATICA: 'Automática', MANUAL: 'Manual', PLATAFORMA: 'RM SOFT' };
const inputClass = 'bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors';

export function when(value) {
  return value ? new Date(value).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-';
}

export function size(bytes) {
  if (!bytes) return '-';
  if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1).replace('.', ',') + ' MB';
}

export default function CompanyBackupsPanel({ companyId = null, canManage = true }) {
  const platform = !!companyId;
  const [data, setData] = useState(null);
  const [mode, setMode] = useState('MANUAL');
  const [times, setTimes] = useState([]);
  const [error, setError] = useToastState('error');
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [making, setMaking] = useState(false);

  async function load() {
    try {
      const result = platform ? await getCompanyBackups(companyId) : await getMyBackups();
      setData(result);
      setMode(result.settings.mode);
      setTimes(result.settings.times.length ? result.settings.times : ['23:00']);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível carregar as cópias de segurança'));
    }
  }
  useEffect(() => { load(); }, [companyId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      const settings = await saveMyBackupSettings(mode, times.filter(Boolean));
      setData((prev) => ({ ...prev, settings }));
      setSaved(true);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível guardar'));
    } finally {
      setSaving(false);
    }
  }

  async function copyNow() {
    setMaking(true);
    setError('');
    try {
      const copy = platform ? await makeCompanyBackup(companyId) : await makeMyBackup();
      if (copy.status === 'ERRO') setError('A cópia falhou: ' + (copy.error || 'erro desconhecido'));
      await load();
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível fazer a cópia'));
    } finally {
      setMaking(false);
    }
  }

  async function download(copy) {
    setError('');
    try {
      if (platform) await downloadCompanyBackupCopy(copy.id, copy.file_name);
      else await downloadMyBackup(copy.id, copy.file_name);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível descarregar a cópia'));
    }
  }

  if (!data) {
    return error
      ? null
      : <div className="flex items-center gap-2 text-[13px] text-text-muted py-6"><Loader2 size={15} className="animate-spin" /> A carregar...</div>;
  }

  const { settings, copies } = data;
  const editable = !platform && canManage;

  return (
    <div className="flex flex-col gap-5">
      <div className="bg-bg-elevated border border-border rounded-lg p-5 flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h3 className="text-[15px] font-semibold text-text-primary flex items-center gap-2"><DatabaseBackup size={17} className="text-accent" /> Cópias de segurança</h3>
            <p className="text-[12px] text-text-muted mt-1 max-w-2xl">
              Cada cópia guarda todos os dados da empresa (documentos, clientes, artigos, stock, utilizadores e imagens) num
              ficheiro no servidor. Guardam-se as cópias dos últimos {settings.keep_days} dias e, antes disso, uma por semana
              durante {settings.keep_weeks} semanas. A reposição de uma cópia é feita pela RM SOFT.
            </p>
          </div>
          <button type="button" onClick={copyNow} disabled={making || !canManage}
            className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer">
            {making ? <Loader2 size={16} className="animate-spin" /> : <DatabaseBackup size={16} />}
            {making ? 'A fazer a cópia...' : 'Fazer cópia agora'}
          </button>
        </div>

        <div className="flex flex-col gap-3 border-t border-border pt-4">
          <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Cópias automáticas</span>
          {editable ? (
            <>
              <div className="flex items-center bg-bg-inset border border-border rounded-md p-0.5 self-start">
                {[['AUTOMATICA', 'Automática'], ['MANUAL', 'Só manual']].map(([key, label]) => (
                  <button key={key} type="button" onClick={() => { setMode(key); setSaved(false); }}
                    className={'px-3.5 py-2 rounded text-[12px] font-medium transition-colors cursor-pointer ' + (mode === key ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}>
                    {label}
                  </button>
                ))}
              </div>
              {mode === 'AUTOMATICA' && (
                <div className="flex items-center gap-2 flex-wrap">
                  {times.map((t, idx) => (
                    <div key={idx} className="flex items-center gap-1">
                      <input type="time" value={t} onChange={(e) => { setTimes((prev) => prev.map((x, i) => (i === idx ? e.target.value : x))); setSaved(false); }} className={inputClass} />
                      {times.length > 1 && (
                        <button type="button" onClick={() => { setTimes((prev) => prev.filter((_, i) => i !== idx)); setSaved(false); }} aria-label="Retirar esta hora"
                          className="w-8 h-8 flex items-center justify-center rounded-md border border-border text-text-muted hover:text-danger hover:border-danger cursor-pointer">
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  ))}
                  {times.length < settings.max_times && (
                    <button type="button" onClick={() => { setTimes((prev) => [...prev, '']); setSaved(false); }}
                      className="flex items-center gap-1.5 border border-dashed border-border hover:border-accent text-text-muted hover:text-text-primary text-[12px] rounded-md px-3 py-2 cursor-pointer">
                      <Plus size={14} /> Outra hora
                    </button>
                  )}
                  <span className="text-[12px] text-text-muted">até {settings.max_times} por dia, hora de Luanda</span>
                </div>
              )}
              <div className="flex items-center gap-3 flex-wrap">
                <button type="button" onClick={save} disabled={saving}
                  className="flex items-center gap-2 border border-border hover:border-accent text-text-primary text-sm font-medium px-4 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50">
                  {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Guardar
                </button>
                {saved && <Notify success="Cópias de segurança: escolha guardada" />}
                {settings.mode === 'AUTOMATICA' && settings.next_run_at && (
                  <span className="text-[12px] text-text-muted flex items-center gap-1.5"><Clock size={13} /> Próxima cópia automática: {when(settings.next_run_at)}</span>
                )}
              </div>
            </>
          ) : (
            <p className="text-[13px] text-text-primary">
              {settings.mode === 'AUTOMATICA'
                ? <>Automática às {settings.times.join(', ')} · próxima: {when(settings.next_run_at)}</>
                : 'Só manual - o gestor ainda não escolheu cópias automáticas.'}
              {platform && <span className="block text-[12px] text-text-muted mt-0.5">Escolhido pelo gestor em Definições da Empresa.</span>}
            </p>
          )}
        </div>
      </div>


      <div className="border border-border rounded-md overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-bg-inset text-[11px] uppercase tracking-wide text-text-muted">
            <tr>
              <th className="text-left px-4 py-2.5 font-medium">Data</th>
              <th className="text-left px-4 py-2.5 font-medium">Tipo</th>
              <th className="text-left px-4 py-2.5 font-medium">Estado</th>
              <th className="text-right px-4 py-2.5 font-medium">Tamanho</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {copies.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-text-muted text-[13px]">Nenhuma cópia ainda.</td></tr>
            )}
            {copies.map((c) => (
              <tr key={c.id}>
                <td className="px-4 py-2.5 font-mono text-[12px] whitespace-nowrap text-text-primary">{when(c.created_at)}</td>
                <td className="px-4 py-2.5 text-[13px] text-text-primary">{KIND_LABELS[c.kind] || c.kind}</td>
                <td className="px-4 py-2.5 text-[13px]">
                  {c.status === 'FEITA'
                    ? <span className="flex items-center gap-1.5 text-success"><CheckCircle2 size={14} /> Feita</span>
                    : <span className="flex items-center gap-1.5 text-danger" title={c.error || ''}><XCircle size={14} /> Erro{c.error ? ' - ' + c.error : ''}</span>}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-[12px] text-text-muted">{size(c.size_bytes)}</td>
                <td className="px-4 py-2.5 text-right">
                  {c.status === 'FEITA' && (
                    <button type="button" onClick={() => download(c)} aria-label="Descarregar" title="Descarregar"
                      className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent cursor-pointer">
                      <Download size={14} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
