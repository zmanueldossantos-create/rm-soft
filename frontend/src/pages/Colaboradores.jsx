import { useEffect, useMemo, useState } from 'react';
import { Users2, Plus, Pencil, Eye, Loader2, Search, LogOut, UserPlus, Settings2, Calculator } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import DateInput from '../components/DateInput';
import EmployeeForm from '../components/EmployeeForm';
import HrTablesModal from '../components/HrTablesModal';
import PayrollSettingsModal from '../components/PayrollSettingsModal';
import { listEmployees, getEmployeeOptions, registerDeparture, readmitEmployee } from '../api/hr';
import { useCan } from '../utils/permissions';
import { formatDate, formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Recursos Humanos → Colaboradores: the employees' files - active, gone (the file stays) or all; a departure with its
// date and reason, a readmission; the HR tables in a modal.
const FILTERS = [{ key: 'ATIVOS', label: 'Ativos' }, { key: 'SAIDOS', label: 'Saídos' }, { key: 'TODOS', label: 'Todos' }];
const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const today = () => new Date().toLocaleDateString('sv-SE');

export default function Colaboradores() {
  const can = useCan();
  const canManage = can('hr:manage');
  const [filter, setFilter] = useState('ATIVOS');
  const [search, setSearch] = useState('');
  const [departmentId, setDepartmentId] = useState('');
  const [data, setData] = useState({ employees: [], counts: {} });
  const [loading, setLoading] = useState(true);
  const [options, setOptions] = useState(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [tablesOpen, setTablesOpen] = useState(false);
  const [payrollOpen, setPayrollOpen] = useState(false);
  const [leaving, setLeaving] = useState(null); // { employee, left_on, reason, note }
  const [readmitting, setReadmitting] = useState(null); // { employee, hired_on }
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setData(await listEmployees({ status_filter: filter, search: search.trim() || undefined, department_id: departmentId || undefined }));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar os colaboradores'));
    } finally {
      setLoading(false);
    }
  }
  const loadOptions = () => getEmployeeOptions().then(setOptions).catch(() => setOptions(null));

  useEffect(() => { loadOptions(); }, []);
  useEffect(() => {
    const timer = setTimeout(load, search ? 250 : 0);
    return () => clearTimeout(timer);
  }, [filter, search, departmentId]); // eslint-disable-line react-hooks/exhaustive-deps

  const departments = useMemo(() => [{ value: '', label: 'Todos os departamentos' },
    ...((options?.tables?.DEPARTAMENTO) || []).map((d) => ({ value: d.id, label: d.name }))], [options]);

  function openNew() { setEditing(null); setFormOpen(true); }
  function openFile(employee) { setEditing(employee); setFormOpen(true); }

  // a new file stays open (its photo and documents are added once it exists)
  async function saved(employee, keepOpen) {
    if (keepOpen) setEditing(employee);
    else setFormOpen(false);
    await Promise.all([load(), loadOptions()]);
  }

  async function confirmDeparture(e) {
    e.preventDefault();
    if (!leaving.left_on) { toast.error('Indique a data de saída'); return; }
    if (!leaving.reason) { toast.error('Escolha o motivo da saída'); return; }
    setBusy(true);
    try {
      const gone = await registerDeparture(leaving.employee.id, { left_on: leaving.left_on, reason: leaving.reason, note: leaving.note || null });
      toast.success(`Saída de ${leaving.employee.full_name} registada` + (gone.account_closed ? ` - a conta de ${gone.user_name} foi desativada` : ''));
      setLeaving(null);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao registar a saída'));
    } finally {
      setBusy(false);
    }
  }

  async function confirmReadmission(e) {
    e.preventDefault();
    if (!readmitting.hired_on) { toast.error('Indique a data de readmissão'); return; }
    setBusy(true);
    try {
      await readmitEmployee(readmitting.employee.id, readmitting.hired_on);
      toast.success(`${readmitting.employee.full_name} readmitido`);
      setReadmitting(null);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao readmitir'));
    } finally {
      setBusy(false);
    }
  }

  const employees = data.employees;
  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Users2 size={22} className="text-accent" /> Colaboradores
      </h2>
      <p className="text-text-muted text-sm mb-5">A ficha de cada colaborador: identificação, contrato e remuneração</p>

      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" onClick={() => setFilter(f.key)}
              className={'h-9 px-3.5 rounded-md text-sm font-medium border transition-colors cursor-pointer ' + (filter === f.key ? 'bg-accent border-accent text-white' : 'border-border text-text-muted hover:text-text-primary')}>
              {f.label} <span className="opacity-70">({data.counts?.[f.key] ?? 0})</span>
            </button>
          ))}
          <div className="relative w-full sm:w-64">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nome, matrícula, NIF, BI, telefone..."
              className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
          </div>
          {departments.length > 1 && (
            <div className="w-56"><Select value={departmentId} onChange={setDepartmentId} options={departments} compact /></div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {can('hr:payroll_settings') && (
            <button type="button" onClick={() => setPayrollOpen(true)} className="flex items-center gap-2 h-9 px-3.5 rounded-md border border-border text-sm text-text-primary hover:border-accent hover:text-accent cursor-pointer">
              <Calculator size={15} /> Parâmetros salariais
            </button>
          )}
          {can('hr:settings') && (
            <button type="button" onClick={() => setTablesOpen(true)} className="flex items-center gap-2 h-9 px-3.5 rounded-md border border-border text-sm text-text-primary hover:border-accent hover:text-accent cursor-pointer">
              <Settings2 size={15} /> Tabelas de RH
            </button>
          )}
          {canManage && (
            <button type="button" onClick={openNew} disabled={!options} className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm h-9 px-4 rounded-md cursor-pointer">
              <Plus size={16} /> Novo colaborador
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" /> A carregar...</div>
      ) : employees.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <Users2 size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium">{search || departmentId ? 'Nenhum colaborador encontrado' : filter === 'SAIDOS' ? 'Nenhuma saída registada' : 'Nenhum colaborador registado'}</p>
        </div>
      ) : (
        <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
                <th className="text-left px-4 py-2.5">Matrícula</th>
                <th className="text-left px-4 py-2.5">Nome</th>
                <th className="text-left px-4 py-2.5">Departamento</th>
                <th className="text-left px-4 py-2.5">Função</th>
                <th className="text-left px-4 py-2.5">Admissão</th>
                <th className="text-right px-4 py-2.5">Salário base</th>
                <th className="text-left px-4 py-2.5">Estado</th>
                <th className="text-right px-4 py-2.5">Ações</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((e) => (
                <tr key={e.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                  <td className="px-4 py-2.5 font-mono text-[12px] text-text-muted">{e.number}</td>
                  <td className="px-4 py-2.5 text-text-primary font-medium">{e.full_name}</td>
                  <td className="px-4 py-2.5 text-text-muted">{e.department || '-'}</td>
                  <td className="px-4 py-2.5 text-text-muted">{e.job_title || '-'}</td>
                  <td className="px-4 py-2.5 text-text-muted whitespace-nowrap">{formatDate(e.hired_on)}</td>
                  <td className="px-4 py-2.5 text-right font-mono whitespace-nowrap">{formatKz(e.base_salary)} Kz</td>
                  <td className="px-4 py-2.5">
                    {e.is_active ? (
                      <span className="inline-block whitespace-nowrap text-[11px] font-semibold px-2 py-0.5 rounded-full bg-success/15 text-success">Ativo</span>
                    ) : (
                      <span title={e.leaving_note || e.leaving_reason_label} className="inline-block whitespace-nowrap text-[11px] font-semibold px-2 py-0.5 rounded-full bg-bg-inset text-text-muted">
                        Saiu em {formatDate(e.left_on)} · {e.leaving_reason_label}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    {canManage && e.is_active && (
                      <button type="button" title="Registar saída" onClick={() => setLeaving({ employee: e, left_on: today(), reason: '', note: '' })}
                        className="inline-flex items-center gap-1.5 h-8 px-2.5 mr-2 rounded-md border border-border text-text-muted text-[12px] font-medium hover:border-danger hover:text-danger cursor-pointer">
                        <LogOut size={13} /> Saída
                      </button>
                    )}
                    {canManage && !e.is_active && (
                      <button type="button" title="Readmitir" onClick={() => setReadmitting({ employee: e, hired_on: today() })}
                        className="inline-flex items-center gap-1.5 h-8 px-2.5 mr-2 rounded-md border border-border text-text-muted text-[12px] font-medium hover:border-accent hover:text-accent cursor-pointer">
                        <UserPlus size={13} /> Readmitir
                      </button>
                    )}
                    <button type="button" title={canManage ? 'Ficha' : 'Ver a ficha'} onClick={() => openFile(e)} disabled={!options}
                      className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent cursor-pointer">
                      {canManage ? <Pencil size={13} /> : <Eye size={13} />}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <EmployeeForm open={formOpen} onClose={() => setFormOpen(false)} onSaved={saved} employee={editing} options={options} readOnly={!canManage} />
      <PayrollSettingsModal open={payrollOpen} onClose={() => setPayrollOpen(false)} canEdit={can('hr:payroll_settings')} />
      <HrTablesModal open={tablesOpen} onClose={() => setTablesOpen(false)} onChanged={() => { loadOptions(); load(); }} />

      <Modal open={!!leaving} onClose={() => setLeaving(null)} title="Registar saída" subtitle={leaving?.employee.full_name}>
        {leaving && (
          <form noValidate onSubmit={confirmDeparture} className="flex flex-col gap-3">
            <div>
              <label className={labelClass}>Data de saída *</label>
              <DateInput value={leaving.left_on} onChange={(e) => setLeaving((p) => ({ ...p, left_on: e.target.value }))} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Motivo *</label>
              <Select value={leaving.reason} onChange={(v) => setLeaving((p) => ({ ...p, reason: v }))} placeholder="Escolha o motivo"
                options={(options?.leaving_reasons || []).map((r) => ({ value: r.value, label: r.label }))} />
            </div>
            <div>
              <label className={labelClass}>{leaving.reason === 'OUTRO' ? 'Descrição *' : 'Observação'}</label>
              <input value={leaving.note} maxLength={300} onChange={(e) => setLeaving((p) => ({ ...p, note: e.target.value }))} className={inputClass} />
            </div>
            <p className="text-[12px] text-text-muted">A ficha fica guardada; o colaborador sai da lista dos ativos e pode ser readmitido.
              {leaving.employee.user_name && options?.users?.find((u) => u.id === leaving.employee.user_id)?.role !== 'GESTOR' ? ` A conta de utilizador (${leaving.employee.user_name}) é desativada.` : ''}</p>
            <button type="submit" disabled={busy} className="bg-danger hover:opacity-90 disabled:opacity-50 text-white font-semibold text-sm rounded-md py-2.5 flex items-center justify-center gap-2 cursor-pointer">
              {busy ? <Loader2 size={16} className="animate-spin" /> : <LogOut size={16} />} Registar saída
            </button>
          </form>
        )}
      </Modal>

      <Modal open={!!readmitting} onClose={() => setReadmitting(null)} title="Readmitir" subtitle={readmitting?.employee.full_name}>
        {readmitting && (
          <form noValidate onSubmit={confirmReadmission} className="flex flex-col gap-3">
            <div>
              <label className={labelClass}>Nova data de admissão *</label>
              <DateInput value={readmitting.hired_on} onChange={(e) => setReadmitting((p) => ({ ...p, hired_on: e.target.value }))} className={inputClass} />
            </div>
            <p className="text-[12px] text-text-muted">Saiu em {formatDate(readmitting.employee.left_on)}. O fim do contrato e do período experimental ficam por indicar na ficha.
              {readmitting.employee.user_name ? ` A conta de utilizador (${readmitting.employee.user_name}) reativa-se em Administração → Utilizadores.` : ''}</p>
            <button type="submit" disabled={busy} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-2.5 flex items-center justify-center gap-2 cursor-pointer">
              {busy ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />} Readmitir
            </button>
          </form>
        )}
      </Modal>
    </main>
  );
}
