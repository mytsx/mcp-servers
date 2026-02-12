import { chromium } from 'playwright';
import dotenv from 'dotenv';

dotenv.config();

async function quickTest() {
  console.log('Hızlı SSH Terminal Testi\n');
  
  const browser = await chromium.launch({ 
    headless: false,
    args: ['--disable-blink-features=AutomationControlled']
  });
  
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }
  });
  
  const page = await context.newPage();
  
  try {
    console.log('1. Terminal URL\'ye gidiliyor...');
    const terminalUrl = process.env.TERMINAL_URL || 'https://asgermapeg.enerji.gov.tr/app/#/client/MTQ4AGMAcG9zdGdyZXNxbABBSUAxMC4wLjIyMS4yMQBzc2g';
    await page.goto(terminalUrl);
    
    console.log('2. Sayfa yükleniyor (5 saniye)...');
    await page.waitForTimeout(5000);
    
    // Giriş kontrolü
    const needsLogin = await page.$('input[type="password"]');
    if (needsLogin) {
      console.log('\n⚠️  GİRİŞ GEREKLİ - Lütfen giriş yapın ve ENTER\'a basın...');
      await page.pause(); // Kullanıcı girişini bekle
    }
    
    console.log('\n3. Terminal hazır, komutlar gönderiliyor...\n');
    
    // Komutları çalıştır
    const commands = [
      'echo "Test başladı!"',
      'hostname',
      'uptime',
      'df -h | head -5',
      'echo "Test tamamlandı!"'
    ];
    
    for (const cmd of commands) {
      console.log(`→ ${cmd}`);
      await page.keyboard.type(cmd);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(1500);
    }
    
    // Son ekran görüntüsü
    await page.screenshot({ path: 'quick-test-result.png', fullPage: true });
    console.log('\n✓ Ekran görüntüsü: quick-test-result.png');
    
    console.log('\n4. Test başarılı! Browser 20 saniye açık kalacak...');
    await page.waitForTimeout(20000);
    
  } catch (error) {
    console.error('❌ Hata:', error.message);
    await page.screenshot({ path: 'error-screenshot.png' });
  } finally {
    await browser.close();
    console.log('\n✓ Test tamamlandı.');
  }
}

quickTest().catch(console.error);