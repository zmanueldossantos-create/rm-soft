// API client - connects to the FastAPI backend.
// The backend address: see ./config.js.
import { API_BASE_URL } from './config';
import axios from 'axios';
import { useAuthStore } from '../store/authStore';

// SaaS mode: the screen's own address tells the backend whose company this is (farmacia-da-luz.rmsystem.co.ao) - sent
// on every call, since in development the backend has another address than the screens.
const TENANT_HEADERS = { 'X-Tenant-Host': window.location.hostname };

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json', ...TENANT_HEADERS },
});

// Attaches the JWT access token to every outgoing request, if present.
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  // a call that brings its own token (a new session being opened: login, support access) keeps it
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = 'Bearer ' + token;
  }
  return config;
});

// Silent token refresh: when an access token expires (401), use the
// refresh token to get a new one and retry the original request once,
// so the user never sees a "session expired" interruption.
let refreshPromise = null;

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isAuthEndpoint = originalRequest.url?.includes('/auth/login') || originalRequest.url?.includes('/auth/refresh');

    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;
      const { refreshToken, login, logout, user } = useAuthStore.getState();

      if (!refreshToken) {
        logout();
        return Promise.reject(error);
      }

      try {
        if (!refreshPromise) {
          refreshPromise = axios.post(API_BASE_URL + '/auth/refresh', {
            refresh_token: refreshToken,
          }, { headers: TENANT_HEADERS }).finally(() => {
            refreshPromise = null;
          });
        }
        const refreshResponse = await refreshPromise;
        const newAccessToken = refreshResponse.data.access_token;

        login(newAccessToken, refreshToken, user);

        originalRequest.headers.Authorization = 'Bearer ' + newAccessToken;
        return apiClient(originalRequest);
      } catch (refreshError) {
        logout();
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
