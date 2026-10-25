import { useEffect, useState } from 'react';
import { Inbox, Loader2, Mail, MessageCircle, Phone, Save } from 'lucide-react';
import Modal from '../components/Modal';
import { listDemoRequests, updateDemoRequest } from '../api/demoRequests';
import { extractErrorMessage } from '../utils/errors';
import { useToastState } from '../components/Toaster';
import { toast } from '../store/toastStore';

// «Pedidos» (menu of the platform): the «Pedir demonstração» of the public site, newest first. Each one is followed
// NOVO -> CONTACTADO -> CONVERTIDO (now a client) or DESCARTADO, with RM SOFT's own notes.

const STATUSES = [
  ['NOVO', 'Novos', 'bg-accent/15 text-accent'],
  ['CONTACTADO', 'Contactados', 'bg-amber-500/15 text-amber-500 [.light_&]:text-amber-700'],
  ['CONVERTIDO', 'Convertidos', 'bg-success/15 text-success'],
  ['DESCARTADO', 'Descartados', 'bg-text-muted/15 text-text-muted'],
];
const TONE = Object.fromEntries(STATUSES.map(([code, , tone]) => [code, tone]));
const when = (iso) => (iso ? new Date(iso).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '');
const waLink = (phone) => 'https://wa.me/' + phone.replace(/\D/g, '');

