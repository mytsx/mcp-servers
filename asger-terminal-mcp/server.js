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

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SESSION_FILE = path.join(__dirname, 'session-state.json');

const DEFAULT_TERMINAL_URL = process.env.TERMINAL_URL || '';
const WAIT_AFTER_COMMAND = parseInt(process.env.WAIT_AFTER_COMMAND || '2000');
const WAIT_AFTER_CLEAR = parseInt(process.env.WAIT_AFTER_CLEAR || '1000');
const WAIT_AFTER_CLICK = parseInt(process.env.WAIT_AFTER_CLICK || '500');

const server = new Server(
  { name: 'asger-terminal-mcp', version: '2.0.0' },
  { capabilities: { tools: {} } }
);

// Global state
let browser = null;
let context = null;
let page = null;

// --- Session Management ---

async function loadSession() {
  try {
    return JSON.parse(await fs.readFile(SESSION_FILE, 'utf-8'));
  } catch { return null; }
}

async function saveSession() {
  if (context) {
    const state = await context.storageState();
    await fs.writeFile(SESSION_FILE, JSON.stringify(state, null, 2));
  }
}

// --- Text Extraction: 3-Layer Hybrid ---

// Layer 1: Guacamole JS API buffer okuma
async function readViaGuacamoleBuffer() {
  if (!page) return null;
  try {
    const text = await page.evaluate(() => {
      // Approach 1: Guacamole.Client on Angular/global scope
      const guacElements = [
        window.client,
        window.guac,
        window.GuacamoleClient,
        document.querySelector('[guac-client]')?.__guac_client,
      ];

      for (const client of guacElements) {
        if (!client) continue;
        // Try to get display text
        const display = client.getDisplay?.();
        if (display) {
          const canvas = display.flatten?.();
          if (canvas) {
            // Display found but Canvas doesn't expose text directly
            // Try alternative: Guacamole.Terminal text buffer
          }
        }
      }

      // Approach 2: Find Guacamole managed clipboard
      const clipboardSelectors = [
        'textarea.clipboard',
        '.clipboard textarea',
        '#clipboard',
        'textarea[name="clipboard"]',
        '.guac-terminal-clipboard',
        '.text-input textarea',
        // ASGER specific selectors
        '.terminal-clipboard',
        '[class*="clipboard"] textarea',
      ];

      for (const sel of clipboardSelectors) {
        const el = document.querySelector(sel);
        if (el && el.value && el.value.trim().length > 0) {
          return el.value;
        }
      }

      // Approach 3: Angular scope access for ASGER
      const appRoot = document.querySelector('[ng-app]') || document.querySelector('app-root');
      if (appRoot) {
        try {
          const ngScope = window.angular?.element(appRoot)?.scope?.();
          if (ngScope?.client) {
            const clipboard = ngScope.client.clipboard;
            if (clipboard) return clipboard;
          }
        } catch {}
      }

      // Approach 4: Intercept from ManagedClient (Guacamole webapp pattern)
      try {
        const managedClients = window.sessionStorage?.getItem?.('GUAC_CLIPBOARD');
        if (managedClients) return managedClients;
      } catch {}

      // Approach 5: Look for any textarea that might hold terminal text
      const textareas = document.querySelectorAll('textarea');
      for (const ta of textareas) {
        if (ta.value && ta.value.trim().length > 10 && !ta.closest('form')) {
          return ta.value;
        }
      }

      return null;
    });

    if (text && text.trim().length > 0) {
      console.error('[Layer1] Guacamole buffer read successful');
      return text.trim();
    }
  } catch (err) {
    console.error('[Layer1] Guacamole buffer read failed:', err.message);
  }
  return null;
}

