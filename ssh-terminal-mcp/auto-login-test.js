import { chromium } from 'playwright';
import dotenv from 'dotenv';

dotenv.config();

async function autoLoginTest() {
  console.log('SSH Terminal Otomatik Giriş Testi\n');
  
  const browser = await chromium.launch({ 
    headless: false,
    args: ['--disable-blink-features=AutomationControlled']
  });
  
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }
  });
  
  const page = await context.newPage();
  
  try {
    console.log('1. Ana sayfaya gidiliyor...');
    // Önce ana sayfaya git
    const baseUrl = process.env.TERMINAL_URL ? process.env.TERMINAL_URL.split('/app/')[0] : 'https://asgermapeg.enerji.gov.tr';
    await page.goto(baseUrl);
    await page.waitForTimeout(3000);
    
    // Giriş formunu kontrol et
    console.log('2. Giriş formu aranıyor...');
    
    // Farklı input selector'ları dene
    const usernameSelectors = [
      'input[name="username"]',
      'input[name="user"]',
      'input[type="text"]:not([type="password"])',
      'input[id*="user"]',
      'input[placeholder*="kullanıcı" i]'
    ];
    
    const passwordSelectors = [
      'input[type="password"]',
      'input[name="password"]',
      'input[id*="pass"]'
    ];
    
    // Username alanını bul
    let usernameInput = null;
    for (const selector of usernameSelectors) {
      usernameInput = await page.$(selector);
      if (usernameInput) {
        console.log(`✓ Kullanıcı adı alanı bulundu: ${selector}`);
        break;
      }
    }
    
    // Password alanını bul
    let passwordInput = null;
    for (const selector of passwordSelectors) {
      passwordInput = await page.$(selector);
      if (passwordInput) {
        console.log(`✓ Şifre alanı bulundu: ${selector}`);
        break;
      }
    }
    
    if (!usernameInput || !passwordInput) {
      console.log('❌ Giriş formu bulunamadı!');
      
      // Tüm formları listele
      const forms = await page.$$('form');
      console.log(`\nSayfada ${forms.length} form bulundu.`);
      
      // Tüm input'ları listele
      const inputs = await page.evaluate(() => {
        return Array.from(document.querySelectorAll('input')).map(input => ({
          type: input.type,
          name: input.name,
          id: input.id,
          placeholder: input.placeholder,
          visible: input.offsetParent !== null
        }));
      });
      
      console.log('\nBulunan input alanları:');
      inputs.forEach((input, i) => {
        if (input.visible) {
          console.log(`${i+1}. Type: ${input.type}, Name: ${input.name}, ID: ${input.id}, Placeholder: ${input.placeholder}`);
        }
      });
    }
    
    // Ekran görüntüsü al
    await page.screenshot({ path: 'login-page.png', fullPage: true });
    console.log('\n✓ Giriş sayfası ekran görüntüsü: login-page.png');
    
    // Terminal URL'sine git
    console.log('\n3. Terminal URL\'sine gidiliyor...');
    const terminalUrl = process.env.TERMINAL_URL || 'https://asgermapeg.enerji.gov.tr/app/#/client/MTQ4AGMAcG9zdGdyZXNxbABBSUAxMC4wLjIyMS4yMQBzc2g';
    await page.goto(terminalUrl);
    await page.waitForTimeout(5000);
    
    // Terminal sayfasında da kontrol et
    const terminalPageInputs = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('input')).map(input => ({
        type: input.type,
        name: input.name,
        id: input.id,
        placeholder: input.placeholder,
        className: input.className,
        visible: input.offsetParent !== null
      }));
    });
    
    if (terminalPageInputs.length > 0) {
      console.log('\nTerminal sayfasında bulunan input alanları:');
      terminalPageInputs.forEach((input, i) => {
        if (input.visible) {
          console.log(`${i+1}. Type: ${input.type}, Name: ${input.name}, ID: ${input.id}, Class: ${input.className}`);
        }
      });
    }
    
    await page.screenshot({ path: 'terminal-login-page.png', fullPage: true });
    console.log('\n✓ Terminal giriş sayfası ekran görüntüsü: terminal-login-page.png');
    
    console.log('\n4. Manuel giriş için 30 saniye bekleniyor...');
    await page.waitForTimeout(30000);
    
  } catch (error) {
    console.error('❌ Hata:', error.message);
    await page.screenshot({ path: 'error-screenshot.png' });
  } finally {
    await browser.close();
    console.log('\n✓ Test tamamlandı.');
  }
}

autoLoginTest().catch(console.error);