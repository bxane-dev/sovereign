# Security and permission review

Sovereign runs with the desktop user's permissions. The Python core enforces workspace path roots, separate computer and visual autonomy switches, and exact per-run approval for state-changing native tools and all configured MCP tools. Models cannot grant their own approvals. The desktop app binds the core to a random loopback port and a per-launch bearer token, with an isolated Electron renderer and an IPC route allowlist. Non-loopback API binding requires an explicit token.

Sessions are stored as plain SQLite files in the configured workspace. Prompts, model replies, tool results, and inline attachments in reasoning sessions may contain sensitive information. Protect the workspace with operating-system account permissions and delete sessions that are no longer needed. The app does not upload session history except when sending selected messages to configured model backends.

Visual actions are not retried automatically after an execution error because their result may be uncertain. After a process interruption, a pending reasoning tool call is reported to the model as an unknown outcome and is never replayed without a new decision. Screenshot and backend request retries are bounded by config. Permission failures stop the visual run.

The release workflow requires Windows and macOS signing credentials. Unsigned local preview packages are for testing only. Review configured backend URLs and MCP server commands before use; they are executed with the local user's network and process access.
