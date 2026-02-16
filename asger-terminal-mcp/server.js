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
import Tesseract from 'tesseract.js';
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SESSION_FILE = path.join(__dirname, 'session-state.json');

// Configuration from environment
const DEFAULT_TERMINAL_URL = process.env.TERMINAL_URL || '';
const WAIT_AFTER_COMMAND = parseInt(process.env.WAIT_AFTER_COMMAND || '2000');
const WAIT_AFTER_CLEAR = parseInt(process.env.WAIT_AFTER_CLEAR || '1000');
const WAIT_AFTER_CLICK = parseInt(process.env.WAIT_AFTER_CLICK || '500');

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
            url: { 
              type: 'string', 
              description: `Terminal URL (varsayılan: ${DEFAULT_TERMINAL_URL || 'ayarlanmamış'})` 
            }
          },
          required: []
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

async function openTerminal({ url = DEFAULT_TERMINAL_URL } = {}) {
  try {
    if (!url) {
      throw new Error('Terminal URL belirtilmedi. Lütfen .env dosyasında TERMINAL_URL ayarlayın veya url parametresi gönderin.');
    }
    
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
    await page.waitForTimeout(WAIT_AFTER_CLICK);
    
    // Önce ekranı temizle
    if (clear_before) {
      await page.keyboard.type('clear');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(WAIT_AFTER_CLEAR);
    }
    
    // Komutu yaz
    await page.keyboard.type(command);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(WAIT_AFTER_COMMAND);
    
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
    await page.waitForTimeout(WAIT_AFTER_CLICK);
    
    // Ekranı temizle
    await page.keyboard.type('clear');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(WAIT_AFTER_CLEAR);
    
    // Komutu yaz
    await page.keyboard.type(command);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(WAIT_AFTER_COMMAND);
    
    // Ekran görüntüsü al
    const timestamp = Date.now();
    const safeName = command.replace(/[^a-zA-Z0-9]/g, '_').substring(0, 50);
    const filename = `output-${safeName}-${timestamp}.png`;
    const filepath = path.join(__dirname, filename);
    
    await page.screenshot({ path: filepath });
    
    // Metni çıkarmaya çalış (OCR ile)
    const extractedText = await extractTextFromTerminal();
    
    return {
      content: [
        {
          type: 'text',
          text: `Command: ${command}\n\nExtracted Output:\n${extractedText}\n\nScreenshot saved: ${filename}`
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
    // Take a screenshot first
    const timestamp = Date.now();
    const tempFile = path.join(__dirname, `temp-ocr-${timestamp}.png`);
    await page.screenshot({ path: tempFile });
    
    // Use Tesseract.js with better settings for terminal text
    const { data: { text } } = await Tesseract.recognize(
      tempFile,
      'eng',
      {
        logger: m => {
          if (m.status === 'recognizing text') {
            console.error(`OCR Progress: ${Math.round(m.progress * 100)}%`);
          }
        },
        tessedit_char_whitelist: '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ \n',
        preserve_interword_spaces: '1',
        tessedit_pageseg_mode: '6', // Uniform block of text
      }
    );
    
    // Clean up temp file
    await fs.unlink(tempFile).catch(() => {});
    
    // Process the text to extract command output
    const lines = text.split('\n');
    const processedLines = [];
    let foundCommand = false;
    let foundPrompt = false;
    
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.length === 0) continue;
      
      // Look for command line (contains $ and the command)
      if (trimmed.includes('$') && !foundCommand) {
        foundCommand = true;
        const commandPart = trimmed.split('$')[1]?.trim();
        if (commandPart) {
          processedLines.push(`Command: ${commandPart}`);
        }
        continue;
      }
      
      // Skip the next prompt line (after output)
      if (foundCommand && trimmed.includes('$') && trimmed.includes('@')) {
        foundPrompt = true;
        continue;
      }
      
      // Add output lines
      if (foundCommand && !foundPrompt) {
        processedLines.push(trimmed);
      }
    }
    
    const result = processedLines.join('\n');
    return result || 'No text extracted from terminal';
    
  } catch (error) {
    console.error('OCR error:', error);
    return 'OCR extraction failed. Please check the screenshot.';
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