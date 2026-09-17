// API client - connects to the FastAPI backend.
// Base URL points to the local backend (port 8001, see backend .env).
import axios from 'axios';
import { useAuthStore } from '../store/authStore';

const apiClient = axios.create({
  baseURL: 'http://127.0.0.1:8001/api/v1',
  headers: { 'Content-Type': 'application/json' },
});

// Attaches the JWT access token to every outgoing request, if present.
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
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
          refreshPromise = axios.post('http://127.0.0.1:8001/api/v1/auth/refresh', {
            refresh_token: refreshToken,
          }).finally(() => {
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
