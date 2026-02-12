import { chromium } from 'playwright';
import fs from 'fs/promises';
import dotenv from 'dotenv';

dotenv.config();

const SESSION_FILE = 'session-state.json';

async function loadSession() {
  try {
    const sessionData = await fs.readFile(SESSION_FILE, 'utf-8');
    return JSON.parse(sessionData);
  } catch (error) {
    console.log('Session bulunamadı, önce session-test.js çalıştırın');
    return null;
  }
}

async function commandTest() {
  console.log('SSH Terminal Komut Testi\n');
  
  const savedSession = await loadSession();
  if (!savedSession) {
    console.log('❌ Session dosyası bulunamadı. Önce "node session-test.js" çalıştırın.');
    return;
  }
  
  const browser = await chromium.launch({ 
    headless: false,
    args: ['--disable-blink-features=AutomationControlled']
  });
  
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    storageState: savedSession
  });
  
  const page = await context.newPage();
  
  try {
    console.log('1. Terminal\'e bağlanılıyor...');
    const terminalUrl = process.env.TERMINAL_URL || 'https://asgermapeg.enerji.gov.tr/app/#/client/MTQ4AGMAcG9zdGdyZXNxbABBSUAxMC4wLjIyMS4yMQBzc2g';
    await page.goto(terminalUrl);
    
    // Terminal yüklenmesini bekle
    console.log('2. Terminal yükleniyor...');
    await page.waitForTimeout(8000);
    
    // Komutları çalıştır
    console.log('3. Komutlar çalıştırılıyor:\n');
    
    const commands = [
      { cmd: 'clear', desc: 'Ekranı temizle' },
      { cmd: 'echo "=== SSH Terminal MCP Test ==="', desc: 'Test başlığı' },
      { cmd: 'date', desc: 'Tarih ve saat' },
      { cmd: 'whoami', desc: 'Kullanıcı adı' },
      { cmd: 'hostname', desc: 'Sunucu adı' },
      { cmd: 'pwd', desc: 'Çalışma dizini' },
      { cmd: 'ls -la | head -10', desc: 'Dosya listesi' },
      { cmd: 'df -h | grep -E "^/dev"', desc: 'Disk kullanımı' },
      { cmd: 'free -h', desc: 'Bellek kullanımı' },
      { cmd: 'echo "Test tamamlandı!"', desc: 'Test sonu' }
    ];
    
    for (const { cmd, desc } of commands) {
      console.log(`→ ${desc}: ${cmd}`);
      await page.keyboard.type(cmd);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(1500);
    }
    
    // Terminal çıktısını oku
    console.log('\n4. Terminal çıktısı okunuyor...');
    await page.waitForTimeout(2000);
    
    const terminalContent = await page.evaluate(() => {
      // xterm.js için özel okuma
      const xtermScreen = document.querySelector('.xterm-screen');
      if (xtermScreen) {
        const rows = xtermScreen.querySelectorAll('.xterm-rows > div');
        if (rows.length > 0) {
          return Array.from(rows)
            .map(row => row.textContent || '')
            .filter(text => text.trim())
            .join('\n');
        }
      }
      
      // Alternatif: tüm xterm içeriği
      const xtermContainer = document.querySelector('.xterm');
      if (xtermContainer) {
        return xtermContainer.textContent || xtermContainer.innerText;
      }
      
      return 'Terminal içeriği okunamadı';
    });
    
    // Son 20 satırı göster
    const lines = terminalContent.split('\n').filter(line => line.trim());
    const lastLines = lines.slice(-20);
    
    console.log('\n--- Son terminal çıktıları ---');
    console.log(lastLines.join('\n'));
    
    // Ekran görüntüsü
    await page.screenshot({ path: 'command-test-result.png', fullPage: true });
    console.log('\n✓ Ekran görüntüsü: command-test-result.png');
    
    console.log('\n5. Test başarılı! 15 saniye içinde kapatılacak...');
    await page.waitForTimeout(15000);
    
  } catch (error) {
    console.error('❌ Hata:', error.message);
    await page.screenshot({ path: 'command-error.png' });
  } finally {
    await browser.close();
    console.log('\n✓ Test tamamlandı.');
  }
}

commandTest().catch(console.error);