import apiClient from "./client";

export const ticketsApi = {
  // filters: { status, assignee_id, priority, ticket_type, sprint_id, epic_id, label_id, search }
  list: (filters = {}) => {
    const params = Object.fromEntries(
      Object.entries(filters).filter(([, v]) => v !== "" && v != null)
    );
    return apiClient.get("/tickets/", { params }).then((r) => r.data);
  },
  get: (id) => apiClient.get(`/tickets/${id}`).then((r) => r.data),
  create: (payload) => apiClient.post("/tickets/", payload).then((r) => r.data),
  update: (id, payload) => apiClient.patch(`/tickets/${id}`, payload).then((r) => r.data),
  // Drag-and-drop: land in `status`, between before_id and after_id.
  move: (id, payload) => apiClient.patch(`/tickets/${id}/move`, payload).then((r) => r.data),
  remove: (id) => apiClient.delete(`/tickets/${id}`),
  activity: (id) => apiClient.get(`/tickets/${id}/activity`).then((r) => r.data),
};

export const commentsApi = {
  list: (ticketId) => apiClient.get(`/tickets/${ticketId}/comments/`).then((r) => r.data),
  create: (ticketId, body) =>
    apiClient.post(`/tickets/${ticketId}/comments/`, { body }).then((r) => r.data),
};

export const labelsApi = {
  list: () => apiClient.get("/labels/").then((r) => r.data),
  create: (payload) => apiClient.post("/labels/", payload).then((r) => r.data),
  update: (id, payload) => apiClient.patch(`/labels/${id}`, payload).then((r) => r.data),
  remove: (id) => apiClient.delete(`/labels/${id}`),
};

export const sprintsApi = {
  list: () => apiClient.get("/sprints/").then((r) => r.data),
  create: (payload) => apiClient.post("/sprints/", payload).then((r) => r.data),
  update: (id, payload) => apiClient.patch(`/sprints/${id}`, payload).then((r) => r.data),
  tickets: (id) => apiClient.get(`/sprints/${id}/tickets`).then((r) => r.data),
};

export const usersApi = {
  list: () => apiClient.get("/users/").then((r) => r.data),
  setRole: (id, role) => apiClient.patch(`/users/${id}/role`, { role }).then((r) => r.data),
};

/** Axios errors are noisy; pull out the one line worth showing a user. */
export function errorMessage(err, fallback = "Something went wrong.") {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  if (err?.code === "ERR_NETWORK") return "Can't reach the server. Is the backend running?";
  return fallback;
}
