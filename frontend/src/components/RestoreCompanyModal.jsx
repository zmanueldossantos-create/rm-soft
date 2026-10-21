import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, FileArchive, Loader2, Upload } from 'lucide-react';
import Modal from './Modal';
import { inspectCompanyBackup, restoreCompanyBackup } from '../api/admin';
import { extractErrorMessage } from '../utils/errors';

// Empresas > «Restaurar empresa»: choose a backup file (made with «Exportar»), see what it holds and what would stop
// it, then put the company back - identical. Never over a company that exists here.

const COUNT_LABELS = [
  ['faturas', 'Faturas'], ['clientes', 'Clientes'], ['artigos', 'Artigos'], ['servicos', 'Serviços'],
  ['fornecedores', 'Fornecedores'], ['utilizadores', 'Utilizadores'], ['movimentos_de_stock', 'Movimentos de stock'],
];

function when(value) {
  return value ? new Date(value).toLocaleString('pt-PT', { dateStyle: 'short', timeStyle: 'short' }) : '';
}

export default function RestoreCompanyModal({ open, onClose, onRestored }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(null);

  useEffect(() => {
    if (open) { setFile(null); setPreview(null); setError(''); setDone(null); setBusy(false); }
  }, [open]);

  async function choose(e) {
    const chosen = e.target.files?.[0];
    e.target.value = '';
    if (!chosen) return;
    setFile(chosen);
    setPreview(null);
    setError('');
    setBusy(true);
    try {
      setPreview(await inspectCompanyBackup(chosen));
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível ler o ficheiro'));
    } finally {
      setBusy(false);
    }
  }

  async function restore() {
    setBusy(true);
    setError('');
    try {
      const result = await restoreCompanyBackup(file);
      setDone(result);
      onRestored?.();
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível restaurar a empresa'));
    } finally {
      setBusy(false);
    }
  }

  const blocked = !preview || preview.problems.length > 0;

  return (
    <Modal open={open} onClose={onClose} title="Restaurar empresa" subtitle="A partir de uma cópia feita com «Exportar»" maxWidthClass="max-w-2xl">
      {done ? (
        <div className="flex flex-col gap-4">
          <div className="flex items-start gap-2.5 bg-success/10 border-l-2 border-success text-success px-3.5 py-2.5 text-[13px] rounded-r">
            <CheckCircle2 size={16} className="shrink-0 mt-0.5" />
            <span>
              «{done.name}» restaurada: {done.faturas} faturas, {done.clientes} clientes, {done.artigos} artigos,
              {' '}{done.utilizadores} utilizadores. Os utilizadores entram com as mesmas palavras-passe.
            </span>
          </div>
          <p className="text-[12px] text-text-muted">
            Numa outra instalação, volte a escrever as palavras-passe guardadas (email da empresa, chaves) se a chave do
            servidor for diferente.
          </p>
          <button type="button" onClick={onClose}
            className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer">
            Fechar
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <input ref={inputRef} type="file" accept=".zip,application/zip" onChange={choose} className="hidden" />
          <button type="button" onClick={() => inputRef.current?.click()} disabled={busy}
            className="flex items-center justify-center gap-2 border border-dashed border-border hover:border-accent rounded-md py-5 text-[13px] text-text-primary cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
            {file ? <FileArchive size={17} className="text-accent" /> : <Upload size={17} className="text-accent" />}
            {file ? file.name : 'Escolher o ficheiro da cópia (.zip)'}
          </button>

          {busy && !preview && (
            <div className="flex items-center gap-2 text-[13px] text-text-muted"><Loader2 size={15} className="animate-spin" /> A ler o ficheiro...</div>
          )}

          {preview && (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-[13px]">
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-text-muted mb-0.5">Empresa</div>
                  <div className="text-text-primary font-semibold">{preview.company.short_name || preview.company.name}</div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-text-muted mb-0.5">NIF</div>
                  <div className="text-text-primary font-mono">{preview.company.nif}</div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-text-muted mb-0.5">Cópia feita em</div>
                  <div className="text-text-primary">{when(preview.exported_at)}</div>
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {COUNT_LABELS.map(([key, label]) => (
                  <div key={key} className="bg-bg-inset border border-border rounded-md px-3 py-2">
                    <div className="text-[11px] text-text-muted">{label}</div>
                    <div className="text-[15px] font-semibold text-text-primary font-mono">{preview.counts[key]}</div>
                  </div>
                ))}
              </div>
              {preview.problems.map((problem) => (
                <div key={problem} className="flex items-start gap-2.5 bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
                  <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                  <span>{problem}</span>
                </div>
              ))}
              {preview.problems.length === 0 && (
                <p className="text-[12px] text-text-muted">
                  A empresa volta exatamente como estava no momento da cópia: documentos, numeração, stock, utilizadores e
                  imagens. O que foi feito depois dessa data não está no ficheiro.
                </p>
              )}
            </div>
          )}

          {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{error}</div>}

          <button type="button" onClick={restore} disabled={busy || blocked}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors">
            {busy && preview ? <Loader2 size={17} className="animate-spin" /> : <Upload size={17} />}
            {busy && preview ? 'A restaurar...' : 'Restaurar a empresa'}
          </button>
        </div>
      )}
    </Modal>
  );
}
