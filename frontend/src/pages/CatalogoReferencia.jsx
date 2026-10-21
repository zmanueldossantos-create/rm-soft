import { useEffect, useRef, useState } from 'react';
import { BookOpen, Download, FileSpreadsheet, Loader2, Pencil, Plus, Save, Search, Trash2, X } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import ConfirmDialog from '../components/ConfirmDialog';
import {
  deleteReferenceProduct, downloadReferenceTemplate, getReferenceMeta, importReferenceCatalog, listReferenceProducts,
  saveReferenceProduct,
} from '../api/referenceCatalog';
import { extractErrorMessage } from '../utils/errors';

// Catálogo de referência (menu of the platform): the products most shops of a sector sell, kept once for the platform. A new
// company takes them at its creation; changing the catalog never touches a company that exists. The VAT is the
// product's nature (normal / reduzida / isento + motive): each company's own regime decides its rate when it takes it.

const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors';
const emptyForm = { barcode: '', name: '', category: '', unit_of_measure_id: '', tax_category: 'NOR', exemption_id: '', price: '', sectors: [], units: [] };
const kz = (v) => (v == null ? null : Number(v).toLocaleString('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Kz');

function Field({ label, children, className = '' }) {
  return (
    <div className={className}>
      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{label}</label>
      {children}
    </div>
  );
}

export default function CatalogoReferencia() {
  const [meta, setMeta] = useState(null);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [sector, setSector] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null); // null closed, {} new, product to edit
  const [toDelete, setToDelete] = useState(null);
  const [importing, setImporting] = useState(false);
  const [report, setReport] = useState(null);
  const fileRef = useRef(null);

  async function loadMeta() {
    try { setMeta(await getReferenceMeta()); } catch (err) { setError(extractErrorMessage(err, 'Não foi possível carregar o catálogo')); }
  }
  async function load(offset = 0) {
    setLoading(true);
    try {
      const page = await listReferenceProducts({ q: search, sector, offset });
      setItems((prev) => (offset ? [...prev, ...page.items] : page.items));
      setTotal(page.total);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível carregar os produtos'));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { loadMeta(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const timer = setTimeout(() => load(0), 250); // the search waits for the typing to pause
    return () => clearTimeout(timer);
  }, [search, sector]); // eslint-disable-line react-hooks/exhaustive-deps

  const unitCode = (id) => meta?.units.find((u) => u.id === id)?.code || '?';
  const motiveCode = (id) => meta?.exemptions.find((m) => m.id === id)?.code || '';
  const sectorName = (code) => meta?.sectors.find((s) => s.code === code)?.name || code;

  async function chooseFile(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setImporting(true);
    setError('');
    setReport(null);
    try {
      setReport(await importReferenceCatalog(file));
      await Promise.all([loadMeta(), load(0)]);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível importar o ficheiro'));
    } finally {
      setImporting(false);
    }
  }

  async function confirmDelete() {
    const product = toDelete;
    setToDelete(null);
    try {
      await deleteReferenceProduct(product.id);
      await Promise.all([loadMeta(), load(0)]);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível eliminar'));
    }
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <BookOpen size={22} className="text-accent" />
        Catálogo de referência
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Os produtos que as lojas de cada setor vendem: uma nova empresa recebe-os na criação. Mudar o catálogo nunca altera
        as empresas existentes.
      </p>
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative w-full sm:w-80">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nome, código de barras ou categoria..."
              className={inputClass + ' pl-9'} />
          </div>
          <div className="flex-1" />
          <button type="button" onClick={() => downloadReferenceTemplate().catch((err) => setError(extractErrorMessage(err, 'Erro ao descarregar o modelo')))}
            className="flex items-center gap-2 border border-border hover:border-accent text-text-primary text-sm font-medium px-3.5 py-2 rounded-md cursor-pointer">
            <Download size={15} /> Descarregar modelo
          </button>
          <input ref={fileRef} type="file" accept=".xlsx" onChange={chooseFile} className="hidden" />
          <button type="button" onClick={() => fileRef.current?.click()} disabled={importing}
            className="flex items-center gap-2 border border-border hover:border-accent text-text-primary text-sm font-medium px-3.5 py-2 rounded-md cursor-pointer disabled:opacity-50">
            {importing ? <Loader2 size={15} className="animate-spin" /> : <FileSpreadsheet size={15} />} Importar Excel
          </button>
          <button type="button" onClick={() => setEditing({})}
            className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-3.5 py-2 rounded-md cursor-pointer">
            <Plus size={16} /> Novo produto
          </button>
        </div>

        {meta && (
          <div className="flex items-center bg-bg-inset border border-border rounded-md p-0.5 flex-wrap self-start">
            {[{ code: null, name: 'Todos', count: meta.total }, ...meta.sectors, { code: 'GERAL', name: 'Sem setor (todos)', count: meta.general }].map((s) => (
              <button key={s.code || 'all'} type="button" onClick={() => setSector(s.code)}
                className={'px-3 py-1.5 rounded text-[12px] font-medium transition-colors cursor-pointer ' + (sector === s.code ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}>
                {s.name} <span className="opacity-70">({s.count})</span>
              </button>
            ))}
          </div>
        )}

        {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{error}</div>}
        {report && (
          <div className="border border-border rounded-md p-3.5 flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[13px] text-text-primary">
                Importação: <span className="text-success font-semibold">{report.created} criados</span>, <span className="font-semibold">{report.updated} atualizados</span>
                {report.errors.length > 0 && <>, <span className="text-danger font-semibold">{report.errors.length} linhas recusadas</span></>}
              </span>
              <button type="button" onClick={() => setReport(null)} aria-label="Fechar" className="text-text-muted hover:text-text-primary cursor-pointer"><X size={15} /></button>
            </div>
            {report.errors.length > 0 && (
              <ul className="text-[12px] text-danger max-h-32 overflow-y-auto">
                {report.errors.map((e) => <li key={e.row}>Linha {e.row}: {e.message}</li>)}
              </ul>
            )}
          </div>
        )}

        <div className="border border-border rounded-md overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-bg-inset text-[11px] uppercase tracking-wide text-text-muted">
              <tr>
                <th className="text-left px-3 py-2.5 font-medium">Código de barras</th>
                <th className="text-left px-3 py-2.5 font-medium">Nome</th>
                <th className="text-left px-3 py-2.5 font-medium">Categoria</th>
                <th className="text-left px-3 py-2.5 font-medium">Unidade</th>
                <th className="text-left px-3 py-2.5 font-medium">IVA</th>
                <th className="text-right px-3 py-2.5 font-medium">Preço indicativo</th>
                <th className="text-left px-3 py-2.5 font-medium">Unidades de venda</th>
                <th className="text-left px-3 py-2.5 font-medium">Setores</th>
                <th className="px-3 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {!loading && items.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-10 text-center text-text-muted text-[13px]">
                  <BookOpen size={20} className="mx-auto mb-2 opacity-50" />
                  {search || sector ? 'Nenhum produto corresponde.' : 'O catálogo está vazio - «Novo produto» ou «Importar Excel».'}
                </td></tr>
              )}
              {items.map((p) => (
                <tr key={p.id} className="hover:bg-bg-inset/40">
                  <td className="px-3 py-2 font-mono text-[12px] text-text-primary">{p.barcode || <span className="text-text-muted">-</span>}</td>
                  <td className="px-3 py-2 text-[13px] text-text-primary font-medium">{p.name}</td>
                  <td className="px-3 py-2 text-[12px] text-text-muted">{p.category || '-'}</td>
                  <td className="px-3 py-2 font-mono text-[12px] text-text-primary">{unitCode(p.unit_of_measure_id)}</td>
                  <td className="px-3 py-2 font-mono text-[12px] text-text-primary">{p.tax_category}{p.exemption_id ? ' ' + motiveCode(p.exemption_id) : ''}</td>
                  <td className="px-3 py-2 text-right font-mono text-[12px]">{kz(p.price) || <span className="text-text-muted">sem preço</span>}</td>
                  <td className="px-3 py-2 font-mono text-[12px] text-text-muted">{p.units.map((u) => unitCode(u.unit_of_measure_id) + '×' + u.factor).join(', ') || '-'}</td>
                  <td className="px-3 py-2 text-[12px] text-text-muted">{p.sectors.length ? p.sectors.map(sectorName).join(', ') : <span className="italic">Todos os setores</span>}</td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <button type="button" onClick={() => setEditing(p)} aria-label="Editar"
                      className="inline-flex items-center justify-center w-7 h-7 mr-1.5 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent cursor-pointer"><Pencil size={12} /></button>
                    <button type="button" onClick={() => setToDelete(p)} aria-label="Eliminar"
                      className="inline-flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-danger hover:border-danger cursor-pointer"><Trash2 size={12} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between text-[12px] text-text-muted">
          <span>{items.length} de {total} produtos</span>
          {loading && <Loader2 size={15} className="animate-spin" />}
          {!loading && items.length < total && (
            <button type="button" onClick={() => load(items.length)} className="border border-border hover:border-accent text-text-primary rounded-md px-3 py-1.5 cursor-pointer">Mostrar mais</button>
          )}
        </div>
      </div>

      {editing && meta && (
        <ReferenceProductForm product={editing.id ? editing : null} meta={meta} onClose={() => setEditing(null)}
          onSaved={async () => { setEditing(null); await Promise.all([loadMeta(), load(0)]); }} />
      )}
      <ConfirmDialog open={!!toDelete} title="Eliminar do catálogo" danger confirmLabel="Eliminar"
        message={toDelete ? `«${toDelete.name}» sai do catálogo de referência. As empresas que já o têm ficam com a sua cópia.` : ''}
        onConfirm={confirmDelete} onCancel={() => setToDelete(null)} />
    </main>
  );
}

function ReferenceProductForm({ product, meta, onClose, onSaved }) {
  const [form, setForm] = useState(() => (product ? {
    ...emptyForm, ...product, barcode: product.barcode || '', category: product.category || '', exemption_id: product.exemption_id || '',
    price: product.price ?? '', units: product.units.map((u) => ({ ...u, barcode: u.barcode || '', price: u.price ?? '' })),
  } : emptyForm));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (field, value) => setForm((prev) => ({ ...prev, [field]: value }));
  const setUnit = (idx, field, value) => setForm((prev) => ({ ...prev, units: prev.units.map((u, i) => (i === idx ? { ...u, [field]: value } : u)) }));
  const unitOptions = meta.units.map((u) => ({ value: u.id, label: u.code + ' - ' + u.name }));

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await saveReferenceProduct(product?.id, {
        ...form, exemption_id: form.tax_category === 'ISE' ? form.exemption_id || null : null,
        unit_of_measure_id: form.unit_of_measure_id || null, price: form.price === '' ? null : form.price,
        units: form.units.filter((u) => u.unit_of_measure_id).map((u) => ({ ...u, price: u.price === '' ? null : u.price })),
      });
      onSaved();
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível guardar'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open stacked onClose={onClose} title={product ? 'Editar produto de referência' : 'Novo produto de referência'} maxWidthClass="max-w-4xl">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-6 gap-3">
          <Field label="Código de barras" className="sm:col-span-2"><input value={form.barcode} onChange={(e) => set('barcode', e.target.value)} placeholder="Opcional (ex.: pão)" className={inputClass} /></Field>
          <Field label="Nome *" className="sm:col-span-4"><input value={form.name} onChange={(e) => set('name', e.target.value)} required className={inputClass} /></Field>
          <Field label="Categoria" className="sm:col-span-2"><input value={form.category} onChange={(e) => set('category', e.target.value)} placeholder="Ex.: Ovos e lacticínios" className={inputClass} /></Field>
          <Field label="Unidade de base *" className="sm:col-span-2"><Select value={form.unit_of_measure_id} onChange={(v) => set('unit_of_measure_id', v)} options={unitOptions} placeholder="Selecionar" /></Field>
          <Field label="Preço indicativo" className="sm:col-span-2"><input type="number" min="0" step="0.01" value={form.price} onChange={(e) => set('price', e.target.value)} placeholder="Opcional" className={inputClass} /></Field>
          <Field label="Natureza do IVA *" className="sm:col-span-3">
            <Select value={form.tax_category} onChange={(v) => set('tax_category', v)} options={meta.tax_categories.map((t) => ({ value: t.code, label: t.code + ' - ' + t.name }))} />
          </Field>
          {form.tax_category === 'ISE' && (
            <Field label="Motivo de isenção *" className="sm:col-span-3">
              <Select value={form.exemption_id} onChange={(v) => set('exemption_id', v)} options={meta.exemptions.map((m) => ({ value: m.id, label: m.code + ' - ' + m.name }))} placeholder="Selecionar" singleLine />
            </Field>
          )}
        </div>
        <p className="text-[12px] text-text-muted -mt-2">
          A natureza, não uma taxa: cada empresa recebe a sua própria taxa conforme o seu regime fiscal (ex.: no regime de
          exclusão, o produto fica isento com o motivo do regime).
        </p>

        <Field label="Setores (nenhum = todos os setores)">
          <div className="flex flex-wrap gap-2">
            {meta.sectors.map((s) => {
              const on = form.sectors.includes(s.code);
              return (
                <button key={s.code} type="button" onClick={() => set('sectors', on ? form.sectors.filter((c) => c !== s.code) : [...form.sectors, s.code])}
                  className={'px-3 py-1.5 rounded-md border text-[12px] cursor-pointer transition-colors ' + (on ? 'bg-accent border-accent text-white' : 'border-border text-text-muted hover:text-text-primary')}>
                  {s.name}
                </button>
              );
            })}
          </div>
        </Field>

        <div className="flex flex-col gap-2">
          <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Unidades de venda (ex.: caixa de 6, cartão de 30)</span>
          {form.units.map((u, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 items-center">
              <div className="col-span-4"><Select value={u.unit_of_measure_id} onChange={(v) => setUnit(idx, 'unit_of_measure_id', v)} options={unitOptions} placeholder="Unidade" /></div>
              <input type="number" min="0" step="0.0001" value={u.factor} onChange={(e) => setUnit(idx, 'factor', e.target.value)} placeholder="Contém (ex.: 6)" className={inputClass + ' col-span-2'} />
              <input value={u.barcode} onChange={(e) => setUnit(idx, 'barcode', e.target.value)} placeholder="Código de barras" className={inputClass + ' col-span-3'} />
              <input type="number" min="0" step="0.01" value={u.price} onChange={(e) => setUnit(idx, 'price', e.target.value)} placeholder="Preço" className={inputClass + ' col-span-2'} />
              <button type="button" onClick={() => set('units', form.units.filter((_, i) => i !== idx))} aria-label="Retirar"
                className="col-span-1 w-8 h-8 flex items-center justify-center rounded-md border border-border text-text-muted hover:text-danger hover:border-danger cursor-pointer"><Trash2 size={13} /></button>
            </div>
          ))}
          <button type="button" onClick={() => set('units', [...form.units, { unit_of_measure_id: '', factor: '', barcode: '', price: '' }])}
            className="self-start flex items-center gap-1.5 border border-dashed border-border hover:border-accent text-text-muted hover:text-text-primary text-[12px] rounded-md px-3 py-2 cursor-pointer">
            <Plus size={14} /> Unidade de venda
          </button>
        </div>

        {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{error}</div>}
        <button type="submit" disabled={saving}
          className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
          {saving ? <Loader2 size={17} className="animate-spin" /> : <Save size={17} />}
          {saving ? 'A guardar...' : product ? 'Guardar alterações' : 'Criar produto'}
        </button>
      </form>
    </Modal>
  );
}
