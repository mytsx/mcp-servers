#!/usr/bin/env node
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { 
  CallToolRequestSchema, 
  ListToolsRequestSchema 
} from '@modelcontextprotocol/sdk/types.js';
import { chromium } from 'playwright';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SESSION_FILE = path.join(__dirname, 'session-state.json');

// Create server
const server = new Server(
  {
    name: 'ssh-terminal-mcp',
    version: '1.0.0',
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Global state
let browser = null;
let context = null;
let page = null;

async function loadSession() {
  try {
    const sessionData = await fs.readFile(SESSION_FILE, 'utf-8');
    return JSON.parse(sessionData);
  } catch (error) {
    return null;
  }
}

async function saveSession() {
  if (context) {
    const state = await context.storageState();
    await fs.writeFile(SESSION_FILE, JSON.stringify(state, null, 2));
  }
}

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'open_terminal',
        description: 'Terminal URL\'sini aç (manuel giriş için)',
        inputSchema: {
          type: 'object',
          properties: {
            url: { type: 'string', description: 'Terminal URL' }
          },
          required: ['url']
        }
      },
      {
        name: 'save_session',
        description: 'Giriş yaptıktan sonra oturumu kaydet',
        inputSchema: {
          type: 'object',
          properties: {}
        }
      },
      {
        name: 'execute_command',
        description: 'Terminal komutu çalıştır (önce ekranı temizler)',
        inputSchema: {
          type: 'object',
          properties: {
            command: { type: 'string', description: 'Çalıştırılacak komut' },
            clear_before: { type: 'boolean', description: 'Komuttan önce ekranı temizle (varsayılan: true)' }
          },
          required: ['command']
        }
      },
      {
        name: 'execute_and_read',
        description: 'Komutu çalıştır ve çıktıyı oku (ekranı temizler, komutu çalıştırır, screenshot alır)',
        inputSchema: {
          type: 'object',
          properties: {
            command: { type: 'string', description: 'Çalıştırılacak komut' }
          },
          required: ['command']
        }
      },
      {
        name: 'take_screenshot',
        description: 'Terminal ekran görüntüsü al',
        inputSchema: {
          type: 'object',
          properties: {}
        }
      },
      {
        name: 'extract_text',
        description: 'Son ekran görüntüsünden metni çıkarmaya çalış',
        inputSchema: {
          type: 'object',
          properties: {}
        }
      },
      {
        name: 'disconnect',
        description: 'Terminal bağlantısını kapat',
        inputSchema: {
          type: 'object',
          properties: {}
        }
      },
      {
        name: 'clear_session',
        description: 'Kayıtlı oturumu temizle',
        inputSchema: {
          type: 'object',
          properties: {}
        }
      }
    ]
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  
  console.error(`Tool called: ${name}`, args);
  
  switch (name) {
    case 'open_terminal':
      return await openTerminal(args);
    case 'save_session':
      return await saveSessionHandler();
    case 'execute_command':
      return await executeCommand(args);
    case 'execute_and_read':
      return await executeAndRead(args);
    case 'take_screenshot':
      return await takeScreenshot();
    case 'extract_text':
      return await extractText();
    case 'disconnect':
      return await disconnect();
    case 'clear_session':
      return await clearSession();
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
});

async function openTerminal({ url }) {
  try {
    browser = await chromium.launch({ 
      headless: false,
      args: ['--disable-blink-features=AutomationControlled']
    });
    
    const savedSession = await loadSession();
    context = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      ...(savedSession ? { storageState: savedSession } : {})
    });
    
    page = await context.newPage();
    
    await page.goto(url);
    await page.waitForTimeout(5000);
    
    const hasPassword = await page.$('input[type="password"]');
    
    if (hasPassword) {
      return {
        content: [
          {
            type: 'text',
            text: 'Giriş sayfası açıldı. Lütfen manuel olarak giriş yapın ve ardından save_session komutunu çalıştırın.'
          }
        ]
      };
    } else {
      return {
        content: [
          {
            type: 'text',
            text: 'Terminal hazır! Önceki oturum başarıyla yüklendi.'
          }
        ]
      };
    }
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Bağlantı hatası: ${error.message}`
        }
      ]
    };
  }
}

async function saveSessionHandler() {
  try {
    if (!page) {
      throw new Error('Önce open_terminal ile terminali açın');
    }
    
    await saveSession();
    
    return {
      content: [
        {
          type: 'text',
          text: 'Oturum başarıyla kaydedildi! Artık terminal komutlarını kullanabilirsiniz.'
        }
      ]
    };
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Kaydetme hatası: ${error.message}`
        }
      ]
    };
  }
}

