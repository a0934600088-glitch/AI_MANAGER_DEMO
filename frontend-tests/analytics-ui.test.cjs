const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const chat = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const admin = fs.readFileSync(path.join(root, 'admin.html'), 'utf8');
const backend = fs.readFileSync(path.join(root, 'backend/app/main.py'), 'utf8');
const version = fs.readFileSync(path.join(root, 'backend/VERSION'), 'utf8').trim();

test('test mode retains diagnostics while keeping the admin dashboard separate', () => {
  assert.match(chat, /ai_conversation_id/);
  assert.match(chat, /trackEvent\('chat_message'/);
  assert.match(chat, /X-Conversation-ID/);
  assert.match(chat, /opsAdminUsername/);
  assert.match(chat, /id="opsToggle"[^>]*hidden/);
  assert.match(chat, /id="opsPanel"[^>]*hidden/);
  assert.match(chat, /new URLSearchParams\(window\.location\.search\)\.get\('mode'\) === 'test'/);
  assert.match(chat, /opsToggle'\)\.hidden = false/);
  assert.match(chat, /opsPanel'\)\.hidden = false/);
  assert.match(chat, /opsAdminPassword/);
  assert.match(chat, /Authorization.*Basic/s);
  assert.doesNotMatch(chat, /ADMIN_API_TOKEN|X-Admin-Token|opsAdminToken/);
  assert.doesNotMatch(chat, /Административная аналитика/);
});

test('administrator analytics uses Basic login and never asks for an API token', () => {
  assert.match(admin, /Административная аналитика/);
  assert.match(admin, /Authorization.*Basic/s);
  assert.match(admin, /api\/admin\/analytics/);
  assert.match(backend, /@app.get\("\/api\/admin\/analytics"\)/);
  assert.doesNotMatch(admin, /ADMIN_API_TOKEN|X-Admin-Token|ai_admin_token/);
  assert.doesNotMatch(backend, /ADMIN_API_TOKEN|X-Admin-Token/);
});

test('frontend release labels are populated from the backend version endpoint', () => {
  assert.match(chat, /appVersion/);
  assert.match(admin, /appVersion/);
  assert.match(chat, /api\('\/health'\)/);
  assert.match(backend, /VERSION/);
  assert.match(version, /^\d+\.\d+\.\d+$/);
  assert.doesNotMatch(chat, /v\d+\.\d+\.\d+/);
  assert.doesNotMatch(admin, /v\d+\.\d+\.\d+/);
});
