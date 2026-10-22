import { useEffect, useState } from 'react';
import { BookOpen, Check, Download, Loader2, Search } from 'lucide-react';
import Modal from './Modal';
import { listCompanyReferenceCatalog, takeReferenceProducts } from '../api/products';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Artigos > «Importar do catálogo»: the platform's reference products (by default those of the company's sectors and
// of every sector) to tick and take - stock 0, the company's VAT, without price off the Caixa until priced. The ones
// the company has already are shown, never taken twice.

const kz = (v) => (v == null ? null : Number(v).toLocaleString('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Kz');

export default function ReferencePickerModal({ open, onClose, onTaken, units = [] }) {
  const [search, setSearch] = useState('');
  const [scope, setScope] = useState('mine'); // 'mine' | 'all' | a sector code
  const [data, setData] = useState(null);
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(false);
  const [taking, setTaking] = useState(false);

  async function load(offset = 0) {
    setLoading(true);
    try {
      const page = await listCompanyReferenceCatalog({
        q: search, mine: scope === 'mine', sector: scope !== 'mine' && scope !== 'all' ? scope : null, offset,
      });
      setData(page);
      setItems((prev) => (offset ? [...prev, ...page.items] : page.items));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Não foi possível carregar o catálogo'));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { if (open) { setSelected([]); setSearch(''); setScope('mine'); } }, [open]);
  useEffect(() => {
    if (!open) return undefined;
    const timer = setTimeout(() => load(0), 250);
    return () => clearTimeout(timer);
  }, [open, search, scope]); // eslint-disable-line react-hooks/exhaustive-deps

  const unitCode = (id) => units.find((u) => u.id === id)?.code || '';
  const free = items.filter((i) => !i.owned);
  const allTicked = free.length > 0 && free.every((i) => selected.includes(i.id));
  const toggle = (id) => setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  async function take() {
    setTaking(true);
    try {
      const result = await takeReferenceProducts(selected);
      toast.success(result.artigos + (result.artigos === 1 ? ' artigo importado' : ' artigos importados') + ' do catálogo'
        + (result.sem_preco ? ' - ' + result.sem_preco + ' sem preço, fora da Caixa até definir o preço' : '')
        + (result.a_rever ? '; ' + result.a_rever + ' a reclassificar (IVA)' : ''));
      onTaken?.(result);
      onClose();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Não foi possível importar'));
    } finally {
      setTaking(false);
    }
  }

  const scopes = [
    { key: 'mine', label: 'Os meus setores' },
    { key: 'all', label: 'Todos' },
    ...((data?.sectors || []).map((s) => ({ key: s.code, label: s.name }))),
  ];

  return (
    <Modal open={open} onClose={onClose} title="Importar do catálogo de referência" size="full" maxWidthClass="max-w-6xl"
      subtitle="Os produtos que as lojas do seu setor vendem: marque os que quer - entram com stock a zero e o IVA do seu regime">
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative w-full sm:w-80">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nome, código de barras ou categoria..." autoFocus
              className="w-full bg-bg-inset border border-border rounded-md pl-9 pr-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
          </div>
          <div className="flex items-center bg-bg-inset border border-border rounded-md p-0.5 flex-wrap">
            {scopes.map((s) => (
              <button key={s.key} type="button" onClick={() => setScope(s.key)}
                className={'px-3 py-1.5 rounded text-[12px] font-medium transition-colors cursor-pointer ' + (scope === s.key ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}>
                {s.label}
              </button>
            ))}
          </div>
        </div>

        <div className="border border-border rounded-md overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-bg-inset text-[11px] uppercase tracking-wide text-text-muted">
              <tr>
                <th className="px-3 py-2.5 w-8">
                  <input type="checkbox" checked={allTicked} disabled={!free.length} aria-label="Marcar todos"
                    onChange={(e) => setSelected(e.target.checked ? [...new Set([...selected, ...free.map((i) => i.id)])] : selected.filter((id) => !free.some((i) => i.id === id)))} />
                </th>
                <th className="text-left px-3 py-2.5 font-medium">Nome</th>
                <th className="text-left px-3 py-2.5 font-medium">Código de barras</th>
                <th className="text-left px-3 py-2.5 font-medium">Categoria</th>
                <th className="text-left px-3 py-2.5 font-medium">Unidade</th>
                <th className="text-left px-3 py-2.5 font-medium">Embalagens</th>
                <th className="text-right px-3 py-2.5 font-medium">Preço indicativo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {!loading && items.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-text-muted text-[13px]">
                  <BookOpen size={20} className="mx-auto mb-2 opacity-50" />
                  Nenhum produto do catálogo {search ? 'corresponde' : 'para estes setores'}.
                </td></tr>
              )}
              {items.map((i) => (
                <tr key={i.id} className={i.owned ? 'opacity-50' : 'cursor-pointer hover:bg-bg-inset/40'} onClick={() => !i.owned && toggle(i.id)}>
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    {i.owned
                      ? <Check size={14} className="text-success" />
                      : <input type="checkbox" checked={selected.includes(i.id)} onChange={() => toggle(i.id)} aria-label={'Marcar ' + i.name} />}
                  </td>
                  <td className="px-3 py-2 text-[13px] text-text-primary font-medium">
                    {i.name}{i.owned && <span className="ml-2 text-[11px] text-success font-normal">já tem</span>}
                  </td>
                  <td className="px-3 py-2 font-mono text-[12px] text-text-muted">{i.barcode || '-'}</td>
                  <td className="px-3 py-2 text-[12px] text-text-muted">{i.category || '-'}</td>
                  <td className="px-3 py-2 font-mono text-[12px] text-text-primary">{unitCode(i.unit_of_measure_id)}</td>
                  <td className="px-3 py-2 font-mono text-[12px] text-text-muted">{i.units.map((u) => unitCode(u.unit_of_measure_id) + '×' + u.factor).join(', ') || '-'}</td>
                  <td className="px-3 py-2 text-right font-mono text-[12px]">{kz(i.price) || <span className="text-amber-500 [.light_&]:text-amber-700">sem preço</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between gap-3 flex-wrap text-[12px] text-text-muted">
          <span>{items.length} de {data?.total ?? 0} produtos{loading && <Loader2 size={13} className="inline animate-spin ml-2" />}</span>
          {!loading && data && items.length < data.total && (
            <button type="button" onClick={() => load(items.length)} className="border border-border hover:border-accent text-text-primary rounded-md px-3 py-1.5 cursor-pointer">Mostrar mais</button>
          )}
        </div>
        <button type="button" onClick={take} disabled={!selected.length || taking}
          className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
          {taking ? <Loader2 size={17} className="animate-spin" /> : <Download size={17} />}
          {taking ? 'A importar...' : selected.length ? 'Importar ' + selected.length + (selected.length === 1 ? ' produto' : ' produtos') : 'Marque os produtos a importar'}
        </button>
      </div>
    </Modal>
  );
}
