# PostgreSQL MCP Server

Natural language queries to PostgreSQL database via Model Context Protocol (MCP).

PostgreSQL veritabanınızı Claude Desktop ile doğal dilde sorgulayın.

## Features / Özellikler

- ✅ PostgreSQL database connection / Veritabanı bağlantısı
- ✅ Natural language queries (Turkish/English) / Doğal dil sorguları
- ✅ Execute SQL queries / SQL sorgu çalıştırma
- ✅ Database schema exploration / Tablo yapısını görüntüleme
- ✅ Database statistics / Veritabanı istatistikleri
- ✅ Smart query suggestions / Akıllı sorgu önerileri
- ✅ Secure connection via environment variables / Güvenli bağlantı

## Installation / Kurulum

### Option 1: Using uvx (Recommended / Önerilen)

No installation required! Just configure Claude Desktop:

```json
{
  "mcpServers": {
    "postgres": {
      "command": "uvx",
      "args": ["mcp-server-postgres"],
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "your_database",
        "DB_USER": "your_user",
        "DB_PASSWORD": "your_password"
      }
    }
  }
}
```

### Option 2: Install from PyPI

```bash
pip install mcp-server-postgres
```

### Option 3: Install from Source / Kaynak Koddan Kurulum

```bash
cd postgresql-mcp-server
pip install -e .
```

## Configuration / Yapılandırma

### Claude Desktop Configuration

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "postgres": {
      "command": "uvx",
      "args": ["mcp-server-postgres"],
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "mydb",
        "DB_USER": "postgres",
        "DB_PASSWORD": "secret"
      }
    }
  }
}
```

### Environment Variables

Alternatively, create a `.env` file:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mydb
DB_USER=postgres
DB_PASSWORD=secret
READ_ONLY=true  # Optional: Block write operations (INSERT, UPDATE, DELETE, DROP, etc.)
```

## Kullanım

Claude Desktop'ı yeniden başlattıktan sonra şu şekilde kullanabilirsiniz:

### 🤖 Doğal Dil Sorguları:
- "Tabloları listele" / "Show tables"
- "Kullanıcıları göster" / "Show users"  
- "Şemaları listele" / "Show schemas"
- "Veritabanı bilgilerini göster" / "Show database info"

### 🛠️ Araçlar:

#### 1. **natural_language_query**
Doğal dilde sorgulama
```
Örnek: "users tablosundaki tüm kayıtları göster"
```

#### 2. **execute_sql** 
Doğrudan SQL çalıştırma
```sql
SELECT * FROM pg_tables WHERE schemaname = 'public';
SELECT table_name, column_name FROM information_schema.columns;
```

#### 3. **describe_table**
Tablo yapısını görüntüleme
```
Örnek: "users" veya "public.users"
```

#### 4. **smart_query**
AI destekli akıllı sorgulama
```
Örnek: "En aktif kullanıcıları bul"
```

### 📊 Kaynaklar:
- **postgresql://tables**: Tüm tabloları listele
- **postgresql://schema**: Detaylı şema bilgisi
- **postgresql://stats**: Veritabanı istatistikleri

## Test

PostgreSQL bağlantısını test etmek için:

```bash
source venv/bin/activate
python -c "
import psycopg2
conn = psycopg2.connect(
    host='localhost', 
    database='docsmapeg', 
    user='postgres', 
    password='postgres'
)
print('✅ Bağlantı başarılı!')
conn.close()
"
```

## Sorun Giderme

### 1. PostgreSQL Bağlantı Hatası:
```bash
# PostgreSQL servisini başlat
brew services start postgresql

# Port kontrolü
lsof -i :5432

# Veritabanı var mı kontrol et
psql -U postgres -l
```

### 2. MCP Server Hatası:
```bash
# Log dosyalarını kontrol et
tail -f ~/Library/Logs/Claude/mcp-server-postgresql-db.log

# Manuel test
source venv/bin/activate
python server.py
```

### 3. Paket Hatası:
```bash
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Güvenlik

- Veritabanı şifreleri `.env` dosyasında saklanır
- Sadece read-only işlemler güvenlidir
- SQL injection koruması otomatik limit ekler
- Parametreli sorgular kullanılır

## Geliştirme

Daha gelişmiş AI özellikler için:
1. `.env` dosyasına `ANTHROPIC_API_KEY` ekleyin
2. `handle_smart_query` fonksiyonunu geliştirin
3. Şema analizi ve SQL üretimi ekleyin

---

**Not:** PostgreSQL sunucunuz çalışmıyorsa, önce `brew services start postgresql` komutu ile başlatın.