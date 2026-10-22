import { useEffect, useState } from 'react';
import { AlertTriangle, Info, Lock } from 'lucide-react';
import apiClient from '../api/client';

// The company's contract, at the top of every screen when there is something to say:
//   15 days before the end (gestor)        - amber: it ends on..., N days left
//   ended, the 7 days of grace (gestor)    - red: everything still works until..., then read only
//   ended more than 7 days ago (everyone)  - red: read only - the reason a sale or a change is refused
//   lifetime licence, maintenance over (gestor) - discreet: no more updates
// Read again every 30 minutes (a renewal by the platform clears it without a new session).

const dateText = (value) => (value ? value.split('-').reverse().join('/') : '');
const days = (n) => (n === 1 ? '1 dia' : n + ' dias');

export default function SubscriptionBanner({ role }) {
  const [sub, setSub] = useState(null);

  useEffect(() => {
    if (!role || role === 'SUPER_ADMIN') return undefined;
    const load = () => apiClient.get('/company/me/subscription').then((r) => setSub(r.data)).catch(() => {});
    load();
    const timer = setInterval(load, 30 * 60 * 1000);
    window.addEventListener('subscription-changed', load); // a licence just imported: read again at once
    return () => { clearInterval(timer); window.removeEventListener('subscription-changed', load); };
  }, [role]);

  if (!sub) return null;
  const gestor = role === 'GESTOR';

  if (sub.license_problem) { // a client's server without a valid licence
    if (!sub.read_only && !gestor) return null;
    return (
      <Bar tone="danger" icon={sub.read_only ? Lock : AlertTriangle}>
        <b>{sub.read_only ? 'Sem licença válida - o sistema está só de leitura.' : 'Sem licença válida.'}</b>
        {' '}{sub.license_problem}.{' '}
        {sub.read_only ? '' : 'Tudo funciona até ' + dateText(sub.grace_until) + '; depois, só leitura. '}
        {gestor ? 'Importe a licença em Definições da Empresa → Licença.' : 'Avise o gestor.'}
      </Bar>
    );
  }

  if (sub.status === 'BLOQUEADO') {
    return (
      <Bar tone="danger" icon={Lock}>
        <b>Contrato terminado - o sistema está só de leitura.</b> Pode consultar, exportar o SAF-T e descarregar as cópias;
        vender e alterar ficam bloqueados até à renovação. Contacte a RM SOFT.
      </Bar>
    );
  }
  if (!gestor) return null;
  if (sub.status === 'TOLERANCIA') {
    return (
      <Bar tone="danger" icon={AlertTriangle}>
        <b>O contrato ({sub.plan}) terminou a {dateText(sub.end_date)}.</b> Tudo continua a funcionar até {dateText(sub.grace_until)}
        {' '}({sub.days_left === 0 ? 'último dia' : 'mais ' + days(sub.days_left)}); depois, o sistema fica só de leitura. Para renovar, contacte a RM SOFT.
      </Bar>
    );
  }
  if (sub.status === 'A_EXPIRAR') {
    return (
      <Bar tone="warning" icon={AlertTriangle}>
        <b>{sub.billing === 'TESTE' ? 'O teste gratuito' : 'O contrato'} ({sub.plan}) termina {sub.days_left === 0 ? 'hoje' : 'a ' + dateText(sub.end_date) + ' - faltam ' + days(sub.days_left)}.</b>
        {' '}Para continuar sem interrupção, contacte a RM SOFT.
      </Bar>
    );
  }
  if (sub.maintenance_over) {
    return (
      <Bar tone="info" icon={Info}>
        A manutenção da licença terminou a {dateText(sub.maintenance_until)}: o sistema continua a funcionar, mas sem novas
        atualizações (incluindo as alterações fiscais da AGT). Para a renovar, contacte a RM SOFT.
      </Bar>
    );
  }
  return null;
}

const TONES = {
  danger: 'bg-danger/10 border-danger text-danger',
  warning: 'bg-amber-500/10 border-amber-500 text-amber-500 [.light_&]:text-amber-700',
  info: 'bg-accent/10 border-accent text-text-primary',
};

function Bar({ tone, icon: Icon, children }) {
  return (
    <div className={'border-b-2 px-4 sm:px-8 py-2.5 text-[13px] flex items-start justify-center gap-2.5 ' + TONES[tone]}>
      <Icon size={16} className="shrink-0 mt-0.5" />
      <span className="max-w-[1400px]">{children}</span>
    </div>
  );
}
