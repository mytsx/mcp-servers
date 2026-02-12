import { chromium } from 'playwright';
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

async function testManualLogin() {
  console.log('Manuel Terminal Testi\n');
  
  const browser = await chromium.launch({ 
    headless: false,
    args: ['--disable-blink-features=AutomationControlled']
  });
  
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }
  });
  
  const page = await context.newPage();
  
  try {
    // 1. Terminal URL'sine git
    console.log('1. Terminal sayfasına gidiliyor...');
    await page.goto(process.env.TERMINAL_URL || 'https://asgermapeg.enerji.gov.tr/app/#/client/MTQ4AGMAcG9zdGdyZXNxbABBSUAxMC4wLjIyMS4yMQBzc2g');
    
    await page.waitForTimeout(5000);
    
    // 2. Giriş durumunu kontrol et
    const status = await page.evaluate(() => {
      const hasPassword = !!document.querySelector('input[type="password"]');
      const terminal = document.querySelector('.xterm, .terminal, pre, .xterm-screen');
      const xtermRows = document.querySelectorAll('.xterm-rows > div');
      
      return {
        needsLogin: hasPassword,
        hasTerminal: !!terminal,
        xtermRowCount: xtermRows.length
      };
    });
    
    console.log('\n2. Sayfa durumu:');
    console.log(`   - Giriş gerekli: ${status.needsLogin ? 'EVET' : 'HAYIR'}`);
    console.log(`   - Terminal var: ${status.hasTerminal ? 'EVET' : 'HAYIR'}`);
    console.log(`   - xterm satır sayısı: ${status.xtermRowCount}`);
    
    if (status.needsLogin) {
      console.log('\n⚠️  Manuel giriş yapmanız gerekiyor!');
      console.log('   Giriş yaptıktan sonra ENTER\'a basın...');
      
      // Kullanıcı girişini bekle
      await page.pause();
    }
    
    // 3. Terminal hazır olana kadar bekle
    console.log('\n3. Terminal yükleniyor...');
    await page.waitForTimeout(5000);
    
    // 4. Terminal'e tıkla
    console.log('\n4. Terminal\'e tıklanıyor...');
    const terminal = await page.$('.xterm, .terminal, .xterm-viewport, .xterm-screen');
    if (terminal) {
      await terminal.click();
      console.log('   ✓ Terminal\'e tıklandı');
    } else {
      console.log('   ❌ Terminal elementi bulunamadı');
    }
    
    await page.waitForTimeout(1000);
    
    // 5. Test komutları
    console.log('\n5. Test komutları çalıştırılıyor:');
    
    const commands = [
      'echo "=== Terminal Test ==="',
      'whoami',
      'hostname',
      'pwd',
      'date'
    ];
    
    for (const cmd of commands) {
      console.log(`   → ${cmd}`);
      await page.keyboard.type(cmd);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(1500);
    }
    
    // 6. Terminal içeriğini oku
    console.log('\n6. Terminal içeriği okunuyor...\n');
    
    const content = await page.evaluate(() => {
      // xterm.js rows
      const xtermRows = document.querySelectorAll('.xterm-rows > div');
      if (xtermRows.length > 0) {
        console.log(`Found ${xtermRows.length} xterm rows`);
        return Array.from(xtermRows)
          .map(row => row.textContent || '')
          .filter(text => text.trim())
          .join('\n');
      }
      
      // Alternatif
      const terminal = document.querySelector('.xterm-screen, .xterm, .terminal');
      if (terminal) {
        return terminal.textContent || terminal.innerText;
      }
      
      return 'Terminal içeriği okunamadı';
    });
    
    console.log('--- Terminal Çıktısı ---');
    console.log(content);
    console.log('------------------------\n');
    
    // 7. Ekran görüntüsü
    await page.screenshot({ path: 'manual-test-result.png', fullPage: true });
    console.log('✓ Ekran görüntüsü: manual-test-result.png');
    
    console.log('\nTest başarılı! 15 saniye içinde kapatılacak...');
    await page.waitForTimeout(15000);
    
  } catch (error) {
    console.error('❌ Test hatası:', error.message);
    await page.screenshot({ path: 'test-error.png' });
  } finally {
    await browser.close();
    console.log('\n✓ Test tamamlandı.');
  }
}

console.log('SSH Terminal Manuel Test');
console.log('========================\n');

testManualLogin().catch(console.error);