async function executeCommand({ command, clear_before = true }) {
  try {
    if (!page) {
      throw new Error('Önce open_terminal ile terminali açın');
    }
    
    // Sayfaya tıkla (focus için)
    await page.mouse.click(640, 400);
    await page.waitForTimeout(500);
    
    // Önce ekranı temizle
    if (clear_before) {
      await page.keyboard.type('clear');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(1000);
    }
    
    // Komutu yaz
    await page.keyboard.type(command);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(2000);
    
    return {
      content: [
        {
          type: 'text',
          text: `Komut çalıştırıldı: ${command}`
        }
      ]
    };
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Komut hatası: ${error.message}`
        }
      ]
    };
  }
}

async function executeAndRead({ command }) {
  try {
    if (!page) {
      throw new Error('Önce open_terminal ile terminali açın');
    }
    
    // Sayfaya tıkla (focus için)
    await page.mouse.click(640, 400);
    await page.waitForTimeout(500);
    
    // Ekranı temizle
    await page.keyboard.type('clear');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(1000);
    
    // Komutu yaz
    await page.keyboard.type(command);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(2000);
    
    // Ekran görüntüsü al
    const timestamp = Date.now();
    const filename = `output-${timestamp}.png`;
    const filepath = path.join(__dirname, filename);
    
    await page.screenshot({ path: filepath });
    
    // Metni çıkarmaya çalış
    const extractedText = await extractTextFromTerminal();
    
    return {
      content: [
        {
          type: 'text',
          text: `Komut: ${command}\n\nÇıktı:\n${extractedText}\n\nEkran görüntüsü: ${filename}`
        }
      ]
    };
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Hata: ${error.message}`
        }
      ]
    };
  }
}

async function takeScreenshot() {
  try {
    if (!page) {
      throw new Error('Önce open_terminal ile terminali açın');
    }
    
    const timestamp = Date.now();
    const filename = `terminal-${timestamp}.png`;
    const filepath = path.join(__dirname, filename);
    
    await page.screenshot({ path: filepath });
    
    return {
      content: [
        {
          type: 'text',
          text: `Ekran görüntüsü alındı: ${filename}`
        }
      ]
    };
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Screenshot hatası: ${error.message}`
        }
      ]
    };
  }
}

async function extractText() {
  try {
    if (!page) {
      throw new Error('Önce open_terminal ile terminali açın');
    }
    
    const extractedText = await extractTextFromTerminal();
    
    return {
      content: [
        {
          type: 'text',
          text: extractedText || 'Metin çıkarılamadı'
        }
      ]
    };
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Metin çıkarma hatası: ${error.message}`
        }
      ]
    };
  }
}

async function extractTextFromTerminal() {
  try {
    // Farklı yöntemler dene
    
    // 1. Selection API
    const selectedText = await page.evaluate(() => {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(document.body);
      selection.removeAllRanges();
      selection.addRange(range);
      const text = selection.toString();
      selection.removeAllRanges();
      return text;
    });
    
    if (selectedText && selectedText.trim()) {
      return selectedText.trim();
    }
    
    // 2. Canvas'tan koordinat bazlı metin okuma simülasyonu
    // Terminal genellikle sabit genişlikte font kullanır
    // Her satır yaklaşık 20px yüksekliğinde olabilir
    const lines = [];
    const lineHeight = 20;
    const startY = 50; // Terminal'in başlangıç y koordinatı (tahmini)
    const maxLines = 30; // Maksimum satır sayısı
    
    for (let i = 0; i < maxLines; i++) {
      const y = startY + (i * lineHeight);
      
      // Bu koordinatta tıkla ve satırı seçmeye çalış
      await page.mouse.click(50, y);
      await page.keyboard.down('Shift');
      await page.mouse.click(1200, y);
      await page.keyboard.up('Shift');
      
      // Seçili metni al
      const lineText = await page.evaluate(() => {
        const selection = window.getSelection();
        const text = selection.toString();
        selection.removeAllRanges();
        return text;
      });
      
      if (lineText && lineText.trim()) {
        lines.push(lineText.trim());
      }
    }
    
    if (lines.length > 0) {
      return lines.join('\n');
    }
    
    // 3. Accessibility tree
    const snapshot = await page.accessibility.snapshot();
    if (snapshot && snapshot.children) {
      const texts = [];
      const extractFromNode = (node) => {
        if (node.name) texts.push(node.name);
        if (node.value) texts.push(node.value);
        if (node.children) {
          node.children.forEach(extractFromNode);
        }
      };
      extractFromNode(snapshot);
      
      if (texts.length > 0) {
        return texts.join('\n');
      }
    }
    
    // 4. Son çare: tüm görünür metin
    const allText = await page.evaluate(() => document.body.innerText);
    return allText || 'Terminal metni okunamadı. Ekran görüntüsüne bakın.';
    
  } catch (error) {
    console.error('Text extraction error:', error);
    return 'Metin çıkarma başarısız. Ekran görüntüsüne bakın.';
  }
}

async function disconnect() {
  try {
    if (browser) {
      await browser.close();
      browser = null;
      context = null;
      page = null;
    }
    
    return {
      content: [
        {
          type: 'text',
          text: 'Bağlantı kapatıldı'
        }
      ]
    };
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Kapatma hatası: ${error.message}`
        }
      ]
    };
  }
}

async function clearSession() {
  try {
    await fs.unlink(SESSION_FILE).catch(() => {});
    return {
      content: [
        {
          type: 'text',
          text: 'Oturum bilgileri temizlendi'
        }
      ]
    };
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Temizleme hatası: ${error.message}`
        }
      ]
    };
  }
}

// Start server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('SSH Terminal MCP server started');
}

main().catch(console.error);