// Layer 2: Hex encoding ile komut çıktısını oku
// Hex sadece 0-9 a-f kullanır — OCR için base64'ten çok daha güvenilir
// Tek komutta: çalıştır → hex dump → exit code — tek OCR yeterli
async function readViaHex(command) {
  if (!page) return null;

  try {
    await focusTerminal();
    await clearScreen();
    await page.waitForTimeout(300);

    // Her şeyi TEK komutta yap: run → save exit → hex dump → markers → cleanup
    const oneShot = `(${command}) > /tmp/.mcp_out 2>&1; E=$?; echo ZZZSTARTZZZ; xxd -p /tmp/.mcp_out; echo ZZZENDZZZ; echo ZZZEXIT$E; rm -f /tmp/.mcp_out`;
    await page.keyboard.type(oneShot);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(WAIT_AFTER_COMMAND + 2000);

    // Step 3: Screenshot al ve OCR ile hex'i oku
    const ocrText = await ocrScreenshot();
    if (!ocrText) return null;

    // Sabit marker'ları bul — SON eşleşmeleri al (komut satırındakileri atla)
    const startPattern = /[Z27]{2,4}\s*START\s*[Z27]{2,4}/gi;
    const endPattern = /[Z27]{2,4}\s*END\s*[Z27]{2,4}/gi;

    const allStarts = [...ocrText.matchAll(startPattern)];
    const allEnds = [...ocrText.matchAll(endPattern)];
    const startMatch = allStarts[allStarts.length - 1] || null;
    const endMatch = allEnds[allEnds.length - 1] || null;

    if (!startMatch || !endMatch) {
      console.error(`[Layer2] Hex markers not found. start=${!!startMatch} end=${!!endMatch}`);
      console.error(`[Layer2] OCR text (first 500): ${ocrText?.substring(0, 500)}`);
      return null;
    }

    const startIdx = startMatch.index + startMatch[0].length;
    const endIdx = endMatch.index;

    const hexBlock = ocrText.substring(startIdx, endIdx).trim();

    // Exit code'u aynı OCR metninden çıkar
    // Son EXIT marker'ını al (komut satırındakini atla)
    const allExits = [...ocrText.matchAll(/[Z27]{2,4}\s*EXIT\s*([O0-9]+)/gi)];
    const exitMatch = allExits[allExits.length - 1] || null;
    const exitCode = exitMatch ? parseInt(exitMatch[1].replace(/[Oo]/g, '0')) : null;

    if (!hexBlock || hexBlock.length === 0) {
      console.error('[Layer2] Empty hex block');
      return { text: '', exitCode, method: 'hex' };
    }

    // Hex temizle: tüm bloğu birleştir, sadece 0-9 a-f bırak, OCR düzeltmeleri uygula
    const cleanHex = hexBlock
      .toLowerCase()
      // Önce OCR karakter düzeltmeleri (hex dışı → hex karşılığı)
      .replace(/o/g, '0')   // OCR: o → 0
      .replace(/g/g, '9')   // OCR: g → 9 (hex'de g yok)
      .replace(/h/g, 'b')   // OCR: h → b (hex'de h yok)
      .replace(/i/g, '1')   // OCR: i → 1 (hex'de i yok)
      .replace(/l/g, '1')   // OCR: l → 1 (hex'de l yok)
      .replace(/q/g, '9')   // OCR: q → 9 (hex'de q yok)
      .replace(/s/g, '5')   // OCR: s → 5 (hex'de s yok)
      .replace(/u/g, '0')   // OCR: u → 0 (hex'de u yok)
      .replace(/z/g, '2')   // OCR: z → 2 (hex'de z yok)
      // Son: hex olmayan her şeyi sil (boşluk, satır sonu, noktalama, $, @ vb.)
      .replace(/[^0-9a-f]/g, '');

    if (cleanHex.length % 2 !== 0) {
      // Tek sayı hex karakter — muhtemelen OCR bir karakter kaçırdı/ekledi
      console.error(`[Layer2] Odd hex length (${cleanHex.length}), trimming last char`);
    }

    const evenHex = cleanHex.length % 2 === 0 ? cleanHex : cleanHex.slice(0, -1);

    try {
      const decoded = Buffer.from(evenHex, 'hex').toString('utf-8');

      if (decoded && decoded.length > 0) {
        // Geçerlilik kontrolü: bozuk karakterler + yazdırılamayan kontrol karakterleri
        const badChars = (decoded.match(/\ufffd/g) || []).length;
        // Kontrol karakterleri (tab ve newline hariç): 0x00-0x08, 0x0B-0x0C, 0x0E-0x1F
        const ctrlChars = (decoded.match(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g) || []).length;
        const totalBad = badChars + ctrlChars;
        const badRatio = totalBad / decoded.length;

        if (badRatio < 0.05) {
          console.error(`[Layer2] Hex decode successful (${decoded.length} chars, ${totalBad} bad)`);
          return { text: decoded.trimEnd(), exitCode, method: 'hex' };
        }
        console.error(`[Layer2] Hex decode too many bad chars (${totalBad}/${decoded.length} = ${(badRatio * 100).toFixed(1)}%)`);
      }
    } catch (decodeErr) {
      console.error('[Layer2] Hex decode failed:', decodeErr.message);
    }

    // Hex decode başarısız — debug bilgisi ile dön
    return { text: null, exitCode, method: 'hex-fail', _debug: `markers: start=${!!startMatch} end=${!!endMatch}, hexLen=${cleanHex?.length || 0}, rawHex=${hexBlock?.substring(0, 100)}` };
  } catch (err) {
    console.error('[Layer2] Hex method failed:', err.message);
    try {
      await page.keyboard.type('rm -f /tmp/.mcp_out 2>/dev/null');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(500);
    } catch {}
    // Exception bilgisi ile dön
    return { text: null, exitCode: null, method: 'hex-error', _debug: err.message };
  }
}

