export type Capability =
  | "reasoning"
  | "vision"
  | "image_generation"
  | "video_generation"
  | "tools";

export interface SovereignStatus {
  version: string;
  controller: string;
  permission_mode: string;
  workspace: string;
  backends: Array<{
    name: string;
    healthy: boolean;
    enabled: boolean;
    priority: number;
    protocol: string;
    model: string | null;
    capabilities: string[];
  }>;
  mcp_servers: string[];
  native_tools: string[];
  computer_control_enabled: boolean;
  visual_autonomy_enabled: boolean;
  filesystem_write_enabled: boolean;
}

export interface ToolsResponse {
  native_tools: string[];
  visual_action_tools: string[];
  mcp_servers: string[];
}

export interface RunRequest {
  prompt: string;
  capability?: Capability;
  attachments?: string[];
  max_steps?: number;
  approved_tools?: string[];
  session_id?: string;
}

export interface SessionSummary {
  id: string;
  capability: Capability;
  status: "idle" | "running" | "completed" | "interrupted";
  created_at: string;
  updated_at: string;
  error: string | null;
  message_count: number;
}

export interface SessionDetail extends SessionSummary {
  messages: Array<Record<string, unknown>>;
}

export interface RunResponse {
  text: string;
  backend: string;
  capability: Capability;
  steps: number;
  tool_calls: number;
}

export interface ComputerRunRequest {
  prompt: string;
  max_steps?: number;
  approved_tools?: string[];
}

export interface ComputerRunResponse {
  text: string;
  backend: string;
  frames: number;
  tool_calls: number;
}
