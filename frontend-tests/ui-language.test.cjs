const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const admin = fs.readFileSync(path.join(root, 'admin.html'), 'utf8');
const language = fs.readFileSync(path.join(root, 'ui-language.js'), 'utf8');
const version = fs.readFileSync(path.join(root, 'backend', 'VERSION'), 'utf8').trim();

test('customer chat and admin dashboard expose Russian/Ukrainian selectors', () => {
  assert.match(html, /<select id="uiLanguage"[^>]*>[\s\S]*?<option value="ru">RU<\/option>[\s\S]*?<option value="uk">UK<\/option>/);
  assert.match(admin, /<select id="uiLanguage"[^>]*>[\s\S]*?<option value="ru">RU<\/option>[\s\S]*?<option value="uk">UK<\/option>/);
  assert.match(html, /ui-language\.js/);
  assert.match(admin, /ui-language\.js/);
});

test('manual interface language is independent from customer message language', () => {
  assert.match(html, /function autoSetLanguage\(text\)\{const detected=detectLanguage\(text\);currentRequestLang=detected;return detected\}/);
  assert.match(html, /AIManagerUiLanguage\?\.preferred\(\)/);
  assert.match(html, /uiLanguage'\)\.addEventListener\('change'/);
});

test('shared translation layer preserves chat message content and supports both directions', () => {
  assert.match(language, /const RU=Object\.fromEntries/);
  assert.match(language, /closest\('\.messages,\.msg'\)/);
  assert.match(language, /function translateValue/);
  assert.match(language, /function preferred/);
});

test('all surfaces use one bumped release version', () => {
  assert.ok(/^[0-9]+[.][0-9]+[.][0-9]+$/.test(version));
  assert.match(html, /id="appVersion"/);
});
