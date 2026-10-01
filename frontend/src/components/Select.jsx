import { useState, useRef, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, Check, Search } from 'lucide-react';

// Searchable themed dropdown (Select2-style) - native <select> cannot be
// fully restyled (the open options list follows the OS/browser theme).
// The options panel renders through a portal into document.body, positioned
// via the trigger's bounding rect - this keeps it visible even inside
// scrollable/overflow-clipped containers (e.g. a table with overflow-x-auto).
// The closed field always shows its value on one line, left-aligned, cut with an ellipsis (full label on hover);
// singleLine only applies the same to the options of the open list.
export default function Select({ value, onChange, options, placeholder, compact = false, singleLine = false, disabled = false }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [coords, setCoords] = useState({ top: 0, left: 0, width: 0 });
  const containerRef = useRef(null);
  const panelRef = useRef(null);
  const searchRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (
        containerRef.current && !containerRef.current.contains(e.target) &&
        panelRef.current && !panelRef.current.contains(e.target)
      ) {
        setOpen(false);
        setQuery('');
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (open && searchRef.current) {
      searchRef.current.focus();
    }
  }, [open]);

  function updateCoords() {
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setCoords({ top: rect.bottom + 4, left: rect.left, width: rect.width });
    }
  }

  function openDropdown() {
    updateCoords();
    setOpen(true);
  }

  // Keep the portal-rendered panel glued to its trigger while open, even when an
  // ancestor (e.g. a table with overflow-x-auto) scrolls - a fixed-position portal
  // otherwise stays put and visually detaches from the button.
  useEffect(() => {
    if (!open) return;
    function handleScrollOrResize() {
      updateCoords();
    }
    window.addEventListener('scroll', handleScrollOrResize, true);
    window.addEventListener('resize', handleScrollOrResize);
    return () => {
      window.removeEventListener('scroll', handleScrollOrResize, true);
      window.removeEventListener('resize', handleScrollOrResize);
    };
  }, [open]);

  const selected = options.find((o) => o.value === value);
  const filteredOptions = useMemo(() => {
    if (!query.trim()) return options;
    const q = query.toLowerCase();
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, query]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openDropdown())}
        className={'w-full flex items-center justify-between gap-2 text-left bg-bg-inset border border-border rounded-md text-text-primary font-mono outline-none focus:border-accent focus:ring-2 focus:ring-accent/30 transition-colors ' + (disabled ? 'opacity-70 cursor-not-allowed ' : 'cursor-pointer ') + (compact ? 'px-2.5 py-1 text-[12px]' : 'px-3.5 py-2.5 text-sm')}
      >
        <span className={(selected ? '' : 'text-text-muted') + ' truncate min-w-0'} title={selected ? selected.label : undefined}>
          {selected ? selected.label : placeholder || 'Selecionar...'}
        </span>
        <ChevronDown size={16} className={'text-text-muted transition-transform shrink-0 ' + (open ? 'rotate-180' : '')} />
      </button>
      {open && createPortal(
        <div
          ref={panelRef}
          style={{ position: 'fixed', top: coords.top, left: coords.left, width: coords.width, zIndex: 1000 }}
          className="bg-bg-elevated border border-border rounded-md shadow-xl overflow-hidden"
        >
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
            <Search size={14} className="text-text-muted shrink-0" />
            <input
              ref={searchRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Pesquisar..."
              className="w-full bg-transparent border-none text-sm text-text-primary font-mono outline-none placeholder:text-text-muted/60"
            />
          </div>
          <div className="max-h-52 overflow-y-auto scrollbar-thin">
            {filteredOptions.length === 0 && (
              <div className="px-3.5 py-3 text-sm text-text-muted text-center">Nenhum resultado</div>
            )}
            {filteredOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                  setQuery('');
                }}
                className={
                  'w-full flex items-center justify-between px-3.5 py-2.5 text-sm font-mono text-left cursor-pointer transition-colors ' +
                  (opt.value === value
                    ? 'bg-accent/15 text-accent font-medium'
                    : 'text-text-primary hover:bg-bg-inset')
                }
              >
                <span className={singleLine ? 'truncate min-w-0' : ''} title={singleLine ? opt.label : undefined}>{opt.label}</span>
                {opt.value === value && <Check size={14} className="shrink-0 ml-2" />}
              </button>
            ))}
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
