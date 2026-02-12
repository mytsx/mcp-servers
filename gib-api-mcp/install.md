# GIB API MCP Kurulum Kılavuzu

## Claude Desktop'a Ekleme

1. Claude Desktop config dosyasını açın:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`

2. Config dosyasına aşağıdaki satırları ekleyin:

```json
{
  "mcpServers": {
    "gib-api": {
      "command": "node",
      "args": ["/Users/yerli/Developer/MCPs/gib-api-mcp/index.js"],
      "env": {}
    }
  }
}
```

3. Dosya yolunu kendi sisteminize göre düzeltin.

4. Claude Desktop'ı yeniden başlatın.

## Test Etme

Claude'da şu komutları deneyebilirsiniz:

```
GIB gecikme zammı hesaplama aracını kullanarak 1000 TL için 01/01/2025 vadeli ödemenin bugün ödenecek tutarını hesapla.
```

veya çoklu hesaplama:

```
Aşağıdaki ödemeler için gecikme zammı hesapla:
- 500 TL, vade: 01/03/2025
- 1000 TL, vade: 01/04/2025  
- 750 TL, vade: 01/05/2025
```