#!/usr/bin/env node
import { McpServer } from '@modelcontextprotocol/server';
import { StdioServerTransport } from '@modelcontextprotocol/server/stdio';
import { chromium } from 'playwright';
import dotenv from 'dotenv';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import Tesseract from 'tesseract.js';
import { z } from 'zod';

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SESSION_FILE = path.join(__dirname, 'session-state.json');

// Configuration from environment
const DEFAULT_TERMINAL_URL = process.env.TERMINAL_URL || '';
const WAIT_AFTER_COMMAND = Number.parseInt(process.env.WAIT_AFTER_COMMAND || '2000', 10);
const WAIT_AFTER_CLEAR = Number.parseInt(process.env.WAIT_AFTER_CLEAR || '1000', 10);
const WAIT_AFTER_CLICK = Number.parseInt(process.env.WAIT_AFTER_CLICK || '500', 10);

// Screenshots land outside the package by default, so running the server does
// not litter the checkout.
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR || path.join(os.tmpdir(), 'asger-terminal-mcp');

// Commands that destroy something on the remote host. These are confirmed with
// the user before they are typed into the terminal.
const DESTRUCTIVE_PATTERNS = [
  [/\brm\s+-[a-z]*[rf]/i, 'dosya/dizin siliyor'],
  [/\b(shutdown|reboot|halt|poweroff)\b|\binit\s+[06]\b/i, 'sunucuyu kapatıyor/yeniden başlatıyor'],
  [/\bmkfs\b|\bdd\s+.*of=\/dev\//i, 'diski biçimlendiriyor'],
  [/\b(kill\s+-9|killall|pkill)\b/i, 'süreçleri zorla sonlandırıyor'],
  [/\b(chown|chmod)\s+-[a-z]*R/i, 'izinleri özyinelemeli değiştiriyor'],
  [/\b(apt|apt-get|yum|dnf)\s+(remove|purge|autoremove)\b/i, 'paket kaldırıyor'],
  [/\bdocker\s+(rm|rmi|prune|system\s+prune)\b/i, 'Docker kaynaklarını siliyor'],
  [/\b(drop\s+(database|table)|truncate\s+table)\b/i, 'veritabanı nesnesi siliyor'],
  [/\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f)\b/i, 'commit edilmemiş değişiklikleri siliyor'],
  [/>\s*\/(?!tmp)/, 'sistem dosyasının üzerine yazıyor'],
];

export const server = new McpServer({
  name: 'asger-terminal-mcp',
  version: '2.0.0',
});

// Browser state, shared across tool calls for the life of the process.
let browser = null;
let context = null;
let page = null;

async function loadSession() {
  try {
    return JSON.parse(await fs.readFile(SESSION_FILE, 'utf-8'));
  } catch {
    return null;
  }
}

/** The open page, or an error telling the caller to open the terminal first. */
function requirePage() {
  if (!page) {
    throw new Error('Terminal açık değil. Önce open_terminal aracını çağırın.');
  }
  return page;
}

/** Why this command needs confirming, or null when it is ordinary. */
function destructiveReason(command) {
  for (const [pattern, reason] of DESTRUCTIVE_PATTERNS) {
    if (pattern.test(command)) return reason;
  }
  return null;
}

/**
 * Ask the user before running a destructive command. Returns true to proceed.
 * A client with no elicitation support refuses rather than running it blind.
 */
async function confirmCommand(ctx, command) {
  const reason = destructiveReason(command);
  if (!reason) return true;

  let answer;
  try {
    answer = await ctx.mcpReq.elicitInput({
      message: `Bu komut ${reason}:\n\n    ${command}\n\nTerminalde çalıştırılsın mı?`,
      requestedSchema: {
        type: 'object',
        properties: {
          confirm: {
            type: 'boolean',
            title: 'Çalıştır',
            description: 'Komut uzak terminalde çalıştırılsın mı?',
          },
        },
        required: ['confirm'],
      },
    });
  } catch (error) {
    throw new Error(
      `Yıkıcı komut için onay alınamadı (${error.message}); komut çalıştırılmadı: ${command}`
    );
  }

  return answer.action === 'accept' && answer.content?.confirm === true;
}

/** Where a screenshot for `label` should be written. */
async function screenshotPath(label) {
  await fs.mkdir(SCREENSHOT_DIR, { recursive: true });
  const safeName = label.replace(/[^a-zA-Z0-9]/g, '_').slice(0, 50) || 'terminal';
  return path.join(SCREENSHOT_DIR, `${safeName}-${Date.now()}.png`);
}

