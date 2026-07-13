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
  // One request for the whole selection, not one per ticket.
  bulkUpdate: (payload) => apiClient.patch("/tickets/bulk", payload).then((r) => r.data),
  bulkDelete: (ticketIds) =>
    apiClient.post("/tickets/bulk/delete", { ticket_ids: ticketIds }).then((r) => r.data),
  activity: (id) => apiClient.get(`/tickets/${id}/activity`).then((r) => r.data),
  clients: () => apiClient.get("/tickets/clients").then((r) => r.data),
  epics: () => apiClient.get("/tickets/epics").then((r) => r.data),

  addSubtask: (id, payload) =>
    apiClient.post(`/tickets/${id}/subtasks`, payload).then((r) => r.data),
  duplicate: (id) => apiClient.post(`/tickets/${id}/duplicate`).then((r) => r.data),
  convertToEpic: (id) => apiClient.post(`/tickets/${id}/convert-to-epic`).then((r) => r.data),

  watch: (id) => apiClient.post(`/tickets/${id}/watch`).then((r) => r.data),
  unwatch: (id) => apiClient.delete(`/tickets/${id}/watch`).then((r) => r.data),

  uploadAttachment: (id, file) => {
    const body = new FormData();
    body.append("file", file);
    return apiClient.post(`/tickets/${id}/attachments`, body).then((r) => r.data);
  },
  deleteAttachment: (ticketId, attachmentId) =>
    apiClient.delete(`/tickets/${ticketId}/attachments/${attachmentId}`),
};

export const filtersApi = {
  list: () => apiClient.get("/filters/").then((r) => r.data),
  create: (payload) => apiClient.post("/filters/", payload).then((r) => r.data),
  update: (id, payload) => apiClient.patch(`/filters/${id}`, payload).then((r) => r.data),
  remove: (id) => apiClient.delete(`/filters/${id}`),
};

export const commentsApi = {
  list: (ticketId) => apiClient.get(`/tickets/${ticketId}/comments/`).then((r) => r.data),
  create: (ticketId, body, mentionUserIds = []) =>
    apiClient
      .post(`/tickets/${ticketId}/comments/`, { body, mention_user_ids: mentionUserIds })
      .then((r) => r.data),
};

export const teamsApi = {
  list: () => apiClient.get("/teams/").then((r) => r.data),
  members: (id) => apiClient.get(`/teams/${id}/members`).then((r) => r.data),
  create: (payload) => apiClient.post("/teams/", payload).then((r) => r.data),
  update: (id, payload) => apiClient.patch(`/teams/${id}`, payload).then((r) => r.data),
  remove: (id) => apiClient.delete(`/teams/${id}`),
};

export const workflowApi = {
  // The chain of custody for one ticket.
  handoffs: (ticketId) => apiClient.get(`/tickets/${ticketId}/handoffs`).then((r) => r.data),
  handoff: (ticketId, payload) =>
    apiClient.post(`/tickets/${ticketId}/handoff`, payload).then((r) => r.data),

  report: () => apiClient.get("/reports/workflow").then((r) => r.data),
  holdingTimes: () => apiClient.get("/reports/team-holding-times").then((r) => r.data),
};

export const componentsApi = {
  list: () => apiClient.get("/components/").then((r) => r.data),
  stats: () => apiClient.get("/components/stats").then((r) => r.data),
  create: (payload) => apiClient.post("/components/", payload).then((r) => r.data),
  update: (id, payload) => apiClient.patch(`/components/${id}`, payload).then((r) => r.data),
  remove: (id) => apiClient.delete(`/components/${id}`),
  tickets: (id) => apiClient.get(`/components/${id}/tickets`).then((r) => r.data),
};

export const slaApi = {
  list: () => apiClient.get("/sla/").then((r) => r.data),
  set: (priority, thresholdHours) =>
    apiClient.patch(`/sla/${priority}`, { threshold_hours: thresholdHours }).then((r) => r.data),
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
  remove: (id) => apiClient.delete(`/sprints/${id}`),
  tickets: (id) => apiClient.get(`/sprints/${id}/tickets`).then((r) => r.data),
  stats: (id) => apiClient.get(`/sprints/${id}/stats`).then((r) => r.data),
  burndown: (id) => apiClient.get(`/sprints/${id}/burndown`).then((r) => r.data),
  velocity: () => apiClient.get("/sprints/velocity").then((r) => r.data),
};

export const usersApi = {
  list: () => apiClient.get("/users/").then((r) => r.data),
  setRole: (id, role) => apiClient.patch(`/users/${id}/role`, { role }).then((r) => r.data),
  setTeam: (id, teamId) =>
    apiClient.patch(`/users/${id}/team`, { team_id: teamId || null }).then((r) => r.data),

  me: () => apiClient.get("/users/me").then((r) => r.data),
  profile: (id) => apiClient.get(`/users/${id}`).then((r) => r.data),
  stats: (id) => apiClient.get(`/users/${id}/stats`).then((r) => r.data),
  tickets: (id) => apiClient.get(`/users/${id}/tickets`).then((r) => r.data),

  updateMe: (payload) => apiClient.patch("/users/me", payload).then((r) => r.data),
  changePassword: (currentPassword, newPassword) =>
    apiClient.post("/users/me/password", {
      current_password: currentPassword,
      new_password: newPassword,
    }),
  uploadAvatar: (file) => {
    const body = new FormData();
    body.append("file", file);
    // Let the browser set the multipart boundary — hardcoding the Content-Type
    // here would omit it and the server would reject the body.
    return apiClient.post("/users/me/avatar", body).then((r) => r.data);
  },
};

/** Axios errors are noisy; pull out the one line worth showing a user. */
export function errorMessage(err, fallback = "Something went wrong.") {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  if (err?.code === "ERR_NETWORK") return "Can't reach the server. Is the backend running?";
  return fallback;
}
