// Every form's browser checks (required, min, max, email...) reported as a toast in PT-PT, like every other message
// of the app - instead of the browser's own bubble, in the browser's language. Installed once, for all screens.
import { toast } from '../store/toastStore';

// The field's visible label: a <label for>, else the nearest label above it in its block (the app's forms put the
// label just before the field, in the same wrapper).
function fieldLabel(el) {
  const own = el.labels && el.labels[0];
  let text = own ? own.textContent : '';
  for (let node = el.parentElement, depth = 0; !text && node && depth < 4; node = node.parentElement, depth += 1) {
    const label = Array.from(node.querySelectorAll('label')).find((l) => !l.contains(el) && l.textContent.trim());
    if (label) text = label.textContent;
  }
  return (text || el.getAttribute('placeholder') || '').replace(/\*/g, '').trim();
}

function message(el) {
  const label = fieldLabel(el);
  const name = label ? '«' + label + '»' : 'este campo';
  const v = el.validity;
  if (v.valueMissing) return el.type === 'checkbox' ? 'Marque ' + name + '.' : 'Preencha o campo ' + name + '.';
  if (v.rangeUnderflow) return 'O valor de ' + name + ' tem de ser no mínimo ' + el.min + '.';
  if (v.rangeOverflow) return 'O valor de ' + name + ' tem de ser no máximo ' + el.max + '.';
  if (v.stepMismatch) return 'O valor de ' + name + ' não é válido (casas decimais a mais?).';
  if (v.typeMismatch) return el.type === 'email' ? 'O email em ' + name + ' não é válido.' : 'O valor de ' + name + ' não é válido.';
  if (v.tooShort) return name.charAt(0).toUpperCase() + name.slice(1) + ' precisa de pelo menos ' + el.minLength + ' caracteres.';
  if (v.tooLong) return name.charAt(0).toUpperCase() + name.slice(1) + ' tem caracteres a mais (máximo ' + el.maxLength + ').';
  if (v.badInput) return 'O valor de ' + name + ' não é válido.';
  return el.validationMessage ? name.charAt(0).toUpperCase() + name.slice(1) + ': valor inválido.' : '';
}

let reported = false; // one toast per submit attempt: the first wrong field, the one that gets the focus

export function installFormValidationToasts() {
  document.addEventListener('invalid', (event) => {
    const el = event.target;
    if (!(el instanceof HTMLElement) || !el.validity) return;
    event.preventDefault(); // no browser bubble
    if (reported) return;
    reported = true;
    setTimeout(() => { reported = false; }, 0);
    el.focus({ preventScroll: false });
    toast.error(message(el));
  }, true); // 'invalid' does not bubble: caught on the way down
}
