# Oracle MCP Server for Claude Desktop

Bu proje, Oracle 19c veritabanınızı Claude Desktop uygulaması ile doğal dilde sorgulamanızı sağlar. PostgreSQL MCP Server ile aynı özelliklere sahip, Oracle'a özgü optimizasyonlar içerir.

## 🚀 Özellikler

- ✅ **Oracle 19c** tam desteği
- ✅ Doğal dil sorguları (Türkçe/İngilizce)
- ✅ SQL sorgu çalıştırma (Oracle syntax)
- ✅ Tablo yapısını görüntüleme
- ✅ Veritabanı istatistikleri
- ✅ Akıllı sorgu önerileri (AI-powered)
- ✅ Güvenli bağlantı (environment variables)
- ✅ Detaylı hata yönetimi

## 📋 Kurulum

1. **Gereksinimler:**
   - Python 3.8+
   - Oracle 19c veritabanı erişimi
   - Claude Desktop uygulaması

2. **Proje Kurulumu:**
   ```bash
   cd oracle-mcp-server
   ./install.sh
   ```

   Not: Oracle thin mode kullanılır, Instant Client gerekmez.

## ⚙️ Yapılandırma

1. **Environment Variables:**
   `.env` dosyasındaki bağlantı bilgilerini güncelleyin:
   ```env
   # Oracle Database Configuration
   ORACLE_CONNECTION_STRING=User Id=MADEN;Password=MADEN;Data Source=(DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=10.50.53.15)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=madendev)))
   
   # AI Configuration (optional)
   ANTHROPIC_API_KEY=your_api_key_here
   ```

2. **Claude Desktop Konfigürasyonu:**
   `~/Library/Application Support/Claude/claude_desktop_config.json`:
   ```json
   {
     "mcpServers": {
       "oracle-db": {
         "command": "/Users/yerli/Developer/ai_db/oracle-mcp-server/venv/bin/python",
         "args": ["/Users/yerli/Developer/ai_db/oracle-mcp-server/server.py"],
         "cwd": "/Users/yerli/Developer/ai_db/oracle-mcp-server"
       }
     }
   }
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
Oracle 19c için optimize edilmiş doğal dil sorgulama
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

## 🔍 Oracle 19c Özellikleri

### Desteklenen Oracle View'ları:
- `USER_TABLES` - Kullanıcı tabloları
- `ALL_TABLES` - Erişilebilir tüm tablolar
- `USER_TAB_COLUMNS` - Tablo sütunları
- `V$INSTANCE` - Veritabanı instance bilgisi
- `ALL_USERS` - Veritabanı kullanıcıları

### SQL Özellikleri:
- `FETCH FIRST n ROWS ONLY` - Oracle 19c syntax
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
print('✅ Oracle 19c bağlantısı başarılı!')
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
- Oracle 19c thin mode kullanılır
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

**Not:** Bu MCP server Oracle 19c için optimize edilmiştir. PostgreSQL versiyonu için `postgresql-mcp-server` klasörüne bakın.