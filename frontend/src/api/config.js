// Where the backend is - the only place in the frontend that knows it.
// In development ('npm run dev'): the backend of this machine, directly.
// In an installation build: the same server that served the screens, which passes /api/v1 and /uploads to the
// backend - one build for every client, whatever the address of its server.
export const API_BASE_URL = import.meta.env.DEV ? 'http://127.0.0.1:8001/api/v1' : '/api/v1';

// The backend origin, for its files (logo, product images): '' in an installation, i.e. the same server.
export const API_ORIGIN = API_BASE_URL.replace(/\/api\/v1$/, '');
