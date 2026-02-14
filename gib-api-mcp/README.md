# GIB API MCP Server

GIB (Gelir İdaresi Başkanlığı) gecikme zammı/faizi hesaplama API'si için MCP server.

## Installation / Kurulum

### Option 1: Using npx (Recommended / Önerilen)

No installation required! Just configure Claude Desktop:

```json
{
  "mcpServers": {
    "gib-api": {
      "command": "npx",
      "args": ["-y", "gib-api-mcp"]
    }
  }
}
```

### Option 2: Install from npm

```bash
npm install -g gib-api-mcp
```

### Option 3: Install from Source / Kaynak Koddan Kurulum

```bash
cd gib-api-mcp
npm install
```

## Claude Desktop Configuration

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "gib-api": {
      "command": "npx",
      "args": ["-y", "gib-api-mcp"]
    }
  }
}
```

### Mevcut Araçlar

#### 1. `calculate_late_payment_interest`
Tek bir ödeme için gecikme zammı/faizi hesaplar.

**Parametreler:**
- `odenecekMiktar` (string): Ödenecek miktar TL (örn: "1000.00")
- `vadeTarihi` (string): Vade tarihi YYYYMMDD formatında (örn: "20250101")
- `odemeTarihi` (string): Ödeme tarihi YYYYMMDD formatında (örn: "20250716")
- `gecikmeTipi` (integer, opsiyonel): 1=Gecikme Zammı, 2=Gecikme Faizi (varsayılan: 2)

**Örnek Kullanım:**
```
1000 TL'lik bir borcum var, vadesi 1 Ocak 2025, bugün ödesem ne kadar gecikme faizi öderim?
```

#### 2. `calculate_multiple_late_payments`
Birden fazla ödeme için toplu hesaplama yapar.

**Parametreler:**
- `odemeler` (array): Ödeme listesi

**Örnek Kullanım:**
```
Şu ödemelerimin gecikme faizlerini hesapla:
- 500 TL, vade: 1 Mart 2025
- 1000 TL, vade: 1 Nisan 2025
- 750 TL, vade: 1 Mayıs 2025
```

## API Endpoint

Worker URL: https://gib-api-proxy.mehmet49946.workers.dev

## Özellikler

- GIB resmi oranları ile hesaplama
- Gecikme zammı ve gecikme faizi desteği
- Toplu hesaplama imkanı
- Detaylı sonuç raporu

## Notlar

- Tarihler YYYYMMDD formatında olmalıdır
- Tutarlar string olarak "1234.56" formatında gönderilmelidir
- API rate limit'e takılırsa 60 saniye bekleyin