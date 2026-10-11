// Pessoa singular or coletiva - it decides the withholding at the source (only a pessoa coletiva keeps one).
export const FINAL_CONSUMER_NIF = '999999999';

// A company's NIF in Angola has 10 digits and starts with 5 (e.g. 5000999012); a person's NIF is his BI number.
// Only a proposal for the quick customer forms: the user confirms or changes it.
export function guessLegalPersonType(nif) {
  return /^5\d{9}$/.test((nif || '').trim()) ? 'JURIDICA' : 'FISICA';
}

// A real pessoa coletiva - never the Consumidor final (NIF 999999999), whatever type was recorded for it.
export function isPessoaColetiva(customer) {
  return customer?.legal_person_type === 'JURIDICA' && !customer?.is_final_consumer && customer?.nif !== FINAL_CONSUMER_NIF;
}

export const LEGAL_PERSON_OPTIONS = [
  { value: 'FISICA', label: 'Pessoa singular' },
  { value: 'JURIDICA', label: 'Pessoa coletiva (empresa)' },
];
