const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

const chat = fs.readFileSync('index.html', 'utf8');
const admin = fs.readFileSync('admin.html', 'utf8');
const backend = fs.readFileSync('backend/app/main.py', 'utf8');
const analytics = fs.readFileSync('backend/app/analytics.py', 'utf8');

test('existing customer chat and admin log remain present', () => {
  for (const id of ['messages', 'input', 'send', 'opsToggle', 'opsPanel', 'opsAdminUsername', 'opsAdminPassword']) {
    assert.match(chat, new RegExp('id="' + id + '"'));
  }
  assert.match(chat, /async function refreshOps/);
  assert.match(chat, /fetch\(API\+'\/api\/admin\/traces'/);
});

test('analytics instrumentation does not send raw message text', () => {
  assert.match(chat, /ai_conversation_id/);
  assert.match(chat, /trackEvent\('chat_message'/);
  assert.match(chat, /X-Conversation-ID/);
  assert.match(chat, /X-Tenant-Key/);
  assert.ok(chat.includes('window.AI_MANAGER_TENANT_KEY'));
  assert.match(chat, /trackEvent\('vehicle_confirmed'/);
  assert.match(chat, /catalogVerified=!!d\?\.is_oem_catalog_verified/);
  assert.match(chat, /if\(!catalogVerified\)/);
  assert.match(chat, /function renderCatalogGroups/);
  assert.match(chat, /function renderCatalogParts/);
  assert.match(chat, /request\.group_id=groupId/);
  assert.match(chat, /Оригинальный каталог TradeSoft/);
  assert.doesNotMatch(chat, /SoloCatalog|NHTSA|solocatalog|nhtsa/i);
  assert.match(chat, /href="admin.html"/);
  assert.match(analytics, /_SAFE_METADATA/);
  assert.match(analytics, /def _clean_metadata/);
  assert.match(analytics, /def database_health/);
  assert.match(analytics, /event_type='catalog_request'/);
});

test('analytics dashboard is separate and protected', () => {
  assert.match(admin, /Административная аналитика/);
  assert.match(admin, /api\/admin\/analytics/);
  assert.match(admin, /Authorization/);
  assert.match(admin, /databaseStatus/);
  assert.match(admin, /providerStatus/);
  assert.match(admin, /analytics_database/);
  assert.match(backend, /@app.get\("\/api\/admin\/analytics"\)/);
  assert.match(backend, /def _authorize_admin/);
  assert.match(backend, /TradesoftPartsCatalogsAdapter/);
  assert.match(backend, /catalog_results/);
  assert.doesNotMatch(backend, /SoloCatalog|NHTSA|solocatalog|nhtsa/i);
});

test('unavailable sales and AI metrics are explicitly marked rather than fabricated', () => {
  assert.match(admin, /Не собирается/);
  assert.match(admin, /Учёт токенов и расходов AI не подключён/);
  assert.match(analytics, /offer_created/);
  assert.match(analytics, /order_created/);
});

test('admin and shop users use distinct role-checked login choices', () => {
  assert.match(admin, /id="accessMode"/);
  assert.match(admin, /data-access="admin"/);
  assert.match(admin, /Администратор/);
  assert.match(admin, /data-access="manager"/);
  assert.match(admin, /Интернет-магазин/);
  assert.match(admin, /login-choice active/);
  assert.match(admin, /currentUser\.role==='super_admin'\?'admin':'manager'/);
  assert.match(admin, /shop_admin:\[\]/);
  assert.match(admin, /observer:\['vehicles','parts','crm','sales','ai','integrations','tenants'\]/);
  assert.match(admin, /Authorization:'Bearer '\+auth/);
  assert.match(admin, /Эта учётная запись не имеет доступа к выбранному кабинету/);
  assert.ok(admin.includes("api/auth/login"));
  assert.ok(admin.includes("api/auth/logout"));
  assert.doesNotMatch(admin, /auth='Basic '/);
  assert.match(backend, /tenant_id = "default" if user\["role"\] == "super_admin" else str\(user\["tenant_id"\]\)/);
  assert.match(backend, /Администратор магазина не может создавать других администраторов магазина/);
  assert.match(analytics, /def dashboard_summary\(days: int = 30, tenant_id: str = "default"\)/);
  assert.match(analytics, /def conversation_summary\(days: int = 30, tenant_id: str = "default"\)/);
});

test('customer chat is focused on the conversation and preserves existing controls', () => {
  assert.doesNotMatch(chat, /class="client-contact"|id="clientPhone"|id="clientCallBtn"|setCustomerPhone/);
  for (const id of [
    'uiLanguage', 'opsToggle', 'refreshBtn', 'opsPanel', 'opsAdminUsername',
    'opsAdminPassword', 'opsAuthBtn', 'opsClose', 'messages', 'attachmentPreview',
    'voiceMeter', 'voiceMeterCanvas', 'attachBtn', 'input', 'cameraBtn', 'callBtn',
    'voiceBtn', 'send', 'fileInput', 'cameraInput'
  ]) {
    assert.match(chat, new RegExp('id="' + id + '"'), 'missing existing control: ' + id);
  }
  assert.match(chat, /assets\/ai-manager-blueprint\.webp/);
  assert.doesNotMatch(chat, /assets\/blueprint-responsive\.svg/);
  assert.match(chat, /@media\(max-width:900px\)/);
  assert.match(chat, /@media\(max-width:600px\)/);
});
