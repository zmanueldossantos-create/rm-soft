import { useEffect, useState } from 'react';
import { Loader2, Save, IdCard, Briefcase, Banknote, GraduationCap } from 'lucide-react';
import Modal from './Modal';
import Select from './Select';
import DateInput from './DateInput';
import { createEmployee, updateEmployee } from '../api/hr';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// The employee's file, in 4 tabs (Identificação, Profissional, Remuneração, Habilitações). The checks are the
// server's (required fields, dates, IBAN, uniqueness): a refusal comes back as a toast and opens the tab of the field.
const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';

const TABS = [
  { key: 'ID', label: 'Identificação', icon: IdCard },
  { key: 'PRO', label: 'Profissional', icon: Briefcase },
  { key: 'PAY', label: 'Remuneração', icon: Banknote },
  { key: 'EDU', label: 'Habilitações', icon: GraduationCap },
];

// the tab where each message's field is, so the user lands on it
const TAB_OF_MESSAGE = [
  [/admissão|contrato|experimental|departamento|categoria|função|horário|local/i, 'PRO'],
  [/salário|iban|pagamento|banco|transferência/i, 'PAY'],
  [/escolaridade/i, 'EDU'],
];

const FIELDS = [
  'number', 'full_name', 'gender', 'birth_date', 'marital_status', 'nationality_id', 'father_name', 'mother_name',
  'id_document_type', 'id_document_number', 'id_issued_on', 'id_expires_on', 'nif', 'social_security_number', 'address',
  'phone', 'email', 'department_id', 'category_id', 'job_title_id', 'establishment_id', 'hired_on', 'contract_type_id',
  'contract_ends_on', 'probation_ends_on', 'work_schedule_id', 'base_salary', 'payment_method', 'bank_id', 'iban',
  'education_level_id', 'training', 'experience', 'notes',
];

function emptyForm(options) {
  const form = Object.fromEntries(FIELDS.map((f) => [f, '']));
  form.number = options?.next_number || '';
  form.payment_method = 'TRANSFERENCIA';
  form.id_document_type = 'BI';
  form.phone = '+244';
  form.nationality_id = options?.countries?.find((c) => c.code === 'AO')?.id || '';
  return form;
}

