// The name a document is saved under: the parts joined by «_», each without spaces (a «-» instead), accents or the
// characters a file system refuses - pdfFileName('MEL DA ROCHA', 'FT2026/2', 'A4') -> MEL-DA-ROCHA_FT2026-2_A4.pdf.
export function fileNamePart(text) {
  return String(text ?? '')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')  // Relatório -> Relatorio
    .replace(/[\\/:*?"<>|·()[\]{},;]+/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

export function pdfFileName(...parts) {
  const name = parts.map(fileNamePart).filter(Boolean).join('_') || 'documento';
  return name.replace(/\.pdf$/i, '') + '.pdf';
}

