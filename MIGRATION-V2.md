# MCP SDK v2 Migrasyonu — Checklist

Tüm sunucuların MCP SDK v2'ye (Python `mcp` 2.x, TypeScript `@modelcontextprotocol/*` 2.x) taşınması
ve 2026-07-28 spec revizyonunun getirdiği özelliklerin benimsenmesi.

## Hedef sürümler

| Taraf | Şu an | Hedef |
|---|---|---|
| Python | `mcp>=1.0.0` | `mcp[cli]>=2.2,<3` |
| TypeScript/JS | `@modelcontextprotocol/sdk@^0.5.0` | `@modelcontextprotocol/server@^2`, `@modelcontextprotocol/node@^2`, `@modelcontextprotocol/core@^2` |
| Spec revizyonu | 2024-11-05 | 2026-07-28 (eski revizyonlar aynı sunucudan servis edilmeye devam eder) |

## Kararlar

- **Python 2.x'e tam geçiş.** `mcp.server.fastmcp` modülü v2'de yok; deprecate değil, kaldırılmış.
  Bu yüzden mevcut 7 Python sunucusu şu an ortamda `CONNECTION_CLOSED` veriyor.
- **Lowlevel `Server` kullanan 4 sunucu decorator API'sine yeniden yazılacak.** v2'de lowlevel
  `Server` zaten baştan yazıldı (`on_*` constructor param'ları, otomatik wrapping yok); elle
  yazılmış `inputSchema` JSON'larını korumanın değeri kalmadı.
- **Yayınlama:** her sunucu `2.0.0`'a bump edilir, PyPI/npm publish ayrı bir adım (elle).

## Her sunucuda uygulanacak ortak değişiklikler

Aşağıdaki maddeler her sunucunun kendi bölümünde tekrar edilmiyor; hepsi için geçerli.

### A. Zorunlu port (kırılan API'ler)
- [ ] `from mcp.server.fastmcp import FastMCP` → `from mcp.server import MCPServer`
- [ ] `mcp.server.fastmcp.*` → `mcp.server.mcpserver.*`; `ctx.fastmcp` → `ctx.mcp_server`
- [ ] `get_context()` kaldırıldı → handler'a `ctx: Context` parametresi ekle
- [ ] camelCase alanlar snake_case (`inputSchema` → `input_schema`, `structuredContent` → `structured_content`)
- [ ] `McpError` → `MCPError`; `FastMCPError` → `MCPServerError`
- [ ] Resource URI'leri `AnyUrl` değil `str`
- [ ] `stdio_server()` + elle `server.run(...)` → `mcp.run()`
- [ ] Transport param'ları constructor'dan `run()`/app metotlarına taşındı (`port=` vb.)
- [ ] Senkron handler'lar artık worker thread'de çalışıyor — `asyncio.get_running_loop()` kullanan `def` handler var mı kontrol et
- [ ] `httpx` → `httpx2` (SDK'nın HTTP istemcisini kullanan yerlerde)
- [ ] `pyproject.toml`: `mcp[cli]>=2.2,<3`, `version = "2.0.0"`

### B. Yeni özellikler (karar verilen kapsam)
- [ ] **Structured output:** tool dönüş tipini gerçek Python tipine/Pydantic modeline bağla → `outputSchema` + `structuredContent` otomatik
- [ ] **Tool annotations:** `title=`, `ToolAnnotations(read_only_hint / destructive_hint / idempotent_hint / open_world_hint)`
- [ ] **Argüman şeması:** elle JSON schema yerine type hint + `Annotated[..., Field(description=, ge=, le=)]` + `Literal` enum
- [ ] **Resources + prompts:** sunucuya özgü (aşağıda her sunucunun kendi bölümünde)
- [ ] **Progress + logging:** uzun işlemlerde `await ctx.report_progress(progress, total, message)`.
      Log için stdlib `logging` — protokol-seviyesi logging capability'si 2026-07-28 spec'inde
      deprecate edildi ve yerine bir şey konmadı; `ctx.info()/debug()` kullanılmayacak.
      `MCPServer(..., log_level=...)` `basicConfig`'i zaten kuruyor, stderr'e yazıyor.
      stdio sunucuda `print()` yasak — stdout protokole ait.
- [ ] **Cancellation:** iptal edilebilir uzun işlemlerde `ctx` üzerinden iptal kontrolü
- [ ] **Elicitation / `Resolve`:** yıkıcı işlemlerde kullanıcı onayı (`Resolve(fn)` + `Elicit(...)`, hem legacy hem 2026-07-28 istemcide çalışır)
- [ ] **Hata yönetimi:** beklenmedik exception artık istemciye `Error executing tool <name>` olarak gidiyor; modele mesaj göstermek isteniyorsa `ToolError` / `ResourceError` fırlat
- [ ] **Lifespan:** DB/SSH bağlantıları modül-global yerine lifespan context'inde kurulsun
- [ ] In-memory `Client(mcp)` ile smoke test (tools/list + en az bir tools/call)
- [ ] README + CHANGELOG güncelle

---

## Sunucular (uygulama sırası)

Sıralama küçükten büyüğe; ilk sunucu diğerlerinde tekrar edilecek konvansiyonu belirler.

### 1. n8n-chatbot-mcp — pilot (152 satır, FastMCP) ✅
- [x] A + B ortak maddeleri
- [x] `ask_chatbot` dönüşü `ChatReply` Pydantic modeli (answer + session_id) → structured output
- [x] `httpx` → `httpx2`, lifespan'da paylaşılan `AsyncClient`
- [x] Annotation: `open_world_hint=True`, `read_only_hint=False`, `destructive_hint=False`
- [x] Resource `n8n://config` — otomatik keşif çıktısı
- [x] Hata dönüşleri `ToolError` (önceden `return "Hata: ..."` idi — model bunu başarı sanıyordu)
- [x] In-memory `Client(mcp)` smoke test: tools/list şeması, structured_content, oturum sürekliliği
- [x] pyproject 2.0.0, README

**Pilotta belirlenen konvansiyonlar (diğer sunucular bunu izleyecek):**
- `MCPServer(name, version=__version__, lifespan=app_lifespan)`
- Paylaşılan kaynaklar (`AsyncClient`, DB bağlantısı) `@dataclass AppContext` içinde, lifespan'dan
  `yield`; handler'da `ctx.request_context.lifespan_context`
- Handler imzası: zorunlu argümanlar → `ctx: Context[AppContext]` → varsayılanlı argümanlar
- Argüman açıklamaları `Annotated[T, Field(description=...)]` ile; docstring sadece tool açıklaması
- Dönüş tipi her zaman Pydantic modeli veya gerçek Python tipi — asla elle JSON string
- Hata: modele okutulacaksa `ToolError`, protokol hatasıysa `MCPError`; asla hata string'i `return` etme
- `logging.getLogger(__name__)` modül seviyesinde; `print()` yok
- Her sunucuda `scripts/smoke_test.py` benzeri in-memory `Client` kontrolü

### 2. agent-chat (403 satır, FastMCP, 9 tool)
- [ ] A + B ortak maddeleri
- [ ] 9 tool'un dönüş tipleri Pydantic modellerine (`Message`, `Room`, `AgentStatus`)
- [ ] Resource: `chat://rooms`, `chat://rooms/{room}/messages` (oda listesi ve geçmiş)
- [ ] Prompt: oda özeti / son mesajları toparlama şablonu
- [ ] Okuma tool'larına `read_only_hint=True`; oda silme varsa `destructive_hint=True` + elicitation

### 3. docusaurus-mcp (560 satır, FastMCP, 4 tool)
- [ ] A + B ortak maddeleri
- [ ] Arama sonuçları için structured output (`SearchHit` listesi)
- [ ] Sitemap tarama uzun sürüyor → `ctx.report_progress()` + cancellation
- [ ] Resource: `docs://{path}` ile doğrudan sayfa okuma
- [ ] Prompt: "bu konuyu dokümanlardan özetle" şablonu
- [ ] `ThreadPoolExecutor` yerine async httpx (v2'de sync handler thread'e taşınıyor)
- [ ] Tüm tool'lar `read_only_hint=True`

### 4. gemini-reviews-mcp (474 satır, lowlevel → decorator)
- [ ] A + B ortak maddeleri
- [ ] `Server` + `stdio_server` sınıf yapısını `MCPServer` decorator'larına yeniden yaz
- [ ] `requests` → `httpx2` (async)
- [ ] Review/comment sonuçları için Pydantic modelleri
- [ ] Resource: `review://{owner}/{repo}/{pr}` 
- [ ] GitHub token yokken `ToolError` ile anlamlı mesaj
- [ ] Tüm tool'lar `read_only_hint=True`

### 5. ssh-mcp-server (1084 satır, lowlevel → decorator)
- [ ] A + B ortak maddeleri
- [ ] Paramiko bağlantısı lifespan'a taşı
- [ ] Komut çıktısı için structured output (`exit_code`, `stdout`, `stderr`, `duration_ms`)
- [ ] Uzun komutlarda `ctx.report_progress()` + log akışı + cancellation
- [ ] **Elicitation:** yıkıcı komut deseni (`rm -rf`, `mkfs`, `dd`, `shutdown`) tespitinde kullanıcı onayı
- [ ] `destructive_hint=True`, `open_world_hint=True`
- [ ] Resource: `ssh://logs/{session}` oturum logları

### 6. mapeg-postgres-mcp (794 satır, lowlevel → decorator)
- [ ] A + B ortak maddeleri
- [ ] `psycopg2` bağlantı havuzu lifespan'a taşı
- [ ] Query sonucu için structured output (`columns`, `rows`, `row_count`, `duration_ms`)
- [ ] Resource: `postgres://schema/{schema}`, `postgres://table/{schema}/{table}` (DDL + kolonlar)
- [ ] Prompt: "bu tabloyu analiz et" / "bu sorguyu optimize et" şablonları
- [ ] **Elicitation:** yazma sorgularında (INSERT/UPDATE/DELETE/DROP/TRUNCATE) onay
- [ ] SELECT tool'ları `read_only_hint=True`; DDL/DML `destructive_hint=True`
- [ ] Uzun sorgularda progress + cancellation

### 7. mapeg-oracle-mcp (1589 satır, lowlevel → decorator) — en büyük iş
- [ ] A + B ortak maddeleri
- [ ] `oracledb` bağlantısı lifespan'a taşı, sürüm tespiti lifespan'da bir kez
- [ ] Query + PL/SQL + DBMS_OUTPUT sonuçları için structured output
- [ ] Resource: `oracle://schema/{schema}`, `oracle://source/{type}/{name}` (PL/SQL kaynağı)
- [ ] Prompt: PL/SQL inceleme / açıklama şablonları
- [ ] **Elicitation:** DML/DDL onayı
- [ ] Progress + logging (DBMS_OUTPUT satırlarını `ctx.info()` ile akıt)
- [ ] Annotation'lar

### 8. gib-api-mcp (149 satır, JS, SDK 0.5 → v2)
- [ ] `package.json`: `@modelcontextprotocol/sdk@^0.5.0` → `@modelcontextprotocol/server@^2` + `@modelcontextprotocol/node@^2`, `version: 2.0.0`
- [ ] `new Server` + `setRequestHandler(ListTools/CallTool)` → `McpServer` + `registerTool` (zod şeması)
- [ ] `node-fetch` kaldır (Node 20+ yerleşik `fetch`); `engines.node >= 20`
- [ ] `outputSchema` (zod) + `structuredContent`
- [ ] Tool annotations (`readOnlyHint: true` — hesaplama tool'ları)
- [ ] Smoke test (in-memory transport)
- [ ] README

### 9. asger-terminal-mcp (536 satır, JS, SDK 0.5 → v2)
- [ ] `package.json` v2 paketleri, `version: 2.0.0`
- [ ] `McpServer` + `registerTool` portu
- [ ] Playwright browser yaşam döngüsü düzgün kapanış (transport close hook)
- [ ] Screenshot dönüşü için image content + `outputSchema`
- [ ] OCR uzun sürüyor → progress notification
- [ ] Yıkıcı komutlarda elicitation
- [ ] Repo kökündeki `output-*.png` çöp dosyalarını temizle + `.gitignore`
- [ ] README

### 10. Repo geneli
- [ ] `README.md`: MCP badge'i 2026-07-28, kurulum satırları, sürüm tablosu
- [ ] `.mcp.json` girdilerini doğrula (tüm sunucular bağlanıyor mu)
- [ ] `docker-compose.yml` güncelle
- [ ] Kök `CHANGELOG.md` — v2 geçişi özeti
- [ ] Repo kökündeki artıklar: `eng.traineddata`, `firebase-debug.log`, `__pycache__`, `.DS_Store` → `.gitignore` / sil
- [ ] Tüm sunucuları `uvx` / `npx` ile temiz ortamda çalıştır, `.mcp.json` üzerinden bağlantı doğrula

## Referanslar

- Python v2 migration: https://py.sdk.modelcontextprotocol.io/migration/
- Python v2 yenilikler: https://py.sdk.modelcontextprotocol.io/whats-new/
- TS v1→v2: https://github.com/modelcontextprotocol/typescript-sdk/blob/main/docs/migration/upgrade-to-v2.md
- TS 2026-07-28 desteği: https://github.com/modelcontextprotocol/typescript-sdk/blob/main/docs/migration/support-2026-07-28.md