export default function EmployeeForm({ open, onClose, onSaved, employee, options, readOnly = false }) {
  const [form, setForm] = useState(() => emptyForm(options));
  const [tab, setTab] = useState('ID');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTab('ID');
    if (employee) {
      setForm(Object.fromEntries(FIELDS.map((f) => [f, employee[f] === null || employee[f] === undefined ? '' : String(employee[f])])));
    } else {
      setForm(emptyForm(options));
    }
  }, [open, employee, options]);

  const set = (field) => (e) => setForm((p) => ({ ...p, [field]: e?.target ? e.target.value : e }));

  // the values of an HR table: the active ones, plus the file's own if it was switched off since
  function tableOptions(kind, field) {
    const values = options?.tables?.[kind] || [];
    return [{ value: '', label: '-' }, ...values.filter((v) => v.is_active || v.id === form[field]).map((v) => ({ value: v.id, label: v.name + (v.is_active ? '' : ' (desativado)') }))];
  }
  const pairs = (list) => (list || []).map((o) => ({ value: o.value, label: o.label }));

  async function handleSubmit(e) {
    e.preventDefault();
    const payload = Object.fromEntries(FIELDS.map((f) => [f, form[f] === '' ? null : form[f]]));
    if (payload.phone === '+244') payload.phone = null;
    payload.base_salary = form.base_salary === '' ? null : Number(String(form.base_salary).replace(/\s/g, '').replace(',', '.'));
    setSaving(true);
    try {
      const saved = employee ? await updateEmployee(employee.id, payload) : await createEmployee(payload);
      toast.success(employee ? 'Ficha guardada' : `Colaborador ${saved.number} registado`);
      onSaved(saved);
    } catch (err) {
      const message = extractErrorMessage(err, 'Erro ao guardar a ficha');
      const found = TAB_OF_MESSAGE.find(([pattern]) => pattern.test(message));
      setTab(found ? found[1] : 'ID');
      toast.error(message);
    } finally {
      setSaving(false);
    }
  }

  const field = (label, name, extra = {}) => (
    <div className={extra.wide ? 'sm:col-span-2' : ''}>
      <label className={labelClass}>{label}</label>
      <input value={form[name]} onChange={set(name)} className={inputClass + (extra.mono ? ' font-mono' : '')}
        placeholder={extra.placeholder} maxLength={extra.maxLength} type={extra.type || 'text'} inputMode={extra.inputMode} />
    </div>
  );
  const date = (label, name) => (
    <div>
      <label className={labelClass}>{label}</label>
      <DateInput value={form[name]} onChange={set(name)} className={inputClass} />
    </div>
  );
  const select = (label, name, opts) => (
    <div>
      <label className={labelClass}>{label}</label>
      <Select value={form[name]} onChange={set(name)} options={opts} placeholder="-" />
    </div>
  );

  return (
    <Modal open={open} onClose={onClose} maxWidthClass="max-w-4xl" size="full"
      title={employee ? `Ficha de ${employee.full_name}` : 'Novo colaborador'}
      subtitle={employee ? `Matrícula ${employee.number}` : 'Nome, data de admissão e salário base são obrigatórios'}
      footer={(
        <div className="px-6 py-3 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="h-10 px-4 rounded-md border border-border text-sm text-text-muted hover:text-text-primary cursor-pointer">{readOnly ? 'Fechar' : 'Cancelar'}</button>
          {!readOnly && <button type="submit" form="employee-form" disabled={saving} className="h-10 px-5 rounded-md bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-semibold flex items-center gap-2 cursor-pointer">
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            {saving ? 'A guardar...' : employee ? 'Guardar alterações' : 'Registar colaborador'}
          </button>}
        </div>
      )}>
      <form id="employee-form" noValidate onSubmit={handleSubmit} className="flex flex-col gap-5">
        <div className="flex gap-1 border-b border-border -mt-1 overflow-x-auto">
          {TABS.map((t) => (
            <button key={t.key} type="button" onClick={() => setTab(t.key)}
              className={'flex items-center gap-2 px-4 h-10 text-sm font-medium border-b-2 -mb-px whitespace-nowrap cursor-pointer transition-colors ' + (tab === t.key ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary')}>
              <t.icon size={15} /> {t.label}
            </button>
          ))}
        </div>

        <fieldset disabled={readOnly} className="contents">
        {tab === 'ID' && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {field('Matrícula', 'number', { mono: true, maxLength: 20 })}
            {field('Nome completo *', 'full_name', { wide: true, maxLength: 200 })}
            {select('Género', 'gender', [{ value: '', label: '-' }, ...pairs(options?.genders)])}
            {date('Data de nascimento', 'birth_date')}
            {select('Estado civil', 'marital_status', [{ value: '', label: '-' }, ...pairs(options?.marital_statuses)])}
            {select('Nacionalidade', 'nationality_id', [{ value: '', label: '-' }, ...(options?.countries || []).map((c) => ({ value: c.id, label: c.name }))])}
            {field('Nome do pai', 'father_name', { maxLength: 200 })}
            {field('Nome da mãe', 'mother_name', { maxLength: 200 })}
            {select('Documento de identificação', 'id_document_type', pairs(options?.id_document_types))}
            {field('N.º do documento', 'id_document_number', { mono: true, maxLength: 30 })}
            {date('Data de emissão', 'id_issued_on')}
            {date('Válido até', 'id_expires_on')}
            {field('NIF', 'nif', { mono: true, maxLength: 20 })}
            {field('N.º de segurança social (INSS)', 'social_security_number', { mono: true, maxLength: 20 })}
            {field('Telefone', 'phone', { maxLength: 20, inputMode: 'tel' })}
            {field('Email', 'email', { maxLength: 120, type: 'email' })}
            {field('Morada', 'address', { wide: true, maxLength: 300 })}
          </div>
        )}

        {tab === 'PRO' && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {select('Departamento', 'department_id', tableOptions('DEPARTAMENTO', 'department_id'))}
            {select('Categoria profissional', 'category_id', tableOptions('CATEGORIA', 'category_id'))}
            {select('Função / cargo', 'job_title_id', tableOptions('FUNCAO', 'job_title_id'))}
            {select('Local de trabalho', 'establishment_id', [{ value: '', label: '-' }, ...(options?.establishments || []).map((e) => ({ value: e.id, label: e.name }))])}
            {date('Data de admissão *', 'hired_on')}
            {select('Tipo de contrato', 'contract_type_id', tableOptions('TIPO_CONTRATO', 'contract_type_id'))}
            {date('Fim do contrato', 'contract_ends_on')}
            {date('Fim do período experimental', 'probation_ends_on')}
            {select('Horário de trabalho', 'work_schedule_id', tableOptions('HORARIO', 'work_schedule_id'))}
          </div>
        )}

        {tab === 'PAY' && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {field('Salário base mensal (Kz) *', 'base_salary', { mono: true, inputMode: 'decimal', placeholder: '0,00' })}
            {select('Forma de pagamento', 'payment_method', pairs(options?.payment_methods))}
            {select('Banco', 'bank_id', [{ value: '', label: '-' }, ...(options?.banks || []).map((b) => ({ value: b.id, label: b.name }))])}
            {field(form.payment_method === 'TRANSFERENCIA' ? 'IBAN *' : 'IBAN', 'iban', { wide: true, mono: true, maxLength: 40, placeholder: 'AO06 0000 0000 0000 0000 0000 0' })}
            <p className="sm:col-span-3 text-[12px] text-text-muted">Os subsídios, o INSS e o IRT configuram-se com o processamento salarial.</p>
          </div>
        )}

        {tab === 'EDU' && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {select('Nível de escolaridade', 'education_level_id', tableOptions('ESCOLARIDADE', 'education_level_id'))}
            <div className="sm:col-span-3">
              <label className={labelClass}>Formação profissional</label>
              <textarea value={form.training} onChange={set('training')} rows={3} className={inputClass} />
            </div>
            <div className="sm:col-span-3">
              <label className={labelClass}>Experiência anterior</label>
              <textarea value={form.experience} onChange={set('experience')} rows={3} className={inputClass} />
            </div>
            <div className="sm:col-span-3">
              <label className={labelClass}>Observações</label>
              <textarea value={form.notes} onChange={set('notes')} rows={2} className={inputClass} />
            </div>
          </div>
        )}
        </fieldset>
      </form>
    </Modal>
  );
}
