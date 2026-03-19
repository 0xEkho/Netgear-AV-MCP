# NETGEAR M4250/M4300/M4350 — MCP Server 🔌

![Version](https://img.shields.io/badge/Version-1.0.0-blue)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![MCP](https://img.shields.io/badge/MCP-1.2.0-green)
![License](https://img.shields.io/badge/License-MIT-green)

An MCP (Model Context Protocol) server that exposes NETGEAR M4250/M4300/M4350 Pro AV network switches as AI-native tools. Connect any MCP-compatible LLM client (Claude Desktop, OpenWebUI, Cursor…) to your network infrastructure and query, monitor, or troubleshoot your NETGEAR switch fleet through natural language.

> **Target audience:** Network engineers and AV integrators who want to interact with NETGEAR Pro AV switches using AI assistants.

## ✨ Features

- **Dual HTTP transport** — `streamable-http` (recommended) and `SSE`, switchable via a single environment variable
- **SSH connectivity** — connects to NETGEAR switches over SSH using [asyncssh](https://asyncssh.readthedocs.io/)
- **Interactive shell handling** — automatic enable mode, pager bypass (`terminal length 0`), and `--More--` prompt handling
- **Multi-switch support** — target any switch by IP; credentials resolved per subnet zone or global fallback
- **Structured JSON output** — every tool returns a consistent, machine-readable JSON payload
- **Security middleware** — Bearer token authentication and IP allowlist (CIDR), enforced at the ASGI layer
- **OpenWebUI compatible** — works out of the box as an MCP Tool Server in OpenWebUI
- **Multi-model support** — M4250, M4300, and M4350 series with model-adaptive commands
- **11 NETGEAR tools** — device info, interfaces, VLANs, PoE, STP, routing, LLDP, config backup, and generic CLI
- **Read-only by design** — no tool can modify switch configuration

## 🔧 Available Tools

### Core & Device Info

| Tool | CLI Command | Description |
|------|-------------|-------------|
| `netgear_show_version` | `show version` / `show switch` | Model, serial, firmware, uptime (model-adaptive) |
| `netgear_show_hosts` | `show hosts` | Hostname, DNS domain, DNS servers |
| `netgear_config_backup` | `show running-config` | Full running configuration backup |

### Ports & Interfaces

| Tool | CLI Command | Description |
|------|-------------|-------------|
| `netgear_show_interfaces` | `show interface counters` | All ports traffic counters |
| `netgear_show_interface_port` | `show interfaces status <port>` + `show interface ethernet <port>` | Detailed single port statistics (port format: `1/0/X`) |

### VLAN

| Tool | CLI Command | Description |
|------|-------------|-------------|
| `netgear_show_vlan` | `show vlan` / `show interfaces switchport <port>` | All VLANs or per-port switchport config |

### PoE

| Tool | CLI Command | Description |
|------|-------------|-------------|
| `netgear_show_poe` | `show poe` | PoE power budget, consumption, per-port status |

### Spanning Tree

| Tool | CLI Command | Description |
|------|-------------|-------------|
| `netgear_show_spanning_tree` | `show spanning-tree` | STP bridge/root info |

### Routing

| Tool | CLI Command | Description |
|------|-------------|-------------|
| `netgear_show_ip_route` | `show ip route` | IP routing table |

### LLDP

| Tool | CLI Command | Description |
|------|-------------|-------------|
| `netgear_show_lldp` | `show lldp remote-device all` | LLDP neighbor discovery |

### Generic CLI

| Tool | CLI Command | Description |
|------|-------------|-------------|
| `netgear_cli_readonly` | Any `show ...` command | Execute any read-only CLI command |

## 🚀 Quick Start

**Prerequisites:** [Python 3.10+](https://www.python.org/downloads/) and [uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
# 1. Clone the repository
git clone https://github.com/0xEkho/Netgear-AV-MCP.git
cd Netgear-AV-MCP

# 2. Install dependencies
uv sync

# 3. Configure
cp .env.example .env
#    → Edit .env: set NETGEAR_GLOBAL_USERNAME, NETGEAR_GLOBAL_PASSWORD, MCP_API_KEY

# 4. Start the MCP server
uv run mcp-server
```

The server starts on `http://0.0.0.0:8082` (Streamable HTTP transport).

### 🐳 Docker (Production)

```bash
cp .env.example .env
# Edit .env
docker compose up -d
```

## ⚙️ Configuration

Copy `.env.example` to `.env` and adjust values. Never commit `.env` to version control.

### MCP Server

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_NAME` | `netgear-av-mcp` | Display name |
| `MCP_TRANSPORT` | `streamable-http` | Transport: `streamable-http`, `sse`, or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Bind address |
| `MCP_PORT` | `8082` | Listening port |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_API_KEY` | (empty) | Bearer token. Leave empty to disable. |
| `MCP_ALLOWED_IPS` | `127.0.0.1/32,...` | Comma-separated CIDR allowlist |

### SSH Credentials

| Variable | Default | Description |
|----------|---------|-------------|
| `NETGEAR_GLOBAL_USERNAME` | — | Default SSH username |
| `NETGEAR_GLOBAL_PASSWORD` | — | Default SSH password |
| `NETGEAR_ZONE{X}_USERNAME` | (empty) | Override for 10.X.0.0/16 |
| `NETGEAR_ZONE{X}_PASSWORD` | (empty) | Override for 10.X.0.0/16 |

> **Zone-based credentials:** set `NETGEAR_ZONE9_USERNAME` / `NETGEAR_ZONE9_PASSWORD` for all switches on `10.9.0.0/16`.

### SSH Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SSH_STRICT_HOST_KEY` | `false` | Strict host key checking |
| `SSH_KNOWN_HOSTS_FILE` | `./known_hosts` | SSH known_hosts path |
| `SSH_CONNECT_TIMEOUT` | `10` | Connection timeout (seconds) |
| `SSH_COMMAND_TIMEOUT` | `30` | Command timeout (seconds) |

## 📁 Project Structure

```
Netgear-AV-MCP/
├── src/
│   └── mcp_server/
│       ├── server.py          # FastMCP init, transport, security middleware
│       ├── tools/             # MCP tools — one file per category
│       │   ├── core.py        # version, hosts, config backup
│       │   ├── ports.py       # interface counters, port details
│       │   ├── vlan.py        # VLAN audit
│       │   ├── poe.py         # PoE status
│       │   ├── spantree.py    # Spanning Tree
│       │   ├── routing.py     # IP routes
│       │   ├── lldp.py        # LLDP neighbors
│       │   └── cli.py         # Generic read-only CLI
│       └── ssh/
│           ├── client.py      # asyncssh interactive shell client
│           └── auth.py        # Credential resolver (global → zone)
├── tests/
├── .env.example
├── pyproject.toml
├── AGENTS.md
└── LICENSE
```

## 🌐 OpenWebUI Integration

1. Start with `MCP_TRANSPORT=streamable-http` (default)
2. In OpenWebUI → Settings → Tools → Add Tool Server:
   - URL: `http://<server-ip>:8082/mcp`
   - Auth: `Authorization: Bearer <MCP_API_KEY>`
3. Tools appear automatically

> SSE: set `MCP_TRANSPORT=sse`, use `/sse` endpoint.

## 🔧 Claude Desktop Integration

Edit `claude_desktop_config.json`:

- **macOS** : `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows** : `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "netgear-av": {
      "command": "uv",
      "args": ["--directory", "/path/to/Netgear-AV-MCP", "run", "mcp-server"],
      "env": {"MCP_TRANSPORT": "stdio"}
    }
  }
}
```

> ⚠️ Replace `/path/to/Netgear-AV-MCP` with the absolute path to this project on your machine.

## 🛠 Development

```bash
uv sync                              # Install dependencies
uv run mcp-server                    # Start (streamable-http)
MCP_TRANSPORT=sse uv run mcp-server  # SSE transport
MCP_TRANSPORT=stdio uv run mcp-server # STDIO
uv run pytest                        # Run tests
uv run pytest --cov=mcp_server       # With coverage
npx @modelcontextprotocol/inspector uv run mcp-server  # MCP Inspector
```

## 🤖 Copilot Agents

This project includes 4 specialized Copilot agents (`.github/agents/`) for automated collaboration.

| Agent | Domain |
|-------|--------|
| `mcp-developer` | Source code: `src/mcp_server/` (tools, SSH client, auth) |
| `mcp-tester` | Tests: `tests/` — never modifies `src/` |
| `mcp-scaffolder` | Config: `pyproject.toml`, `.gitignore`, `.env.example` |
| `mcp-documenter` | Docs: `README.md`, docstrings, `AGENTS.md` |

## 🔗 Resources

- [Model Context Protocol — Documentation](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [asyncssh — Documentation](https://asyncssh.readthedocs.io/)
- [OpenWebUI — MCP Tool Servers](https://docs.openwebui.com/)
- [NETGEAR Pro AV Switches](https://www.netgear.com/business/wired/switches/pro-av/)

## 📄 License

MIT License — see [LICENSE](LICENSE).
