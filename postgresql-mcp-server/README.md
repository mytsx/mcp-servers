# PostgreSQL MCP Server for Claude Desktop

Bu proje, PostgreSQL veritabanınızı Claude Desktop uygulaması ile doğal dilde sorgulamanızı sağlar.

## Özellikler

- ✅ PostgreSQL veritabanı bağlantısı
- ✅ Doğal dil sorguları (Türkçe/İngilizce)
- ✅ SQL sorgu çalıştırma
- ✅ Tablo yapısını görüntüleme  
- ✅ Veritabanı istatistikleri
- ✅ Akıllı sorgu önerileri
- ✅ Güvenli bağlantı (environment variables)
- ✅ Detaylı hata yönetimi

## Kurulum

1. **PostgreSQL Sunucusu:**
   PostgreSQL sunucusunun çalıştığından emin olun:
   ```bash
   brew services start postgresql
   # veya
   pg_ctl -D /usr/local/var/postgres start
   ```

2. **Proje Kurulumu:**
   ```bash
   cd postgresql-mcp-server
   ./install.sh
   ```

## Yapılandırma

1. **Environment Variables:**
   `.env` dosyasındaki bağlantı bilgilerini güncelleyin:
   ```env
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=docsmapeg
   DB_USER=postgres
   DB_PASSWORD=postgres
   ```

2. **Claude Desktop Konfigürasyonu:**
   Config dosyası otomatik olarak güncellendi:
   ```json
   {
     "mcpServers": {
       "postgresql-db": {
         "command": "/Users/yerli/Developer/ai_db/postgresql-mcp-server/venv/bin/python",
         "args": ["/Users/yerli/Developer/ai_db/postgresql-mcp-server/server.py"],
         "cwd": "/Users/yerli/Developer/ai_db/postgresql-mcp-server"
       }
     }
   }
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