import { chromium } from 'playwright';
import Tesseract from 'tesseract.js';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function testOCR() {
  console.log('Testing OCR on existing screenshots...');
  
  const screenshots = [
    'ocr-test-hostname.png',
    'ocr-test-date.png',
    'ocr-test-pwd.png',
    'ocr-test-whoami.png',
    'ocr-test-echo__Test_metni__12345_.png'
  ];
  
  for (const screenshot of screenshots) {
    const filepath = path.join(__dirname, screenshot);
    
    try {
      console.log(`\n=== Processing ${screenshot} ===`);
      
      const { data: { text } } = await Tesseract.recognize(
        filepath,
        'eng',
        {
          logger: m => {
            if (m.status === 'recognizing text') {
              process.stdout.write(`Progress: ${Math.round(m.progress * 100)}%\r`);
            }
          }
        }
      );
      
      console.log('\nExtracted text:');
      console.log('---');
      console.log(text);
      console.log('---');
      
      // Clean up the text
      const cleanedText = text
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0)
        .join('\n');
      
      console.log('\nCleaned text:');
      console.log('---');
      console.log(cleanedText);
      console.log('---');
      
    } catch (error) {
      console.error(`Error processing ${screenshot}:`, error.message);
    }
  }
}

testOCR().catch(console.error);