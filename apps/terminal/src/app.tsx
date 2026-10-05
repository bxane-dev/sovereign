import React, {useEffect, useMemo, useRef, useState} from "react";
import {Box, Text, useApp, useInput} from "ink";

import {HELP_TEXT, parseInput} from "./commands.ts";
import {SovereignApi} from "./client.ts";
import {computeTerminalLayout} from "./layout.ts";
import type {SovereignStatus, ToolsResponse} from "./types.ts";

type LineKind = "user" | "assistant" | "system" | "error";

interface TranscriptLine {
  id: number;
  kind: LineKind;
  text: string;
}

function prefix(kind: LineKind): string {
  switch (kind) {
    case "user":
      return "you";
    case "assistant":
      return "sovereign";
    case "error":
      return "error";
    default:
      return "system";
  }
}

export function App({api}: {api: SovereignApi}) {
  const {exit} = useApp();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [status, setStatus] = useState<SovereignStatus | null>(null);
  const [lines, setLines] = useState<TranscriptLine[]>([
    {
      id: 1,
      kind: "system",
      text: "Sovereign terminal. Type /help for commands.",
    },
  ]);
  const nextId = useRef(2);
  const [pendingApprovals, setPendingApprovals] = useState<Set<string>>(
    new Set(),
  );

  const layout = useMemo(
    () =>
      computeTerminalLayout(
        process.stdout.columns ?? 100,
        process.stdout.rows ?? 32,
      ),
    [],
  );

  const append = (kind: LineKind, text: string) => {
    const id = nextId.current++;
    setLines((current) => [...current, {id, kind, text}]);
  };

  const refreshStatus = async () => {
    try {
      const next = await api.status();
      setStatus(next);
      setConnected(true);
      return next;
    } catch (error) {
      setConnected(false);
      throw error;
    }
  };

  useEffect(() => {
    void refreshStatus().catch((error) => {
      append(
        "error",
        error instanceof Error ? error.message : String(error),
      );
    });
  }, []);

  const showTools = async () => {
    const tools: ToolsResponse = await api.tools();
    append(
      "system",
      [
        `native: ${tools.native_tools.join(", ") || "(none)"}`,
        `mcp: ${tools.mcp_servers.join(", ") || "(none)"}`,
      ].join("\n"),
    );
  };

  const submit = async (raw: string) => {
    const parsed = parseInput(raw);
    if (parsed.kind === "empty") return;

    if (parsed.kind === "quit") {
      exit();
      return;
    }
    if (parsed.kind === "clear") {
      setLines([]);
      return;
    }
    if (parsed.kind === "help") {
      append("system", HELP_TEXT);
      return;
    }
    if (parsed.kind === "approve") {
      setPendingApprovals((current) => {
        const next = new Set(current);
        next.add(parsed.tool);
        return next;
      });
      append("system", `approved for next prompt: ${parsed.tool}`);
      return;
    }
    if (parsed.kind === "revoke") {
      setPendingApprovals((current) => {
        const next = new Set(current);
        next.delete(parsed.tool);
        return next;
      });
      append("system", `revoked next-run approval: ${parsed.tool}`);
      return;
    }
    if (parsed.kind === "unknown") {
      append("error", `unknown command: ${parsed.command}`);
      return;
    }

    setBusy(true);
    try {
      if (parsed.kind === "status") {
        const next = await refreshStatus();
        append(
          "system",
          [
            `Sovereign ${next.version}`,
            `permission: ${next.permission_mode}`,
            `workspace: ${next.workspace}`,
            `computer control: ${next.computer_control_enabled ? "enabled" : "disabled"}`,
            `filesystem writes: ${next.filesystem_write_enabled ? "enabled" : "disabled"}`,
          ].join("\n"),
        );
        return;
      }

      if (parsed.kind === "tools") {
        await showTools();
        return;
      }

      if (parsed.kind === "prompt") {
        append("user", parsed.prompt);
        const approvedTools = [...pendingApprovals];
        setPendingApprovals(new Set());
        const result = await api.run({
          prompt: parsed.prompt,
          approved_tools: approvedTools,
        });
        setConnected(true);
        append(
          "assistant",
          `${result.text}\n[backend=${result.backend} steps=${result.steps} tools=${result.tool_calls}]`,
        );
      }
    } catch (error) {
      setConnected(false);
      append(
        "error",
        error instanceof Error ? error.message : String(error),
      );
    } finally {
      setBusy(false);
    }
  };

  useInput((typed, key) => {
    if (key.ctrl && typed === "c") {
      exit();
      return;
    }
    if (busy) return;
    if (key.return) {
      const value = input;
      setInput("");
      void submit(value);
      return;
    }
    if (key.backspace || key.delete) {
      setInput((value) => value.slice(0, -1));
      return;
    }
    if (typed && !key.ctrl) {
      setInput((value) => value + typed);
    }
  });

  const visibleLines = lines.slice(-Math.max(4, layout.transcriptHeight - 2));
  const approvalText =
    pendingApprovals.size > 0
      ? [...pendingApprovals].join(", ")
      : "(none)";

  return (
    <Box flexDirection="column" width={layout.contentWidth}>
      <Box justifyContent="space-between">
        <Text bold>SOVEREIGN</Text>
        <Text>
          {connected === true
            ? `connected • v${status?.version ?? "?"}`
            : connected === false
              ? "offline"
              : "connecting"}
        </Text>
      </Box>

      <Box flexDirection="column" marginTop={1}>
        {visibleLines.map((line) => (
          <Text key={line.id}>
            <Text bold>{prefix(line.kind)}: </Text>
            {line.text}
          </Text>
        ))}
      </Box>

      <Box flexDirection="column" marginTop={1}>
        <Text dimColor>next-run approvals: {approvalText}</Text>
        <Text>
          <Text bold>{busy ? "working…" : "> "}</Text>
          {busy ? "" : input}
          {!busy ? <Text inverse> </Text> : null}
        </Text>
      </Box>
    </Box>
  );
}
