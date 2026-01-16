import type { AgentRequest, AgentResponse } from "../types/api";
import { httpJson } from "./http";

/**
 * Calls the backend agent endpoint.
 *
 * Backend contract:
 * - Endpoint: POST `${baseUrl}/agent`
 * - Request: { query, max_steps, session_id }
 * - Response: { response, tool_trace, occurrences?, artifacts?, session_id? }
 */
export async function runAgent(baseUrl: string, req: AgentRequest): Promise<AgentResponse> {
  const b = baseUrl.replace(/\/$/, "");
  return await httpJson<AgentResponse>(`${b}/agent/`, {
    method: "POST",
    json: {
      query: req.query,
      max_steps: req.max_steps ?? 3,
      session_id: req.session_id ?? null,
    },
  });
}

