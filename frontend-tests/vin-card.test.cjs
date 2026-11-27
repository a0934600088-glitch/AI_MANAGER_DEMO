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
  assert.equal(fields['Тип двигателя'], '1600CC / 115hp / 85kW TDI CR');
  assert.equal(fields['Трансмиссия'], 'SSV(7A)');
});

test('normalized Car2 parameter rows reach the vehicle card as stable attributes', () => {
  const start = html.indexOf('function collectFields(');
  const end = html.indexOf('\nfunction showVehicle(', start);
  const context = {};
  vm.runInNewContext(html.slice(start, end) + '\nglobalThis.__collectFields = collectFields;', context);
  const fields = context.__collectFields({
    brand: 'MERCEDES-BENZ',
    title: 'C-CLASS Coupe (C205)',
    vehicle_attributes: {
      modelYear: '09.2016 - 12.2018',
      engineType: '083',
      engineCode: 'M 274.920',
      engineDisplacement: '1991 cc',
      fuelType: 'Petrol',
      cylindersValves: '4 / 4',
      bodyType: 'Coupe',
      fuelSystem: 'Direct injection',
      driveType: 'AWD',
      tecdocId: '122128'
    }
  });
  assert.equal(fields['Год выпуска'], '09.2016 - 12.2018');
  assert.equal(fields['Тип двигателя'], '083');
  assert.equal(fields['Код двигателя'], 'M 274.920');
  assert.equal(fields['Объём двигателя'], '1991 cc');
  assert.equal(fields['Топливо'], 'Petrol');
  assert.equal(fields['Цилиндры / клапаны'], '4 / 4');
  assert.equal(fields['Тип кузова'], 'Coupe');
  assert.equal(fields['Топливная система'], 'Direct injection');
  assert.equal(fields['Тип привода'], 'AWD');
  assert.equal(fields['Идентификатор TecDoc'], '122128');
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
  assert.match(html, /technical\.has\(normalized\)/);
  assert.match(html, /Тип двигателя/);
  assert.match(html, /productionYear/);
});
test('vehicle confirmation waits for the customer part request instead of opening the catalogue tree', () => {
  const handler = html.slice(html.indexOf('yes.onclick='), html.indexOf('const no=', html.indexOf('yes.onclick=')));
  assert.match(handler, /vehicleConfirmed=true/);
  assert.doesNotMatch(handler, /lookup\('groups'/);
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

test('customer part request searches TradeSoft schemas directly without exposing the catalogue root tree', () => {
  assert.match(html, /async function searchCatalogForRequest\(query\)[\s\S]*?await lookup\('parts',query\)/);
  assert.match(html, /renderCatalogSchemas\(d\.result,pendingPartQuery\|\|q\)/);
  assert.match(html, /async function lookup\(mode,q,groupId\)/);
  assert.match(html, /groupOf\(schemas\[0\]\)/);
  assert.doesNotMatch(html.slice(html.indexOf('async function searchCatalogForRequest'), html.indexOf('function renderCatalogParts')), /renderCatalogGroupSuggestions/);
});
test('TradeSoft diagram supports zoom and callout-to-OE selection', () => {
  assert.match(html, /Увеличить схему/);
  assert.match(html, /Уменьшить схему/);
  assert.match(html, /position\.number\?\?position\.positionNumber/);
  assert.match(html, /оригинальный номер/);
});