// Layer 3: Improved OCR (fallback)
async function readViaOCR() {
  if (!page) return null;

  try {
    const text = await ocrScreenshot();
    if (text && text.trim().length > 0) {
      console.error(`[Layer3] OCR extraction (${text.length} chars)`);
      return { text: text.trim(), exitCode: null, method: 'ocr' };
    }
  } catch (err) {
    console.error('[Layer3] OCR failed:', err.message);
  }
  return null;
}

// OCR helper - improved Tesseract settings
async function ocrScreenshot() {
  const tempFile = path.join(__dirname, `temp-ocr-${Date.now()}.png`);
  try {
    await page.screenshot({ path: tempFile });

    const { data: { text } } = await Tesseract.recognize(tempFile, 'eng', {
      logger: m => {
        if (m.status === 'recognizing text') {
          console.error(`OCR: ${Math.round(m.progress * 100)}%`);
        }
      },
      tessedit_char_whitelist: '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ \n\t',
      preserve_interword_spaces: '1',
      tessedit_pageseg_mode: '6',
    });

    return text || null;
  } finally {
    await fs.unlink(tempFile).catch(() => {});
  }
}

// --- Terminal Helpers ---

async function focusTerminal() {
  await page.mouse.click(640, 400);
  await page.waitForTimeout(WAIT_AFTER_CLICK);
}

async function typeAndExecute(command) {
  await focusTerminal();
  await page.keyboard.type(command);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(WAIT_AFTER_COMMAND);
}

async function clearScreen() {
  await page.keyboard.type('clear');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(WAIT_AFTER_CLEAR);
}

// --- Tool Implementations ---

async function openTerminal({ url = DEFAULT_TERMINAL_URL } = {}) {
  try {
    if (!url) {
      throw new Error('Terminal URL belirtilmedi. .env dosyasında TERMINAL_URL ayarlayın veya url parametresi gönderin.');
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
      return { content: [{ type: 'text', text: 'Giriş sayfası açıldı. Lütfen manuel olarak giriş yapın ve ardından save_session komutunu çalıştırın.' }] };
    }

    // Bağlantı bilgilerini topla
    const pageTitle = await page.title().catch(() => '');
    return {
      content: [{
        type: 'text',
        text: `Terminal hazır! Önceki oturum başarıyla yüklendi.${pageTitle ? ` (${pageTitle})` : ''}`
      }]
    };
  } catch (error) {
    return { content: [{ type: 'text', text: `Bağlantı hatası: ${error.message}` }] };
  }
}

async function saveSessionHandler() {
  try {
    if (!page) throw new Error('Önce open_terminal ile terminali açın');
    await saveSession();
    return { content: [{ type: 'text', text: 'Oturum başarıyla kaydedildi!' }] };
  } catch (error) {
    return { content: [{ type: 'text', text: `Kaydetme hatası: ${error.message}` }] };
  }
}

