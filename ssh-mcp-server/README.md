# SSH MCP Server

SSH üzerinden uzak Linux sunucularında komut çalıştırma ve sistem yönetimi için Claude Desktop MCP Server'ı.

## 🚀 Özellikler

### 🛠️ Araçlar (Tools)
- **execute_command**: Shell komutları çalıştırma
- **file_operations**: Dosya okuma/yazma/listeleme
- **system_monitor**: Sistem kaynaklarını izleme
- **process_manager**: Process yönetimi
- **sftp_download**: SFTP ile dosya indirme (text/base64)
- **sftp_upload**: SFTP ile dosya yükleme (overwrite/append)
- **ssh_reconnect**: Bağlantıyı kontrol et ve gerekirse tazele

### 🆕 MCP 2.x ile gelenler
- **Structured output**: Her tool tipli JSON döner. `execute_command` artık `exit_code`,
  `stdout`, `stderr` ve `duration_ms` alanlarını ayrı ayrı veriyor — çıktı ile hata mesajı
  aynı metin bloğunda karışmıyor.
- **Onay soruları (elicitation)**: Yıkıcı işlemler çalıştırılmadan önce kullanıcıya sorulur —
  silme/yeniden başlatma komutları, var olan bir dosyanın üzerine yazma, süreç sonlandırma.
  Zararsız durumda soru sorulmaz (yeni dosya oluşturma, append, listeleme).
- **Progress bildirimi**: `system_monitor` her metriği okurken ilerleme raporlar.
- **Tool annotations**: Okuyan tool'lar `read_only_hint`, yazanlar `destructive_hint` taşır.
- **Prompt**: `diagnose_server` — belirtiden nedene giden teşhis akışı.

### 📊 Kaynaklar (Resources)
- **ssh://system**: Sistem bilgileri
- **ssh://processes**: Çalışan processler
- **ssh://disk**: Disk kullanımı
- **ssh://network**: Ağ bilgileri
- **ssh://logs**: Sistem logları

### 🔒 Güvenlik
- Tehlikeli komutlar otomatik engellenir
- SSH key authentication desteği
- Timeout koruması
- Safe file operations (SFTP)
- Process kill sadece numeric PID ile
- Tüm işlemler loglanır

## 📦 Installation / Kurulum

### Option 1: Using uvx (Recommended / Önerilen)

No installation required! Just configure Claude Desktop:

```json
{
  "mcpServers": {
    "ssh": {
      "command": "uvx",
      "args": ["mcp-server-ssh"],
      "env": {
        "SSH_HOST": "your_server_ip",
        "SSH_PORT": "22",
        "SSH_USER": "your_username",
        "SSH_PASSWORD": "your_password",
        "SSH_KEY_FILE": "/path/to/private_key"
      }
    }
  }
}
```

### Option 2: Install from PyPI

```bash
pip install mcp-server-ssh
```

### Option 3: Install from Source / Kaynak Koddan Kurulum

```bash
cd ssh-mcp-server
pip install -e .
# or
./install.sh
```

### Environment Variables

`.env` dosyasını düzenleyin:
```env
SSH_HOST=your_server_ip
SSH_PORT=22
SSH_USER=your_username
SSH_PASSWORD=your_password
SSH_TIMEOUT=30

# SSH Key Authentication (optional - preferred over password)
SSH_KEY_FILE=/path/to/your/private_key
SSH_KEY_PASSPHRASE=your_key_passphrase  # Optional: only if key is encrypted
```

**Authentication Priority:**
1. `SSH_KEY_FILE` set ise -> Key authentication
2. `SSH_PASSWORD` set ise -> Password authentication
3. Hicbiri yoksa -> Default key lookup (~/.ssh/id_rsa) + SSH agent

### Test
```bash
python test_ssh.py
```

## 🔧 Claude Desktop Configuration

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

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

Güvenlik iki katmanlı: bazı komutlar hiç çalıştırılmaz, bazıları için kullanıcıya sorulur.

### Hiçbir koşulda çalıştırılmayanlar
- `rm -rf /` ve `rm -rf /*` (sistem dizinlerinin tamamı: `/etc`, `/usr`, `/var`, ...)
- `format`, `mkfs`
- `dd ... of=/dev/...`
- Fork bomb desenleri
- `sudo passwd`, `userdel`, `deluser`

Bunlar tool hatası olarak reddedilir. Not: `rm -rf /var/tmp/build` gibi alt dizin silmeleri
artık engellenmiyor — bir alt katmana, onay sorusuna düşüyor.

### Önce kullanıcıya sorulanlar
- Dosya/dizin silme (`rm -r`, `rm -f`)
- `shutdown`, `reboot`, `halt`, `poweroff`, `init 0/6`
- `kill -9`, `killall`, `pkill`
- Özyinelemeli `chmod -R` / `chown -R`
- Paket kaldırma (`apt remove`, `yum remove`, ...)
- `docker rm/rmi/prune`
- `git reset --hard`, `git clean -f`
- Var olan bir dosyanın üzerine yazma (`file_operations` write, `sftp_upload` overwrite)
- Süreç sonlandırma (`process_manager` kill) — hangi sürecin öldürüleceği soruda gösterilir

Kullanıcı onay vermezse komut hiç çalıştırılmaz ve tool hata döner.

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

### sftp_download
```json
{
  "remote_path": "/etc/hosts",
  "encoding": "utf-8"
}
```

### sftp_upload
```json
{
  "remote_path": "/tmp/test.txt",
  "content": "Hello World",
  "mode": "overwrite"
}
```

### ssh_reconnect
```json
{
  "force": false
}
```

## 🧾 Promptlar

| Ad | Açıklama |
|----|----------|
| `diagnose_server` | Bir belirtiden yola çıkıp sistem durumu, loglar ve süreçler üzerinden nedeni bulur |

## 📐 Gereksinimler

Python 3.10+ ve MCP SDK 2.x (`mcp>=2.2,<3`). Sunucu 2026-07-28 protokol revizyonunu konuşur,
aynı süreçten eski MCP istemcilerine de hizmet verir. Tüm paramiko çağrıları worker thread'de
çalışır; uzun süren bir komut artık event loop'u bloklamıyor.

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
- Connection pooling
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