export default function Pedidos() {
  const [filter, setFilter] = useState('NOVO');
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(null);
  const [, setError] = useToastState('error');

  async function load(status = filter) {
    try {
      setRows(await listDemoRequests(status || null));
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível carregar os pedidos'));
    }
  }
  useEffect(() => { load(filter); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  function saved(row) {
    setOpen(null);
    load();
    window.dispatchEvent(new Event('demo-requests-changed')); // the menu's badge follows
    toast.success('Pedido de ' + row.company_name + ': ' + row.status_label.toLowerCase());
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Inbox size={22} className="text-accent" /> Pedidos de demonstração
      </h2>
      <p className="text-text-muted text-sm mb-6">Os pedidos enviados pelo site público. Abra um pedido para o seguir: contactar, converter em cliente ou descartar.</p>

      <div className="flex flex-wrap gap-2 mb-5">
        {[...STATUSES, ['', 'Todos']].map(([code, label]) => (
          <button key={code || 'all'} type="button" onClick={() => setFilter(code)}
            className={'px-3.5 py-1.5 rounded-md text-sm font-medium border cursor-pointer ' + (filter === code
              ? 'bg-accent border-accent text-white' : 'border-border text-text-muted hover:text-text-primary')}>
            {label}
          </button>
        ))}
      </div>

      {rows === null ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>
      ) : rows.length === 0 ? (
        <div className="border border-border rounded-lg py-14 text-center text-text-muted text-sm">Nenhum pedido {filter ? 'neste estado' : 'ainda'}.</div>
      ) : (
        <div className="border border-border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted border-b border-border">
                <th className="px-4 py-3 font-medium">Data</th>
                <th className="px-4 py-3 font-medium">Empresa</th>
                <th className="px-4 py-3 font-medium">Contacto</th>
                <th className="px-4 py-3 font-medium">Atividade</th>
                <th className="px-4 py-3 font-medium">Plano</th>
                <th className="px-4 py-3 font-medium">Instalação</th>
                <th className="px-4 py-3 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} onClick={() => setOpen(r)} className="border-b border-border last:border-0 hover:bg-bg-inset cursor-pointer">
                  <td className="px-4 py-3 font-mono text-[12px] text-text-muted whitespace-nowrap">{when(r.created_at)}</td>
                  <td className="px-4 py-3 text-text-primary font-medium">{r.company_name}</td>
                  <td className="px-4 py-3 text-text-primary whitespace-nowrap">{r.name}<span className="block font-mono text-[12px] text-text-muted">{r.phone}</span></td>
                  <td className="px-4 py-3 text-text-muted">{r.sectors.map((s) => s.name).join(', ') || '-'}</td>
                  <td className="px-4 py-3 text-text-muted">{r.plan || '-'}</td>
                  <td className="px-4 py-3 text-text-muted whitespace-nowrap">{r.deployment_label}</td>
                  <td className="px-4 py-3"><span className={'text-[12px] font-semibold px-2 py-0.5 rounded ' + TONE[r.status]}>{r.status_label}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {open && <RequestModal row={open} onClose={() => setOpen(null)} onSaved={saved} />}
    </main>
  );
}

function RequestModal({ row, onClose, onSaved }) {
  const [status, setStatus] = useState(row.status);
  const [notes, setNotes] = useState(row.notes || '');
  const [saving, setSaving] = useState(false);
  const [, setError] = useToastState('error');

  async function save() {
    setSaving(true);
    try {
      onSaved(await updateDemoRequest(row.id, status, notes));
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível guardar'));
    } finally {
      setSaving(false);
    }
  }

  const facts = [
    ['Recebido', when(row.created_at)], ['Nome', row.name], ['Telefone', row.phone], ['Email', row.email || '-'],
    ['NIF', row.nif || '-'], ['Atividade', row.sectors.map((s) => s.name).join(', ') || '-'], ['Plano', row.plan || 'Ainda não sabe'],
    ['Instalação', row.deployment_label], ['Língua do site', row.language === 'en' ? 'Inglês' : 'Português'],
  ];

  return (
    <Modal open onClose={onClose} title={row.company_name} subtitle={'Pedido de demonstração · ' + row.status_label} maxWidthClass="max-w-3xl">
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap gap-2">
          <a href={waLink(row.phone)} target="_blank" rel="noreferrer" className="flex items-center gap-2 bg-[#1F9D55] hover:bg-[#188247] text-white text-sm font-semibold px-3.5 py-2 rounded-md">
            <MessageCircle size={15} /> WhatsApp
          </a>
          <a href={'tel:' + row.phone} className="flex items-center gap-2 border border-border hover:border-accent text-text-primary text-sm px-3.5 py-2 rounded-md"><Phone size={15} /> Ligar</a>
          {row.email && <a href={'mailto:' + row.email} className="flex items-center gap-2 border border-border hover:border-accent text-text-primary text-sm px-3.5 py-2 rounded-md"><Mail size={15} /> Email</a>}
        </div>
        <dl className="grid grid-cols-1 sm:grid-cols-3 gap-x-5 gap-y-3">
          {facts.map(([label, value]) => (
            <div key={label}>
              <dt className="text-[11px] uppercase tracking-wide text-text-muted">{label}</dt>
              <dd className="text-sm text-text-primary break-words">{value}</dd>
            </div>
          ))}
        </dl>
        {row.message && (
          <div className="bg-bg-inset border border-border rounded-md px-4 py-3 text-sm text-text-primary whitespace-pre-wrap">{row.message}</div>
        )}
        <div>
          <div className="text-[11px] uppercase tracking-wide text-text-muted mb-1.5">Estado</div>
          <div className="flex flex-wrap gap-2">
            {STATUSES.map(([code, label]) => (
              <button key={code} type="button" onClick={() => setStatus(code)}
                className={'px-3 py-1.5 rounded-md text-sm font-medium border cursor-pointer ' + (status === code
                  ? 'bg-accent border-accent text-white' : 'border-border text-text-muted hover:text-text-primary')}>
                {label.replace(/s$/, '')}
              </button>
            ))}
          </div>
        </div>
        <label>
          <span className="text-[11px] uppercase tracking-wide text-text-muted mb-1.5 block">Notas da RM SOFT</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} maxLength={2000}
            placeholder="Ex.: demonstração marcada para 2.ª feira às 10:00"
            className="w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent" />
        </label>
        {row.handled_by && <p className="text-[12px] text-text-muted">Última mudança de estado: {row.handled_by}, {when(row.handled_at)}.</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="border border-border hover:border-accent text-text-primary text-sm px-4 py-2.5 rounded-md cursor-pointer">Fechar</button>
          <button type="button" onClick={save} disabled={saving}
            className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm px-4 py-2.5 rounded-md cursor-pointer">
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Guardar
          </button>
        </div>
      </div>
    </Modal>
  );
}
