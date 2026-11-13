// The Painel's blocks (Dashboard.jsx): each one shows a part of the summary (dashboard_service) and is only rendered
// when the server sent it - a block the user may not see never arrives.
import { useState } from 'react';
import { formatKz } from '../utils/format';
import { Link } from 'react-router-dom';
import { qtyWithUnit } from '../utils/stockUnits';

export function formatMoney(value) {
  return formatKz(value) + ' Kz';
}

const shortKz = (value) => formatKz(Math.round(value || 0)).slice(0, -3);  // 12 500 (no decimals)

// A titled box; «to» puts a «Ver tudo» link to the full screen in its header.
export function Block({ icon: Icon, title, to, tone = 'text-accent', children, className = '' }) {
  return (
    <div className={'bg-bg-elevated border border-border rounded-lg overflow-hidden flex flex-col ' + className}>
      <div className="px-5 py-3.5 border-b border-border flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-2">
          {Icon && <Icon size={15} className={tone} />}{title}
        </p>
        {to && <Link to={to} className="text-[12px] text-accent hover:text-accent-hover">Ver tudo</Link>}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );
}

export function Empty({ children }) {
  return <div className="text-center py-10 text-text-muted text-sm px-4">{children}</div>;
}

// One figure with its label and a line under it (a comparison, what is late).
export function Kpi({ icon: Icon, label, value, sub, subTone = 'text-text-muted', valueTone = 'text-text-primary' }) {
  return (
    <div className="bg-bg-elevated border border-border rounded-lg p-5">
      <div className="flex items-center gap-2 text-text-muted text-[11px] uppercase tracking-wide mb-2">
        {Icon && <Icon size={13} className="text-accent" />}{label}
      </div>
      <p className={'font-display font-semibold text-2xl ' + valueTone}>{value}</p>
      {sub && <p className={'text-[12px] mt-1 ' + subTone}>{sub}</p>}
    </div>
  );
}

// The day compared with yesterday: «+12 % face a ontem», or what yesterday made when today is still empty.
export function versusYesterday(today, yesterday) {
  if (!yesterday) return { text: today ? 'Sem vendas ontem' : 'Ainda sem vendas hoje', tone: 'text-text-muted' };
  const pct = Math.round(((today - yesterday) / yesterday) * 100);
  return { text: (pct >= 0 ? '+' : '') + pct + ' % face a ontem (' + shortKz(yesterday) + ' Kz)', tone: pct >= 0 ? 'text-success' : 'text-danger' };
}

// The last 30 days as bars - one per day, today last and highlighted; the value on hover.
export function SalesChart({ days }) {
  const max = Math.max(...days.map((d) => d.total), 0);
  const total = days.reduce((t, d) => t + d.total, 0);
  const W = 600, H = 150, gap = 3, barW = (W - gap * (days.length - 1)) / days.length;
  const label = (iso) => { const [, m, d] = iso.split('-'); return d + '/' + m; };
  return (
    <div className="px-5 py-4">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <p className="font-mono text-[18px] text-text-primary">{formatMoney(total)}</p>
        <p className="text-[12px] text-text-muted">Média por dia {formatMoney(total / days.length)}</p>
      </div>
      {max <= 0 ? <Empty>Sem vendas nos últimos 30 dias</Empty> : (
        <svg viewBox={"0 0 " + W + " " + (H + 12)} className="w-full h-auto" role="img" aria-label="Vendas dos últimos 30 dias">
          <line x1="0" y1={H} x2={W} y2={H} className="stroke-border" strokeWidth="1" />
          {days.map((d, i) => {
            const h = d.total > 0 ? Math.max(2, (d.total / max) * (H - 6)) : 0;
            const last = i === days.length - 1;
            return (
              <g key={d.date}>
                <rect x={i * (barW + gap)} y={H - h} width={barW} height={h} rx="2"
                  className={last ? 'fill-accent' : 'fill-accent/40 hover:fill-accent/70'}>
                  <title>{label(d.date) + ': ' + formatMoney(d.total)}</title>
                </rect>
              </g>
            );
          })}
          <text x="0" y={H + 10} className="fill-text-muted" fontSize="7">{label(days[0].date)}</text>
          <text x={W} y={H + 10} textAnchor="end" className="fill-text-muted" fontSize="7">Hoje</text>
        </svg>
      )}
    </div>
  );
}

