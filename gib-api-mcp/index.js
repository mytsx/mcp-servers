#!/usr/bin/env node
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import fetch from 'node-fetch';

const BASE_URL = process.env.GIB_API_URL;

if (!BASE_URL) {
  console.error(
    'HATA: GIB_API_URL environment variable zorunludur.\n' +
    'Kendi worker\'ınızı deploy edin: https://github.com/mytsx/gib-gecikme-zammi-faizi\n' +
    'Örnek: GIB_API_URL=https://your-worker.your-account.workers.dev'
  );
  process.exit(1);
}

const server = new Server({
  name: 'gib-api-mcp',
  version: '2.0.0',
}, {
  capabilities: {
    tools: {},
  },
});

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'calculate_gecikme_zammi',
        description: 'GIB Gecikme Zammı hesapla (6183 sayılı AATUHK m.51). Kesinleşmiş vergi borcu vadesinde ödenmezse, vade tarihinden fiili ödeme tarihine kadar aylık+günlük karma sistemle hesaplanır.',
        inputSchema: {
          type: 'object',
          properties: {
            odenecekMiktar: {
              type: 'string',
              description: 'Borç tutarı (TL). Örnek: "1000.00"'
            },
            vadeTarihi: {
              type: 'string',
              description: 'Vade tarihi (YYYYMMDD). Örnek: "20260101"'
            },
            odemeTarihi: {
              type: 'string',
              description: 'Ödeme tarihi (YYYYMMDD). Örnek: "20260301"'
            }
          },
          required: ['odenecekMiktar', 'vadeTarihi', 'odemeTarihi']
        }
      },
      {
        name: 'calculate_gecikme_faizi',
        description: 'GIB Gecikme Faizi hesapla (213 sayılı VUK m.112). İkmalen/resen/idarece yapılan tarhiyatlarda, normal vade tarihinden tahakkuk tarihine kadar sadece tam ay esasına göre hesaplanır.',
        inputSchema: {
          type: 'object',
          properties: {
            odenecekMiktar: {
              type: 'string',
              description: 'Borç tutarı (TL). Örnek: "1000.00"'
            },
            vadeTarihi: {
              type: 'string',
              description: 'Normal vade tarihi (YYYYMMDD). Örnek: "20260101"'
            },
            odemeTarihi: {
              type: 'string',
              description: 'Tahakkuk/tarhiyat tarihi (YYYYMMDD). Örnek: "20260601"'
            }
          },
          required: ['odenecekMiktar', 'vadeTarihi', 'odemeTarihi']
        }
      }
    ]
  };
});

async function callGibApi(endpoint, params) {
  const response = await fetch(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

function formatResult(result, tipiLabel) {
  if (!result.hesaplamaList || !result.hesaplamaList[0]) {
    throw new Error('Hesaplama sonucu alınamadı');
  }

  const h = result.hesaplamaList[0];
  return `GİB ${tipiLabel} Hesaplama Sonucu:

Ana Para: ${h.odenecekMiktar} TL
Vade Tarihi: ${h.vadeTarihi}
Ödeme Tarihi: ${h.odemeTarihi}
Gecikme Oranı: ${h.hesaplananZamOrani}
Gecikme Tutarı: ${h.hesaplananFaizTutari} TL
Toplam Ödenecek: ${h.hesaplananMiktar} TL`;
}

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    if (name === 'calculate_gecikme_zammi') {
      const result = await callGibApi('/api/gecikme-zammi', {
        odenecekMiktar: args.odenecekMiktar,
        vadeTarihi: args.vadeTarihi,
        odemeTarihi: args.odemeTarihi
      });
      return { content: [{ type: 'text', text: formatResult(result, 'Gecikme Zammı') }] };
    }

    if (name === 'calculate_gecikme_faizi') {
      const result = await callGibApi('/api/gecikme-faizi', {
        odenecekMiktar: args.odenecekMiktar,
        vadeTarihi: args.vadeTarihi,
        odemeTarihi: args.odemeTarihi
      });
      return { content: [{ type: 'text', text: formatResult(result, 'Gecikme Faizi') }] };
    }

    return { content: [{ type: 'text', text: `Unknown tool: ${name}` }], isError: true };
  } catch (error) {
    return { content: [{ type: 'text', text: `Hata: ${error.message}` }], isError: true };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch(console.error);
