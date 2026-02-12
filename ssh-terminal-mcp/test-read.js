import { chromium } from 'playwright';
import dotenv from 'dotenv';

dotenv.config();

async function testTerminalReading() {
  console.log('Terminal Okuma Testi\n');
  
  const browser = await chromium.launch({ 
    headless: false,
    args: ['--disable-blink-features=AutomationControlled']
  });
  
  const page = await browser.newPage();
  
  try {
    // Terminal URL'sine git (session varsa otomatik giriş yapar)
    console.log('1. Terminal\'e bağlanılıyor...');
    const terminalUrl = process.env.TERMINAL_URL || 'https://asgermapeg.enerji.gov.tr/app/#/client/MTQ4AGMAcG9zdGdyZXNxbABBSUAxMC4wLjIyMS4yMQBzc2g';
    await page.goto(terminalUrl);
    
    // Giriş gerekli mi?
    await page.waitForTimeout(5000);
    const needsLogin = await page.$('input[type="password"]');
    
    if (needsLogin) {
      console.log('\n⚠️  Giriş yapın ve ENTER\'a basın...');
      await page.pause();
    }
    
    console.log('\n2. Terminal hazır, okuma yöntemleri test ediliyor...\n');
    
    // Farklı okuma yöntemlerini dene
    const readMethods = [
      {
        name: 'xterm-rows',
        selector: '.xterm-rows > div',
        extract: (elements) => Array.from(elements).map(el => el.textContent).join('\n')
      },
      {
        name: 'xterm-screen',
        selector: '.xterm-screen',
        extract: (el) => el.textContent || el.innerText
      },
      {
        name: 'xterm container',
        selector: '.xterm',
        extract: (el) => el.textContent || el.innerText
      },
      {
        name: 'canvas text layer',
        selector: '.xterm-text-layer',
        extract: (el) => el.textContent || el.innerText
      },
      {
        name: 'xterm lines',
        selector: '.xterm-rows .xterm-line',
        extract: (elements) => Array.from(elements).map(el => el.textContent).join('\n')
      }
    ];
    
    for (const method of readMethods) {
      console.log(`Deneniyor: ${method.name}`);
      
      const result = await page.evaluate(({ selector, isMultiple }) => {
        if (isMultiple) {
          const elements = document.querySelectorAll(selector);
          return elements.length > 0 ? Array.from(elements).map(el => el.textContent || '') : null;
        } else {
          const element = document.querySelector(selector);
          return element ? (element.textContent || element.innerText || '') : null;
        }
      }, {
        selector: method.selector,
        isMultiple: method.selector.includes('>')
      });
      
      if (result) {
        console.log(`✓ Bulundu! İçerik uzunluğu: ${Array.isArray(result) ? result.join('').length : result.length}`);
        if (Array.isArray(result)) {
          console.log(`  Satır sayısı: ${result.filter(r => r.trim()).length}`);
        }
      } else {
        console.log(`✗ Bulunamadı`);
      }
      console.log('');
    }
    
    // Terminal DOM yapısını incele
    console.log('\n3. Terminal DOM yapısı:\n');
    const domInfo = await page.evaluate(() => {
      const info = {
        xtermClasses: [],
        terminalClasses: [],
        inputElements: []
      };
      
      // xterm class'larını bul
      document.querySelectorAll('[class*="xterm"]').forEach(el => {
        info.xtermClasses.push({
          tag: el.tagName,
          className: el.className,
          childCount: el.children.length,
          hasText: !!el.textContent?.trim()
        });
      });
      
      // terminal class'larını bul
      document.querySelectorAll('[class*="terminal"]').forEach(el => {
        info.terminalClasses.push({
          tag: el.tagName,
          className: el.className,
          childCount: el.children.length,
          hasText: !!el.textContent?.trim()
        });
      });
      
      // input/textarea elementlerini bul
      document.querySelectorAll('input, textarea').forEach(el => {
        if (el.offsetParent !== null) { // görünür olanlar
          info.inputElements.push({
            tag: el.tagName,
            type: el.type,
            className: el.className,
            value: el.value?.substring(0, 20)
          });
        }
      });
      
      return info;
    });
    
    console.log('xterm elementleri:');
    domInfo.xtermClasses.forEach(el => {
      console.log(`  ${el.tag}.${el.className} (${el.childCount} child, text: ${el.hasText})`);
    });
    
    console.log('\nterminal elementleri:');
    domInfo.terminalClasses.forEach(el => {
      console.log(`  ${el.tag}.${el.className} (${el.childCount} child, text: ${el.hasText})`);
    });
    
    console.log('\ninput/textarea elementleri:');
    domInfo.inputElements.forEach(el => {
      console.log(`  ${el.tag}[type="${el.type}"] class="${el.className}" value="${el.value}"`);
    });
    
    // Ekran görüntüsü
    await page.screenshot({ path: 'terminal-read-test.png' });
    console.log('\n✓ Ekran görüntüsü: terminal-read-test.png');
    
    console.log('\n20 saniye içinde kapatılacak...');
    await page.waitForTimeout(20000);
    
  } catch (error) {
    console.error('❌ Hata:', error.message);
  } finally {
    await browser.close();
  }
}

testTerminalReading().catch(console.error);