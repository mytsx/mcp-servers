# MCP Servers - Birleşik MCP Sunucu Koleksiyonu

Tüm MCP (Model Context Protocol) sunucularını tek bir repoda toplayan nihai koleksiyon.

## Proje Yapısı

### Veritabanı Sunucuları
| Proje | Açıklama | Kaynak |
|-------|----------|--------|
| `oracle-mcp-server/` | Oracle 19c veritabanı MCP sunucusu (execute_sql, describe_table, DBMS_OUTPUT) | ai_db (güncel) |
| `postgresql-mcp-server/` | PostgreSQL veritabanı MCP sunucusu | ai_db |
| `postgresql-db-lib/` | PostgreSQL veritabanı kütüphanesi (Node.js/TypeScript) | ai_db |
| `postgresql-py-lib/` | PostgreSQL Python kütüphanesi | ai_db |

### SSH / Terminal Sunucuları
| Proje | Açıklama | Kaynak |
|-------|----------|--------|
| `ssh-mcp-server/` | Python SSH MCP sunucusu (komut çalıştırma, log, dashboard) | ai_db |
| `ssh-terminal-mcp/` | Node.js SSH terminal MCP (screenshot, OCR destekli) | MCPs |

### Git / CI/CD Araçları
| Proje | Açıklama | Kaynak |
|-------|----------|--------|
| `mcp-server-git-extended/` | Gelişmiş Git MCP sunucusu | ai_db |
| `gh-tool/` | Gemini PR Reviews - GitHub PR analiz aracı | MCPs (github.com/mytsx/mcp-gemini-pr-reviews) |

### API Araçları
| Proje | Açıklama | Kaynak |
|-------|----------|--------|
| `gib-api-mcp/` | GİB (Gelir İdaresi Başkanlığı) API MCP sunucusu | MCPs |

### Yardımcı Araçlar
| Dosya | Açıklama |
|-------|----------|
| `shared_logger.py` | Ortak loglama modülü |
| `query_dashboard/` | Sorgu izleme dashboard'u |
| `kill_all_mcp_servers.sh` | Tüm MCP sunucularını durdurma scripti |
| `claude_desktop_config_template.json` | Claude Desktop config şablonu |

## Kurulum

Her alt proje için:

```bash
cd <proje-dizini>
python -m venv venv          # Python projeleri için
source venv/bin/activate
pip install -r requirements.txt
```

Node.js projeleri için:
```bash
cd <proje-dizini>
npm install
```

## Konsolidasyon Notu

Bu repo aşağıdaki eski dizinlerin birleşimidir:
- **ai_db** → Ana kaynak (Git: github.com/mytsx/ai_db.git) - en güncel versiyonlar
- **mcp_db** → ai_db'nin eski alt kümesi (oracle eski versiyon, postgresql/dashboard aynı)
- **MCPs** → Karışık projeler (gh_tool, ssh_terminal_mcp, gib-api-mcp benzersiz)

Eski dizinler artık silinebilir. Bu repo nihai ve güncel olan kaynaktır.
