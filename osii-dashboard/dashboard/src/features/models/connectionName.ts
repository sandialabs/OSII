/** Friendly labels are independent of stable IDs and credential references. */
export function suggestedConnectionName(endpoint: string): string {
  let host = "Connection";
  try {
    const hostname = new URL(endpoint).hostname;
    host = ["localhost", "127.0.0.1", "[::1]"].includes(hostname) ? "Local models" : /^[0-9.]+$/.test(hostname) || hostname.includes(":") ? "Model server" : hostname.replace(/^(?:(?:www|api)\.)+/, "").split(".")[0];
    host = host.charAt(0).toUpperCase() + host.slice(1);
  } catch { /* An incomplete address is normal while typing. */ }
  return host;
}

export function sameEndpoint(first: string, second: string): boolean {
  try {
    return new URL(first).href.replace(/\/+$/, "") === new URL(second).href.replace(/\/+$/, "");
  } catch { return false; }
}

type ConnectionIdentity = {id: string; type: string; base_url: string; credential_env: string; display_name?: string; chat_model?: string; embedding_model?: string};
/** Recognize the earlier automatic hostname-plus-model labels without changing IDs. */
export function connectionDisplayName(connection: ConnectionIdentity): string {
  const endpoint = suggestedConnectionName(connection.base_url);
  const name = connection.display_name?.trim();
  if (!name) return endpoint;
  const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, "");
  const models = [connection.chat_model, connection.embedding_model].filter(Boolean) as string[];
  return models.some(model => normalize(name) === normalize(endpoint + model.split("/").pop())) ? endpoint : name;
}

/** Group presentation only. Stable model aliases and credential references stay intact. */
export function groupModelConnections<T extends ConnectionIdentity>(connections: readonly T[]): {primary: T; members: T[]; name: string}[] {
  const groups = new Map<string, T[]>();
  for (const connection of connections) {
    let endpoint = connection.base_url.trim().replace(/\/+$/, "");
    try {endpoint = new URL(endpoint).href.replace(/\/+$/, "");} catch { /* Preserve malformed saved entries for repair. */ }
    const key = JSON.stringify([connection.type, endpoint, connection.credential_env]);
    groups.set(key, [...(groups.get(key) || []), connection]);
  }
  return [...groups.values()].map(members => {
    const primary = members.find(connection => connection.chat_model) || members[0];
    return {primary, members, name: connectionDisplayName(primary.display_name ? primary : members.find(member => member.display_name) || primary)};
  });
}
