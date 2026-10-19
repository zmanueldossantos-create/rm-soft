import Select from './Select';

// The exemption motive of an exempt (ISE) article - one field for products, services and the grouped reclassification:
// - the company's regime imposes a motive (Simplificado M00, Exclusão M04): shown locked; if the regime keeps some
//   exemptions (M11 medicines...: Configurações -> Regimes Fiscais), they can be chosen instead (empty = the imposed one);
// - otherwise the article chooses its motive among the active ones.
export default function ExemptionMotiveField({ rule, value, onChange, vatCodes, lockedClass }) {
  const imposed = rule?.exemption;
  const kept = rule?.kept || [];
  if (imposed && kept.length === 0) {
    return (
      <>
        <div className={lockedClass + ' opacity-80 cursor-not-allowed truncate'}>{imposed.code + ' - ' + imposed.name}</div>
        <p className="text-[11px] text-text-muted mt-1">{'Imposto pelo ' + (rule.regime || 'regime da empresa')}</p>
      </>
    );
  }
  if (imposed) {
    const keptIds = kept.map((k) => k.id);
    return (
      <>
        <Select
          value={keptIds.includes(value) ? value : ''}
          onChange={onChange}
          options={[{ value: '', label: imposed.code + ' - ' + imposed.name }, ...kept.map((k) => ({ value: k.id, label: k.code + ' - ' + k.name }))]}
        />
        <p className="text-[11px] text-text-muted mt-1">{'Imposto pelo ' + (rule.regime || 'regime da empresa') + ', salvo as isenções que o regime mantém'}</p>
      </>
    );
  }
  return <Select value={value} onChange={onChange} options={vatCodes.map((c) => ({ value: c.id, label: c.code + ' - ' + c.name }))} placeholder="Selecionar motivo" />;
}