/** Focus the terminal, optionally clear it, then type a command and press Enter. */
async function typeCommand(command, { clearBefore }) {
  const target = requirePage();

  await target.mouse.click(640, 400);
  await target.waitForTimeout(WAIT_AFTER_CLICK);

  if (clearBefore) {
    await target.keyboard.type('clear');
    await target.keyboard.press('Enter');
    await target.waitForTimeout(WAIT_AFTER_CLEAR);
  }

  await target.keyboard.type(command);
  await target.keyboard.press('Enter');
  await target.waitForTimeout(WAIT_AFTER_COMMAND);
}

/**
 * OCR the current terminal screen.
 *
 * The terminal renders to a canvas, so there is no DOM text to read; a
 * screenshot through Tesseract is the only thing available here.
 */
async function readScreen(ctx, { keepFile = false, label = 'ocr' } = {}) {
  const target = requirePage();
  const file = await screenshotPath(label);
  await target.screenshot({ path: file });

  const progressToken = ctx?.mcpReq?._meta?.progressToken;
  const notifyProgress = async (progress) => {
    if (progressToken === undefined) return;
    await ctx.mcpReq.notify({
      method: 'notifications/progress',
      params: { progressToken, progress, total: 1, message: 'OCR' },
    });
  };

  let text = '';
  try {
    const result = await Tesseract.recognize(file, 'eng', {
      logger: (m) => {
        if (m.status === 'recognizing text') {
          notifyProgress(m.progress).catch(() => {});
        }
      },
      tessedit_char_whitelist:
        '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ \n',
      preserve_interword_spaces: '1',
      tessedit_pageseg_mode: '6', // Uniform block of text
    });
    text = result.data.text;
  } finally {
    if (!keepFile) await fs.unlink(file).catch(() => {});
  }

  return { rawText: text, lines: extractOutputLines(text), screenshotPath: keepFile ? file : null };
}

/**
 * Trim the OCR'd screen down to the command's output: drop everything before
 * the prompt line that ran it, and stop at the next prompt.
 */
function extractOutputLines(text) {
  const output = [];
  let seenCommand = false;

  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (trimmed.length === 0) continue;

    if (!seenCommand && trimmed.includes('$')) {
      seenCommand = true;
      continue;
    }
    if (seenCommand && trimmed.includes('$') && trimmed.includes('@')) {
      break; // the next prompt: the output ended here
    }
    if (seenCommand) output.push(trimmed);
  }

  return output;
}

const OCR_CAVEAT =
  'Metin OCR ile okundu; terminal canvas olarak çizildiği için karakterler yanlış tanınmış olabilir. ' +
  'Kritik değerleri ekran görüntüsünden doğrulayın.';

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

server.registerTool(
  'open_terminal',
  {
    title: 'Terminali aç',
    description:
      "Terminal URL'sini bir tarayıcıda açar. Kayıtlı oturum varsa yüklenir; yoksa giriş " +
      'sayfası açılır ve giriş yaptıktan sonra save_session çağrılmalıdır.',
    inputSchema: z.object({
      url: z
        .string()
        .url()
        .optional()
        .describe(`Terminal URL. Varsayılan: ${DEFAULT_TERMINAL_URL || 'ayarlanmamış'}`),
    }),
    outputSchema: z.object({
      url: z.string(),
      loginRequired: z.boolean().describe('true ise manuel giriş yapıp save_session çağırın.'),
      sessionRestored: z.boolean().describe('Kayıtlı oturum yüklendi mi.'),
    }),
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
  },
  async ({ url }) => {
    const target = url || DEFAULT_TERMINAL_URL;
    if (!target) {
      throw new Error(
        'Terminal URL belirtilmedi. .env dosyasında TERMINAL_URL ayarlayın ya da url parametresi gönderin.'
      );
    }

    if (browser) await closeBrowser();

    browser = await chromium.launch({
      headless: false,
      args: ['--disable-blink-features=AutomationControlled'],
    });

    const savedSession = await loadSession();
    context = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      ...(savedSession ? { storageState: savedSession } : {}),
    });
    page = await context.newPage();

    await page.goto(target);
    await page.waitForTimeout(5000);

    const loginRequired = (await page.$('input[type="password"]')) !== null;
    const result = { url: target, loginRequired, sessionRestored: savedSession !== null };

    return {
      content: [
        {
          type: 'text',
          text: loginRequired
            ? 'Giriş sayfası açıldı. Manuel olarak giriş yapın, ardından save_session aracını çağırın.'
            : 'Terminal hazır. Önceki oturum yüklendi.',
        },
      ],
      structuredContent: result,
    };
  }
);

