import { chromium } from 'playwright';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SESSION_FILE = path.join(__dirname, 'session-state.json');

async function loadSession() {
  try {
    const sessionData = await fs.readFile(SESSION_FILE, 'utf-8');
    return JSON.parse(sessionData);
  } catch (error) {
    return null;
  }
}

async function testOCRApproach() {
  console.log('Terminal OCR Test\n');
  
  const browser = await chromium.launch({ 
    headless: false,
    args: ['--disable-blink-features=AutomationControlled']
  });
  
  const savedSession = await loadSession();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    ...(savedSession ? { storageState: savedSession } : {})
  });
  
  const page = await context.newPage();
  
  try {
    // 1. Terminal'e git
    console.log('1. Terminal açılıyor...');
    const terminalUrl = process.env.TERMINAL_URL || 'https://asgermapeg.enerji.gov.tr/app/#/client/MTQ4AGMAcG9zdGdyZXNxbABBSUAxMC4wLjIyMS4yMQBzc2g';
    await page.goto(terminalUrl);
    await page.waitForTimeout(5000);
    
    // Giriş kontrolü
    const hasPassword = await page.$('input[type="password"]');
    if (hasPassword) {
      console.log('\n⚠️  Giriş yapın ve ENTER\'a basın...');
      await page.pause();
    }
    
    console.log('\n2. Clear ve komut testi başlıyor...\n');
    
    // Test komutları
    const testCommands = [
      'hostname',
      'whoami',
      'pwd',
      'date',
      'echo "Test metni: 12345"'
    ];
    
    for (const cmd of testCommands) {
      console.log(`\n=== Komut: ${cmd} ===`);
      
      // Terminal'e tıkla
      await page.mouse.click(640, 400);
      await page.waitForTimeout(500);
      
      // Ekranı temizle
      console.log('   → Ekran temizleniyor...');
      await page.keyboard.type('clear');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(1000);
      
      // Komutu çalıştır
      console.log('   → Komut çalıştırılıyor...');
      await page.keyboard.type(cmd);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(2000);
      
      // Metni çıkarmayı dene
      console.log('   → Metin okunuyor...');
      
      // Selection API
      const selectedText = await page.evaluate(() => {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(document.body);
        selection.removeAllRanges();
        selection.addRange(range);
        const text = selection.toString();
        selection.removeAllRanges();
        return text;
      });
      
      if (selectedText && selectedText.trim()) {
        console.log('   ✓ Selection API ile bulundu:');
        const lines = selectedText.trim().split('\n').filter(l => l.trim());
        lines.forEach(line => console.log(`     ${line}`));
      } else {
        console.log('   ✗ Selection API başarısız');
      }
      
      // Ekran görüntüsü
      const screenshotName = `ocr-test-${cmd.replace(/[^a-z0-9]/gi, '_')}.png`;
      await page.screenshot({ path: screenshotName });
      console.log(`   → Screenshot: ${screenshotName}`);
    }
    
    console.log('\n\n3. Test tamamlandı! 15 saniye içinde kapatılacak...');
    await page.waitForTimeout(15000);
    
  } catch (error) {
    console.error('\n❌ Hata:', error.message);
  } finally {
    await browser.close();
  }
}

console.log('SSH Terminal OCR Test');
console.log('====================\n');

testOCRApproach().catch(console.error);