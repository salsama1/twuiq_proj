import { httpJson } from "./http";

export type JobResponse = {
  id: string;
  type: string;
  status: "pending" | "queued" | "running" | "succeeded" | "failed" | string;
  created_at?: string | null;
  updated_at?: string | null;
  progress?: number | null;
  message?: string | null;
  result?: any;
  error?: string | null;
};

export async function fetchJob(baseUrl: string, jobId: string): Promise<JobResponse> {
  const b = baseUrl.replace(/\/$/, "");
  return await httpJson<JobResponse>(`${b}/jobs/${encodeURIComponent(jobId)}`, { method: "GET" });
}

