import { useEffect, useState } from 'react';
import { getReclassification, reclassifyArticles } from '../api/vat';
import { extractErrorMessage } from '../utils/errors';
import Modal from './Modal';

// Grouped VAT reclassification of products or services (kind = 'products' | 'services'): the banner of the articles
// left behind by a regime change (they cannot be sold until reclassified), the action bar of the selection, and the
// modal that gives the selected articles one rate - and its motive, or the one the regime imposes.
export default function VatReclassify({ kind, selectedIds, setSelectedIds, vatRates, vatCodes, articleVatRule, onDone }) {
  const [pending, setPending] = useState([]);
  const [open, setOpen] = useState(false);
  const [vatId, setVatId] = useState('');
  const [motiveId, setMotiveId] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  function loadPending() {
    getReclassification().then((d) => setPending((d && d[kind]) || [])).catch(() => setPending([]));
  }
  useEffect(() => { loadPending(); }, [kind]);

  const vat = vatRates.find((v) => v.id === vatId);
  const isExempt = !!vat && vat.tax_category === 'ISE';
  const imposed = isExempt ? articleVatRule?.exemption : null;
  const canApply = vatId && (!isExempt || imposed || motiveId) && !saving;
  const label = kind === 'products' ? 'produtos' : 'servi\u00e7os';
  const field = 'w-full rounded-lg border border-border bg-bg-inset px-3 py-2 text-[13px] text-text-primary';

  async function apply() {
    setSaving(true);
    setError('');
    try {
      await reclassifyArticles({
        product_ids: kind === 'products' ? selectedIds : [],
        service_ids: kind === 'services' ? selectedIds : [],
        vat_id: vatId,
        exemption_reason_id: isExempt && !imposed ? motiveId || null : null,
      });
      setOpen(false);
      setSelectedIds([]);
      setVatId('');
      setMotiveId('');
      loadPending();
      if (onDone) onDone();
    } catch (e) {
      setError(extractErrorMessage(e, 'Erro ao reclassificar'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {pending.length > 0 && (
        <div className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2.5 text-[13px] text-amber-500">
          <span>{pending.length + ' ' + label + ' a reclassificar (IVA) ap\u00f3s a mudan\u00e7a de regime \u2013 n\u00e3o podem ser vendidos at\u00e9 l\u00e1.'}</span>
          <button type="button" onClick={() => setSelectedIds(pending.map((a) => a.id))} className="shrink-0 rounded-md border border-amber-500/50 px-3 py-1 text-[12px] font-medium hover:bg-amber-500/20 cursor-pointer">Selecionar</button>
        </div>
      )}
      {selectedIds.length > 0 && (
        <div className="mb-3 flex items-center gap-3 rounded-lg border border-border bg-bg-elevated px-4 py-2 text-[13px] text-text-primary">
          <span>{selectedIds.length + ' selecionado(s)'}</span>
          <button type="button" onClick={() => setOpen(true)} className="rounded-md bg-accent px-3 py-1 text-[12px] font-medium text-white cursor-pointer">Reclassificar IVA</button>
          <button type="button" onClick={() => setSelectedIds([])} className="text-[12px] text-text-muted hover:text-text-primary cursor-pointer">Limpar</button>
        </div>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="Reclassificar IVA">
        <div className="flex flex-col gap-4">
          <p className="text-[13px] text-text-muted">{selectedIds.length + ' ' + label + ' v\u00e3o receber esta taxa de IVA.'}</p>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Taxa de IVA *</label>
            <select value={vatId} onChange={(e) => { setVatId(e.target.value); setMotiveId(''); }} className={field}>
              <option value="">Selecionar</option>
              {vatRates.filter((v) => v.is_active !== false).map((v) => <option key={v.id} value={v.id}>{v.name + ' (' + v.rate + '%)'}</option>)}
            </select>
          </div>
          {isExempt && (
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{'Motivo de isen\u00e7\u00e3o *'}</label>
              {imposed ? (
                <>
                  <div className={field + ' opacity-80 cursor-not-allowed truncate'}>{imposed.code + ' - ' + imposed.name}</div>
                  <p className="text-[11px] text-text-muted mt-1">{'Imposto pelo ' + (articleVatRule.regime || 'regime da empresa')}</p>
                </>
              ) : (
                <select value={motiveId} onChange={(e) => setMotiveId(e.target.value)} className={field}>
                  <option value="">Selecionar motivo</option>
                  {vatCodes.map((c) => <option key={c.id} value={c.id}>{c.code + ' - ' + c.name}</option>)}
                </select>
              )}
            </div>
          )}
          {error && <p className="text-[12px] text-danger">{error}</p>}
          <button type="button" disabled={!canApply} onClick={apply} className="rounded-lg bg-accent px-4 py-2.5 text-[13px] font-medium text-white disabled:opacity-50 cursor-pointer">{saving ? 'A aplicar...' : 'Aplicar'}</button>
        </div>
      </Modal>
    </>
  );
}