server.registerTool(
  'save_session',
  {
    title: 'Oturumu kaydet',
    description:
      'Tarayıcıdaki oturum durumunu (çerezler, storage) diske kaydeder; sonraki açılışta ' +
      'yeniden giriş gerekmez.',
    outputSchema: z.object({ sessionFile: z.string() }),
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  },
  async () => {
    requirePage();
    const state = await context.storageState();
    await fs.writeFile(SESSION_FILE, JSON.stringify(state, null, 2));
    return {
      content: [{ type: 'text', text: `Oturum kaydedildi: ${SESSION_FILE}` }],
      structuredContent: { sessionFile: SESSION_FILE },
    };
  }
);

server.registerTool(
  'execute_command',
  {
    title: 'Komut çalıştır',
    description:
      'Terminale bir komut yazar ve Enter\'a basar. Çıktıyı okumaz — çıktı için ' +
      'execute_and_read kullanın. Yıkıcı komutlar önce kullanıcıya sorulur.',
    inputSchema: z.object({
      command: z.string().min(1).describe('Çalıştırılacak komut.'),
      clear_before: z
        .boolean()
        .default(true)
        .describe('Komuttan önce ekranı temizle.'),
    }),
    outputSchema: z.object({
      command: z.string(),
      cleared: z.boolean(),
    }),
    annotations: { readOnlyHint: false, destructiveHint: true, openWorldHint: true },
  },
  async ({ command, clear_before }, ctx) => {
    requirePage();
    if (!(await confirmCommand(ctx, command))) {
      throw new Error(`Kullanıcı komutu onaylamadı; hiçbir şey çalıştırılmadı: ${command}`);
    }

    await typeCommand(command, { clearBefore: clear_before });
    return {
      content: [{ type: 'text', text: `Komut çalıştırıldı: ${command}` }],
      structuredContent: { command, cleared: clear_before },
    };
  }
);

server.registerTool(
  'execute_and_read',
  {
    title: 'Komut çalıştır ve oku',
    description:
      'Ekranı temizler, komutu çalıştırır, ekran görüntüsü alır ve çıktıyı OCR ile okur. ' +
      'Yıkıcı komutlar önce kullanıcıya sorulur.',
    inputSchema: z.object({
      command: z.string().min(1).describe('Çalıştırılacak komut.'),
    }),
    outputSchema: z.object({
      command: z.string(),
      output: z.string().describe('OCR ile okunan komut çıktısı.'),
      lines: z.array(z.string()).describe('Çıktının satır satır hâli.'),
      screenshotPath: z.string().nullable().describe('Kaydedilen ekran görüntüsünün yolu.'),
      caveat: z.string().describe('OCR güvenilirliği hakkında uyarı.'),
    }),
    annotations: { readOnlyHint: false, destructiveHint: true, openWorldHint: true },
  },
  async ({ command }, ctx) => {
    requirePage();
    if (!(await confirmCommand(ctx, command))) {
      throw new Error(`Kullanıcı komutu onaylamadı; hiçbir şey çalıştırılmadı: ${command}`);
    }

    await typeCommand(command, { clearBefore: true });
    const { lines, screenshotPath: file } = await readScreen(ctx, {
      keepFile: true,
      label: command,
    });
    const output = lines.join('\n');

    return {
      content: [
        {
          type: 'text',
          text: `Command: ${command}\n\nOutput:\n${output || '(metin okunamadı)'}\n\n${OCR_CAVEAT}\nScreenshot: ${file}`,
        },
      ],
      structuredContent: { command, output, lines, screenshotPath: file, caveat: OCR_CAVEAT },
    };
  }
);

