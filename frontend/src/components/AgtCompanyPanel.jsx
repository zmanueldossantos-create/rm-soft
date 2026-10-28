import { useEffect, useState } from 'react';
import { KeyRound, Loader2, Zap, Trash2, Save, History, CheckCircle2, AlertTriangle } from 'lucide-react';
import Modal from './Modal';
import Select from './Select';
import { getCompanyAgt, saveCompanyAgtKey, testCompanyAgt, getCompanyAgtCalls, setCompanyAgtTestNif } from '../api/agt';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Definições da Empresa → Faturação Eletrónica: the taxpayer's private key issued by the AGT (portal do contribuinte),
// kept encrypted - never shown again, only its size and fingerprint -, the connection test and the journal of the calls.
const ENVIRONMENT_LABEL = { HOMOLOGACAO: 'Homologação (testes)', PRODUCAO: 'Produção' };

function when(iso) {
  return iso ? new Date(iso).toLocaleString('pt-PT') : '';
}

export default function AgtCompanyPanel() {
  const [info, setInfo] = useState(null);
  const [pem, setPem] = useState('');
  const [busy, setBusy] = useState('');
  const [result, setResult] = useState(null);
  const [calls, setCalls] = useState(null);

  useEffect(() => {
    getCompanyAgt().then(setInfo).catch(() => {});
  }, []);

  async function saveKey(value) {
    setBusy(value ? 'save' : 'remove');
    try {
      setInfo(await saveCompanyAgtKey(value));
      setPem('');
      toast.success(value ? 'Chave guardada (cifrada)' : 'Chave removida');
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar a chave'));
    } finally {
      setBusy('');
    }
  }

  async function pickTestNif(nif) {
    setBusy('nif');
    try {
      setInfo(await setCompanyAgtTestNif(nif));
      toast.success(nif ? 'Em homologação, envia como o NIF de teste ' + nif : 'Envia como o NIF da empresa');
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setBusy('');
    }
  }

  async function runTest() {
    setBusy('test');
    try {
      const answer = await testCompanyAgt();
      setResult(answer);
      if (answer.ok) toast.success(answer.message + ' (' + answer.seconds + ' s)');
      else toast.error(answer.message);
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Falha no teste'));
    } finally {
      setBusy('');
    }
  }

  async function openCalls() {
    try {
      setCalls(await getCompanyAgtCalls());
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao ler o registo'));
    }
  }

  if (!info) return null;
  const field = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-[12px] text-text-primary font-mono outline-none focus:border-accent transition-colors';
  const button = 'flex items-center gap-1.5 text-sm font-medium px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed';

  return (
    <div className="border border-border rounded-lg px-4 py-4 flex flex-col gap-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <KeyRound size={16} className="text-accent" />
          <span className="text-sm font-medium text-text-primary">Faturação Eletrónica - AGT</span>
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-bg-inset border border-border text-text-muted">{ENVIRONMENT_LABEL[info.environment] || info.environment}</span>
        </div>
        <span className="text-[12px] text-text-muted">NIF emissor <span className="font-mono text-text-primary">{info.nif}</span></span>
      </div>

      {info.missing.length > 0 ? (
        <div className="flex items-start gap-2 text-[12px] text-amber-500 bg-amber-500/10 border border-amber-500/30 rounded-md px-3 py-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span>Falta: {info.missing.join(' · ')}</span>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-[12px] text-success">
          <CheckCircle2 size={14} /> Pronto para comunicar com a AGT
        </div>
      )}

      {info.test_nifs.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-end">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Emitir como (só em homologação)</label>
            <Select value={info.test_nif || ''} onChange={(v) => pickTestNif(v || null)} disabled={!!busy}
              options={[{ value: '', label: 'NIF da empresa (' + info.nif + ')' }, ...info.test_nifs.map((t) => ({ value: t.nif, label: 'Teste ' + t.nif + ' - ' + t.name }))]} />
          </div>
          <p className="text-[12px] text-text-muted pb-2">
            {info.sending_as_test
              ? <>As chamadas à AGT saem com o NIF de teste <span className="font-mono text-text-primary">{info.sending_as}</span> e a sua chave. Em produção, sempre o NIF da empresa.</>
              : 'As chamadas à AGT saem com o NIF da empresa e a chave abaixo.'}
          </p>
        </div>
      )}

      <div>
        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Chave privada do contribuinte (portal da AGT)</label>
        {info.has_key && (
          <p className="text-[12px] text-text-muted mb-1.5">Guardada: RSA {info.key.bits} bits · impressão digital <span className="font-mono text-text-primary">{info.key.fingerprint}</span> - colar outra para trocar</p>
        )}
        <textarea value={pem} onChange={(e) => setPem(e.target.value)} rows={4} spellCheck={false} autoComplete="off"
          placeholder={'-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----'} className={field} />
        <p className="text-[11px] text-text-muted mt-1">Guardada cifrada no servidor e nunca mais mostrada.</p>
      </div>

      <div className="flex items-center gap-2.5 flex-wrap">
        <button type="button" onClick={() => saveKey(pem.trim())} disabled={!!busy || !pem.trim()} className={button + ' bg-accent hover:bg-accent-hover text-white'}>
          {busy === 'save' ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Guardar chave
        </button>
        <button type="button" onClick={runTest} disabled={!!busy || info.missing.length > 0}
          title={info.missing.length > 0 ? 'Complete primeiro o que falta' : undefined}
          className={button + ' border border-border hover:border-accent text-text-primary'}>
          {busy === 'test' ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />} Testar ligação à AGT
        </button>
        <button type="button" onClick={openCalls} className={button + ' border border-border hover:border-accent text-text-primary'}>
          <History size={14} /> Registo das chamadas
        </button>
        {info.has_key && (
          <button type="button" onClick={() => saveKey('')} disabled={!!busy} className="flex items-center gap-1 text-[12px] text-text-muted hover:text-danger transition-colors cursor-pointer">
            <Trash2 size={13} /> Remover a chave
          </button>
        )}
      </div>

      <Modal open={!!result} onClose={() => setResult(null)} title="Resposta da AGT" maxWidthClass="max-w-2xl"
        subtitle={result ? (result.status_code ? 'HTTP ' + result.status_code + ' · ' : '') + result.seconds + ' s' : ''}>
        {result && (
          <div className="flex flex-col gap-2">
            <p className={'text-sm ' + (result.ok ? 'text-success' : 'text-danger')}>{result.message}</p>
            {result.answer != null && (
              <pre className="bg-bg-inset border border-border rounded-md p-3 text-[11px] font-mono text-text-primary overflow-auto max-h-96 whitespace-pre-wrap break-words">{JSON.stringify(result.answer, null, 2)}</pre>
            )}
          </div>
        )}
      </Modal>

      <Modal open={!!calls} onClose={() => setCalls(null)} title="Chamadas à AGT" subtitle="Últimas 30 - guardadas 90 dias" maxWidthClass="max-w-4xl">
        {calls && calls.length === 0 && <p className="text-sm text-text-muted">Nenhuma chamada ainda.</p>}
        {calls && calls.length > 0 && (
          <div className="flex flex-col gap-2 max-h-[65vh] overflow-auto">
            {calls.map((c) => (
              <details key={c.id} className="border border-border rounded-md px-3 py-2">
                <summary className="cursor-pointer text-[12px] flex items-center gap-3 flex-wrap">
                  <span className="text-text-muted">{when(c.created_at)}</span>
                  <span className="font-mono text-text-primary">{c.service}</span>
                  <span className={c.status_code && c.status_code < 300 ? 'text-success' : 'text-danger'}>{c.status_code ? 'HTTP ' + c.status_code : 'sem resposta'}</span>
                  <span className="text-text-muted">{c.duration_ms} ms</span>
                  {c.error && <span className="text-danger truncate max-w-md">{c.error}</span>}
                </summary>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 mt-2">
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">Enviado</p>
                    <pre className="bg-bg-inset border border-border rounded-md p-2 text-[10px] font-mono text-text-primary overflow-auto max-h-64 whitespace-pre-wrap break-words">{JSON.stringify(c.request, null, 2)}</pre>
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">Resposta</p>
                    <pre className="bg-bg-inset border border-border rounded-md p-2 text-[10px] font-mono text-text-primary overflow-auto max-h-64 whitespace-pre-wrap break-words">{c.response ? JSON.stringify(c.response, null, 2) : '-'}</pre>
                  </div>
                </div>
              </details>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
}
