import { useState, useEffect } from 'react';
import { PiggyBank, Loader2, ArrowLeftRight } from 'lucide-react';
import { listCashMovements } from '../api/tesouraria';
import { extractErrorMessage } from '../utils/errors';

const MOVEMENT_TYPES = [
  { value: 'TRANSFERENCIA', label: 'Transferencia entre caixas' },
  { value: 'ENTRADA_EXTERNA', label: 'Entrada externa' },
  { value: 'SAIDA_EXTERNA', label: 'Saida externa' },
];

export default function Tesouraria() {
  const [movements, setMovements] = useState([]);
  const [movementsLoading, setMovementsLoading] = useState(true);
  const [error, setError] = useState('');

  async function loadMovements() {
    setMovementsLoading(true);
    setError('');
    try {
      setMovements(await listCashMovements());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar movimentos'));
    } finally {
      setMovementsLoading(false);
    }
  }

  useEffect(() => {
    loadMovements();
  }, []);

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <PiggyBank size={22} className="text-accent" />
        Tesouraria
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Historico de movimentos de caixa de todas as atividades - as operacoes (transferencias, entradas e saidas) sao feitas a partir do ecra Caixa
      </p>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      <div className="bg-bg-elevated border border-border rounded-lg p-6 sm:p-8">
        <div className="flex items-center gap-2 mb-5">
          <ArrowLeftRight size={14} className="text-accent" />
          <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">Historico de movimentos</p>
        </div>
        {movementsLoading ? (
          <div className="flex justify-center py-12"><Loader2 size={20} className="animate-spin text-accent" /></div>
        ) : movements.length === 0 ? (
          <p className="text-text-muted text-[13px] text-center py-12">Nenhum movimento registado ainda</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5">Data</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5">Tipo</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5">Valor</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5">Descricao</th>
                </tr>
              </thead>
              <tbody>
                {movements.map((m) => (
                  <tr key={m.id} className="border-b border-border last:border-0">
                    <td className="px-3 py-2.5 font-mono text-[12px] text-text-muted">{new Date(m.movement_date).toLocaleDateString('pt-PT')}</td>
                    <td className="px-3 py-2.5 text-[13px] text-text-primary">{MOVEMENT_TYPES.find((t) => t.value === m.movement_type)?.label || m.movement_type}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-[13px] text-text-primary">{Number(m.amount).toFixed(2)} Kz</td>
                    <td className="px-3 py-2.5 text-[12px] text-text-muted">{m.description || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
