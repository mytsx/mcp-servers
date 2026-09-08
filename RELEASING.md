# Yayınlama

Depodaki dokuz sunucu iki yere yayınlanıyor: yedisi PyPI'ye, ikisi npm'e. Bu
belge 2.0.0 sürümünün nasıl çıkarılacağını anlatıyor; aynı adımlar sonraki
sürümler için de geçerli.

## Durum

| Paket | Kayıt | Yayında | Bu depoda |
|---|---|---|---|
| `agent-chat-mcp` | PyPI | 1.0.0 | 2.0.0 |
| `docusaurus-mcp` | PyPI | 1.0.0 | 2.0.0 |
| `gemini-reviews-mcp` | PyPI | 1.0.0 | 2.0.0 |
| `mapeg-oracle-mcp` | PyPI | 1.0.0 | 2.0.0 |
| `mapeg-postgres-mcp` | PyPI | 1.0.0 | 2.0.0 |
| `mcp-server-ssh` | PyPI | 1.0.0 | 2.0.0 |
| `n8n-chatbot-mcp` | PyPI | 1.0.0 | 2.0.0 |
| `asger-terminal-mcp` | npm | 1.0.0 | 2.0.0 |
| `gib-api-mcp` | npm | 1.0.0 | 2.0.0 |

**Yayınlanana kadar `uvx <paket>` ve `npx -y <paket>` 1.0.0'ı çeker.** 1.0.0
Python sunucuları `mcp.server.fastmcp`'yi import ediyor ve bu modül SDK 2.x'te
yok, dolayısıyla `mcp` 2.x'e çözülen her ortamda hiç başlamıyorlar. Yani
yayınlama bir iyileştirme değil, bu paketleri yeniden çalışır hâle getirmenin
yolu.

## Yayın öncesi

```bash
# 1. Testler. Veritabanı gerektiren iki suite, bağlantı değişkenleri yoksa
#    fail etmek yerine skip eder — yayın öncesi ikisini de gerçekten çalıştır.
docker compose up -d postgres oracle
export DB_HOST=127.0.0.1 DB_PORT=5433 DB_NAME=testdb DB_USER=testuser DB_PASSWORD=testpass
export ORACLE_CONNECTION_STRING='User Id=testuser;Password=testpass;Data Source=127.0.0.1:1522/XEPDB1'
./scripts/run-tests.sh

# 2. Dağıtımları üret ve twine ile doğrula.
./scripts/build-release.sh

# 3. Her paketi temiz bir ortama kurup gerçekten başlat.
./scripts/verify-release.py
```

`verify-release.py` test suite'lerinin göremediği paketleme hatalarını yakalar:
eksik bir konsol betiği, wheel'e girmemiş bir modül, npm'in `.bin` symlink'i
üzerinden çalıştırıldığında başlamayan bir giriş noktası. Üçü de bu depoda
gerçekten yaşandı.

Sürüm numarasını değiştirdiysen üç yerde birden değiştir: `pyproject.toml`
(`version`), paketin `__init__.py` dosyası (`__version__`) ve Node tarafında
`package.json`. Sunucular kendi sürümlerini `MCPServer(version=...)` ile
bildiriyor, yani tutarsızlık istemciye yansır.

## PyPI

Kimlik doğrulama için API token gerekiyor (kullanıcı adı `__token__`, parola
`pypi-...`). Token'ı `~/.pypirc` içinde ya da `TWINE_USERNAME` /
`TWINE_PASSWORD` ortam değişkenlerinde tut.

```bash
# Önce TestPyPI'ye — geri alınamaz bir adımı prova etmenin tek yolu.
python3 -m twine upload --repository testpypi \
  agent-chat/dist/* docusaurus-mcp/dist/* gemini-reviews-mcp/dist/* \
  mapeg-oracle-mcp/dist/* mapeg-postgres-mcp/dist/* n8n-chatbot-mcp/dist/* \
  ssh-mcp-server/dist/*

# TestPyPI'den kurup çalıştığını gör.
uvx --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ n8n-chatbot-mcp --help

# Gerçek yayın.
python3 -m twine upload \
  agent-chat/dist/* docusaurus-mcp/dist/* gemini-reviews-mcp/dist/* \
  mapeg-oracle-mcp/dist/* mapeg-postgres-mcp/dist/* n8n-chatbot-mcp/dist/* \
  ssh-mcp-server/dist/*
```

## npm

```bash
npm whoami   # oturum açık değilse: npm login

npm publish dist/npm/gib-api-mcp-2.0.0.tgz --access public
npm publish dist/npm/asger-terminal-mcp-2.0.0.tgz --access public
```

## Yayın sonrası

```bash
# uvx/npx artık yeni sürümü çekiyor mu?
uvx n8n-chatbot-mcp --help
npx -y gib-api-mcp --help

# .mcp.json üzerinden bağlanan istemcileri yeniden başlat: uvx ve npx eski
# sürümü önbelleğe almış olabilir.
uv cache clean
npm cache clean --force
```

Git etiketi:

```bash
git tag -a v2.0.0 -m "MCP SDK v2 migration"
git push origin v2.0.0
```

## Geri alma

PyPI ve npm'de bir sürümü **silmek geri alınamaz ve aynı numara tekrar
kullanılamaz**. Yayınlanmış bir sürümde sorun çıkarsa:

- PyPI: `pip install` ile gelmemesi için sürümü *yank*'le
  (`pypi.org` arayüzünden), sonra düzeltmeyi 2.0.1 olarak yayınla.
- npm: `npm deprecate <paket>@2.0.0 "sebep"`, sonra 2.0.1.

`npm unpublish` yalnızca yayından sonraki 72 saat içinde ve başka paketler
bağımlı değilse çalışır; buna güvenme.

## Bilinen sınır

`ssh_activity_logger.py`, `mcp_server_ssh` paketinin **yanında** duruyor,
içinde değil (`[tool.setuptools] packages = ["mcp_server_ssh"]`). Yayınlanmış
kurulumda import başarısız oluyor ve opsiyonel logger devre dışı kalıyor;
depodan çalıştırıldığında giriş noktası onu `sys.path`'e ekliyor ve çalışıyor.
Modülü paketin içine almak, çalıştırılan her komutu bir SQLite veritabanına
yazan bu özelliği herkes için varsayılan açar — nereye ve ne kadar log
yazılacağı ayrı bir karar, `CHANGELOG.md` içinde takip maddesi olarak duruyor.
