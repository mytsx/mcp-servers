import { chromium } from 'playwright';
import fs from 'fs/promises';
import path from 'path';
import dotenv from 'dotenv';

dotenv.config();

const SESSION_FILE = 'session-state.json';

async function saveSession(context) {
  const state = await context.storageState();
  await fs.writeFile(SESSION_FILE, JSON.stringify(state, null, 2));
  console.log('✓ Oturum kaydedildi');
}

async function loadSession() {
  try {
    const sessionData = await fs.readFile(SESSION_FILE, 'utf-8');
    return JSON.parse(sessionData);
  } catch (error) {
    return null;
  }
}

async function sessionTest() {
  console.log('SSH Terminal Session Testi\n');
  
  const browser = await chromium.launch({ 
    headless: false,
    args: ['--disable-blink-features=AutomationControlled']
  });
  
  // Session varsa yükle
  const savedSession = await loadSession();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    ...(savedSession ? { storageState: savedSession } : {})
  });
  
  if (savedSession) {
    console.log('✓ Önceki oturum yüklendi');
  }
  
  const page = await context.newPage();
  
  try {
    // Doğrudan terminal URL'sine git
    console.log('1. Terminal URL\'sine gidiliyor...');
    const terminalUrl = process.env.TERMINAL_URL || 'https://asgermapeg.enerji.gov.tr/app/#/client/MTQ4AGMAcG9zdGdyZXNxbABBSUAxMC4wLjIyMS4yMQBzc2g';
    await page.goto(terminalUrl);
    
    // Biraz bekle
    await page.waitForTimeout(5000);
    
    // Giriş gerekli mi kontrol et
    const needsLogin = await page.evaluate(() => {
      // Giriş formu var mı?
      const hasPasswordInput = document.querySelector('input[type="password"]');
      const hasLoginButton = document.querySelector('button') && 
        Array.from(document.querySelectorAll('button')).some(btn => 
          btn.textContent.includes('Giriş') || btn.textContent.includes('Login')
        );
      
      // Terminal elementi var mı?
      const hasTerminal = document.querySelector('.xterm, .terminal, pre');
      
      return {
        needsLogin: !!(hasPasswordInput || hasLoginButton),
        hasTerminal: !!hasTerminal,
        pageTitle: document.title,
        url: window.location.href
      };
    });
    
    console.log('\nSayfa durumu:');
    console.log(`- URL: ${needsLogin.url}`);
    console.log(`- Başlık: ${needsLogin.pageTitle}`);
    console.log(`- Giriş gerekli: ${needsLogin.needsLogin ? 'EVET' : 'HAYIR'}`);
    console.log(`- Terminal var: ${needsLogin.hasTerminal ? 'EVET' : 'HAYIR'}`);
    
    if (needsLogin.needsLogin) {
      console.log('\n⚠️  Giriş gerekiyor. Lütfen giriş yapın...');
      console.log('Giriş yaptıktan sonra ENTER\'a basın.');
      
      // Kullanıcı girişini bekle
      await page.pause();
      
      // Giriş sonrası oturumu kaydet
      await saveSession(context);
    } else if (needsLogin.hasTerminal) {
      console.log('\n✓ Terminal hazır! Komutlar çalıştırılıyor...\n');
      
      // Komutları çalıştır
      const commands = [
        'echo "Session test başarılı!"',
        'date',
        'pwd',
        'ls | head -5'
      ];
      
      for (const cmd of commands) {
        console.log(`→ ${cmd}`);
        await page.keyboard.type(cmd);
        await page.keyboard.press('Enter');
        await page.waitForTimeout(1500);
      }
      
      // Ekran görüntüsü
      await page.screenshot({ path: 'session-test-success.png' });
      console.log('\n✓ Ekran görüntüsü: session-test-success.png');
    } else {
      console.log('\n⚠️  Terminal bulunamadı, sayfa hala yükleniyor olabilir.');
      await page.screenshot({ path: 'session-test-loading.png' });
    }
    
    console.log('\n10 saniye içinde kapatılacak...');
    await page.waitForTimeout(10000);
    
  } catch (error) {
    console.error('❌ Hata:', error.message);
    await page.screenshot({ path: 'session-error.png' });
  } finally {
    await browser.close();
    console.log('\n✓ Test tamamlandı.');
  }
}

// Session'ı temizleme komutu
if (process.argv[2] === '--clear') {
  try {
    await fs.unlink(SESSION_FILE);
    console.log('✓ Session temizlendi');
  } catch (error) {
    console.log('Session dosyası bulunamadı');
  }
} else {
  sessionTest().catch(console.error);
}