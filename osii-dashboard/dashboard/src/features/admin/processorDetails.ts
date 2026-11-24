import type { CapabilityReadiness, ProcessorEndpoint } from "../../api/types";

export function processorDetailsPath(id: string, registered = false) {
  return "/admin/processors/" + (registered ? "registered/" : "") + encodeURIComponent(id);
}

export function matchingEndpoint(item: CapabilityReadiness, endpoints: ProcessorEndpoint[]) {
  const matches = endpoints.filter(endpoint => endpoint.processor_id === item.id);
  return matches.find(endpoint => endpoint.base_url === item.base_url)
    ?? (item.base_url ? undefined : matches.find(endpoint => endpoint.built_in));
}
