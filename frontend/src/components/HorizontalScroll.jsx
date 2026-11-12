import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

// A wide table in a box that scrolls sideways, as on Faturas: the thin themed scrollbar and the ‹ › buttons above
// it - shown only when the content is wider than the box, each one off at its end. className max-h-[70vh]: the box
// also scrolls down, so its sideways scrollbar stays on screen (with a sticky header in the table).
export default function HorizontalScroll({ children, step = 400, className = '' }) {
  const ref = useRef(null);
  const [edges, setEdges] = useState({ overflow: false, start: true, end: true });

  function measure() {
    const el = ref.current;
    if (!el) return;
    setEdges({
      overflow: el.scrollWidth > el.clientWidth + 1,
      start: el.scrollLeft <= 0,
      end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 1,
    });
  }

  useEffect(() => {
    measure();
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    if (el.firstElementChild) observer.observe(el.firstElementChild);
    return () => observer.disconnect();
  }, [children]);

  const button = 'inline-flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:border-border';
  return (
    <>
      {edges.overflow && (
        <div className="flex items-center justify-end gap-1.5 px-4 py-1.5 border-b border-border bg-bg-inset/30">
          <span className="text-[11px] text-text-muted mr-1">Deslocar tabela</span>
          <button type="button" aria-label="Para a esquerda" disabled={edges.start} onClick={() => ref.current?.scrollBy({ left: -step, behavior: 'smooth' })} className={button}>
            <ChevronLeft size={14} />
          </button>
          <button type="button" aria-label="Para a direita" disabled={edges.end} onClick={() => ref.current?.scrollBy({ left: step, behavior: 'smooth' })} className={button}>
            <ChevronRight size={14} />
          </button>
        </div>
      )}
      <div ref={ref} onScroll={measure} className={'overflow-auto scrollbar-thin ' + className}>
        {children}
      </div>
    </>
  );
}
