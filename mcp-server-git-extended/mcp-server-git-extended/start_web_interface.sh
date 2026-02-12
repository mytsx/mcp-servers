#!/bin/bash

# Git MCP Extended - Web Interface Launcher
# Bu script gerekli kurulumları yapar ve web arayüzünü başlatır

# Renkler
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Git MCP Extended - Log Viewer     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════╝${NC}"
echo ""

# Script dizinine git
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Python kontrolü
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Hata: Python 3 yüklü değil${NC}"
    exit 1
fi

# Virtual environment kontrol ve kurulum
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}📦 Virtual environment oluşturuluyor...${NC}"
    python3 -m venv venv
    
    # venv'i aktifle
    source venv/bin/activate
    
    # pip güncelle
    echo -e "${YELLOW}📦 pip güncelleniyor...${NC}"
    pip install --upgrade pip --quiet
    
    # Paketi ve tüm bağımlılıklarını yükle
    echo -e "${YELLOW}📦 Paket ve bağımlılıklar yükleniyor...${NC}"
    pip install -e . --quiet
    
    echo -e "${GREEN}✅ Kurulum tamamlandı!${NC}"
else
    # venv'i aktifle
    source venv/bin/activate
fi

# Log dizinini oluştur
mkdir -p ~/.mcp-git-extended

# Database kontrolü
if [ -f ~/.mcp-git-extended/logs.db ]; then
    echo -e "${GREEN}✓ Log veritabanı bulundu${NC}"
    # Log sayısını göster - basit sqlite3 komutu ile
    if command -v sqlite3 &> /dev/null; then
        LOG_COUNT=$(sqlite3 ~/.mcp-git-extended/logs.db "SELECT COUNT(*) FROM gitlog;" 2>/dev/null || echo "0")
        echo -e "${BLUE}📊 Toplam log sayısı: $LOG_COUNT${NC}"
    else
        echo -e "${BLUE}📊 Log sayısı gösterimi için sqlite3 gerekli${NC}"
    fi
else
    echo -e "${YELLOW}! Log veritabanı ilk kullanımda oluşturulacak${NC}"
fi

# Web arayüzünü başlat
echo ""
echo -e "${GREEN}🚀 Git MCP Extended Web Arayüzü başlatılıyor...${NC}"

# Port bilgisi
DEFAULT_PORT=5555
PORT=${MCP_GIT_WEB_PORT:-$DEFAULT_PORT}
echo -e "${GREEN}🌐 Port aralığı: ${BLUE}$PORT-$((PORT+10))${NC}"
echo -e "${YELLOW}⏹️  Durdurmak için Ctrl+C tuşlarına basın${NC}"
echo ""
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""

# Web arayüzünü modül olarak çalıştır
MCP_GIT_WEB_PORT=$PORT python -m mcp_server_git.web_interface