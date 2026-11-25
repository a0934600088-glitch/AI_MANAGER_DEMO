const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const chat = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const admin = fs.readFileSync(path.join(root, 'admin.html'), 'utf8');
const backend = fs.readFileSync(path.join(root, 'backend/app/main.py'), 'utf8');

test('customer chat emits conversation and message analytics without admin credentials', () => {
  assert.match(chat, /ai_conversation_id/);
  assert.match(chat, /trackEvent\('chat_message'/);
  assert.match(chat, /X-Conversation-ID/);
  assert.doesNotMatch(chat, /ADMIN_API_TOKEN/);
});

test('administrator analytics is a separate protected frontend', () => {
  assert.match(admin, /Административная аналитика/);
  assert.match(admin, /X-Admin-Token/);
  assert.match(admin, /api\/admin\/analytics/);
  assert.match(backend, /@app.get\("\/api\/admin\/analytics"\)/);
});
