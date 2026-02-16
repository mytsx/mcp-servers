# Oracle MCP Server

Natural language queries to Oracle database via Model Context Protocol (MCP).

Oracle 19c veritabanınızı Claude Desktop ile doğal dilde sorgulayın.

## Features / Özellikler

- ✅ Oracle multi-version support (11g, 12c, 18c, 19c, 21c, 23ai) / Çoklu versiyon desteği
- ✅ Natural language queries (Turkish/English) / Doğal dil sorguları
- ✅ Execute Oracle SQL / SQL sorgu çalıştırma
- ✅ Database schema exploration / Tablo yapısını görüntüleme
- ✅ Database statistics / Veritabanı istatistikleri
- ✅ Smart query suggestions / Akıllı sorgu önerileri
- ✅ Secure connection via environment variables / Güvenli bağlantı
- ✅ Dynamic version detection / Dinamik versiyon tespiti
- ✅ Oracle thin mode (no Instant Client required) / Instant Client gerektirmez

## Installation / Kurulum

### Option 1: Using uvx (Recommended / Önerilen)

No installation required! Just configure Claude Desktop:

```json
{
  "mcpServers": {
    "oracle": {
      "command": "uvx",
      "args": ["mapeg-oracle-mcp"],
      "env": {
        "ORACLE_CONNECTION_STRING": "User Id=username;Password=password;Data Source=(DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=hostname)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=service)))"
      }
    }
  }
}
```

### Option 2: Install from PyPI

```bash
pip install mapeg-oracle-mcp
```

### Option 3: Install from Source / Kaynak Koddan Kurulum

```bash
cd oracle-mcp-server
pip install -e .
```

## Configuration / Yapılandırma

### Claude Desktop Configuration

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "oracle": {
      "command": "uvx",
      "args": ["mapeg-oracle-mcp"],
      "env": {
        "ORACLE_CONNECTION_STRING": "User Id=MYUSER;Password=MYPASS;Data Source=(DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=localhost)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=ORCL)))"
      }
    }
  }
}
```

### Environment Variables

Alternatively, create a `.env` file:

```env
ORACLE_CONNECTION_STRING=User Id=MYUSER;Password=MYPASS;Data Source=(DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=localhost)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=ORCL)))
READ_ONLY=true  # Optional: Block write operations (INSERT, UPDATE, DELETE, DROP, etc.)
```

## 🛠️ Kullanım

Claude Desktop'ı yeniden başlattıktan sonra şu şekilde kullanabilirsiniz:

### 🤖 Doğal Dil Sorguları:
- "Tabloları listele" / "Show tables"
- "Kullanıcıları göster" / "Show users"
- "Şemaları listele" / "Show schemas"
- "Veritabanı bilgilerini göster" / "Show database info"

### 🔧 Araçlar:

#### 1. **natural_language_query**
Oracle için optimize edilmiş doğal dil sorgulama
```
Örnek: "MADEN kullanıcısının tablolarını göster"
```

#### 2. **execute_sql**
Doğrudan Oracle SQL çalıştırma
```sql
-- Oracle'a özgü sorgular
SELECT * FROM user_tables;
SELECT * FROM all_tables WHERE owner = 'MADEN';
SELECT table_name, column_name FROM user_tab_columns;
```

#### 3. **describe_table**
Oracle tablo yapısını görüntüleme
```
Örnek: "TBL_PROJE" (Oracle'da tablo isimleri BÜYÜK HARFLE)
```

#### 4. **smart_query**
AI destekli akıllı Oracle sorgulama
```
Örnek: "En büyük tabloları bul"
```

### 📊 Kaynaklar:
- **oracle://tables**: USER_TABLES view'ından tablo listesi
- **oracle://schema**: USER_TAB_COLUMNS'dan şema bilgisi
- **oracle://stats**: V$INSTANCE'dan veritabanı istatistikleri

## 🔍 Oracle Özellikleri

### Desteklenen Oracle View'ları:
- `USER_TABLES` - Kullanıcı tabloları
- `ALL_TABLES` - Erişilebilir tüm tablolar
- `USER_TAB_COLUMNS` - Tablo sütunları
- `V$INSTANCE` - Veritabanı instance bilgisi
- `ALL_USERS` - Veritabanı kullanıcıları

### SQL Özellikleri:
- `FETCH FIRST n ROWS ONLY` - Oracle 12c+ syntax
- `ROWNUM` - Klasik Oracle limitleme
- Büyük/küçük harf duyarlılığı (tablo isimleri BÜYÜK HARF)

## 🧪 Test

Oracle bağlantısını test etmek için:

```bash
source venv/bin/activate
python -c "
import oracledb
conn = oracledb.connect(
    user='MADEN',
    password='MADEN',
    dsn='(DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=10.50.53.15)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=madendev)))'
)
print('✅ Oracle bağlantısı başarılı!')
conn.close()
"
```

## 🐛 Sorun Giderme

### 1. Oracle Bağlantı Hatası:
```bash
# Ağ bağlantısını kontrol et
telnet 10.50.53.15 1521

# TNS ping
tnsping madendev
```

### 2. MCP Server Hatası:
```bash
# Log dosyalarını kontrol et
tail -f ~/Library/Logs/Claude/mcp-server-oracle-db.log

# Manuel test
source venv/bin/activate
python server.py
```

### 3. Version Uyumsuzluğu:
- Oracle thin mode kullanılır (versiyon otomatik tespit edilir)
- Eski Oracle sürümleri için Instant Client gerekebilir

## 🔒 Güvenlik

- Veritabanı şifreleri `.env` dosyasında saklanır
- `.gitignore` ile versiyon kontrolünden hariç tutulur
- Sadece read-only işlemler önerilir
- Parametreli sorgular kullanılır

## 📈 Geliştirme

Gelişmiş AI özellikleri için:
1. `.env` dosyasına geçerli `ANTHROPIC_API_KEY` ekleyin
2. `handle_smart_query` fonksiyonunu geliştirin
3. Şema analizi ve otomatik SQL üretimi ekleyin

---

**Not:** Bu MCP server Oracle veritabanları için optimize edilmiştir (versiyon otomatik tespit edilir). PostgreSQL versiyonu için `postgresql-mcp-server` klasörüne bakın.