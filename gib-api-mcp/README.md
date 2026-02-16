# GIB API MCP Server

[![Node.js](https://img.shields.io/badge/node-18+-blue?logo=node.js&logoColor=white)](https://nodejs.org)
[![MCP](https://img.shields.io/badge/MCP-1.0+-purple)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![npm](https://img.shields.io/npm/v/gib-api-mcp)](https://www.npmjs.com/package/gib-api-mcp)

GIB (Gelir İdaresi Başkanlığı) gecikme zammı ve gecikme faizi hesaplama MCP server'ı. [gib-gecikme-zammi-faizi](https://github.com/mytsx/gib-gecikme-zammi-faizi) Cloudflare Worker proxy üzerinden GİB Dijital Vergi Dairesi hesaplama servisine bağlanır.

## Features

- **Gecikme Zammı** — Kesinleşmiş vergi borcu için aylık+günlük karma hesaplama (AATUHK m.51)
- **Gecikme Faizi** — İkmalen/resen tarhiyatlarda tam ay esasına göre hesaplama (VUK m.112)
- **Zero Config** — Env var gerekmez, direkt çalışır

## Quick Start

### Claude Code

```bash
claude mcp add gib-api -- npx -y gib-api-mcp
```

### Claude Desktop

Add to your config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "gib-api": {
      "command": "npx",
      "args": ["-y", "gib-api-mcp"]
    }
  }
}
```

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "gib-api": {
      "command": "npx",
      "args": ["-y", "gib-api-mcp"]
    }
  }
}
```

### Windsurf

Add to Windsurf MCP config:

```json
{
  "mcpServers": {
    "gib-api": {
      "command": "npx",
      "args": ["-y", "gib-api-mcp"]
    }
  }
}
```

### VS Code

Add to your VS Code settings (JSON):

```json
"mcp": {
  "servers": {
    "gib-api": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "gib-api-mcp"]
    }
  }
}
```

### Gemini CLI

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "gib-api": {
      "command": "npx",
      "args": ["-y", "gib-api-mcp"]
    }
  }
}
```

### GitHub Copilot

Add to `~/.copilot/mcp-config.json`:

```json
{
  "mcpServers": {
    "gib-api": {
      "command": "npx",
      "args": ["-y", "gib-api-mcp"]
    }
  }
}
```

### OpenAI Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.gib-api]
command = "npx"
args = ["-y", "gib-api-mcp"]
```

### Install from Source

```bash
cd gib-api-mcp
npm install
```

## Tools

<details>
<summary><code>calculate_gecikme_zammi</code> — Gecikme Zammı hesapla</summary>

Kesinleşmiş vergi borcu vadesinde ödenmezse uygulanan gecikme zammını hesaplar. Vade tarihinden ödeme tarihine kadar aylık + günlük karma sistem ile hesaplanır.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `odenecekMiktar` | string | Yes | Borç tutarı (TL). Örnek: `"10000.00"` |
| `vadeTarihi` | string | Yes | Vade tarihi (YYYYMMDD). Örnek: `"20260101"` |
| `odemeTarihi` | string | Yes | Ödeme tarihi (YYYYMMDD). Örnek: `"20260301"` |

</details>

<details>
<summary><code>calculate_gecikme_faizi</code> — Gecikme Faizi hesapla</summary>

İkmalen, resen veya idarece yapılan tarhiyatlarda uygulanan gecikme faizini hesaplar. Sadece tam ay esasına göre hesaplanır, ay kesirleri dikkate alınmaz.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `odenecekMiktar` | string | Yes | Borç tutarı (TL). Örnek: `"10000.00"` |
| `vadeTarihi` | string | Yes | Normal vade tarihi (YYYYMMDD). Örnek: `"20260101"` |
| `odemeTarihi` | string | Yes | Tahakkuk tarihi (YYYYMMDD). Örnek: `"20260601"` |

</details>

## Usage Examples

```
# Gecikme zammı
1000 TL borcum var, vadesi 1 Ocak 2026, bugün ödesem ne kadar gecikme zammı öderim?

# Gecikme faizi
5000 TL'lik ikmalen tarhiyat, normal vade 1 Mart 2026, tahakkuk tarihi 1 Eylül 2026
```

## API

Proxy: [`gib-gecikme-zammi-faizi`](https://github.com/mytsx/gib-gecikme-zammi-faizi) — Cloudflare Worker üzerinden GİB Dijital Vergi Dairesi'ne bağlanır.

## License

MIT