async function executeCommand({ command, clear_before = true }) {
  try {
    if (!page) throw new Error('Önce open_terminal ile terminali açın');

    await focusTerminal();
    if (clear_before) await clearScreen();

    await page.keyboard.type(command);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(WAIT_AFTER_COMMAND);

    return { content: [{ type: 'text', text: `Komut çalıştırıldı: ${command}` }] };
  } catch (error) {
    return { content: [{ type: 'text', text: `Komut hatası: ${error.message}` }] };
  }
}

async function executeAndRead({ command, method = 'auto', wait_ms }) {
  try {
    if (!page) throw new Error('Önce open_terminal ile terminali açın');

    const effectiveWait = wait_ms || WAIT_AFTER_COMMAND;
    const originalWait = WAIT_AFTER_COMMAND;

    let result = null;
    let screenshotFile = null;

    // Method selection
    if (method === 'auto' || method === 'buffer') {
      // Önce komutu çalıştır (OCR/buffer için)
      await focusTerminal();
      await clearScreen();
      await page.keyboard.type(command);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(effectiveWait);

      // Layer 1: Guacamole buffer dene
      result = await readViaGuacamoleBuffer();
      if (result) {
        result = { text: result, exitCode: null, method: 'buffer' };
      }
    }

    let hexExitCode = null;

    let hexDebug = null;

    if (!result && (method === 'auto' || method === 'base64')) {
      // Layer 2: Hex encoding sarmalama
      const hexResult = await readViaHex(command);
      if (hexResult) {
        hexExitCode = hexResult.exitCode;
        hexDebug = hexResult._debug || null;
        if (hexResult.text !== null) {
          result = hexResult;
        }
      }
    }

    if (!result) {
      // Layer 3: OCR fallback — her zaman son çare olarak çalışır
      if (method === 'ocr' || method === 'base64' || hexExitCode !== null || method === 'auto') {
        // Komutu tekrar çalıştır (temiz ekranda OCR için)
        await focusTerminal();
        await clearScreen();
        await page.keyboard.type(command);
        await page.keyboard.press('Enter');
        await page.waitForTimeout(effectiveWait);
      }

      // Screenshot al ve OCR yap
      const timestamp = Date.now();
      const safeName = command.replace(/[^a-zA-Z0-9]/g, '_').substring(0, 50);
      screenshotFile = `output-${safeName}-${timestamp}.png`;
      await page.screenshot({ path: path.join(__dirname, screenshotFile) });

      result = await readViaOCR();

      // Hex'ten gelen exit code'u OCR sonucuna ekle
      if (result && hexExitCode !== null && result.exitCode === null) {
        result.exitCode = hexExitCode;
      }
    }

    // Screenshot yoksa al (base64/buffer başarılı olduysa bile referans için)
    if (!screenshotFile) {
      const timestamp = Date.now();
      const safeName = command.replace(/[^a-zA-Z0-9]/g, '_').substring(0, 50);
      screenshotFile = `output-${safeName}-${timestamp}.png`;
      await page.screenshot({ path: path.join(__dirname, screenshotFile) });
    }

    if (!result) {
      return {
        content: [{
          type: 'text',
          text: `Command: ${command}\n\nExtracted Output:\nMetin çıkarılamadı. Screenshot: ${screenshotFile}`
        }]
      };
    }

    // Structured output
    const parts = [`Command: ${command}`];
    parts.push(`\nExtracted Output:\n${result.text}`);
    if (result.exitCode !== null && result.exitCode !== undefined) {
      parts.push(`\nExit Code: ${result.exitCode}`);
    }
    parts.push(`\nMethod: ${result.method}`);
    if (hexDebug) parts.push(`Hex debug: ${hexDebug}`);
    parts.push(`Screenshot saved: ${screenshotFile}`);

    return { content: [{ type: 'text', text: parts.join('\n') }] };
  } catch (error) {
    return { content: [{ type: 'text', text: `Hata: ${error.message}` }] };
  }
}

async function takeScreenshot() {
  try {
    if (!page) throw new Error('Önce open_terminal ile terminali açın');

    const filename = `terminal-${Date.now()}.png`;
    await page.screenshot({ path: path.join(__dirname, filename) });

    return { content: [{ type: 'text', text: `Ekran görüntüsü alındı: ${filename}` }] };
  } catch (error) {
    return { content: [{ type: 'text', text: `Screenshot hatası: ${error.message}` }] };
  }
}

