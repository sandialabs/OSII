/** Friendly labels are independent of stable IDs and credential references. */
export function suggestedConnectionName(endpoint: string, model = ""): string {
  let host = "Connection";
  try {
    const hostname = new URL(endpoint).hostname;
    host = ["localhost", "127.0.0.1", "[::1]"].includes(hostname) ? "Local" : hostname.replace(/^(www\.|api\.)/, "").split(".")[0];
    host = host.charAt(0).toUpperCase() + host.slice(1);
  } catch { /* An incomplete address is normal while typing. */ }
  const shortModel = model.split("/").pop() ?? "";
  return shortModel ? `${host} · ${shortModel}` : host;
}

export function sameEndpoint(first: string, second: string): boolean {
  try {
    return new URL(first).href.replace(/\/+$/, "") === new URL(second).href.replace(/\/+$/, "");
  } catch { return false; }
}
