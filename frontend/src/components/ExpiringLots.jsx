import { Trash2 } from 'lucide-react';

const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3';
const qty = (v) => Number(v || 0).toLocaleString('pt-PT', { maximumFractionDigits: 3 });
const day = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('pt-PT');

function State({ lot }) {
  if (lot.expired) {
    const ago = -lot.days_left;
    return (
      <span className="inline-flex bg-danger/10 text-danger text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded">
        {ago === 0 ? 'Expirou hoje' : ago === 1 ? 'Expirou ontem' : 'Expirou há ' + ago + ' dias'}
      </span>
    );
  }
  const text = lot.days_left === 0 ? 'Expira hoje' : lot.days_left === 1 ? 'Expira amanhã' : 'Expira em ' + lot.days_left + ' dias';
  return <span className="inline-flex bg-amber-500/10 text-amber-500 text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded">{text}</span>;
}

// Stock > Validades: the lots expired (never sold - to write off) and the lots expiring within the company's alert days,
// in every warehouse, the first to expire first. "Registar perda" opens the loss already filled for that lot.
export default function ExpiringLots({ data, search, canLoss, onWriteOff }) {
  const q = (search || '').trim().toLowerCase();
  const lots = (data?.lots || []).filter((l) => !q || (l.product_code + ' ' + l.product_name + ' ' + (l.lot_number || '')).toLowerCase().includes(q));
  if (!data) return null;
  return (
    <div>
      <p className="px-6 py-3 text-[12px] text-text-muted border-b border-border">
        Lotes expirados e lotes que expiram nos próximos <span className="font-mono text-text-primary">{data.alert_days}</span> dias (Configurações → Empresa), em todos os armazéns.
        Um lote expirado nunca é vendido: registe a perda.
      </p>
      {lots.length === 0 ? (
        <p className="text-center py-14 text-text-muted text-sm">{q ? 'Nenhum lote encontrado' : 'Nenhum lote expirado ou a expirar'}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[860px]">
            <thead><tr className="border-b border-border">
              <th className={th + ' text-left'}>Produto</th><th className={th + ' text-left'}>Armazém</th><th className={th + ' text-left'}>Lote</th>
              <th className={th + ' text-left'}>Validade</th><th className={th + ' text-right'}>Quantidade</th><th className={th + ' text-left'}>Estado</th>
              <th className={th + ' text-right'}>Ações</th>
            </tr></thead>
            <tbody>
              {lots.map((l) => (
                <tr key={l.id} className={'border-b border-border last:border-0 ' + (l.expired ? 'bg-danger/5' : '')}>
                  <td className="px-6 py-3.5"><span className="font-mono text-text-muted text-[12px] mr-2">{l.product_code}</span><span className="font-display font-medium text-text-primary">{l.product_name}</span></td>
                  <td className="px-6 py-3.5 text-text-primary">{l.warehouse_name}{l.location_code && <span className="block font-mono text-[11px] text-text-muted">Localização {l.location_code}</span>}</td>
                  <td className="px-6 py-3.5 font-mono text-text-primary">{l.lot_number || '-'}</td>
                  <td className="px-6 py-3.5 font-mono text-text-muted">{day(l.expiry_date)}</td>
                  <td className="px-6 py-3.5 font-mono text-text-primary text-right whitespace-nowrap">{qty(l.quantity)} <span className="text-[11px] text-text-muted">{l.unit_code}</span></td>
                  <td className="px-6 py-3.5"><State lot={l} /></td>
                  <td className="px-6 py-3.5 text-right">
                    {canLoss && (
                      <button type="button" onClick={() => onWriteOff(l)} className="inline-flex items-center gap-1.5 text-[12px] border border-border hover:border-danger hover:text-danger text-text-primary px-2.5 py-1 rounded-md cursor-pointer">
                        <Trash2 size={13} /> Registar perda
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
