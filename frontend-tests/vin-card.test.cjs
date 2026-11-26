const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');

test('TradeSoft camelCase vehicle parameters are extracted for the card', () => {
  const start = html.indexOf('function collectFields(');
  const end = html.indexOf('\nfunction showVehicle(', start);
  assert.notEqual(start, -1, 'collectFields must exist');
  assert.notEqual(end, -1, 'showVehicle must follow collectFields');

  const context = {};
  vm.runInNewContext(
    html.slice(start, end) + '\nglobalThis.__collectFields = collectFields;',
    context
  );
  const fields = context.__collectFields({
    brand: 'VOLKSWAGEN',
    title: 'Golf/Variant/4Motion',
    parameters: {
      productionYear: 2018,
      engineInfo: '1600CC / 115hp / 85kW TDI CR',
      transmission: 'SSV(7A)'
    }
  });

  assert.equal(fields['Марка'], 'VOLKSWAGEN');
  assert.equal(fields['Модель'], 'Golf/Variant/4Motion');
  assert.equal(fields['Год выпуска'], '2018');
  assert.equal(fields['Двигатель'], '1600CC / 115hp / 85kW TDI CR');
  assert.equal(fields['Трансмиссия'], 'SSV(7A)');
});

test('translated display fields are not normalized a second time', () => {
  assert.match(
    html,
    /response\?\.normalizedFields\s*&&\s*typeof response\.normalizedFields==='object'/
  );
  assert.match(html, /showVehicle\(\{normalizedFields:displayVehicleFields\}\)/);
});

test('release version is read from the canonical backend VERSION endpoint', () => {
  const version = fs.readFileSync(path.join(__dirname, '..', 'backend', 'VERSION'), 'utf8').trim();
  assert.match(version, /^\d+\.\d+\.\d+$/);
  assert.ok(html.includes('id="appVersion"'));
  assert.ok(html.includes("api('/health')"));
  assert.ok(!html.includes('2.4.8'));
  assert.ok(!html.includes('2.4.10'));
});
test('VIN input normalization removes spaces and hyphens before lookup', () => {
  assert.ok(html.includes("const clean=v.replace(/[\\s-]/g,'').toUpperCase();"));
});

test('ambiguous VIN and catalogue results stop automatic selection', () => {
  assert.match(html, /status==='ambiguous'/);
  assert.match(html, /d\?\.status==='ambiguous'/);
});

test('vehicle confirmation starts the real TradeSoft group navigation', () => {
  assert.match(html, /yes\.onclick=async\(\)=>\{vehicleConfirmed=true/);
  assert.match(html, /if\(catalogVerified\)await lookup\('groups',''\)/);
  assert.match(html, /api\('\/api\/catalog\/v1\/lookup',request\)/);
});
test('catalog groups select a provider group ID and request its real parts', () => {
  assert.match(html, /function renderCatalogGroups\(result\)/);
  assert.match(html, /button\.onclick=\(\)=>lookup\('parts','',id\)/);
  assert.match(html, /request\.group_id=groupId/);
  assert.match(html, /function renderCatalogParts\(result\)/);
  assert.match(html, /oeNumber/);
  assert.match(html, /callout/);
});
test('empty provider responses are reported without synthetic catalogue fixtures', () => {
  assert.match(html, /TradeSoft подтвердил автомобиль, но не вернул список каталожных групп/);
  assert.match(html, /TradeSoft не вернул позиции деталей для выбранной группы/);
  assert.doesNotMatch(html, /synthetic|fixture|demoPart/i);
});
