import { useEffect, useRef, useState } from 'react';
import { ChefHat, Loader2, Volume2, VolumeX, Play, Check, Ban, Minus } from 'lucide-react';
import { useCan } from '../utils/permissions';
import { extractErrorMessage } from '../utils/errors';
import { getKitchenBoard, kitchenLineAction, kitchenOrderAction } from '../api/kitchen';

// The kitchen screen (point 34c): one card per order sent from an open account - number of the day, table, sender,
// time and minutes elapsed - and its dishes, moved forward dish by dish or card by card. Refreshed every 15 s;
// a beep announces each new order (switchable, remembered on this device).
const STATUS_LABEL = { EM_ESPERA: 'Em espera', EM_PREPARACAO: 'Em preparacao', PRONTO: 'Pronto', ANULADO: 'Anulado' };
const STATUS_STYLE = {
  EM_ESPERA: 'text-sky-400 bg-sky-400/10',
  EM_PREPARACAO: 'text-amber-500 bg-amber-500/10',
  PRONTO: 'text-success bg-success/10',
  ANULADO: 'text-danger bg-danger/10',
};
const ACTIVE = ['EM_ESPERA', 'EM_PREPARACAO'];
const LATE_MINUTES = 20;
const REFRESH_MS = 15000;
const SOUND_KEY = 'rm.kitchen.sound';

function readSound() {
  try { return localStorage.getItem(SOUND_KEY) !== 'off'; } catch { return true; }
}
function saveSound(on) {
  try { localStorage.setItem(SOUND_KEY, on ? 'on' : 'off'); } catch { /* this device keeps no preference */ }
}
function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 880;
    gain.gain.value = 0.25;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.4);
    osc.onended = () => ctx.close();
  } catch { /* no sound on this device */ }
}
function formatTime(value) {
  return new Date(value).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' });
}
function formatQty(q) {
  const n = Number(q);
  return Number.isInteger(n) ? String(n) : n.toLocaleString('pt-PT', { maximumFractionDigits: 3 });
}

