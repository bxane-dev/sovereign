import {describe, expect, test} from "bun:test";

import {parseInput} from "../src/commands.ts";

describe("terminal commands", () => {
  test("plain text becomes a prompt", () => {
    expect(parseInput("inspect the repo")).toEqual({
      kind: "prompt",
      prompt: "inspect the repo",
    });
  });

  test("visual command carries the task", () => {
    expect(parseInput("/visual open the editor")).toEqual({
      kind: "visual",
      prompt: "open the editor",
    });
  });

  test("approval commands preserve exact tool names", () => {
    expect(parseInput("/approve sovereign__mouse_click")).toEqual({
      kind: "approve",
      tool: "sovereign__mouse_click",
    });
    expect(parseInput("/revoke sovereign__mouse_click")).toEqual({
      kind: "revoke",
      tool: "sovereign__mouse_click",
    });
  });

  test("known control commands parse", () => {
    expect(parseInput("/status")).toEqual({kind: "status"});
    expect(parseInput("/tools")).toEqual({kind: "tools"});
    expect(parseInput("/clear")).toEqual({kind: "clear"});
    expect(parseInput("/help")).toEqual({kind: "help"});
    expect(parseInput("/quit")).toEqual({kind: "quit"});
    expect(parseInput("/session new")).toEqual({kind: "session_new"});
    expect(parseInput("/session abc")).toEqual({kind: "session_use", id: "abc"});
    expect(parseInput("/sessions")).toEqual({kind: "sessions"});
    expect(parseInput("/resume")).toEqual({kind: "resume"});
  });
});
