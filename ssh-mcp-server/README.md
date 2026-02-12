# SSH MCP Server

SSH üzerinden uzak Linux sunucularında komut çalıştırma ve sistem yönetimi için Claude Desktop MCP Server'ı.

## 🚀 Özellikler

### 🛠️ Araçlar (Tools)
- **execute_command**: Shell komutları çalıştırma
- **file_operations**: Dosya okuma/yazma/listeleme 
- **system_monitor**: Sistem kaynaklarını izleme
- **process_manager**: Process yönetimi

### 📊 Kaynaklar (Resources)
- **ssh://system**: Sistem bilgileri
- **ssh://processes**: Çalışan processler
- **ssh://disk**: Disk kullanımı
- **ssh://network**: Ağ bilgileri
- **ssh://logs**: Sistem logları

### 🔒 Güvenlik
- Tehlikeli komutlar otomatik engellenir
- Timeout koruması
- Safe file operations
- Process kill sadece numeric PID ile
- Tüm işlemler loglanır

## 📦 Kurulum

### 1. Gereksinimler
```bash
Python 3.8+
SSH erişimi olan Linux sunucu
```

### 2. Kurulum
```bash
cd ssh-mcp-server
./install.sh
```

### 3. Konfigürasyon
`.env` dosyasını düzenleyin:
```env
SSH_HOST=your_server_ip
SSH_PORT=22
SSH_USER=your_username  
SSH_PASSWORD=your_password
SSH_TIMEOUT=30
```

### 4. Test
```bash
python test_ssh.py
```

## 🔧 Claude Desktop Konfigürasyonu

`claude_desktop_config.json` dosyasına ekleyin:

```json
{
  "mcpServers": {
    "ssh-mcp-server": {
      "command": "/path/to/ssh-mcp-server/venv/bin/python",
      "args": ["/path/to/ssh-mcp-server/server.py"],
      "cwd": "/path/to/ssh-mcp-server"
    }
  }
}
```

## 🧪 Kullanım Örnekleri

### Sistem Bilgileri
```
"Linux sunucumda sistem bilgilerini göster"
"Sunucunun uptime'ını kontrol et"
"Disk kullanımını göster"
```

### Dosya İşlemleri
```
"/etc/hosts dosyasını oku"
"/var/log/nginx/error.log dosyasının son 100 satırını göster"
"/home dizinini listele"
```

### Process Yönetimi
```
"Nginx processlerini listele"
"Python processlerini bul"
"CPU kullanımını göster"
```

### Komut Çalıştırma
```
"df -h komutunu çalıştır"
"ps aux | grep nginx"
"systemctl status docker"
```

## 🔐 Güvenlik Özellikleri

### Engellenen Komutlar
- `rm -rf /`
- `format`, `mkfs`
- `dd if=/dev/zero of=/dev/sda`
- Fork bomb patterns
- `shutdown`, `reboot`, `halt`
- User deletion commands

### Güvenlik Best Practices
1. Sadece güvendiğiniz sunucularda kullanın
2. Limited yetkili kullanıcı hesabı kullanın
3. SSH key authentication tercih edin
4. Logları düzenli kontrol edin
5. Firewall kurallarını gözden geçirin

## 📋 Mevcut Araçlar

### execute_command
```json
{
  "command": "ls -la /home",
  "timeout": 30
}
```

### file_operations
```json
{
  "operation": "read",
  "path": "/etc/hosts",
  "limit": 100
}
```

### system_monitor
```json
{
  "metric": "all",
  "detailed": true
}
```

### process_manager
```json
{
  "action": "search",
  "target": "nginx"
}
```

## 🐛 Sorun Giderme

### SSH Bağlantısı Başarısız
```bash
# Test SSH bağlantısı
ssh -p 42922 root@31.210.36.85

# .env dosyasını kontrol edin
cat .env

# SSH client test
python test_ssh.py
```

### MCP Server Başlamıyor
```bash
# Virtual environment kontrol
source venv/bin/activate
python -c "import paramiko; print('OK')"

# Server test
python server.py
```

### Komutlar Çalışmıyor
1. SSH kullanıcısının yetkileri
2. Komutun path'te olması
3. Timeout değeri
4. Güvenlik kısıtlamaları

## 📊 Performans

### Optimizasyon
- Connection pooling (gelecek sürüm)
- Command caching
- Parallel execution
- Resource monitoring

### Limits
- Command timeout: 30s (varsayılan)
- File read limit: 100 lines (varsayılan)
- Connection timeout: 30s
- Memory usage monitoring

## 🔄 Güncellemeler

### v1.0.0
- Temel SSH komut çalıştırma
- Dosya operasyonları
- Sistem monitoring
- Process management
- Güvenlik kontrolleri

### Roadmap
- SSH key authentication
- Connection pooling
- File transfer (SCP/SFTP)
- Interactive shell
- Multi-server support

## 📊 Activity Dashboard

SSH MCP server aktivitelerini izlemek için modern web dashboard:

### Dashboard Özellikleri
- 📈 Real-time aktivite izleme
- 📊 İstatistik ve grafikler
- 🔍 Detaylı arama ve filtreleme
- 📥 Export (JSON/CSV)
- 🎨 Modern responsive tasarım

### Dashboard Başlatma
```bash
cd ssh-mcp-server
./start_dashboard.sh
```

Dashboard http://localhost:5555 adresinde açılacaktır.

⚠️ **Production Uyarısı**: Development sunucusu sadece test için uygundur. Production ortamında güvenlik ve performans için profesyonel web sunucusu kullanın:

```bash
# Gunicorn ile production deployment
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5555 ssh_log_dashboard:app

# Nginx reverse proxy önerisi
# nginx.conf:
# location /ssh-dashboard/ {
#     proxy_pass http://127.0.0.1:5555/;
#     proxy_set_header Host $host;
#     proxy_set_header X-Real-IP $remote_addr;
# }
```

### Dashboard Sayfaları
1. **Overview**: Genel istatistikler ve timeline
2. **Activities**: Tüm aktivitelerin detaylı listesi
3. **Sessions**: SSH oturumları ve analizleri
4. **Commands**: En çok kullanılan komutlar
5. **Errors**: Hata analizi ve raporları
6. **Search**: Gelişmiş arama özellikleri

## 📞 Destek

### Loglar
```bash
tail -f ~/.local/share/Claude/logs/mcp-server-ssh.log
```

### Debug Mode
```bash
DEBUG=1 python server.py
```

### Common Issues
1. **Connection refused**: Firewall/port kontrol
2. **Authentication failed**: Username/password kontrol  
3. **Command not found**: PATH ve package kurulumu
4. **Permission denied**: User permissions kontrol

## ⚖️ License
MIT License

## 🤝 Contributing
1. Fork repository
2. Create feature branch
3. Test thoroughly
4. Submit pull request

## ⚠️ Disclaimer
Bu tool sistem yönetimi içindir. Kötü amaçlı kullanımdan kullanıcı sorumludur. Production sistemlerde dikkatli kullanın.