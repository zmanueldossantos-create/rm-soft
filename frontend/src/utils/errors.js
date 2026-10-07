// Extracts a human-readable message from an API error response.
// FastAPI/Pydantic validation errors return detail as an array of
// {type, loc, msg, input, ctx} objects rather than a plain string -
// this normalizes both shapes to avoid crashing React (objects are not
// valid children) and to avoid showing raw error internals to the user.
export function extractErrorMessage(err, fallback) {
  // No answer at all (server stopped, network down): say so instead of each screen's generic message.
  if (err && !err.response && err.request) {
    return 'Servidor inacessivel - verifique a ligacao ou se o servidor esta ativo';
  }
  const detail = err.response?.data?.detail;

  if (!detail) return fallback;

  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item.msg || fallback).replace(/^Value error,\s*/i, ''))
      .join(' ');
  }

  return fallback;
}
