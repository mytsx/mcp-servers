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
- [x] `from mcp.server.fastmcp import FastMCP` → `from mcp.server import MCPServer`
- [x] `mcp.server.fastmcp.*` → `mcp.server.mcpserver.*`; `ctx.fastmcp` → `ctx.mcp_server`
- [x] `get_context()` kaldırıldı → handler'a `ctx: Context` parametresi ekle
- [x] camelCase alanlar snake_case (`inputSchema` → `input_schema`, `structuredContent` → `structured_content`)
- [x] `McpError` → `MCPError`; `FastMCPError` → `MCPServerError`
- [x] Resource URI'leri `AnyUrl` değil `str`
- [x] `stdio_server()` + elle `server.run(...)` → `mcp.run()`
- [x] Transport param'ları constructor'dan `run()`/app metotlarına taşındı (`port=` vb.)
- [x] Senkron handler'lar artık worker thread'de çalışıyor — `asyncio.get_running_loop()` kullanan `def` handler var mı kontrol et
- [x] `httpx` → `httpx2` (SDK'nın HTTP istemcisini kullanan yerlerde)
- [x] `pyproject.toml`: `mcp[cli]>=2.2,<3`, `version = "2.0.0"`

### B. Yeni özellikler (karar verilen kapsam)
- [x] **Structured output:** tool dönüş tipini gerçek Python tipine/Pydantic modeline bağla → `outputSchema` + `structuredContent` otomatik
- [x] **Tool annotations:** `title=`, `ToolAnnotations(read_only_hint / destructive_hint / idempotent_hint / open_world_hint)`
- [x] **Argüman şeması:** elle JSON schema yerine type hint + `Annotated[..., Field(description=, ge=, le=)]` + `Literal` enum
- [x] **Resources + prompts:** sunucuya özgü (aşağıda her sunucunun kendi bölümünde)
- [x] **Progress + logging:** uzun işlemlerde `await ctx.report_progress(progress, total, message)`.
      Log için stdlib `logging` — protokol-seviyesi logging capability'si 2026-07-28 spec'inde
      deprecate edildi ve yerine bir şey konmadı; `ctx.info()/debug()` kullanılmayacak.
      `MCPServer(..., log_level=...)` `basicConfig`'i zaten kuruyor, stderr'e yazıyor.
      stdio sunucuda `print()` yasak — stdout protokole ait.
- [x] **Cancellation:** iptal edilebilir uzun işlemlerde `ctx` üzerinden iptal kontrolü
- [x] **Elicitation / `Resolve`:** yıkıcı işlemlerde kullanıcı onayı (`Resolve(fn)` + `Elicit(...)`, hem legacy hem 2026-07-28 istemcide çalışır)
- [x] **Hata yönetimi:** beklenmedik exception artık istemciye `Error executing tool <name>` olarak gidiyor; modele mesaj göstermek isteniyorsa `ToolError` / `ResourceError` fırlat
- [x] **Lifespan:** DB/SSH bağlantıları modül-global yerine lifespan context'inde kurulsun
- [x] In-memory `Client(mcp)` ile smoke test (tools/list + en az bir tools/call)
- [x] README + CHANGELOG güncelle

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

**Yolda çıkan v2 kısıtları (hepsinde geçerli):**
- **Resource handler'ları lifespan context'ine erişemez.** `Context` parametresi alsalar bile
  `ctx.request_context` "Context is not available outside of a request" ile patlıyor; URI
  şablonlu olması da değiştirmiyor. Statik URI'li resource `Context` parametresini kabul bile
  etmiyor (kayıt anında `ValueError`). Çözüm: lifespan'ın doldurduğu modül seviyesinde bir
  tutucu (`_app` / `_store`), resource oradan okur.
- Tool handler'ları sync (`def`) olsa bile `ctx.request_context` çalışıyor — kısıt sadece
  resource'larda.

### 2. agent-chat (403 satır, FastMCP, 9 tool) ✅
- [x] A + B ortak maddeleri
- [x] 9 tool'un dönüşü Pydantic modeli (`Message`, `AgentInfo`, `RoomInfo`, `MessageBatch`, ...)
- [x] Dosya erişimi `ChatStore` sınıfına toplandı, lifespan'da tutuluyor
- [x] Resource: `chat://rooms`, `chat://rooms/{room}/messages`
- [x] Prompt: `summarize_room`
- [x] `clear_room` → `Resolve`/`Elicit` ile onay; oda zaten boşsa soru sorulmuyor
- [x] `leave_room` odada olmayan agent için `ToolError`
- [x] Annotation'lar; `last_seen` yazan tool'lar dürüstçe `read_only_hint=False`

**Bilinen sorun (bu migrasyonun kapsamı dışı, ayrı iş):** `_write_json` dosyayı `open(..., "w")`
ile açıp *sonra* `flock` alıyor — truncate kilitten önce oluyor. Aynı odaya eşzamanlı iki yazıcı
mesaj kaybedebilir. Mesaj ID'si de `len(messages)+1` ile üretiliyor, yani yarış durumunda ID
çakışabilir. Düzeltme: geçici dosyaya yazıp `os.replace` ile atomik taşıma + ayrı kilit dosyası.

### 3. docusaurus-mcp (560 satır, FastMCP, 4 tool) ✅
- [x] A + B ortak maddeleri
- [x] Arama sonuçları için structured output (`SearchResults` / `SearchHit`)
- [x] `refresh_index` tool'u eklendi: `ctx.report_progress()` ile sayfa sayfa ilerleme
- [x] Cancellation: anyio task group; çağrı iptal edilince uçuştaki fetch'ler de iptal oluyor
- [x] Resource: `docs://{doc_ref}` (ID, path veya URL ile)
- [x] Prompt: `explain_topic`
- [x] `ThreadPoolExecutor` + sync `httpx` → `httpx2.AsyncClient` + `anyio` (10 eşzamanlı)
- [x] Tarama import anından lifespan'a taşındı; başarısız tarama artık `sys.exit` etmiyor
- [x] Tüm okuma tool'ları `read_only_hint=True`

### 4. gemini-reviews-mcp (474 satır, lowlevel → decorator) ✅
- [x] A + B ortak maddeleri
- [x] `Server` + `stdio_server` sınıf yapısını `MCPServer` decorator'larına yeniden yaz
- [x] `requests` → `httpx2` (async)
- [x] Review/comment sonuçları için Pydantic modelleri
- [x] Resource: `review://{owner}/{repo}/{pr}` 
- [x] GitHub token yokken `ToolError` ile anlamlı mesaj
- [x] Tüm tool'lar `read_only_hint=True`

### 5. ssh-mcp-server (1084 satır, lowlevel → decorator) ✅
- [x] A + B ortak maddeleri
- [x] Paramiko bağlantısı lifespan'a taşı
- [x] Komut çıktısı için structured output (`exit_code`, `stdout`, `stderr`, `duration_ms`)
- [x] Uzun komutlarda `ctx.report_progress()` + log akışı + cancellation
- [x] **Elicitation:** yıkıcı komut deseni (`rm -rf`, `mkfs`, `dd`, `shutdown`) tespitinde kullanıcı onayı
- [x] `destructive_hint=True`, `open_world_hint=True`
- [x] Resource: `ssh://logs/{session}` oturum logları

### 6. mapeg-postgres-mcp (794 satır, lowlevel → decorator) ✅
- [x] A + B ortak maddeleri
- [x] `psycopg2` bağlantı havuzu lifespan'a taşı
- [x] Query sonucu için structured output (`columns`, `rows`, `row_count`, `duration_ms`)
- [x] Resource: `postgres://schema/{schema}`, `postgres://table/{schema}/{table}` (DDL + kolonlar)
- [x] Prompt: "bu tabloyu analiz et" / "bu sorguyu optimize et" şablonları
- [x] **Elicitation:** yazma sorgularında (INSERT/UPDATE/DELETE/DROP/TRUNCATE) onay
- [x] SELECT tool'ları `read_only_hint=True`; DDL/DML `destructive_hint=True`
- [x] Uzun sorgularda progress + cancellation

### 7. mapeg-oracle-mcp (1589 satır, lowlevel → decorator) ✅
- [x] A + B ortak maddeleri
- [x] `oracledb` bağlantısı lifespan'a taşı, sürüm tespiti lifespan'da bir kez
- [x] Query + PL/SQL + DBMS_OUTPUT sonuçları için structured output
- [x] Resource: `oracle://schema/{schema}`, `oracle://source/{type}/{name}` (PL/SQL kaynağı)
- [x] Prompt: PL/SQL inceleme / açıklama şablonları
- [x] **Elicitation:** DML/DDL onayı
- [x] Progress + logging (DBMS_OUTPUT satırlarını `ctx.info()` ile akıt)
- [x] Annotation'lar

### 8. gib-api-mcp (149 satır, JS, SDK 0.5 → v2) ✅
- [x] `package.json`: `@modelcontextprotocol/sdk@^0.5.0` → `@modelcontextprotocol/server@^2` + `@modelcontextprotocol/node@^2`, `version: 2.0.0`
- [x] `new Server` + `setRequestHandler(ListTools/CallTool)` → `McpServer` + `registerTool` (zod şeması)
- [x] `node-fetch` kaldır (Node 20+ yerleşik `fetch`); `engines.node >= 20`
- [x] `outputSchema` (zod) + `structuredContent`
- [x] Tool annotations (`readOnlyHint: true` — hesaplama tool'ları)
- [x] Smoke test (in-memory transport)
- [x] README

### 9. asger-terminal-mcp (536 satır, JS, SDK 0.5 → v2) ✅
- [x] `package.json` v2 paketleri, `version: 2.0.0`
- [x] `McpServer` + `registerTool` portu
- [x] Playwright browser yaşam döngüsü düzgün kapanış (transport close hook)
- [x] Screenshot dönüşü için image content + `outputSchema`
- [x] OCR uzun sürüyor → progress notification
- [x] Yıkıcı komutlarda elicitation
- [x] Repo kökündeki `output-*.png` çöp dosyalarını temizle + `.gitignore`
- [x] README

### 10. Repo geneli
- [x] `README.md`: MCP rozeti 2026-07-28, tüm sunucularda ortak kazanımlar bölümü
- [x] Kök `CHANGELOG.md` — v2 geçişinin tam özeti
- [x] Her sunucu gerçek stdio alt süreci olarak başlatılıp `protocolVersion` doğrulandı:
      9/9 sunucu **2026-07-28** konuşuyor
- [x] mapeg-postgres-mcp gerçek PostgreSQL 16'ya, mapeg-oracle-mcp gerçek Oracle 23ai'ye karşı test edildi
- [x] İki JS sunucusuna `npm test` smoke testi eklendi
- [ ] **PyPI / npm yayını** — paketler hâlâ 1.0.0'da. `uvx <paket>` / `npx -y <paket>` eski,
      artık çalışmayan kodu çekiyor. Bu yüzden `.mcp.json` üzerinden bağlantı doğrulaması
      yapılamadı: yayın yapılana kadar bu girdiler kopuk kalacak.
      Ara çözüm isterseniz `.mcp.json` girdilerini yerel yola çevirebiliriz
      (`uvx --from /path/to/server <komut>`).
- [ ] `docker-compose.yml` — dokunulmadı. Oracle servisi `gvenzl/oracle-xe:21-slim`
      kullanıyor; testleri `gvenzl/oracle-free:23-slim` ile yaptım. Geçilecekse port ve
      PDB adı da değişir (`XEPDB1` → `FREEPDB1`), yani `.mcp.json` ile birlikte
      güncellenmeli — ayrı bir karar.
- [ ] Repo kökündeki artıklar: `eng.traineddata` (5 MB), `firebase-debug.log`,
      `__pycache__/`, `.DS_Store`. Hepsi `.gitignore`'da, silinmeleri gerekip gerekmediği
      sizin kararınız — dokunmadım.

## Referanslar

- Python v2 migration: https://py.sdk.modelcontextprotocol.io/migration/
- Python v2 yenilikler: https://py.sdk.modelcontextprotocol.io/whats-new/
- TS v1→v2: https://github.com/modelcontextprotocol/typescript-sdk/blob/main/docs/migration/upgrade-to-v2.md
- TS 2026-07-28 desteği: https://github.com/modelcontextprotocol/typescript-sdk/blob/main/docs/migration/support-2026-07-28.md
