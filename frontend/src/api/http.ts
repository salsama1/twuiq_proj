/**
 * Minimal JSON HTTP helper.
 *
 * - If `init.json` is provided, it is JSON-stringified and Content-Type is set.
 * - Throws on non-2xx responses and includes response text when available.
 */
export async function httpJson<T>(
  url: string,
  init?: RequestInit & { json?: unknown }
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  let body = init?.body;
  if (init && "json" in init) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }

  const res = await fetch(url, { ...init, headers, body });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${text}`.trim());
  }
  return (await res.json()) as T;
}