// Received today, by payment method: the amount and its share.
export function PaymentsToday({ payments }) {
  const total = payments.reduce((t, p) => t + p.amount, 0);
  if (!payments.length) return <Empty>Nada recebido hoje</Empty>;
  return (
    <div className="px-5 py-4 flex flex-col gap-3">
      {payments.map((p) => (
        <div key={p.method}>
          <div className="flex items-center justify-between text-[13px] mb-1">
            <span className="text-text-primary">{p.method}</span>
            <span className="font-mono text-text-primary">{formatMoney(p.amount)}</span>
          </div>
          <div className="h-1.5 rounded bg-bg-inset overflow-hidden">
            <div className={'h-full rounded ' + (p.is_cash ? 'bg-success' : 'bg-accent')} style={{ width: Math.max(2, (p.amount / total) * 100) + '%' }} />
          </div>
        </div>
      ))}
      <div className="flex items-center justify-between border-t border-border pt-2.5 text-[13px]">
        <span className="text-text-muted">Total recebido</span>
        <span className="font-mono font-semibold text-text-primary">{formatMoney(total)}</span>
      </div>
    </div>
  );
}

// The best sellers of the day or of the month.
export function TopProducts({ today, month }) {
  const [period, setPeriod] = useState('today');
  const rows = period === 'today' ? today : month;
  return (
    <div className="flex flex-col">
      <div className="flex gap-1 px-5 pt-3">
        {[['today', 'Hoje'], ['month', 'Este mês']].map(([key, label]) => (
          <button key={key} type="button" onClick={() => setPeriod(key)}
            className={'px-2.5 py-1 rounded text-[12px] font-medium cursor-pointer ' + (period === key ? 'bg-accent/15 text-accent' : 'text-text-muted hover:text-text-primary')}>
            {label}
          </button>
        ))}
      </div>
      {!rows.length ? <Empty>Sem vendas {period === 'today' ? 'hoje' : 'este mês'}</Empty> : (
        <div className="divide-y divide-border">
          {rows.map((p, i) => (
            <div key={p.name + i} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm">
              <div className="flex items-center gap-3 min-w-0">
                <span className="font-mono text-[12px] text-text-muted w-4">{i + 1}</span>
                <div className="min-w-0">
                  <p className="text-text-primary truncate">{p.name}</p>
                  <p className="text-[12px] font-mono text-text-muted">{qtyWithUnit(p.quantity, p.unit_code)}</p>
                </div>
              </div>
              <p className="font-mono text-text-primary whitespace-nowrap">{formatMoney(p.total)}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Each till: open (who, the cash it should hold) or closed (its last closing and its difference).
export function Tills({ tills }) {
  if (!tills.length) return <Empty>Nenhuma caixa usada ainda</Empty>;
  const time = (iso) => (iso ? new Date(iso).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '');
  return (
    <div className="divide-y divide-border">
      {tills.map((t) => (
        <div key={t.name} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
          <div className="min-w-0">
            <p className="text-text-primary flex items-center gap-2">
              {t.name}
              <span className={'text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ' + (t.open ? 'bg-success/10 text-success' : 'bg-text-muted/10 text-text-muted')}>
                {t.open ? 'Aberta' : 'Fechada'}
              </span>
            </p>
            <p className="text-[12px] text-text-muted truncate">
              {t.open ? (t.user || '') + ' · desde ' + time(t.opened_at) : 'Fecho ' + time(t.closed_at)}
            </p>
          </div>
          <div className="text-right whitespace-nowrap">
            <p className="font-mono text-text-primary">{formatMoney(t.cash)}</p>
            <p className="text-[11px] text-text-muted">
              {t.open ? 'na gaveta' : t.difference ? <span className={t.difference < 0 ? 'text-danger' : 'text-amber-500'}>diferença {formatMoney(t.difference)}</span> : 'contado, sem diferença'}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

// Low stock: one row per product, each warehouse where it is at or under its minimum; raw materials can be hidden.
export function LowStock({ products }) {
  const [hideRaw, setHideRaw] = useState(false);
  const rows = products.filter((p) => !(hideRaw && p.is_raw_material));
  return (
    <div className="flex flex-col">
      {products.some((p) => p.is_raw_material) && (
        <label className="flex items-center gap-2 px-5 pt-3 text-[12px] text-text-muted cursor-pointer select-none">
          <input type="checkbox" checked={hideRaw} onChange={(e) => setHideRaw(e.target.checked)} className="w-3.5 h-3.5 accent-accent cursor-pointer" />
          Ocultar matérias-primas
        </label>
      )}
      {!rows.length ? <Empty>Nenhum produto em alerta</Empty> : (
        <div className="divide-y divide-border">
          {rows.map((p) => (
            <div key={p.code} className="px-5 py-2.5 text-sm">
              <div className="flex items-center gap-2">
                <p className="text-text-primary">{p.name}</p>
                {p.is_raw_material && <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted bg-bg-inset px-1.5 py-0.5 rounded">MP</span>}
                <span className="text-[11px] font-mono text-text-muted">{p.code}</span>
              </div>
              {p.warehouses.map((w) => (
                <div key={w.name} className="flex items-center justify-between text-[12px] mt-0.5">
                  <span className="text-text-muted">{w.name}</span>
                  <span className="font-mono text-danger">{qtyWithUnit(w.quantity, p.unit_code)} <span className="text-text-muted">/ mín. {qtyWithUnit(p.min_stock_threshold, p.unit_code)}</span></span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// The lots that expire soonest (or have expired - never sold).
export function Expiring({ data }) {
  if (!data.lots.length) return <Empty>Nenhum lote a expirar nos próximos {data.alert_days} dias</Empty>;
  return (
    <div className="divide-y divide-border">
      {data.lots.map((l, i) => (
        <div key={i} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm">
          <div className="min-w-0">
            <p className="text-text-primary truncate">{l.product_name}</p>
            <p className="text-[12px] text-text-muted truncate">{l.warehouse_name} · {qtyWithUnit(l.quantity, l.unit_code)}</p>
          </div>
          <span className={'text-[11px] font-semibold px-2 py-0.5 rounded whitespace-nowrap ' + (l.expired ? 'bg-danger/10 text-danger' : l.days_left <= 2 ? 'bg-amber-500/10 text-amber-500' : 'bg-text-muted/10 text-text-muted')}>
            {l.expired ? 'Expirado' : l.days_left === 0 ? 'Expira hoje' : 'Faltam ' + l.days_left + ' d'}
          </span>
        </div>
      ))}
    </div>
  );
}

// What was made today and what it cost.
export function ProductionToday({ data }) {
  if (!data.count) return <Empty>Nenhuma produção hoje</Empty>;
  return (
    <div className="flex flex-col">
      <div className="divide-y divide-border">
        {data.items.map((item, i) => (
          <div key={i} className="flex items-center justify-between px-5 py-2.5 text-sm">
            <span className="text-text-primary">{item.name}</span>
            <span className="font-mono text-accent">+{qtyWithUnit(item.quantity, item.unit_code)}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between border-t border-border px-5 py-2.5 text-[13px]">
        <span className="text-text-muted">{data.count} produção(ões) · custo</span>
        <span className="font-mono font-semibold text-text-primary">{formatMoney(data.cost)}</span>
      </div>
    </div>
  );
}

const DOC_SHORT = { FACTURA: 'FT', FACTURA_RECIBO: 'FR', NOTA_CREDITO: 'NC', NOTA_DEBITO: 'ND', RECIBO: 'RC' };

// The last sales documents (never a pro-forma): number, type, customer, total.
export function RecentDocuments({ invoices }) {
  if (!invoices.length) return <Empty>Nenhuma venda emitida ainda</Empty>;
  return (
    <div className="divide-y divide-border">
      {invoices.map((inv) => (
        <div key={inv.id} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm">
          <div className="min-w-0">
            <p className="text-text-primary flex items-center gap-2">
              <span className="text-[10px] font-semibold font-mono px-1.5 py-0.5 rounded bg-bg-inset text-text-muted">{DOC_SHORT[inv.invoice_type] || inv.invoice_type}</span>
              {inv.series}/{inv.number}
            </p>
            <p className="text-[12px] text-text-muted truncate">{inv.customer_name || 'Consumidor final'}</p>
          </div>
          <p className={'font-mono whitespace-nowrap ' + (inv.invoice_type === 'NOTA_CREDITO' ? 'text-danger' : 'text-text-primary')}>
            {inv.invoice_type === 'NOTA_CREDITO' ? '-' : ''}{formatMoney(inv.total)}
          </p>
        </div>
      ))}
    </div>
  );
}
