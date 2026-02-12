import { chromium } from 'playwright';
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

async function testTerminal() {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();
  
  try {
    // Terminal sayfasına git
    console.log('Terminal sayfasına gidiliyor...');
    await page.goto(process.env.TERMINAL_URL || 'https://asgermapeg.enerji.gov.tr/app/#/client/MTQ4AGMAcG9zdGdyZXNxbABBSUAxMC4wLjIyMS4yMQBzc2g');
    
    // Sayfanın yüklenmesini bekle
    await page.waitForTimeout(5000);
    
    // Oturum kontrolü - giriş formu var mı?
    const loginForm = await page.$('input[type="password"], form[action*="login"]');
    
    if (loginForm) {
      console.log('Giriş formu bulundu, oturum açılması gerekiyor');
      // Burada manuel giriş yapılmasını bekle
      console.log('Lütfen manuel olarak giriş yapın...');
      await page.waitForTimeout(60000); // 60 saniye bekle
    } else {
      console.log('Oturum zaten açık görünüyor');
    }
    
    // Terminal hazır mı kontrol et
    await page.waitForTimeout(3000);
    
    // Basit Linux komutları çalıştır
    console.log('\n--- Komutları çalıştırma ---');
    
    // 1. pwd komutu
    console.log('PWD komutu çalıştırılıyor...');
    await page.keyboard.type('pwd');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(2000);
    
    // 2. ls komutu
    console.log('LS komutu çalıştırılıyor...');
    await page.keyboard.type('ls -la');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(2000);
    
    // 3. whoami komutu
    console.log('WHOAMI komutu çalıştırılıyor...');
    await page.keyboard.type('whoami');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(2000);
    
    // 4. date komutu
    console.log('DATE komutu çalıştırılıyor...');
    await page.keyboard.type('date');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(2000);
    
    // Terminal içeriğini oku
    console.log('\n--- Terminal çıktısı ---');
    const terminalContent = await page.evaluate(() => {
      // xterm.js için özel selector
      const xtermRows = document.querySelectorAll('.xterm-rows > div');
      if (xtermRows.length > 0) {
        return Array.from(xtermRows).map(row => row.textContent).join('\n');
      }
      
      // Farklı terminal yapıları için kontrol
      const selectors = [
        '.xterm-screen',
        '.xterm-container',
        '.terminal-output',
        '.terminal',
        'pre',
        '[role="log"]',
        '.console-output'
      ];
      
      for (const selector of selectors) {
        const element = document.querySelector(selector);
        if (element) {
          return element.textContent || element.innerText;
        }
      }
      
      // Son çare: tüm body içeriği
      return document.body.innerText;
    });
    
    console.log(terminalContent);
    
    // Ekran görüntüsü al
    await page.screenshot({ path: 'terminal_commands.png' });
    console.log('\nEkran görüntüsü kaydedildi: terminal_commands.png');
    
    // Test için bekle
    console.log('\nTest tamamlandı. 10 saniye içinde kapatılacak...');
    await page.waitForTimeout(10000);
    
  } catch (error) {
    console.error('Test hatası:', error);
  } finally {
    await browser.close();
  }
}

console.log('SSH Terminal Test Başlatılıyor...');
console.log('NOT: Eğer giriş ekranı görürseniz, manuel olarak giriş yapın.\n');

testTerminal();