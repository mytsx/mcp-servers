#!/bin/bash

echo "PostgreSQL MCP Server Kurulumu Başlıyor..."

# Python sanal ortamı oluştur
python3 -m venv venv

# Sanal ortamı aktifleştir
source venv/bin/activate

# Gerekli paketleri yükle
pip install --upgrade pip
pip install -r requirements.txt

echo "PostgreSQL MCP Server kurulumu tamamlandı!"
echo ""
echo "Kullanım:"
echo "1. .env dosyasındaki PostgreSQL bağlantı bilgilerini kontrol edin"
echo "2. PostgreSQL sunucusunun çalıştığından emin olun"
echo "3. Claude Desktop config dosyasını güncelleyin"
echo "4. Claude Desktop'ı yeniden başlatın"