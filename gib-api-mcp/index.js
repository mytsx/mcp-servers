#!/usr/bin/env node
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import fetch from 'node-fetch';

const API_URL = 'https://gib-api-proxy.mehmet49946.workers.dev/api/gecikme-zammi';

const server = new Server({
  name: 'gib-api-mcp',
  version: '1.0.0',
}, {
  capabilities: {
    tools: {},
  },
});

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'calculate_late_payment_interest',
        description: 'GIB (Gelir İdaresi Başkanlığı) gecikme zammı/faizi hesaplama. Calculate late payment interest/penalty for Turkish tax payments.',
        inputSchema: {
          type: 'object',
          properties: {
            odenecekMiktar: {
              type: 'string',
              description: 'Ödenecek miktar (TL) / Amount to be paid (TRY). Örnek/Example: "1000.00"'
            },
            vadeTarihi: {
              type: 'string',
              description: 'Vade tarihi / Due date (YYYYMMDD format). Örnek/Example: "20250101"'
            },
            odemeTarihi: {
              type: 'string',
              description: 'Ödeme tarihi / Payment date (YYYYMMDD format). Örnek/Example: "20250716"'
            },
            gecikmeTipi: {
              type: 'integer',
              description: 'Gecikme tipi / Delay type. 1: Gecikme Zammı, 2: Gecikme Faizi (varsayılan/default: 1)',
              default: 1
            }
          },
          required: ['odenecekMiktar', 'vadeTarihi', 'odemeTarihi']
        }
      },
      {
        name: 'calculate_multiple_late_payments',
        description: 'Birden fazla gecikme zammı/faizi hesapla. Calculate multiple late payment interests at once.',
        inputSchema: {
          type: 'object',
          properties: {
            odemeler: {
              type: 'array',
              description: 'Ödemeler listesi / List of payments',
              items: {
                type: 'object',
                properties: {
                  odenecekMiktar: {
                    type: 'string',
                    description: 'Ödenecek miktar (TL)'
                  },
                  vadeTarihi: {
                    type: 'string',
                    description: 'Vade tarihi (YYYYMMDD)'
                  },
                  odemeTarihi: {
                    type: 'string',
                    description: 'Ödeme tarihi (YYYYMMDD)'
                  },
                  gecikmeTipi: {
                    type: 'integer',
                    description: 'Gecikme tipi (1 veya 2)',
                    default: 1
                  }
                },
                required: ['odenecekMiktar', 'vadeTarihi', 'odemeTarihi']
              }
            }
          },
          required: ['odemeler']
        }
      }
    ]
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  if (request.params.name === 'calculate_late_payment_interest') {
    const { odenecekMiktar, vadeTarihi, odemeTarihi, gecikmeTipi = 1 } = request.params.arguments;
    
    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          data: {
            data: [{
              gecikmeTipi: gecikmeTipi,
              odenecekMiktar: odenecekMiktar,
              vadeTarihi: vadeTarihi,
              odemeTarihi: odemeTarihi
            }]
          },
          toBeLink: false
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(`API Error: ${errorData.error || response.statusText}`);
      }

      const result = await response.json();
      
      if (result.hesaplamaList && result.hesaplamaList[0]) {
        const hesaplama = result.hesaplamaList[0];
        return {
          content: [
            {
              type: 'text',
              text: `GIB Gecikme ${hesaplama.gecikmeTipi} Hesaplama Sonucu:
              
Ana Para: ${hesaplama.odenecekMiktar} TL
Vade Tarihi: ${hesaplama.vadeTarihi}
Ödeme Tarihi: ${hesaplama.odemeTarihi}
Gecikme Oranı: ${hesaplama.hesaplananZamOrani}
Gecikme Tutarı: ${hesaplama.hesaplananFaizTutari} TL
Toplam Ödenecek: ${hesaplama.hesaplananMiktar} TL`
            }
          ]
        };
      }
      
      throw new Error('Hesaplama sonucu alınamadı');
      
    } catch (error) {
      return {
        content: [
          {
            type: 'text',
            text: `Hata: ${error.message}`
          }
        ],
        isError: true
      };
    }
  }
  
  if (request.params.name === 'calculate_multiple_late_payments') {
    const { odemeler } = request.params.arguments;
    
    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          data: {
            data: odemeler.map(odeme => ({
              gecikmeTipi: odeme.gecikmeTipi || 1,
              odenecekMiktar: odeme.odenecekMiktar,
              vadeTarihi: odeme.vadeTarihi,
              odemeTarihi: odeme.odemeTarihi
            }))
          },
          toBeLink: false
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(`API Error: ${errorData.error || response.statusText}`);
      }

      const result = await response.json();
      
      if (result.hesaplamaList) {
        let text = 'GIB Toplu Gecikme Hesaplama Sonuçları:\n\n';
        
        result.hesaplamaList.forEach((hesaplama, index) => {
          text += `${index + 1}. Ödeme:\n`;
          text += `   Ana Para: ${hesaplama.odenecekMiktar} TL\n`;
          text += `   Vade: ${hesaplama.vadeTarihi} → Ödeme: ${hesaplama.odemeTarihi}\n`;
          text += `   Oran: ${hesaplama.hesaplananZamOrani}\n`;
          text += `   Gecikme: ${hesaplama.hesaplananFaizTutari} TL\n`;
          text += `   Toplam: ${hesaplama.hesaplananMiktar} TL\n\n`;
        });
        
        if (result.toplam) {
          text += `GENEL TOPLAM:\n`;
          text += `   Toplam Ana Para: ${result.toplam.toplamMiktar} TL\n`;
          text += `   Toplam Gecikme: ${result.toplam.toplamZam} TL\n`;
          text += `   Toplam Ödenecek: ${result.toplam.toplamOdenecekTutar} TL`;
        }
        
        return {
          content: [
            {
              type: 'text',
              text: text
            }
          ]
        };
      }
      
      throw new Error('Hesaplama sonucu alınamadı');
      
    } catch (error) {
      return {
        content: [
          {
            type: 'text',
            text: `Hata: ${error.message}`
          }
        ],
        isError: true
      };
    }
  }
  
  return {
    content: [
      {
        type: 'text',
        text: `Unknown tool: ${request.params.name}`
      }
    ],
    isError: true
  };
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch(console.error);