#!/bin/bash

echo "Oracle MCP Server Kurulumu Başlıyor..."

# Python sanal ortamı oluştur
python3 -m venv venv

# Sanal ortamı aktifleştir
source venv/bin/activate

# Gerekli paketleri yükle
pip install --upgrade pip
pip install -r requirements.txt

echo "Kurulum tamamlandı!"
echo ""
echo "Kullanım:"
echo "1. .env dosyasındaki bağlantı bilgilerini kontrol edin"
echo "2. Claude Desktop config dosyasını güncelleyin"
echo "3. Claude Desktop'ı yeniden başlatın"