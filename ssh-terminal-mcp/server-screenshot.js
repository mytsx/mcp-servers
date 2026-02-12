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
        description: 'Terminal komutu çalıştır',
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
        name: 'read_visible_text',
        description: 'Görünür terminal metnini oku (OCR benzeri)',
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
    case 'take_screenshot':
      return await takeScreenshot();
    case 'read_visible_text':
      return await readVisibleText();
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

async function executeCommand({ command }) {
  try {
    if (!page) {
      throw new Error('Önce open_terminal ile terminali açın');
    }
    
    // Sayfaya tıkla (focus için)
    await page.mouse.click(640, 400);
    await page.waitForTimeout(500);
    
    // Komutu yaz
    await page.keyboard.type(command);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(2000);
    
    return {
      content: [
        {
          type: 'text',
          text: `Komut çalıştırıldı: ${command}\n\nÇıktıyı görmek için take_screenshot veya read_visible_text kullanın.`
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

async function readVisibleText() {
  try {
    if (!page) {
      throw new Error('Önce open_terminal ile terminali açın');
    }
    
    // Sayfadaki tüm görünür metni al
    const visibleText = await page.evaluate(() => {
      // Canvas üzerindeki metni alamayız ama etrafındaki metinleri alabiliriz
      const body = document.body;
      const selection = window.getSelection();
      const range = document.createRange();
      
      // Tüm sayfayı seç
      range.selectNodeContents(body);
      selection.removeAllRanges();
      selection.addRange(range);
      
      // Seçili metni al
      const text = selection.toString();
      
      // Seçimi temizle
      selection.removeAllRanges();
      
      return text || document.body.innerText || 'Metin okunamadı';
    });
    
    // Alternatif: accessibility tree'den oku
    const accessibilityText = await page.evaluate(() => {
      const elements = document.querySelectorAll('[role], [aria-label], [aria-live]');
      const texts = [];
      elements.forEach(el => {
        const text = el.textContent || el.getAttribute('aria-label') || '';
        if (text.trim()) texts.push(text.trim());
      });
      return texts.join('\n');
    });
    
    const result = visibleText || accessibilityText || 'Terminal metni okunamadı. take_screenshot kullanın.';
    
    return {
      content: [
        {
          type: 'text',
          text: result
        }
      ]
    };
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Okuma hatası: ${error.message}`
        }
      ]
    };
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