async function extractText() {
  try {
    if (!page) throw new Error('Önce open_terminal ile terminali açın');

    // Önce Guacamole buffer dene
    const bufferText = await readViaGuacamoleBuffer();
    if (bufferText) {
      return { content: [{ type: 'text', text: `[buffer] ${bufferText}` }] };
    }

    // OCR fallback
    const ocrResult = await readViaOCR();
    if (ocrResult) {
      return { content: [{ type: 'text', text: `[ocr] ${ocrResult.text}` }] };
    }

    return { content: [{ type: 'text', text: 'Metin çıkarılamadı' }] };
  } catch (error) {
    return { content: [{ type: 'text', text: `Metin çıkarma hatası: ${error.message}` }] };
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
    return { content: [{ type: 'text', text: 'Bağlantı kapatıldı' }] };
  } catch (error) {
    return { content: [{ type: 'text', text: `Kapatma hatası: ${error.message}` }] };
  }
}

async function clearSession() {
  try {
    await fs.unlink(SESSION_FILE).catch(() => {});
    return { content: [{ type: 'text', text: 'Oturum bilgileri temizlendi' }] };
  } catch (error) {
    return { content: [{ type: 'text', text: `Temizleme hatası: ${error.message}` }] };
  }
}

// --- Tool Definitions ---

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: 'open_terminal',
      description: 'Terminal URL\'sini aç (manuel giriş için)',
      inputSchema: {
        type: 'object',
        properties: {
          url: { type: 'string', description: `Terminal URL (varsayılan: ${DEFAULT_TERMINAL_URL || 'ayarlanmamış'})` }
        }
      }
    },
    {
      name: 'save_session',
      description: 'Giriş yaptıktan sonra oturumu kaydet',
      inputSchema: { type: 'object', properties: {} }
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
      description: 'Komutu çalıştır ve çıktıyı oku. Hibrit yaklaşım: önce Guacamole buffer, sonra base64 encoding, son çare OCR. Exit code ve method bilgisi döner.',
      inputSchema: {
        type: 'object',
        properties: {
          command: { type: 'string', description: 'Çalıştırılacak komut' },
          method: {
            type: 'string',
            enum: ['auto', 'buffer', 'base64', 'ocr'],
            description: 'Metin çıkarma yöntemi. auto: sırasıyla buffer→hex→ocr dener (varsayılan). buffer: sadece Guacamole buffer. base64: komut çıktısını hex encode edip decode eder (en güvenilir, sadece 0-9a-f). ocr: sadece screenshot+OCR.'
          },
          wait_ms: {
            type: 'number',
            description: 'Komut sonrası bekleme süresi (ms). Uzun süren komutlar için artırın. Varsayılan: 2000'
          }
        },
        required: ['command']
      }
    },
    {
      name: 'take_screenshot',
      description: 'Terminal ekran görüntüsü al',
      inputSchema: { type: 'object', properties: {} }
    },
    {
      name: 'extract_text',
      description: 'Terminalden metin çıkar. Önce Guacamole buffer dener, sonra OCR. Çıktıda [buffer] veya [ocr] etiketi hangi yöntemin kullanıldığını gösterir.',
      inputSchema: { type: 'object', properties: {} }
    },
    {
      name: 'disconnect',
      description: 'Terminal bağlantısını kapat',
      inputSchema: { type: 'object', properties: {} }
    },
    {
      name: 'clear_session',
      description: 'Kayıtlı oturumu temizle',
      inputSchema: { type: 'object', properties: {} }
    }
  ]
}));

// --- Request Handler ---

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  console.error(`Tool called: ${name}`, args);

  switch (name) {
    case 'open_terminal': return await openTerminal(args);
    case 'save_session': return await saveSessionHandler();
    case 'execute_command': return await executeCommand(args);
    case 'execute_and_read': return await executeAndRead(args);
    case 'take_screenshot': return await takeScreenshot();
    case 'extract_text': return await extractText();
    case 'disconnect': return await disconnect();
    case 'clear_session': return await clearSession();
    default: throw new Error(`Unknown tool: ${name}`);
  }
});

// --- Start ---

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('ASGER Terminal MCP server v2.0.0 started (hybrid: buffer→base64→ocr)');
}

main().catch(console.error);
