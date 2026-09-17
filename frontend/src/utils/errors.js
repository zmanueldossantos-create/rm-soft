// Extracts a human-readable message from an API error response.
// FastAPI/Pydantic validation errors return detail as an array of
// {type, loc, msg, input, ctx} objects rather than a plain string -
// this normalizes both shapes to avoid crashing React (objects are not
// valid children) and to avoid showing raw error internals to the user.
export function extractErrorMessage(err, fallback) {
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
