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

async function saveSession(context) {
  if (context) {
    const state = await context.storageState();
    await fs.writeFile(SESSION_FILE, JSON.stringify(state, null, 2));
  }
}

async function testScreenshotApproach() {
  console.log('Terminal Screenshot Test\n');
  
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
    
    // 2. Giriş kontrolü
    const hasPassword = await page.$('input[type="password"]');
    
    if (hasPassword) {
      console.log('\n⚠️  GİRİŞ GEREKLİ!');
      console.log('   Lütfen giriş yapın ve ENTER\'a basın...');
      
      await page.pause();
      
      // Giriş sonrası session'ı kaydet
      console.log('\n2. Session kaydediliyor...');
      await saveSession(context);
      console.log('   ✓ Session kaydedildi');
    } else {
      console.log('   ✓ Önceki oturum yüklendi');
    }
    
    // 3. Terminal'e odaklan
    console.log('\n3. Terminal\'e odaklanılıyor...');
    await page.mouse.click(640, 400);
    await page.waitForTimeout(1000);
    
    // 4. Test komutları
    console.log('\n4. Komutlar çalıştırılıyor:\n');
    
    const commands = [
      'clear',
      'echo "=== SCREENSHOT TEST ==="',
      'date',
      'hostname',
      'pwd',
      'ls -la | head -5',
      'echo "Test tamamlandı!"'
    ];
    
    for (const cmd of commands) {
      console.log(`   → ${cmd}`);
      await page.keyboard.type(cmd);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(1500);
    }
    
    // 5. Ekran görüntüsü al
    console.log('\n5. Ekran görüntüleri alınıyor...');
    
    // Tam ekran
    const fullScreenshot = 'test-full-screen.png';
    await page.screenshot({ path: fullScreenshot, fullPage: true });
    console.log(`   ✓ Tam ekran: ${fullScreenshot}`);
    
    // Sadece terminal alanı (tahmini)
    const terminalScreenshot = 'test-terminal-area.png';
    await page.screenshot({ 
      path: terminalScreenshot,
      clip: { x: 0, y: 0, width: 1280, height: 700 }
    });
    console.log(`   ✓ Terminal alanı: ${terminalScreenshot}`);
    
    // 6. Metin okuma denemeleri
    console.log('\n6. Metin okuma denemeleri...\n');
    
    // Selection API ile dene
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
      console.log('   ✓ Selection API ile metin bulundu:');
      console.log(selectedText.substring(0, 200) + '...');
    } else {
      console.log('   ✗ Selection API ile metin bulunamadı');
    }
    
    // Accessibility tree
    const accessibilitySnapshot = await page.accessibility.snapshot();
    console.log('\n   Accessibility tree:', accessibilitySnapshot ? 'Mevcut' : 'Boş');
    
    console.log('\n✓ Test tamamlandı! 20 saniye içinde kapatılacak...');
    await page.waitForTimeout(20000);
    
  } catch (error) {
    console.error('\n❌ Hata:', error.message);
    await page.screenshot({ path: 'test-error.png' });
  } finally {
    await browser.close();
  }
}

console.log('SSH Terminal Screenshot Test');
console.log('===========================\n');

testScreenshotApproach().catch(console.error);