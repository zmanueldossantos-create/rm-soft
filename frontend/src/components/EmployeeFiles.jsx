import { useEffect, useRef, useState } from 'react';
import { Camera, Trash2, Loader2, UserRound, Upload, FileText, Eye, CheckCircle2, Circle, Paperclip, Plus } from 'lucide-react';
import Select from './Select';
import DateInput from './DateInput';
import {
  fetchEmployeePhotoUrl, uploadEmployeePhoto, deleteEmployeePhoto, listEmployeeDocuments, addEmployeeDocument,
  deleteEmployeeDocument, fetchEmployeeDocumentUrl,
} from '../api/hr';
import { openPdf } from '../store/pdfViewerStore';
import { formatDate } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// The employee's photo and the documents of his file. Personal data: read through the session (a blob), never from a
// public address. The checks are the server's (kind of file read from its bytes, size, dates).
const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';

export function EmployeePhoto({ employee, canManage, onChanged }) {
  const [url, setUrl] = useState(null);
  const [busy, setBusy] = useState(false);
  const input = useRef(null);

  useEffect(() => {
    let current = null;
    setUrl(null);
    if (employee?.has_photo) {
      fetchEmployeePhotoUrl(employee.id).then((u) => { current = u; setUrl(u); }).catch(() => setUrl(null));
    }
    return () => { if (current) URL.revokeObjectURL(current); };
  }, [employee?.id, employee?.has_photo]);

  async function choose(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { toast.error('A fotografia tem no máximo 2 MB'); return; }
    setBusy(true);
    try {
      await uploadEmployeePhoto(employee.id, file);
      toast.success('Fotografia guardada');
      onChanged({ has_photo: true, photo_version: Date.now() });
      setUrl(URL.createObjectURL(file));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar a fotografia'));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await deleteEmployeePhoto(employee.id);
      setUrl(null);
      onChanged({ has_photo: false });
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao remover a fotografia'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-4">
      <div className="w-24 h-28 rounded-md border border-border bg-bg-inset overflow-hidden flex items-center justify-center shrink-0">
        {busy ? <Loader2 size={20} className="animate-spin text-text-muted" />
          : url ? <img src={url} alt={employee.full_name} className="w-full h-full object-cover" />
            : <UserRound size={36} className="text-text-muted" />}
      </div>
      {canManage && (
        <div className="flex flex-col gap-2">
          <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={choose} />
          <button type="button" disabled={busy} onClick={() => input.current?.click()}
            className="flex items-center gap-2 h-8 px-3 rounded-md border border-border text-[12px] font-medium text-text-primary hover:border-accent hover:text-accent cursor-pointer">
            <Camera size={14} /> {url ? 'Alterar fotografia' : 'Juntar fotografia'}
          </button>
          {url && (
            <button type="button" disabled={busy} onClick={remove}
              className="flex items-center gap-2 h-8 px-3 rounded-md border border-border text-[12px] font-medium text-text-muted hover:border-danger hover:text-danger cursor-pointer">
              <Trash2 size={14} /> Remover
            </button>
          )}
          <p className="text-[11px] text-text-muted">JPEG, PNG ou WebP, até 2 MB</p>
        </div>
      )}
    </div>
  );
}

const emptyDoc = () => ({ typeId: '', description: '', deliveredOn: new Date().toLocaleDateString('sv-SE'), expiresOn: '', file: null });

export function EmployeeDocuments({ employee, canManage }) {
  const [data, setData] = useState({ documents: [], checklist: [] });
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(emptyDoc);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef(null);

  async function load() {
    try {
      setData(await listEmployeeDocuments(employee.id));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar os documentos'));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { setLoading(true); setForm(emptyDoc()); load(); }, [employee.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function add(e) {
    e.preventDefault();
    if (!form.typeId && !form.description.trim()) { toast.error('Escolha o tipo de documento ou descreva-o'); return; }
    if (form.file && form.file.size > 5 * 1024 * 1024) { toast.error('O ficheiro tem no máximo 5 MB'); return; }
    setBusy(true);
    try {
      await addEmployeeDocument(employee.id, { documentTypeId: form.typeId, description: form.typeId ? '' : form.description,
        deliveredOn: form.deliveredOn, expiresOn: form.expiresOn, file: form.file });
      toast.success('Documento registado');
      setForm(emptyDoc());
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao registar o documento'));
    } finally {
      setBusy(false);
    }
  }

  async function view(doc) {
    try {
      const url = await fetchEmployeeDocumentUrl(employee.id, doc.id);
      if (doc.content_type === 'application/pdf') openPdf({ url, title: doc.name, fileName: doc.file_name.replace(/\.pdf$/i, '') });
      else window.open(url, '_blank', 'noopener');
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao abrir o documento'));
    }
  }

  async function remove(doc) {
    setBusy(true);
    try {
      await deleteEmployeeDocument(employee.id, doc.id);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao apagar o documento'));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="flex items-center justify-center py-10 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" /> A carregar...</div>;

  const typeOptions = [{ value: '', label: 'Outro (descrever)' }, ...data.checklist.map((c) => ({ value: c.document_type_id, label: c.name }))];
  return (
    <div className="flex flex-col gap-5">
      {data.checklist.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {data.checklist.map((c) => (
            <span key={c.document_type_id} className={'inline-flex items-center gap-1.5 text-[12px] px-2.5 py-1 rounded-full border ' + (c.delivered ? 'border-success/40 text-success bg-success/10' : 'border-border text-text-muted')}>
              {c.delivered ? <CheckCircle2 size={13} /> : <Circle size={13} />} {c.name}
            </span>
          ))}
        </div>
      )}

      {canManage && (
        <form noValidate onSubmit={add} className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end border border-border rounded-md p-3">
          <div className="sm:col-span-2">
            <label className={labelClass}>Documento</label>
            <Select value={form.typeId} onChange={(v) => setForm((p) => ({ ...p, typeId: v }))} options={typeOptions} />
          </div>
          <div>
            <label className={labelClass}>Entregue em</label>
            <DateInput value={form.deliveredOn} onChange={(e) => setForm((p) => ({ ...p, deliveredOn: e.target.value }))} className={inputClass} />
          </div>
          <div>
            <label className={labelClass}>Válido até</label>
            <DateInput value={form.expiresOn} onChange={(e) => setForm((p) => ({ ...p, expiresOn: e.target.value }))} className={inputClass} />
          </div>
          {!form.typeId && (
            <div className="sm:col-span-2">
              <label className={labelClass}>Descrição *</label>
              <input value={form.description} maxLength={200} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} className={inputClass} placeholder="Ex.: Declaração de residência" />
            </div>
          )}
          <div className={form.typeId ? 'sm:col-span-3' : ''}>
            <input ref={fileInput} type="file" accept="application/pdf,image/jpeg,image/png" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; setForm((p) => ({ ...p, file: f || null })); }} />
            <button type="button" onClick={() => fileInput.current?.click()}
              className="w-full flex items-center gap-2 h-[42px] px-3 rounded-md border border-dashed border-border text-[13px] text-text-muted hover:border-accent hover:text-accent cursor-pointer truncate">
              <Paperclip size={14} className="shrink-0" /> <span className="truncate">{form.file ? form.file.name : 'Digitalização (opcional) - PDF, JPEG, PNG até 5 MB'}</span>
            </button>
          </div>
          <button type="submit" disabled={busy} className="h-[42px] rounded-md bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-semibold flex items-center justify-center gap-2 cursor-pointer">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />} Registar
          </button>
        </form>
      )}

      {data.documents.length === 0 ? (
        <p className="text-sm text-text-muted text-center py-6">Nenhum documento entregue.</p>
      ) : (
        <div className="border border-border rounded-md overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
                <th className="text-left px-3 py-2">Documento</th>
                <th className="text-left px-3 py-2">Entregue em</th>
                <th className="text-left px-3 py-2">Válido até</th>
                <th className="text-left px-3 py-2">Ficheiro</th>
                <th className="text-right px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {data.documents.map((d) => (
                <tr key={d.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 text-text-primary">{d.name}</td>
                  <td className="px-3 py-2 text-text-muted whitespace-nowrap">{formatDate(d.delivered_on)}</td>
                  <td className={'px-3 py-2 whitespace-nowrap ' + (d.expired ? 'text-danger font-medium' : 'text-text-muted')}>
                    {formatDate(d.expires_on)}{d.expired ? ' · expirado' : ''}
                  </td>
                  <td className="px-3 py-2">
                    {d.has_file ? (
                      <button type="button" onClick={() => view(d)} className="inline-flex items-center gap-1.5 text-accent hover:underline cursor-pointer text-[13px]">
                        {d.content_type === 'application/pdf' ? <FileText size={14} /> : <Eye size={14} />} Ver
                      </button>
                    ) : <span className="text-text-muted text-[12px]">Em papel</span>}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {canManage && (
                      <button type="button" title="Apagar" disabled={busy} onClick={() => remove(d)} className="w-8 h-8 inline-flex items-center justify-center rounded-md border border-border text-text-muted hover:text-danger hover:border-danger cursor-pointer">
                        <Trash2 size={13} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] text-text-muted flex items-center gap-1.5"><Upload size={12} /> Os ficheiros ficam na base de dados da empresa e só são vistos por quem tem acesso aos Recursos Humanos.</p>
    </div>
  );
}
