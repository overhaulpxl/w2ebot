"use client";

export async function phase9bMutation<T>(route: string, body: Record<string, unknown>, requestId: string): Promise<T> {
  const csrfQuery = new URLSearchParams({ method: "POST", route, requestId });
  const csrfResponse = await fetch(`/api/auth/csrf?${csrfQuery}`, { cache: "no-store" });
  if (!csrfResponse.ok) throw new Error("csrf_unavailable");
  const csrf = await csrfResponse.json() as { token: string };
  const response = await fetch(route, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf.token },
    body: JSON.stringify({ ...body, requestId }),
  });
  const data = await response.json().catch(() => ({ error: "internal_error" }));
  if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : "internal_error");
  return data as T;
}
