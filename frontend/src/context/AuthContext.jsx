import { createContext, useContext, useState, useEffect } from "react";
import apiClient from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(localStorage.getItem("access_token"));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      apiClient
        .get("/auth/me")
        .then((res) => setUser(res.data))
        .catch(() => {
          localStorage.removeItem("access_token");
          setToken(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = async (email, password) => {
    const formData = new URLSearchParams();
    formData.append("username", email);
    formData.append("password", password);

    const { data } = await apiClient.post("/auth/login", formData, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });

    localStorage.setItem("access_token", data.access_token);
    setToken(data.access_token);
  };

  const register = async (fullName, email, password) => {
    // Deliberately no `role` in this payload. The server assigns it (first
    // account becomes admin, everyone after is a developer); accepting a role
    // from the client is exactly the privilege-escalation hole we closed.
    await apiClient.post("/auth/register", {
      full_name: fullName,
      email,
      password,
    });
    // Registration doesn't return a token, so sign in with the same credentials.
    await login(email, password);
  };

  const logout = () => {
    localStorage.removeItem("access_token");
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ token, user, isAuthenticated: !!token, login, register, logout, loading }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}