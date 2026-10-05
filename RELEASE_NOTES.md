# Sovereign 8.0.0

Sovereign 8.0 adds a desktop shell for Windows, macOS, and Linux, with a bundled Python control plane and Bun terminal. Agent conversations now persist locally and interrupted tasks can be resumed without replaying an uncertain tool action. Native Ollama and Anthropic adapters complement OpenAI-compatible and Sovereign backends.

Visual autonomy now retries capture and backend requests, reports action failures to the next screenshot turn, and verifies actions on a fresh frame. The desktop shell uses a loopback API token, isolated renderer, and permission approvals for state-changing tools.

The desktop workspace defaults to dark mode, offers a light theme toggle, supports native right-click edit and copy menus, and sends with Enter (Shift+Enter inserts a newline). First-run setup reports the local config path and keeps Send disabled until a healthy reasoning backend is available. Desktop control can be explicitly enabled or disabled in the app, with per-run action approval retained. Plugins currently support configured local MCP servers; the OAuth connector catalog is not included in this preview.

The version badge shows the 8.0.0 product version and marks this build as a preview. Core API errors are shown without Electron IPC wrapper text, and the bundled Windows core is stopped with its process tree when the app closes.

Installers are built from the release tag. Windows and macOS release jobs require signing credentials; macOS is notarized. The app checks GitHub Releases for updates and asks before installing one.
