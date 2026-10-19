import { useEffect, useState } from 'react';
import { FileText } from 'lucide-react';
import Modal from './Modal';

const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const empty = { number: '', prescriber: '', health_unit: '', patient_name: '', patient_document: '' };

// The medicines of a cart sold on prescription (Farmácia): RECEITA and/or RECEITA_ESPECIAL.
export function prescriptionNeedOf(cart, productById) {
  const regimes = new Set();
  const names = [];
  (cart || []).forEach((l) => {
    const p = productById[l.productId || l.product_id];
    if (p && p.is_medicine && (p.dispensing_regime === 'RECEITA' || p.dispensing_regime === 'RECEITA_ESPECIAL')) {
      regimes.add(p.dispensing_regime);
      if (!names.includes(p.name)) names.push(p.name);
    }
  });
  if (regimes.size === 0) return null;
  return { special: regimes.has('RECEITA_ESPECIAL'), names };
}

function Field({ label, children }) {
  return (
    <div>
      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{label}</label>
      {children}
    </div>
  );
}

// The receita a pharmacy sale is dispensed against - asked before the sale is confirmed. A receita especial
// (psychotropics, narcotics) always needs the number, the patient and his identity document; a receita médica needs
// its number when the company requires it (Empresa -> Farmácia), otherwise what the customer shows is recorded.
export default function PrescriptionModal({ need, required, initial, onCancel, onConfirm }) {
  const [form, setForm] = useState(empty);
  useEffect(() => { if (need) setForm({ ...empty, ...(initial || {}) }); }, [need]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (field, value) => setForm((prev) => ({ ...prev, [field]: value }));
  const filled = (v) => v.trim() !== '';
  const special = !!need?.special;
  const numberRequired = special || required;
  const valid = (!numberRequired || filled(form.number)) && (!special || (filled(form.patient_name) && filled(form.patient_document)));

  return (
    <Modal open={!!need} onClose={onCancel} title={special ? 'Receita especial' : 'Receita médica'} maxWidthClass="max-w-2xl">
      <div className="flex flex-col gap-4">
        <div className={'flex items-start gap-2.5 rounded-md px-3.5 py-2.5 text-[13px] ' + (special ? 'bg-danger/10 text-danger' : 'bg-amber-500/10 text-amber-500 [.light_&]:text-amber-700')}>
          <FileText size={16} className="mt-0.5 shrink-0" />
          <span>
            {(special ? 'Medicamento de receita especial (psicotrópico ou estupefaciente): ' : 'Medicamento sujeito a receita médica: ') + (need?.names || []).join(', ')}
            {!numberRequired && <span className="block text-text-muted mt-0.5">Registe a receita se o cliente a apresentar; pode continuar sem ela.</span>}
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label={'N.º da receita' + (numberRequired ? ' *' : '')}>
            <input autoFocus value={form.number} onChange={(e) => set('number', e.target.value)} className={inputClass + ' font-mono'} />
          </Field>
          <Field label="Médico">
            <input value={form.prescriber} onChange={(e) => set('prescriber', e.target.value)} placeholder="Ex.: Dr. João Manuel" className={inputClass} />
          </Field>
          <Field label="Unidade de saúde">
            <input value={form.health_unit} onChange={(e) => set('health_unit', e.target.value)} placeholder="Ex.: Hospital Josina Machel" className={inputClass} />
          </Field>
          <Field label={'Nome do utente' + (special ? ' *' : '')}>
            <input value={form.patient_name} onChange={(e) => set('patient_name', e.target.value)} className={inputClass} />
          </Field>
          {special && (
            <Field label="Documento de identificação *">
              <input value={form.patient_document} onChange={(e) => set('patient_document', e.target.value)} placeholder="N.º do BI ou passaporte" className={inputClass + ' font-mono'} />
            </Field>
          )}
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onCancel} className="border border-border hover:border-accent text-text-primary text-sm font-medium rounded-md px-4 py-2.5 cursor-pointer">Cancelar</button>
          <button type="button" disabled={!valid} onClick={() => onConfirm(form)} className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-md px-5 py-2.5 cursor-pointer">Continuar</button>
        </div>
      </div>
    </Modal>
  );
}
