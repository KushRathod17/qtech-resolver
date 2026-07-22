import { describe, it, expect } from "vitest";

import { isSessionExpiry } from "./client";

/** Shaped like the axios error the response interceptor actually receives. */
function axiosError(status, url) {
  return { response: { status }, config: { url } };
}

describe("isSessionExpiry", () => {
  it("treats a 401 on an ordinary call as an expired session", () => {
    expect(isSessionExpiry(axiosError(401, "/tickets/"))).toBe(true);
  });

  it("does NOT bounce on a failed sign-in", () => {
    // THE BUG: a wrong password redirected to /login, and the page reload wiped
    // the "Incorrect email or password" message the form had just set -- you
    // got a blank form back with no idea what went wrong.
    expect(isSessionExpiry(axiosError(401, "/auth/login"))).toBe(false);
  });

  it("does NOT bounce on a failed sign-up", () => {
    expect(isSessionExpiry(axiosError(401, "/auth/signup/join"))).toBe(false);
    expect(isSessionExpiry(axiosError(401, "/auth/signup/organization"))).toBe(false);
  });

  it("DOES bounce when /auth/me rejects -- that one is a real expiry", () => {
    // Deliberately not covered by the exclusion: refreshUser() has no catch of
    // its own, so without the redirect an expired session strands the user.
    expect(isSessionExpiry(axiosError(401, "/auth/me"))).toBe(true);
  });

  it("ignores non-401 failures", () => {
    // 429 is the login throttle -- the form shows "try again in N minutes", and
    // reloading would wipe that too.
    expect(isSessionExpiry(axiosError(429, "/auth/login"))).toBe(false);
    expect(isSessionExpiry(axiosError(403, "/tickets/"))).toBe(false);
    expect(isSessionExpiry(axiosError(500, "/tickets/"))).toBe(false);
  });

  it("survives a network error, where there is no response at all", () => {
    expect(isSessionExpiry({ code: "ERR_NETWORK", config: { url: "/tickets/" } })).toBe(false);
    expect(isSessionExpiry({})).toBe(false);
  });
});
