import axios from "axios";

// Set VITE_API_URL at build time in production (Render injects it from the
// service's env vars during `npm run build`); falls back to the local
// backend for `npm run dev`.
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://127.0.0.1:8000",
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// A 401 means one of two very different things, and they need opposite handling:
//
//   * an EXPIRED SESSION on any ordinary call -- the token is dead, so drop it
//     and bounce to the login page.
//   * WRONG CREDENTIALS on the sign-in/sign-up calls themselves -- the form is
//     about to render "Incorrect email or password" from the same rejection.
//     Redirecting here reloads the page out from under it, which wipes that
//     message before it can be read: you type the wrong password and get a
//     blank form back with no idea why.
//
// Only the credential endpoints are excluded, NOT all of /auth/ -- a 401 from
// /auth/me really does mean the session died, and refreshUser() has no catch of
// its own to fall back on.
//
// Exported for the unit test.
const CREDENTIAL_ROUTES = ["/auth/login", "/auth/signup"];

export function isSessionExpiry(error) {
  if (error.response?.status !== 401) return false;
  const url = error.config?.url || "";
  return !CREDENTIAL_ROUTES.some((route) => url.startsWith(route));
}

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (isSessionExpiry(error)) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default apiClient;