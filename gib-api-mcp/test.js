import fetch from 'node-fetch';

const API_URL = 'https://gib-api-proxy.mehmet49946.workers.dev/api/gecikme-zammi';

async function testAPI() {
  console.log('GIB API MCP Test başlatılıyor...\n');
  
  // Test 1: Tek hesaplama
  console.log('Test 1: Tek ödeme hesaplama');
  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        data: {
          data: [{
            gecikmeTipi: 2,
            odenecekMiktar: "1000.00",
            vadeTarihi: "20250101",
            odemeTarihi: "20250716"
          }]
        },
        toBeLink: false
      })
    });

    const result = await response.json();
    console.log('Sonuç:', JSON.stringify(result, null, 2));
  } catch (error) {
    console.error('Hata:', error.message);
  }
  
  console.log('\n-------------------\n');
  
  // Test 2: Çoklu hesaplama
  console.log('Test 2: Çoklu ödeme hesaplama');
  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        data: {
          data: [
            {
              gecikmeTipi: 2,
              odenecekMiktar: "500.00",
              vadeTarihi: "20250301",
              odemeTarihi: "20250716"
            },
            {
              gecikmeTipi: 2,
              odenecekMiktar: "1000.00",
              vadeTarihi: "20250401",
              odemeTarihi: "20250716"
            },
            {
              gecikmeTipi: 1,
              odenecekMiktar: "750.00",
              vadeTarihi: "20250501",
              odemeTarihi: "20250716"
            }
          ]
        },
        toBeLink: false
      })
    });

    const result = await response.json();
    console.log('Sonuç:', JSON.stringify(result, null, 2));
  } catch (error) {
    console.error('Hata:', error.message);
  }
}

testAPI();