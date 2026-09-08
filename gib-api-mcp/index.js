#!/usr/bin/env node
import { McpServer } from '@modelcontextprotocol/server';
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import { realpathSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { z } from 'zod';

const BASE_URL = process.env.GIB_API_URL;
const API_KEY = process.env.GIB_API_KEY || '';

if (!BASE_URL) {
  console.error(
    'HATA: GIB_API_URL environment variable zorunludur.\n' +
    'Kendi worker\'ınızı deploy edin: https://github.com/mytsx/gib-gecikme-zammi-faizi\n' +
    'Örnek: GIB_API_URL=https://your-worker.your-account.workers.dev'
  );
  process.exit(1);
}

/** Whether an 8-digit string is a date that exists (20260231 is not). */
function isRealDate(value) {
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(4, 6));
  const day = Number(value.slice(6, 8));
  if (year < 1900 || month < 1 || month > 12 || day < 1) return false;

  const asDate = new Date(Date.UTC(year, month - 1, day));
  return (
    asDate.getUTCFullYear() === year &&
    asDate.getUTCMonth() === month - 1 &&
    asDate.getUTCDate() === day
  );
}

const dateField = (description) =>
  z
    .string()
    .regex(/^\d{8}$/, 'Tarih YYYYAAGG biçiminde 8 haneli olmalı, örnek: "20260101"')
    .refine(isRealDate, 'Takvimde olmayan tarih. Örnek geçerli değer: "20260101"')
    .describe(description);

const amountField = (description) =>
  z
    .string()
    .regex(/^\d+([.,]\d{1,2})?$/, 'Tutar sayı olmalı, örnek: "1000.00"')
    .describe(description);

const inputSchema = (vadeDescription, odemeDescription) =>
  z.object({
    odenecekMiktar: amountField('Borç tutarı (TL). Örnek: "1000.00"'),
    vadeTarihi: dateField(vadeDescription),
    odemeTarihi: dateField(odemeDescription),
  });

const outputSchema = z.object({
  tip: z.string().describe('Hangi hesaplama yapıldı: Gecikme Zammı ya da Gecikme Faizi.'),
  anaPara: z.string().describe('Hesaplamaya giren ana para, TL.'),
  vadeTarihi: z.string().describe('Vade tarihi, YYYYAAGG.'),
  odemeTarihi: z.string().describe('Ödeme ya da tahakkuk tarihi, YYYYAAGG.'),
  gecikmeOrani: z.string().describe('Uygulanan toplam gecikme oranı.'),
  gecikmeTutari: z.string().describe('Hesaplanan gecikme tutarı, TL.'),
  toplamOdenecek: z.string().describe('Ana para + gecikme tutarı, TL.'),
});

