# Query Dashboard - MCP Server Log Viewer

Bu Flask uygulaması, PostgreSQL ve Oracle MCP serverlarının sorgu loglarını güzel bir web arayüzünde görüntüler.

## 🚀 Özellikler

- ✅ **Real-time Dashboard**: Canlı istatistikler ve grafikler
- ✅ **Query Logs**: Detaylı sorgu geçmişi ve filtreleme
- ✅ **Performance Monitoring**: Çalışma süreleri ve başarı oranları
- ✅ **Error Tracking**: Hata mesajları ve analizi
- ✅ **Search & Filter**: Güçlü arama ve filtreleme özellikleri
- ✅ **Responsive Design**: Mobil uyumlu modern arayüz

## 📋 Kurulum

1. **Python Virtual Environment**:
   ```bash
   cd query_dashboard
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Flask Uygulamasını Başlat**:
   ```bash
   python app.py
   ```

3. **Web Arayüzü**:
   http://localhost:5001 adresini ziyaret edin

## 🛠️ Kullanım

### Dashboard Sayfası
- **Ana İstatistikler**: Toplam sorgu sayısı, başarı oranı, ortalama süre
- **Server Dağılımı**: PostgreSQL vs Oracle sorgu grafiği
- **Son Aktiviteler**: En son çalıştırılan sorgular
- **Hatalar**: Son hata mesajları

### Query Logs Sayfası
- **Arama**: Sorgu metni içinde arama
- **Filtreleme**: Server türü ve durum bazında filtreleme
- **Detay Görünümü**: Sorguya tıklayarak tam detay
- **Zamanlı Görünüm**: Sorguların kronolojik sıralaması

## 📊 Log Verileri

Loglar şu bilgileri içerir:
- **Timestamp**: Sorgu çalıştırılma zamanı
- **Server Type**: postgresql / oracle
- **Tool Name**: execute_sql, natural_language_query, vb.
- **Query Text**: Çalıştırılan SQL sorgusu
- **Execution Time**: Milisaniye cinsinden süre
- **Status**: success / error
- **Row Count**: Dönen satır sayısı
- **Error Message**: Hata mesajı (varsa)
- **User Query**: Kullanıcının doğal dil sorgusu (varsa)

## 🔧 Yapılandırma

Log veritabanı otomatik olarak `../logs/query_logs.db` konumunda oluşturulur.

## 🎨 Teknolojiler

- **Backend**: Flask (Python)
- **Frontend**: Tailwind CSS, Chart.js
- **Database**: SQLite3 (log veritabanı)
- **Icons**: Font Awesome

## 📱 Ekran Görüntüleri

### Dashboard
- Kart bazlı istatistikler
- Donut grafik ile server dağılımı
- Real-time aktivite akışı

### Query Logs
- Tablo bazlı log görünümü
- Detay modal penceresi
- Arama ve filtreleme araçları

## 🚀 Geliştirme

### Yeni Özellikler Eklemek
1. `app.py` içinde yeni API endpoint'ler
2. `shared_logger.py` içinde veri yapısı değişiklikleri
3. HTML şablonlarında yeni UI bileşenleri

### Özelleştirmeler
- `templates/` klasöründe HTML şablonları
- Tailwind CSS ile stil değişiklikleri
- Chart.js ile grafik özelleştirmeleri