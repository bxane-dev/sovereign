export type ParsedInput =
  | { kind: "empty" }
  | { kind: "prompt"; prompt: string }
  | { kind: "visual"; prompt: string }
  | { kind: "status" }
  | { kind: "tools" }
  | { kind: "session_new" }
  | { kind: "session_use"; id: string }
  | { kind: "sessions" }
  | { kind: "resume" }
  | { kind: "approve"; tool: string }
  | { kind: "revoke"; tool: string }
  | { kind: "clear" }
  | { kind: "help" }
  | { kind: "quit" }
  | { kind: "unknown"; command: string };

export function parseInput(raw: string): ParsedInput {
  const value = raw.trim();
  if (!value) return { kind: "empty" };
  if (!value.startsWith("/")) return { kind: "prompt", prompt: value };

  const [command, ...rest] = value.split(/\s+/);
  const argument = rest.join(" ").trim();

  switch (command.toLowerCase()) {
    case "/visual":
      return argument
        ? { kind: "visual", prompt: argument }
        : { kind: "unknown", command: value };
    case "/status":
      return { kind: "status" };
    case "/tools":
      return { kind: "tools" };
    case "/session":
      if (argument === "new") return { kind: "session_new" };
      return argument ? { kind: "session_use", id: argument } : { kind: "unknown", command: value };
    case "/sessions":
      return { kind: "sessions" };
    case "/resume":
      return { kind: "resume" };
    case "/approve":
      return argument
        ? { kind: "approve", tool: argument }
        : { kind: "unknown", command: value };
    case "/revoke":
      return argument
        ? { kind: "revoke", tool: argument }
        : { kind: "unknown", command: value };
    case "/clear":
      return { kind: "clear" };
    case "/help":
      return { kind: "help" };
    case "/quit":
    case "/exit":
      return { kind: "quit" };
    default:
      return { kind: "unknown", command: value };
  }
}

export const HELP_TEXT = [
  "/visual <task>         run screenshot-driven visual computer autonomy",
  "/status                show controller and permission status",
  "/tools                 list native, visual, and MCP tools",
  "/session new           start a persistent conversation",
  "/session <id>          switch to an existing conversation",
  "/sessions              list recent conversations",
  "/resume                resume an interrupted task",
  "/approve <tool>        approve a gated tool for the next prompt only",
  "/revoke <tool>         remove a pending next-run approval",
  "/clear                 clear the visible transcript",
  "/help                  show commands",
  "/quit                  exit the terminal client",
].join("\n");
