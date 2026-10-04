import { useEffect, useRef, useState } from 'react';
import { Calendar } from 'lucide-react';

// THE date field of the app: always DD/MM/YYYY, whatever the browser's language - the native field followed it, so a
// browser set to English showed MM/DD/YYYY and turned '09/01' into 9 January. Value in and out: 'YYYY-MM-DD', and
// onChange gets { target: { value } } like a native input, so it replaces <input type="date"> as is. An incomplete,
// impossible (31/02) or out-of-bounds (min / max) date is never sent: the field turns red instead.
function isoToText(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return '';
  const [y, m, d] = iso.split('-');
  return d + '/' + m + '/' + y;
}

function textToIso(text) {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text);
  if (!match) return null;
  const [, d, m, y] = match;
  const dt = new Date(Number(y), Number(m) - 1, Number(d));
  if (dt.getFullYear() !== Number(y) || dt.getMonth() !== Number(m) - 1 || dt.getDate() !== Number(d)) return null;
  return y + '-' + m + '-' + d;
}

function mask(raw) {
  const digits = raw.replace(/\D/g, '').slice(0, 8);
  let out = digits.slice(0, 2);
  if (digits.length > 2) out += '/' + digits.slice(2, 4);
  if (digits.length > 4) out += '/' + digits.slice(4);
  return out;
}

export default function DateInput({ value, onChange, min, max, required, readOnly, disabled, className = '', ...rest }) {
  const [text, setText] = useState(isoToText(value));
  const [invalid, setInvalid] = useState(false);
  const pickerRef = useRef(null);

  useEffect(() => {
    setText(isoToText(value));
    setInvalid(false);
  }, [value]);

  function emit(iso) {
    if (onChange) onChange({ target: { value: iso } });
  }

  function handleText(e) {
    const next = mask(e.target.value);
    setText(next);
    if (next === '') {
      setInvalid(false);
      if (value) emit('');
      return;
    }
    const iso = textToIso(next);
    if (!iso) {
      setInvalid(next.length === 10);
      return;
    }
    if ((min && iso < min) || (max && iso > max)) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    if (iso !== value) emit(iso);
  }

  function openPicker() {
    const el = pickerRef.current;
    if (!el || readOnly || disabled) return;
    try {
      el.showPicker();
    } catch {
      el.focus();
      el.click();
    }
  }

  return (
    <div className="relative">
      <input
        {...rest}
        type="text"
        inputMode="numeric"
        placeholder="DD/MM/AAAA"
        value={text}
        onChange={handleText}
        required={required}
        readOnly={readOnly}
        disabled={disabled}
        className={className + ' pr-9'}
        style={invalid ? { borderColor: 'var(--color-danger, #e5484d)' } : undefined}
        title={invalid ? 'Data inv\u00e1lida ou fora do intervalo permitido' : rest.title}
      />
      <button
        type="button"
        tabIndex={-1}
        onClick={openPicker}
        disabled={readOnly || disabled}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary cursor-pointer disabled:cursor-default"
        aria-label="Abrir calend\u00e1rio"
      >
        <Calendar size={15} />
      </button>
      <input
        ref={pickerRef}
        type="date"
        value={value || ''}
        min={min}
        max={max}
        onChange={(e) => { if (e.target.value) emit(e.target.value); }}
        tabIndex={-1}
        aria-hidden="true"
        className="absolute right-2 bottom-0 w-px h-px opacity-0 pointer-events-none"
      />
    </div>
  );
}
