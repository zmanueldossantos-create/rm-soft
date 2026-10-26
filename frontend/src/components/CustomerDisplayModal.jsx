import { useEffect, useRef, useState } from 'react';
import { ImagePlus, Loader2, MonitorUp, Save, Trash2 } from 'lucide-react';
import Modal from './Modal';
import { API_ORIGIN } from '../api/config';
import { addCustomerDisplayImage, deleteCustomerDisplayImage, getCustomerDisplay, saveCustomerDisplay } from '../api/customerDisplay';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Configurações → Atividades → Ecrã do cliente: what the customer's screen of this activity shows when no sale is
// going on - a welcome message and up to 6 pictures (promotions, products...), each shown a few seconds.
export default function CustomerDisplayModal({ activity, onClose }) {
  const [data, setData] = useState(null);
  const [message, setMessage] = useState('');
  const [seconds, setSeconds] = useState(8);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const fileRef = useRef(null);

  useEffect(() => {
    if (!activity) return;
    setData(null);
    getCustomerDisplay(activity.id)
      .then((d) => { setData(d); setMessage(d.welcome_message || ''); setSeconds(d.slide_seconds || 8); })
      .catch((err) => { toast.error(extractErrorMessage(err, 'Erro ao carregar o ecrã do cliente')); onClose(); });
  }, [activity]); // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    setSaving(true);
    try {
      const d = await saveCustomerDisplay(activity.id, { welcome_message: message, slide_seconds: Number(seconds) || 8 });
      setData({ ...data, ...d });
      toast.success('Ecrã do cliente guardado');
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setSaving(false);
    }
  }

  async function upload(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (!files.length) return;
    setUploading(true);
    try {
      let d = data;
      for (const file of files) {
        d = await addCustomerDisplayImage(activity.id, file);
      }
      setData({ ...data, ...d });
      toast.success(files.length > 1 ? files.length + ' imagens adicionadas' : 'Imagem adicionada');
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao enviar a imagem'));
      getCustomerDisplay(activity.id).then(setData).catch(() => {});
    } finally {
      setUploading(false);
    }
  }

  async function remove(image) {
    setDeletingId(image.id);
    try {
      const d = await deleteCustomerDisplayImage(image.id);
      setData({ ...data, ...d });
      toast.success('Imagem apagada');
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao apagar a imagem'));
    } finally {
      setDeletingId(null);
    }
  }

  // closed: nothing to draw (the last activity's data must not be drawn without its activity)
  if (!activity) return null;

  const images = data?.images || [];
  const full = data && images.length >= data.max_images;

  return (
    <Modal open={!!activity} onClose={onClose} maxWidthClass="max-w-3xl"
           title={'Ecrã do cliente - ' + (activity?.name || '')}
           subtitle="O que o cliente vê no segundo monitor da caixa quando não há venda em curso"
           footer={(
             <div className="flex justify-end gap-2">
               <button type="button" onClick={onClose} className="border border-border text-text-primary text-sm px-4 py-2 rounded-md hover:border-accent cursor-pointer">Fechar</button>
               <button type="button" onClick={save} disabled={!data || saving}
                       className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white text-sm font-medium px-4 py-2 rounded-md cursor-pointer disabled:opacity-50">
                 {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}Guardar
               </button>
             </div>
           )}>
      {!data ? (
        <div className="flex justify-center py-10"><Loader2 size={20} className="animate-spin text-accent" /></div>
      ) : (
        <div className="flex flex-col gap-5">
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_12rem] gap-4">
            <label className="flex flex-col gap-1.5">
              <span className="text-[12px] font-semibold text-text-muted uppercase tracking-wide">Mensagem de boas-vindas</span>
              <input value={message} maxLength={200} onChange={(e) => setMessage(e.target.value)}
                     placeholder="Bem-vindo! (ex.: Promoções da semana)"
                     className="bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent" />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-[12px] font-semibold text-text-muted uppercase tracking-wide">Cada imagem (segundos)</span>
              <input type="number" min={3} max={60} value={seconds} onChange={(e) => setSeconds(e.target.value)}
                     className="bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent" />
            </label>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2.5">
              <p className="text-[12px] font-semibold text-text-muted uppercase tracking-wide">
                Imagens ({images.length}/{data.max_images})
              </p>
              <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading || full}
                      title={full ? 'Apague uma imagem para adicionar outra' : 'PNG, JPG ou WEBP, até 2MB'}
                      className="flex items-center gap-1.5 text-accent hover:text-accent-hover text-[13px] font-medium cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
                {uploading ? <Loader2 size={14} className="animate-spin" /> : <ImagePlus size={14} />}Adicionar imagens
              </button>
              <input ref={fileRef} type="file" accept=".png,.jpg,.jpeg,.webp" multiple className="hidden" onChange={upload} />
            </div>
            {images.length === 0 ? (
              <div className="border border-dashed border-border rounded-lg py-8 text-center text-text-muted text-[13px]">
                <MonitorUp size={22} className="mx-auto mb-2 opacity-50" />
                Sem imagens: o ecrã mostra a mensagem e o logótipo da empresa
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {images.map((image) => (
                  <div key={image.id} className="relative group border border-border rounded-lg overflow-hidden bg-bg-inset aspect-video">
                    <img src={API_ORIGIN + image.url} alt="" className="w-full h-full object-contain" />
                    <button type="button" onClick={() => remove(image)} disabled={deletingId === image.id} aria-label="Apagar imagem"
                            className="absolute top-1.5 right-1.5 inline-flex items-center justify-center w-8 h-8 rounded-md bg-bg-elevated/90 border border-border text-text-muted hover:text-danger hover:border-danger cursor-pointer">
                      {deletingId === image.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                    </button>
                  </div>
                ))}
              </div>
            )}
            <p className="text-[12px] text-text-muted mt-2">PNG, JPG ou WEBP, até 2MB cada. De preferência no formato do monitor (ex. 1920 × 1080).</p>
          </div>
        </div>
      )}
    </Modal>
  );
}
