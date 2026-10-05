import type {
  ComputerRunRequest,
  ComputerRunResponse,
  RunRequest,
  RunResponse,
  SovereignStatus,
  ToolsResponse,
} from "./types.ts";

export class SovereignApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "SovereignApiError";
  }
}

export class SovereignApi {
  readonly baseUrl: string;

  constructor(baseUrl = "http://127.0.0.1:8765") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          "content-type": "application/json",
          ...(init?.headers ?? {}),
        },
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      throw new SovereignApiError(
        `Cannot reach Sovereign at ${this.baseUrl}: ${detail}`,
      );
    }

    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const detail =
        body && typeof body === "object" && "detail" in body
          ? String((body as { detail: unknown }).detail)
          : `HTTP ${response.status}`;
      throw new SovereignApiError(detail, response.status);
    }
    return body as T;
  }

  health(): Promise<{ ok: boolean; service: string; version: string }> {
    return this.request("/health");
  }

  status(): Promise<SovereignStatus> {
    return this.request("/v1/status");
  }

  tools(): Promise<ToolsResponse> {
    return this.request("/v1/tools");
  }

  run(payload: RunRequest): Promise<RunResponse> {
    return this.request("/v1/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  computerRun(payload: ComputerRunRequest): Promise<ComputerRunResponse> {
    return this.request("/v1/computer/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}