/** Post to the calculation worker and return its parsed body. */
async function callGibApi(endpoint, params) {
  let response;
  try {
    response = await fetch(`${BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(API_KEY && { 'X-API-Key': API_KEY }),
      },
      body: JSON.stringify(params),
    });
  } catch (error) {
    // Anything can be thrown, not just an Error; reading .message off a
    // non-Error would mask the real failure with a TypeError.
    const reason = error instanceof Error ? error.message : String(error);
    throw new Error(`GİB API'sine ulaşılamadı (${BASE_URL}): ${reason}`, { cause: error });
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

/** Turn the worker's response into this server's result shape. */
function toResult(apiResult, tipiLabel) {
  const hesaplama = apiResult?.hesaplamaList?.[0];
  if (!hesaplama) {
    throw new Error('Hesaplama sonucu alınamadı: GİB API beklenen alanları döndürmedi.');
  }

  return {
    tip: tipiLabel,
    anaPara: String(hesaplama.odenecekMiktar),
    vadeTarihi: String(hesaplama.vadeTarihi),
    odemeTarihi: String(hesaplama.odemeTarihi),
    gecikmeOrani: String(hesaplama.hesaplananZamOrani),
    gecikmeTutari: String(hesaplama.hesaplananFaizTutari),
    toplamOdenecek: String(hesaplama.hesaplananMiktar),
  };
}

/** The text a model reads, alongside the structured content. */
function summarize(result) {
  return [
    `GİB ${result.tip} Hesaplama Sonucu:`,
    '',
    `Ana Para: ${result.anaPara} TL`,
    `Vade Tarihi: ${result.vadeTarihi}`,
    `Ödeme Tarihi: ${result.odemeTarihi}`,
    `Gecikme Oranı: ${result.gecikmeOrani}`,
    `Gecikme Tutarı: ${result.gecikmeTutari} TL`,
    `Toplam Ödenecek: ${result.toplamOdenecek} TL`,
  ].join('\n');
}

/** Register one calculation tool; the two differ only in endpoint and wording. */
function registerCalculation(server, { name, title, description, endpoint, label, vade, odeme }) {
  server.registerTool(
    name,
    {
      title,
      description,
      inputSchema: inputSchema(vade, odeme),
      outputSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async ({ odenecekMiktar, vadeTarihi, odemeTarihi }) => {
      const apiResult = await callGibApi(endpoint, { odenecekMiktar, vadeTarihi, odemeTarihi });
      const result = toResult(apiResult, label);
      return {
        content: [{ type: 'text', text: summarize(result) }],
        structuredContent: result,
      };
    }
  );
}

/**
 * Build a fresh server. `serveStdio` calls this once per connection, so that a
 * connection's protocol era is pinned to its own instance.
 */
export function buildServer() {
  const server = new McpServer({
    name: 'gib-api-mcp',
    version: '2.0.0',
  });

  registerCalculation(server, {
    name: 'calculate_gecikme_zammi',
    title: 'Gecikme zammı hesapla',
    description:
      'GIB Gecikme Zammı hesapla (6183 sayılı AATUHK m.51). Kesinleşmiş vergi borcu vadesinde ' +
      'ödenmezse, vade tarihinden fiili ödeme tarihine kadar aylık+günlük karma sistemle hesaplanır.',
    endpoint: '/api/gecikme-zammi',
    label: 'Gecikme Zammı',
    vade: 'Vade tarihi (YYYYAAGG). Örnek: "20260101"',
    odeme: 'Fiili ödeme tarihi (YYYYAAGG). Örnek: "20260301"',
  });

  registerCalculation(server, {
    name: 'calculate_gecikme_faizi',
    title: 'Gecikme faizi hesapla',
    description:
      'GIB Gecikme Faizi hesapla (213 sayılı VUK m.112). İkmalen/resen/idarece yapılan ' +
      'tarhiyatlarda, normal vade tarihinden tahakkuk tarihine kadar sadece tam ay esasına göre hesaplanır.',
    endpoint: '/api/gecikme-faizi',
    label: 'Gecikme Faizi',
    vade: 'Normal vade tarihi (YYYYAAGG). Örnek: "20260101"',
    odeme: 'Tahakkuk/tarhiyat tarihi (YYYYAAGG). Örnek: "20260601"',
  });

  server.registerPrompt(
  'gecikme_karsilastir',
  {
    title: 'Gecikme zammı ve faizini karşılaştır',
    description:
      'Aynı borç için gecikme zammı ile gecikme faizini hesaplat ve hangisinin hangi durumda ' +
      'uygulandığını açıkla.',
    // The same validation the tools apply: a prompt that accepts a date the
    // tools will reject would look valid and then fail at the tool call.
    argsSchema: z.object({
      odenecekMiktar: amountField('Borç tutarı (TL).'),
      vadeTarihi: dateField('Vade tarihi (YYYYAAGG).'),
      odemeTarihi: dateField('Ödeme ya da tahakkuk tarihi (YYYYAAGG).'),
    }),
  },
  ({ odenecekMiktar, vadeTarihi, odemeTarihi }) => ({
    messages: [
      {
        role: 'user',
        content: {
          type: 'text',
          text:
            `${odenecekMiktar} TL borç için vade ${vadeTarihi}, ödeme ${odemeTarihi} olduğunda:\n\n` +
            '1. `calculate_gecikme_zammi` ve `calculate_gecikme_faizi` araçlarını ikisini de çağır.\n' +
            '2. Çıkan tutarları yan yana koy ve farkın nereden geldiğini açıkla ' +
            '(zam: aylık + günlük karma; faiz: yalnızca tam ay).\n' +
            '3. Hangisinin bu olayda uygulanacağını söyle: kesinleşmiş borcun geç ödenmesi ise ' +
            'gecikme zammı, ikmalen/resen/idarece tarhiyat ise gecikme faizi.\n' +
            '4. Hesabı kendin yapma; araçların döndürdüğü rakamları kullan.',
        },
      },
      ],
    })
  );

  return server;
}

/**
 * Whether this module is the program being run.
 *
 * npm installs the bin as a symlink in node_modules/.bin, so `process.argv[1]`
 * is that link while `import.meta.url` is the real file. Comparing them
 * unresolved meant an installed server started nothing at all and exited
 * silently — it only worked when the file was run by its own path.
 */
function isProgram() {
  const entry = process.argv[1];
  if (!entry) return false;
  try {
    return import.meta.url === pathToFileURL(realpathSync(entry)).href;
  } catch {
    return false;
  }
}

// Only serve over stdio when run as the program; importing the module (tests)
// gets buildServer without a transport attached. serveStdio serves both the
// 2026-07-28 revision and the 2025-era protocol, picking per connection.
if (isProgram()) {
  try {
    serveStdio(buildServer);
  } catch (error) {
    console.error('Sunucu başlatılamadı:', error);
    process.exit(1);
  }
}
