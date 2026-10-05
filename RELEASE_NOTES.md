# Sovereign 8.0.0

Sovereign 8.0 adds a desktop shell for Windows, macOS, and Linux, with a bundled Python control plane and Bun terminal. Agent conversations now persist locally and interrupted tasks can be resumed without replaying an uncertain tool action. Native Ollama and Anthropic adapters complement OpenAI-compatible and Sovereign backends.

Visual autonomy now retries capture and backend requests, reports action failures to the next screenshot turn, and verifies actions on a fresh frame. The desktop shell uses a loopback API token, isolated renderer, and permission approvals for state-changing tools.

The desktop workspace now uses a warm, minimal chat layout with a Plugins view for configured MCP servers. First-run setup reports the local config path and keeps Send disabled until a healthy reasoning backend is available. Core API errors are shown without Electron IPC wrapper text.

Installers are built from the release tag. Windows and macOS release jobs require signing credentials; macOS is notarized. The app checks GitHub Releases for updates and asks before installing one.
