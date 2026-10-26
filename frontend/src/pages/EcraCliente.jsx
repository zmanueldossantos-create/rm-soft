import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CheckCircle2, Maximize } from 'lucide-react';
import { API_ORIGIN } from '../api/config';
import { getCustomerDisplay } from '../api/customerDisplay';
import { displayChannelName } from '../utils/customerDisplay';
import { formatKz } from '../utils/format';

// Ecrã do cliente: the till's second monitor, turned to the customer. Read only - no button, nothing to type. It is fed
// by the Caixa of the same PC (utils/customerDisplay.js); with no sale it shows the activity's welcome and pictures.
const DONE_SECONDS = 6;
const SETTINGS_REFRESH_MS = 5 * 60 * 1000;

const url = (path) => (path ? API_ORIGIN + path : null);

export default function EcraCliente() {
  const [params] = useSearchParams();
  const posId = params.get('pos');
  const activityId = params.get('activity');
  const [settings, setSettings] = useState(null);
  const [view, setView] = useState({ type: 'idle' });
  const [slide, setSlide] = useState(0);
  const [fullscreen, setFullscreen] = useState(!!document.fullscreenElement);
  const doneUntil = useRef(0);

  // the activity's welcome and pictures - read again from time to time (the gestor may change them)
  useEffect(() => {
    if (!activityId) return undefined;
    let alive = true;
    const load = () => getCustomerDisplay(activityId).then((d) => { if (alive) setSettings(d); }).catch(() => {});
    load();
    const timer = setInterval(load, SETTINGS_REFRESH_MS);
    return () => { alive = false; clearInterval(timer); };
  }, [activityId]);

  // the Caixa's messages: after a sale, «Obrigado» stays a few seconds (unless the next sale already starts)
  useEffect(() => {
    if (!posId || typeof BroadcastChannel === 'undefined') return undefined;
    const channel = new BroadcastChannel(displayChannelName(posId));
    let back = null;
    channel.onmessage = (event) => {
      const message = event.data || {};
      if (message.type === 'done') {
        doneUntil.current = Date.now() + DONE_SECONDS * 1000;
        setView(message);
        clearTimeout(back);
        back = setTimeout(() => { doneUntil.current = 0; setView({ type: 'idle' }); }, DONE_SECONDS * 1000);
      } else if (message.type === 'idle') {
        if (Date.now() >= doneUntil.current) setView(message);
      } else if (message.type === 'sale') {
        doneUntil.current = 0;
        clearTimeout(back);
        setView(message);
      }
    };
    channel.postMessage({ type: 'hello' });
    return () => { clearTimeout(back); channel.close(); };
  }, [posId]);

  const images = settings?.images || [];
  useEffect(() => {
    if (view.type !== 'idle' || images.length < 2) return undefined;
    const timer = setInterval(() => setSlide((n) => (n + 1) % images.length), (settings?.slide_seconds || 8) * 1000);
    return () => clearInterval(timer);
  }, [view.type, images.length, settings?.slide_seconds]);

  useEffect(() => {
    const onChange = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  if (settings && !settings.allowed) {
    return <Center><p className="text-text-muted text-lg">O ecrã do cliente não está incluído no plano desta empresa.</p></Center>;
  }

  const enterFullscreen = () => document.documentElement.requestFullscreen?.().catch(() => {});
  const welcome = settings?.welcome_message || (settings ? 'Bem-vindo!' : '');

  return (
    <div className="h-screen w-screen overflow-hidden bg-bg-primary text-text-primary select-none cursor-default flex flex-col"
         onDoubleClick={enterFullscreen}>
      <header className="flex items-center gap-4 px-8 py-4 border-b border-border shrink-0">
        {settings?.logo && <img src={url(settings.logo)} alt="" className="h-12 w-auto object-contain" />}
        <div className="min-w-0">
          <p className="text-xl font-semibold truncate">{settings?.company_name}</p>
          <p className="text-sm text-text-muted truncate">{settings?.activity_name}</p>
        </div>
        {!fullscreen && (
          <button type="button" onClick={enterFullscreen}
                  className="ml-auto flex items-center gap-2 text-sm text-text-muted border border-border rounded-md px-3 py-1.5 hover:text-accent hover:border-accent cursor-pointer">
            <Maximize size={15} /> Ecrã inteiro
          </button>
        )}
      </header>

      {view.type === 'sale' && <Sale view={view} />}
      {view.type === 'done' && <Done view={view} />}
      {view.type === 'idle' && (
        <div className="flex-1 min-h-0 flex flex-col">
          <p className="text-center text-3xl md:text-4xl font-semibold px-8 pt-8 pb-6 shrink-0">{welcome}</p>
          <div className="flex-1 min-h-0 relative mx-8 mb-8">
            {images.map((image, n) => (
              <img key={image.id} src={url(image.url)} alt=""
                   className={'absolute inset-0 w-full h-full object-contain transition-opacity duration-1000 ' +
                     (n === slide % images.length ? 'opacity-100' : 'opacity-0')} />
            ))}
            {images.length === 0 && settings?.logo && (
              <img src={url(settings.logo)} alt="" className="absolute inset-0 m-auto max-h-[60%] max-w-[60%] object-contain opacity-80" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Center({ children }) {
  return <div className="h-screen w-screen flex items-center justify-center bg-bg-primary text-center px-8">{children}</div>;
}

function Sale({ view }) {
  const listRef = useRef(null);
  // the last article added is always in sight
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [view.lines.length]);
  return (
    <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[1fr_26rem]">
      <div ref={listRef} className="min-h-0 overflow-y-auto px-8 py-6">
        <table className="w-full text-xl">
          <tbody>
            {view.lines.map((line) => (
              <tr key={line.key} className="border-b border-border/60">
                <td className="py-3 pr-4 font-mono text-text-muted whitespace-nowrap align-top">
                  {formatQuantity(line.quantity)}{line.unit && line.unit !== 'UN' && line.unit !== 'Un' ? ' ' + line.unit : ''} ×
                </td>
                <td className="py-3 pr-4 w-full">{line.name}</td>
                <td className="py-3 text-right font-mono whitespace-nowrap align-top">{formatKz(line.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <aside className="bg-bg-elevated border-l border-border px-8 py-8 flex flex-col justify-end gap-4">
        {view.discount > 0 && <Row label="Desconto" value={'-' + formatKz(view.discount) + ' Kz'} />}
        {view.retention > 0 && <Row label="Retenção" value={'-' + formatKz(view.retention) + ' Kz'} />}
        <div>
          <p className="text-text-muted uppercase tracking-wide text-sm">Total a pagar</p>
          <p className="text-5xl font-bold font-mono mt-1 break-all">{formatKz(view.total)} <span className="text-2xl">Kz</span></p>
        </div>
        {view.received > 0 && (
          <div className="border-t border-border pt-4 space-y-2">
            <Row label="Recebido" value={formatKz(view.received) + ' Kz'} />
            {view.change > 0 && (
              <div className="flex items-baseline justify-between gap-4 text-success">
                <span className="text-xl font-semibold">Troco</span>
                <span className="text-4xl font-bold font-mono">{formatKz(view.change)} Kz</span>
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

function Done({ view }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-5 text-center px-8">
      <CheckCircle2 size={88} className="text-success" />
      <p className="text-5xl font-bold">Obrigado pela preferência!</p>
      {view.change > 0 && <p className="text-3xl">Troco: <span className="font-mono font-bold text-success">{formatKz(view.change)} Kz</span></p>}
      {view.document && <p className="text-text-muted text-lg font-mono">{view.document}</p>}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-xl">
      <span className="text-text-muted">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}

function formatQuantity(quantity) {
  const n = Number(quantity) || 0;
  return Number.isInteger(n) ? String(n) : n.toLocaleString('pt-PT', { maximumFractionDigits: 3 });
}
