# GIB API MCP Server

[![Node.js](https://img.shields.io/badge/node-20+-blue?logo=node.js&logoColor=white)](https://nodejs.org)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-purple)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![npm](https://img.shields.io/npm/v/gib-api-mcp)](https://www.npmjs.com/package/gib-api-mcp)

GIB (Gelir İdaresi Başkanlığı) gecikme zammı ve gecikme faizi hesaplama MCP server'ı. [gib-gecikme-zammi-faizi](https://github.com/mytsx/gib-gecikme-zammi-faizi) Cloudflare Worker proxy üzerinden GİB Dijital Vergi Dairesi hesaplama servisine bağlanır.

## Features

- **Gecikme Zammı** — Kesinleşmiş vergi borcu için aylık+günlük karma hesaplama (AATUHK m.51)
- **Gecikme Faizi** — İkmalen/resen tarhiyatlarda tam ay esasına göre hesaplama (VUK m.112)
- **Kendi Worker'ın** — Kendi Cloudflare Worker'ını deploy et, URL'i env var olarak ver
- **Structured Output** — Sonuç tipli JSON döner (`anaPara`, `gecikmeOrani`, `gecikmeTutari`,
  `toplamOdenecek`), metni ayrıştırmaya gerek yok
- **Girdi Doğrulama** — Tarih ve tutar biçimi araç çalışmadan önce kontrol edilir
- **Prompt** — `gecikme_karsilastir`: aynı borç için zam ve faizi hesaplatıp farkı açıklar

## Prerequisites

Bu MCP server'ı kullanmak için kendi GİB API proxy worker'ınızı deploy etmeniz gerekir:

1. [gib-gecikme-zammi-faizi](https://github.com/mytsx/gib-gecikme-zammi-faizi) reposunu fork edin
2. Cloudflare Workers'a deploy edin
3. Worker URL'inizi `GIB_API_URL` olarak ayarlayın

## Quick Start

### Claude Code

```bash
claude mcp add gib-api \
  -e GIB_API_URL="https://your-worker.your-account.workers.dev" \
  -e GIB_API_KEY="your-api-key" \
  -- npx -y gib-api-mcp
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
      "args": ["-y", "gib-api-mcp"],
      "env": {
        "GIB_API_URL": "https://your-worker.your-account.workers.dev"
      }
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
      "args": ["-y", "gib-api-mcp"],
      "env": {
        "GIB_API_URL": "https://your-worker.your-account.workers.dev"
      }
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
      "args": ["-y", "gib-api-mcp"],
      "env": {
        "GIB_API_URL": "https://your-worker.your-account.workers.dev"
      }
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
      "args": ["-y", "gib-api-mcp"],
      "env": {
        "GIB_API_URL": "https://your-worker.your-account.workers.dev"
      }
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
      "args": ["-y", "gib-api-mcp"],
      "env": {
        "GIB_API_URL": "https://your-worker.your-account.workers.dev"
      }
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
      "args": ["-y", "gib-api-mcp"],
      "env": {
        "GIB_API_URL": "https://your-worker.your-account.workers.dev"
      }
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

[mcp_servers.gib-api.env]
GIB_API_URL = "https://your-worker.your-account.workers.dev"
```

### Install from Source

```bash
cd gib-api-mcp
npm install
```

## Configuration

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `GIB_API_URL` | Yes | Kendi Cloudflare Worker proxy URL'iniz. Deploy: [gib-gecikme-zammi-faizi](https://github.com/mytsx/gib-gecikme-zammi-faizi) |
| `GIB_API_KEY` | No | Worker'da API key koruması aktifse, `X-API-Key` header'ı olarak gönderilir |

## Tools

<details>
<summary><code>calculate_gecikme_zammi</code> — Gecikme Zammı hesapla</summary>

Kesinleşmiş vergi borcu vadesinde ödenmezse uygulanan gecikme zammını hesaplar. Vade tarihinden ödeme tarihine kadar aylık + günlük karma sistem ile hesaplanır.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `odenecekMiktar` | string | Yes | Borç tutarı (TL). Örnek: `"10000.00"` |
| `vadeTarihi` | string | Yes | Vade tarihi (YYYYMMDD). Örnek: `"20260101"` |
| `odemeTarihi` | string | Yes | Ödeme tarihi (YYYYMMDD). Örnek: `"20260301"` |

Dönen alanlar: `tip`, `anaPara`, `vadeTarihi`, `odemeTarihi`, `gecikmeOrani`,
`gecikmeTutari`, `toplamOdenecek`.

</details>

<details>
<summary><code>calculate_gecikme_faizi</code> — Gecikme Faizi hesapla</summary>

İkmalen, resen veya idarece yapılan tarhiyatlarda uygulanan gecikme faizini hesaplar. Sadece tam ay esasına göre hesaplanır, ay kesirleri dikkate alınmaz.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `odenecekMiktar` | string | Yes | Borç tutarı (TL). Örnek: `"10000.00"` |
| `vadeTarihi` | string | Yes | Normal vade tarihi (YYYYMMDD). Örnek: `"20260101"` |
| `odemeTarihi` | string | Yes | Tahakkuk tarihi (YYYYMMDD). Örnek: `"20260601"` |

Dönen alanlar `calculate_gecikme_zammi` ile aynı.

</details>

## Prompts

| Ad | Açıklama |
|----|----------|
| `gecikme_karsilastir` | Aynı borç için zam ve faizi hesaplatır, farkı ve hangisinin uygulanacağını açıklar |

## Usage Examples

```
# Gecikme zammı
1000 TL borcum var, vadesi 1 Ocak 2026, bugün ödesem ne kadar gecikme zammı öderim?

# Gecikme faizi
5000 TL'lik ikmalen tarhiyat, normal vade 1 Mart 2026, tahakkuk tarihi 1 Eylül 2026
```

## Gereksinimler

Node.js 20+ ve MCP SDK 2.x (`@modelcontextprotocol/server@^2`). `node-fetch` bağımlılığı
kaldırıldı — Node 20'nin yerleşik `fetch`'i kullanılıyor.

Testler: `npm test` (in-memory transport üzerinden sahte bir GİB worker'ıyla uçtan uca).

## License

MIT
