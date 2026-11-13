import { useRef } from 'react';
import { Download, Printer } from 'lucide-react';
import Modal from './Modal';
import { pdfFileName } from '../utils/fileName';

// Every PDF preview of the app: the document, and «Imprimir» / «Guardar» under it. «Guardar» saves it under a real
// name (fileName, else the title - MEL-DA-ROCHA_FT2026-2_A4.pdf): the browser's own download icon, inside the
// preview, can only name it after the temporary blob address (e2a79e69-….pdf).
export default function PdfViewer({ url, title, fileName, onClose, maxWidthClass = 'max-w-3xl', stacked = false, heightClass = 'h-[66vh]' }) {
  const frame = useRef(null);
  const name = pdfFileName(fileName || title);

  function save() {
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
  }

  function print() {
    try {
      frame.current.contentWindow.focus();
      frame.current.contentWindow.print();
    } catch {
      window.open(url, '_blank');  // a browser that refuses to print the frame: the PDF in its own tab
    }
  }

  const button = 'flex items-center justify-center gap-2 text-sm font-semibold rounded-md py-2.5 px-4 transition-colors cursor-pointer';
  // the buttons in the modal's footer: always in sight, whatever the height of the screen
  const footer = url && (
    <div className="flex items-center justify-between gap-3 px-6 py-3">
      <span className="text-[12px] text-text-muted font-mono truncate" title={name}>{name}</span>
      <div className="flex gap-2 shrink-0">
        <button type="button" onClick={print} className={button + ' border border-border text-text-primary hover:border-accent'}>
          <Printer size={15} /> Imprimir
        </button>
        <button type="button" onClick={save} className={button + ' bg-accent hover:bg-accent-hover text-white'}>
          <Download size={15} /> Guardar
        </button>
      </div>
    </div>
  );
  return (
    <Modal open={!!url} onClose={onClose} title={title} maxWidthClass={maxWidthClass} stacked={stacked} footer={footer}>
      {url && <iframe ref={frame} src={url} title={title} className={'w-full rounded-md border border-border ' + heightClass} />}
    </Modal>
  );
}
