import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';
import { useToastStore, toast } from '../store/toastStore';

// The toasts, top right, above every screen and window: a cross to close, a bar that empties and closes it alone -
// paused while the pointer is over it, to have time to read.

const STYLE = {
  success: { icon: CheckCircle2, ring: 'border-success/50', text: 'text-success', bar: 'bg-success' },
  error: { icon: AlertCircle, ring: 'border-danger/50', text: 'text-danger', bar: 'bg-danger' },
  info: { icon: Info, ring: 'border-accent/50', text: 'text-accent', bar: 'bg-accent' },
};

export default function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  const remove = useToastStore((s) => s.remove);
  return (
    <div className="fixed top-4 right-4 z-[200] flex flex-col gap-2.5 w-[min(380px,calc(100vw-2rem))] pointer-events-none" aria-live="polite">
      {toasts.map((t) => {
        const s = STYLE[t.type] || STYLE.info;
        const Icon = s.icon;
        return (
          <div key={t.id} role={t.type === 'error' ? 'alert' : 'status'}
            className={'toast-item group pointer-events-auto relative overflow-hidden bg-bg-elevated border rounded-lg shadow-2xl ' + s.ring}>
            <div className="flex items-start gap-3 px-4 py-3 pr-10">
              <Icon size={18} className={'shrink-0 mt-0.5 ' + s.text} />
              <p className="text-[13px] text-text-primary leading-snug break-words">{t.message}</p>
            </div>
            <button type="button" onClick={() => remove(t.id)} aria-label="Fechar"
              className="absolute top-2.5 right-2.5 w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-text-primary hover:bg-bg-inset cursor-pointer">
              <X size={14} />
            </button>
            <div className={'toast-bar absolute bottom-0 left-0 h-[3px] ' + s.bar}
              style={{ animationDuration: t.duration + 'ms' }} onAnimationEnd={() => remove(t.id)} />
          </div>
        );
      })}
    </div>
  );
}

// A screen's message state shown as a toast: <Notify error={formError} /> - each new message once, nothing drawn in
// the screen itself.
export function Notify({ error, success, info }) {
  useEffect(() => { if (error) toast.error(error); }, [error]);
  useEffect(() => { if (success) toast.success(success); }, [success]);
  useEffect(() => { if (info) toast.info(info); }, [info]);
  return null;
}

// A screen's message state whose every set shows a toast - the same message set again shows it again (a state that
// keeps its value would not): const [error, setError] = useToastState('error'). The value stays readable (a button
// disabled while there is an error...); nothing is drawn in the screen itself.
export function useToastState(type = 'error', initial = '') {
  const [value, setValue] = useState(initial);
  const current = useRef(initial);
  const set = useCallback((next) => {
    const v = typeof next === 'function' ? next(current.current) : next;
    current.current = v;
    setValue(v);
    if (typeof v === 'string' && v.trim()) toast[type](v);
  }, [type]);
  return [value, set];
}
