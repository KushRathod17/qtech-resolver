import { createContext, useContext, useState, useEffect } from "react";
import apiClient from "../api/client";
import { clearFileCache } from "../api/files";

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

  // Both signup paths return a token directly -- no separate login round trip
  // needed. Deliberately no `role` in either payload: the server decides
  // (first person in an org is its admin, everyone after is a developer):
  // accepting a role from the client is the privilege-escalation hole that
  // used to exist here.
  const signupNewOrganization = async ({ fullName, email, password, organizationName, keyPrefix, inviteCode }) => {
    const { data } = await apiClient.post("/auth/signup/organization", {
      full_name: fullName,
      email,
      password,
      organization_name: organizationName,
      key_prefix: keyPrefix,
      invite_code: inviteCode,
    });
    localStorage.setItem("access_token", data.access_token);
    setToken(data.access_token);
  };

  const signupJoinOrganization = async ({ fullName, email, password, organizationId, joinCode, inviteCode }) => {
    const { data } = await apiClient.post("/auth/signup/join", {
      full_name: fullName,
      email,
      password,
      organization_id: organizationId,
      join_code: joinCode,
      invite_code: inviteCode,
    });
    localStorage.setItem("access_token", data.access_token);
    setToken(data.access_token);
  };

  // Called after a profile edit so the top-bar avatar/name update without a reload.
  const refreshUser = async () => {
    const { data } = await apiClient.get("/auth/me");
    setUser(data);
  };

  const logout = () => {
    // Avatars and attachments are held as blob: URLs fetched with the old
    // token. Drop them rather than leaving one user's files in memory for the
    // next person to sign in on this machine.
    clearFileCache();
    localStorage.removeItem("access_token");
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        token, user, isAuthenticated: !!token, login,
        signupNewOrganization, signupJoinOrganization,
        logout, refreshUser, loading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}