server.registerTool(
  'take_screenshot',
  {
    title: 'Ekran görüntüsü al',
    description:
      'Terminalin ekran görüntüsünü alır ve hem görüntü olarak hem de dosya yolu olarak döner.',
    outputSchema: z.object({
      screenshotPath: z.string(),
      widthHint: z.number().describe('Görüntünün piksel genişliği.'),
      heightHint: z.number().describe('Görüntünün piksel yüksekliği.'),
    }),
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  async () => {
    const target = requirePage();
    const file = await screenshotPath('terminal');
    const buffer = await target.screenshot({ path: file });
    const viewport = target.viewportSize() ?? { width: 0, height: 0 };

    return {
      content: [
        { type: 'image', data: buffer.toString('base64'), mimeType: 'image/png' },
        { type: 'text', text: `Ekran görüntüsü kaydedildi: ${file}` },
      ],
      structuredContent: {
        screenshotPath: file,
        widthHint: viewport.width,
        heightHint: viewport.height,
      },
    };
  }
);

server.registerTool(
  'extract_text',
  {
    title: 'Ekrandaki metni oku',
    description:
      'Terminalin o anki ekranını OCR ile metne çevirir. Terminal canvas olarak çizildiği ' +
      'için DOM metni yoktur; sonuç OCR doğruluğuyla sınırlıdır.',
    outputSchema: z.object({
      output: z.string().describe('Komut çıktısı olarak ayıklanan kısım.'),
      lines: z.array(z.string()),
      rawText: z.string().describe('OCR çıktısının tamamı, ayıklama öncesi.'),
      caveat: z.string(),
    }),
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  async (ctx) => {
    requirePage();
    const { rawText, lines } = await readScreen(ctx, { label: 'extract' });
    const output = lines.join('\n');
    if (!rawText.trim()) {
      throw new Error('Ekrandan hiç metin okunamadı. Terminal görünür ve okunabilir durumda mı?');
    }
    return {
      content: [{ type: 'text', text: `${output || rawText.trim()}\n\n${OCR_CAVEAT}` }],
      structuredContent: { output, lines, rawText, caveat: OCR_CAVEAT },
    };
  }
);

server.registerTool(
  'disconnect',
  {
    title: 'Bağlantıyı kapat',
    description: 'Tarayıcıyı kapatır ve terminal oturumunu bırakır.',
    outputSchema: z.object({ wasOpen: z.boolean() }),
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
  },
  async () => {
    const wasOpen = browser !== null;
    await closeBrowser();
    return {
      content: [{ type: 'text', text: wasOpen ? 'Bağlantı kapatıldı.' : 'Zaten kapalıydı.' }],
      structuredContent: { wasOpen },
    };
  }
);

server.registerTool(
  'clear_session',
  {
    title: 'Kayıtlı oturumu sil',
    description:
      'Diskteki oturum dosyasını siler. Sonraki open_terminal çağrısında yeniden giriş gerekir.',
    outputSchema: z.object({ existed: z.boolean(), sessionFile: z.string() }),
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true },
  },
  async () => {
    let existed = true;
    try {
      await fs.unlink(SESSION_FILE);
    } catch {
      existed = false;
    }
    return {
      content: [
        {
          type: 'text',
          text: existed ? 'Kayıtlı oturum silindi.' : 'Silinecek kayıtlı oturum yoktu.',
        },
      ],
      structuredContent: { existed, sessionFile: SESSION_FILE },
    };
  }
);

server.registerPrompt(
  'terminal_arastir',
  {
    title: 'Terminalde araştır',
    description: 'Uzak sunucuda bir soruyu adım adım, komut çalıştırarak araştır.',
    argsSchema: z.object({
      soru: z.string().describe('Sunucuda cevaplanacak soru.'),
    }),
  },
  ({ soru }) => ({
    messages: [
      {
        role: 'user',
        content: {
          type: 'text',
          text:
            `Uzak terminalde şu soruyu araştır: ${soru}\n\n` +
            '1. Gerekirse `open_terminal` ile terminali aç.\n' +
            '2. Her adımda tek bir komut çalıştır; `execute_and_read` kullan ki çıktıyı görebilesin.\n' +
            '3. Çıktı OCR ile okunuyor: rakam ve yol gibi kritik değerleri şüpheyle karşıla, ' +
            'gerekirse `take_screenshot` ile görüntüden doğrula.\n' +
            '4. Okunamayan çıktıyı tahmin etme; komutu daha dar bir çıktı verecek şekilde tekrar yaz ' +
            '(head, grep, wc gibi).\n' +
            '5. Sonunda cevabı, dayandığın komut çıktılarıyla birlikte yaz.',
        },
      },
    ],
  })
);

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

async function closeBrowser() {
  if (browser) {
    await browser.close().catch(() => {});
  }
  browser = null;
  context = null;
  page = null;
}

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('asger-terminal-mcp started');

  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, () => {
      closeBrowser().finally(() => process.exit(0));
    });
  }
}

// Only serve over stdio when run as the program; importing the module (tests)
// gets the configured server without a transport attached.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error('Sunucu başlatılamadı:', error);
    process.exit(1);
  });
}
