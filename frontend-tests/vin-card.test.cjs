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
  assert.equal(fields['Характеристики двигателя'], '1600CC / 115hp / 85kW TDI CR');
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
  assert.match(html, /yes\.onclick=\(\)=>\{vehicleConfirmed=true/);
  assert.match(html, /Автомобиль подтверждён\. Теперь напишите нужную запчасть/);
  assert.match(html, /api\('\/api\/catalog\/v1\/lookup',request\)/);
});
test('catalog groups select a provider group ID and request its real parts', () => {
  assert.match(html, /function renderCatalogGroups\(result\)/);
  assert.match(html, /button\.onclick=\(\)=>lookup\(hasParts\?'parts':'groups',pendingPartQuery,id\)/);
  assert.match(html, /request\.group_id=groupId/);
  assert.match(html, /function renderCatalogParts\(result\)/);
  assert.match(html, /oeNumber/);
  assert.match(html, /callout/);
});
test('empty provider responses are reported without synthetic catalogue fixtures', () => {
  assert.match(html, /TradeSoft не вернул группы оригинального каталога/);
  assert.match(html, /TradeSoft не вернул позиции деталей для выбранной группы/);
  assert.doesNotMatch(html, /synthetic|fixture|demoPart/i);
});

test('group navigation descends until TradeSoft marks a node hasParts=true', () => {
  assert.match(html, /function catalogFlag\(value\)/);
  assert.match(html, /const hasParts=catalogFlag\(item\.hasParts\?\?item\.has_parts\)/);
  assert.match(html, /lookup\(hasParts\?'parts':'groups',pendingPartQuery,id\)/);
});
test('TradeSoft parts2 response renders original diagram, partGroups and callout positions', () => {
  assert.match(html, /catalogRows\(payload,\['partGroups','part_groups'\]\)/);
  assert.match(html, /const positions=catalogRows\(payload,\['positions'\]\)/);
  assert.match(html, /positionNumber/);
  assert.match(html, /payload\?\.img/);
  assert.ok(html.includes("v.startsWith('//')"));
});

test('part request is queued before vehicle confirmation instead of being discarded', () => {
  assert.match(html, /pendingPartQuery=v;add\('Запрос сохранён:/);
  assert.match(html, /if\(!vehicleConfirmed\)\{pendingPartQuery=v;/);
  assert.match(html, /Автомобиль подтверждён\. Теперь напишите нужную запчасть/);
});
test('confirmed customer part request opens groups and carries query to the selected leaf', () => {
  assert.match(html, /pendingPartQuery=v;[\s\S]*?await searchCatalogForRequest\(v\)/);
  assert.match(html, /button\.onclick=\(\)=>lookup\(hasParts\?'parts':'groups',pendingPartQuery,id\)/);
  assert.match(html, /request\.group_id=groupId/);
  assert.match(html, /pendingPartQuery=''/);
});

test('full TradeSoft vehicle response fields are preserved for the expanded VIN card', () => {
  assert.match(html, /function collectFields\(obj,out=\{\},seen=new Set\(\),parent=''/);
  assert.match(html, /hidden\.has\(normalized\)/);
  assert.match(html, /Характеристики двигателя/);
  assert.match(html, /productionYear/);
});
test('vehicle confirmation waits for the customer part request instead of opening the catalogue tree', () => {
  const handler = html.slice(html.indexOf('yes.onclick='), html.indexOf('const no=', html.indexOf('yes.onclick=')));
  assert.match(handler, /vehicleConfirmed=true/);
  assert.doesNotMatch(handler, /lookup\('groups'/);
});
test('customer part request triggers automatic TradeSoft group-tree search', () => {
  assert.match(html, /async function searchCatalogForRequest\(query\)/);
  assert.match(html, /groupMatchTerms\(query\)/);
  assert.match(html, /await searchCatalogForRequest\(v\)/);
  assert.match(html, /mode:'groups'.*group_id:id/);
  assert.match(html, /await lookup\('parts',query,best\.id\)/);
});
test('catalog search stops for ambiguous group matches and asks customer to choose', () => {
  assert.match(html, /Не удалось надёжно определить точный узел/);
  assert.match(html, /candidates\.slice\(0,6\)/);
});

test('VIN card labels TradeSoft engine code and engine type separately', () => {
  const start = html.indexOf('function collectFields(');
  const end = html.indexOf('\\nfunction showVehicle(', start);
  const source = html.slice(start, end);
  assert.match(source, /engine:'Код двигателя'/);
  assert.match(source, /engine_info:'Тип двигателя'/);
  assert.match(source, /engine_type:'Тип двигателя'/);
  assert.match(source, /engineInfo:'Тип двигателя'/);
  assert.match(html, /'Код двигателя','Тип двигателя','Объём двигателя'/);
});
test('VIN card keeps the engine type value from the supplied TradeSoft template', () => {
  const collect = html.slice(html.indexOf('function collectFields('), html.indexOf('\\nfunction showVehicle('));
  assert.match(collect, /engine_info:'Тип двигателя'/);
  assert.match(collect, /engine:'Код двигателя'/);
});