export default function Cozinha() {
  const can = useCan();
  const canUpdate = can('kitchen:update');
  const [board, setBoard] = useState({ orders: [], recent: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null);
  const [soundOn, setSoundOn] = useState(readSound);
  const [activityFilter, setActivityFilter] = useState('');
  const [confirmRefuse, setConfirmRefuse] = useState(null);
  const [now, setNow] = useState(Date.now());
  const knownOrders = useRef(null);
  const soundRef = useRef(soundOn);
  soundRef.current = soundOn;

  function apply(data) {
    const ids = new Set(data.orders.map((o) => o.id));
    if (knownOrders.current && soundRef.current && data.orders.some((o) => !knownOrders.current.has(o.id))) beep();
    knownOrders.current = ids;
    setBoard(data);
  }

  async function load() {
    try {
      apply(await getKitchenBoard());
      setError('');
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar a cozinha'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const refresh = setInterval(load, REFRESH_MS);
    const clock = setInterval(() => setNow(Date.now()), 30000);
    return () => { clearInterval(refresh); clearInterval(clock); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function lineAction(line, action, quantity = null) {
    setBusy(line.id);
    setError('');
    try {
      apply(await kitchenLineAction(line.id, action, quantity));
      setConfirmRefuse(null);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar o prato'));
    } finally {
      setBusy(null);
    }
  }

  async function orderAction(order, action) {
    setBusy(order.id);
    setError('');
    try {
      apply(await kitchenOrderAction(order.id, action));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar o pedido'));
    } finally {
      setBusy(null);
    }
  }

  function toggleSound() {
    const next = !soundOn;
    setSoundOn(next);
    saveSound(next);
    if (next) beep(); // also unlocks the sound on browsers that wait for a first touch
  }

  const activities = [...new Set(board.orders.map((o) => o.activity_name))];
  const orders = activityFilter ? board.orders.filter((o) => o.activity_name === activityFilter) : board.orders;
  const chip = (active) => 'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer '
    + (active ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary');

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
          <ChefHat size={22} className="text-accent" />
          Cozinha
        </h2>
        <button
          type="button"
          onClick={toggleSound}
          title={soundOn ? 'Desligar o som' : 'Ligar o som'}
          className="flex items-center gap-2 border border-border hover:border-accent text-text-primary text-sm rounded-md px-3 py-2 transition-colors cursor-pointer"
        >
          {soundOn ? <Volume2 size={16} className="text-accent" /> : <VolumeX size={16} className="text-text-muted" />}
          {soundOn ? 'Som ligado' : 'Som desligado'}
        </button>
      </div>
      <p className="text-text-muted text-sm mb-6">Pedidos enviados pela sala - atualizado a cada 15 segundos</p>

      {activities.length > 1 && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <button type="button" onClick={() => setActivityFilter('')} className={chip(!activityFilter)}>Todas</button>
          {activities.map((a) => (
            <button key={a} type="button" onClick={() => setActivityFilter(a)} className={chip(activityFilter === a)}>{a}</button>
          ))}
        </div>
      )}

      {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : orders.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <ChefHat size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium mb-1">Nenhum pedido em curso</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {orders.map((o) => {
            const minutes = Math.max(0, Math.floor((now - new Date(o.sent_at).getTime()) / 60000));
            const late = minutes >= LATE_MINUTES;
            const waiting = o.lines.some((l) => l.status === 'EM_ESPERA');
            const inKitchen = o.lines.some((l) => ACTIVE.includes(l.status));
            return (
              <div key={o.id} className={'bg-bg-elevated border rounded-lg p-4 flex flex-col gap-3 ' + (late ? 'border-danger/60' : 'border-border')}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-display font-semibold text-text-primary text-[16px] truncate">#{o.number} - {o.account_label}</p>
                    <p className="text-text-muted text-[11px] font-mono truncate">
                      {activities.length > 1 ? o.activity_name + ' - ' : ''}{o.sent_by_name} - {formatTime(o.sent_at)}
                    </p>
                  </div>
                  <span className={'font-mono text-[13px] font-semibold shrink-0 ' + (late ? 'text-danger' : 'text-text-muted')}>{minutes} min</span>
                </div>

                <div className="flex flex-col gap-1.5">
                  {o.lines.map((l) => {
                    const active = ACTIVE.includes(l.status);
                    return (
                      <div key={l.id} className="bg-bg-inset border border-border rounded-md px-3 py-2">
                        <div className="flex items-start justify-between gap-2">
                          <p className={'text-[13px] ' + (l.status === 'ANULADO' ? 'text-text-muted line-through' : 'text-text-primary font-medium')}>
                            {formatQty(l.quantity)}{l.unit_code && l.unit_code !== 'UN' ? ' ' + l.unit_code : ''} x {l.name}
                          </p>
                          <span className={'text-[10px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ' + (STATUS_STYLE[l.status] || '')}>{STATUS_LABEL[l.status] || l.status}</span>
                        </div>
                        {(l.modified && l.status !== 'ANULADO') && <p className="text-amber-500 text-[11px] font-semibold mt-0.5">Modificado</p>}
                        {l.cancel_reason && <p className="text-danger text-[11px] mt-0.5">{l.cancel_reason}</p>}
                        {l.account_label && l.account_label !== o.account_label && (
                          <p className="text-sky-400 text-[12px] font-semibold mt-0.5">Servir em: {l.account_label}</p>
                        )}
                        {active && canUpdate && (
                          <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                            {l.status === 'EM_ESPERA' && (
                              <button type="button" disabled={busy === l.id} onClick={() => lineAction(l, 'start')} className="flex items-center gap-1 border border-border hover:border-accent text-text-primary text-[12px] rounded px-2 py-1 cursor-pointer disabled:opacity-50">
                                <Play size={12} /> Comecar
                              </button>
                            )}
                            <button type="button" disabled={busy === l.id} onClick={() => lineAction(l, 'ready')} className="flex items-center gap-1 bg-success/15 border border-success/40 hover:border-success text-success text-[12px] rounded px-2 py-1 cursor-pointer disabled:opacity-50">
                              <Check size={12} /> Pronto
                            </button>
                            {l.quantity > 1 && (
                              <button type="button" disabled={busy === l.id} onClick={() => lineAction(l, 'quantity', l.quantity - 1)} title="Baixar a quantidade" className="flex items-center border border-border hover:border-accent text-text-muted text-[12px] rounded px-1.5 py-1 cursor-pointer disabled:opacity-50">
                                <Minus size={12} />
                              </button>
                            )}
                            <button
                              type="button"
                              disabled={busy === l.id}
                              onClick={() => (confirmRefuse === l.id ? lineAction(l, 'refuse') : setConfirmRefuse(l.id))}
                              className={'flex items-center gap-1 text-[12px] rounded px-2 py-1 cursor-pointer disabled:opacity-50 ml-auto ' + (confirmRefuse === l.id ? 'bg-danger text-white' : 'border border-danger/40 hover:border-danger text-danger')}
                            >
                              <Ban size={12} /> {confirmRefuse === l.id ? 'Confirmar esgotado' : 'Esgotado'}
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {canUpdate && inKitchen && (
                  <div className="flex items-stretch gap-2">
                    {waiting && (
                      <button type="button" disabled={busy === o.id} onClick={() => orderAction(o, 'start_all')} className="flex-1 flex items-center justify-center gap-1.5 border border-border hover:border-accent text-text-primary text-sm rounded-md py-2 cursor-pointer disabled:opacity-50">
                        <Play size={14} /> Comecar tudo
                      </button>
                    )}
                    <button type="button" disabled={busy === o.id} onClick={() => orderAction(o, 'ready_all')} className="flex-1 flex items-center justify-center gap-1.5 bg-success hover:opacity-90 text-white font-semibold text-sm rounded-md py-2 cursor-pointer disabled:opacity-50">
                      <Check size={14} /> Tudo pronto
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {board.recent.length > 0 && (
        <div className="mt-8">
          <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-2">Prontos recentes</p>
          <div className="flex gap-2 flex-wrap">
            {board.recent.map((o) => (
              <div key={o.id} className="bg-bg-elevated border border-border rounded-md px-3 py-2 text-[12px]">
                <span className="font-semibold text-text-primary">#{o.number} - {o.account_label}</span>
                <span className="text-text-muted font-mono"> - {formatTime(o.sent_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
