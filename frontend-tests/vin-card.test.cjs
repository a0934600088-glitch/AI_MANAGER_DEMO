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
test('vehicle confirmation resumes a part request queued before VIN confirmation', () => {
  const handler = html.slice(html.indexOf('yes.onclick='), html.indexOf('const no=', html.indexOf('yes.onclick=')));
  assert.match(handler, /vehicleConfirmed=true/);
  assert.match(handler, /const queuedPartQuery=pendingPartQuery\.trim\(\)/);
  assert.match(handler, /if\(catalogVerified&&queuedPartQuery\)/);
  assert.match(handler, /searchCatalogForRequest\(queuedPartQuery\)/);
  assert.doesNotMatch(handler, /lookup\('groups'/);
});

test('rejecting or replacing a VIN clears a queued request from the previous vehicle', () => {
  const decodeStart = html.indexOf('async function decode(');
  const decodeEnd = html.indexOf('\nfunction catalogRows', decodeStart);
  const decode = html.slice(decodeStart, decodeEnd);
  const rejectStart = html.indexOf('const no=');
  const rejectEnd = html.indexOf('actions.append', rejectStart);
  const reject = html.slice(rejectStart, rejectEnd);
  assert.match(decode, /pendingPartQuery=''/);
  assert.match(reject, /pendingPartQuery=''/);
});

test('brake pad axle cards use explicit front and rear customer labels', () => {
  const start = html.indexOf('function renderCatalogSchemas(');
  const end = html.indexOf('\n\nasync function lookup(', start);
  const renderer = html.slice(start, end);
  assert.match(renderer, /Передние тормозные колодки/);
  assert.match(renderer, /Задние тормозные колодки/);
  assert.match(renderer, /schema\.axle==='front'\|\|schema\.axle==='rear'/);
});

test('VIN card labels TradeSoft engine code and engine type separately', () => {
  const start = html.indexOf('function collectFields(');
  const end = html.indexOf('\\nfunction showVehicle(', start);
  const source = html.slice(start, end);
  assert.match(source, /engine:'Код двигателя'/);
  assert.match(source, /engine_info:'Тип двигателя'/);
  assert.match(source, /engine_type:'Тип двигателя'/);
  assert.match(source, /engineInfo:'Тип двигателя'/);
  assert.match(html, /\['Двигатель',\['Двигатель','Тип двигателя','Код двигателя','Объём двигателя'/);
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

test('Mercedes TradeSoft description is split into separate customer card rows', () => {
  const start=html.indexOf('function collectFields('), end=html.indexOf('function showVehicle(',start), context={};
  vm.runInNewContext(html.slice(start,end)+'\nglobalThis.__collect=collectFields;',context);
  const fields=context.__collect({brand:'Mercedes',modelName:'C-class',title:'205.349 (C 300 4MATIC)',description:'C COUPE. . Regions: Europe, North America, Japan, 7-SPEED AUTOMATIC TRANSMISSION W7X700 (722969 06 680783, 722.969), R4 GASOLINE ENGINE M274 E20 (274920 30 609221, 274.920, M274 E20)',parameters:[{name:'Year',value:'2016'}]});
  assert.equal(fields['Регион'],'Europe, North America, Japan');assert.equal(fields['Тип кузова'],'C COUPE');assert.equal(fields['Трансмиссия'],'7-SPEED AUTOMATIC TRANSMISSION');assert.equal(fields['Код КПП'],'722.969');assert.equal(fields['Тип топлива'],'Бензин');assert.equal(fields['Цилиндры'],'4');assert.ok(fields['Код двигателя'].includes('M274 E20'));
});
test('VIN card uses grouped responsive vehicle sections',()=>{assert.match(html,/vehicle-sections/);assert.match(html,/Идентификация/);assert.match(html,/Кузов и регион/);});

test('non-brake multi-schema results are not forced into front/rear classification', () => {
  const start = html.indexOf('function renderCatalogSchemas(');
  const end = html.indexOf('\n\nasync function lookup(', start);
  assert.notEqual(start, -1);
  const renderer = html.slice(start, end);
  assert.doesNotMatch(renderer, /const classified=schemas\.filter\(schema=>schema\.axle/);
  assert.match(renderer, /деталей двигателя и других систем/);
  assert.match(renderer, /schemas\.forEach\(\(schema,index\)=>/);
  assert.match(renderer, /schema\.catalogPath/);
  assert.match(renderer, /card\.onclick=\(\)=>lookup\('parts',query,id\)/);
  assert.match(renderer, /Найдено несколько узлов в каталоге этого автомобиля/);
});
test('multilingual terminology resolves engine pistons and keeps piston rings and brake pistons distinct', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'automotive-language.js'), 'utf8');
  const context = { window: {} };
  vm.runInNewContext(source, context);
  const language = context.window.AIManagerLanguage;
  assert.ok(language.termIds('ПОРШЕНЬ').includes('engine_piston'));
  assert.ok(language.termIds('поршня двигателя').includes('engine_piston'));
  assert.ok(language.termIds('поршневые кольца').includes('piston_ring'));
  assert.ok(!language.termIds('поршневые кольца').includes('engine_piston'));
  assert.ok(language.termIds('поршень суппорта').includes('brake_caliper_piston'));
  assert.ok(!language.termIds('поршень суппорта').includes('engine_piston'));
  const expanded = language.expandQuery('поршень');
  assert.match(expanded, /поршень двигателя/);
  assert.match(expanded, /engine piston/i);
  assert.ok(expanded.length <= 580);
  const front = language.expandQuery('передние тормозные колодки');
  const rear = language.expandQuery('тормозные колодки задние');
  assert.match(front, /передний brake pads|front brake pads/i);
  assert.match(rear, /задний brake pads|rear brake pads/i);
});
test('parking-brake pad phrases do not resolve to service brake pads', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'automotive-language.js'), 'utf8');
  const context = { window: {} };
  vm.runInNewContext(source, context);
  const ids = context.window.AIManagerLanguage.termIds('колодки ручника');
  assert.ok(ids.includes('parking_brake_shoe'));
  assert.ok(!ids.includes('brake_pad'));
});
test('backend axle metadata is only assigned for brake searches', () => {
  const backend = fs.readFileSync('backend/app/providers/tradesoft_parts_catalogs.py', 'utf8');
  assert.match(backend, /if brake_query:[\s\S]{0,300}axle = self\._schema_axle/);
});

test('backend resolves axle from exact VIN catalogue group ancestry', () => {
  const backend = fs.readFileSync('backend/app/providers/tradesoft_parts_catalogs.py', 'utf8');
  assert.match(backend, /async def _schema_catalog_paths/);
  assert.match(backend, /schema\["catalogPath"\]/);
  assert.match(backend, /schema\["axle"\]/);
  assert.match(backend, /front|rear/i);
});

test('brake searches show one plain-language original diagram card per confirmed brake category', () => {
  const start = html.indexOf('function renderCatalogSchemas(');
  const end = html.indexOf('\n\nasync function lookup(', start);
  const renderer = html.slice(start, end);
  assert.match(renderer, /Передняя тормозная система/);
  assert.match(renderer, /Задняя тормозная система/);
  assert.match(renderer, /Барабанная тормозная система/);
  assert.match(renderer, /Стояночный тормоз \(ручник\)/);
  assert.match(renderer, /Выберите нужную тормозную систему/);
  assert.match(renderer, /cards\.forEach\(\(\{category,schema\}\)=>/);
  assert.match(renderer, /card\.onclick=\(\)=>lookup\('parts',query,id\)/);
  assert.match(renderer, /const selected=rows\.map\(/);
  assert.doesNotMatch(renderer.slice(renderer.indexOf('if(brakeQuery)'), renderer.indexOf('const classified=')), /rows\.forEach\(/);
  assert.doesNotMatch(renderer, /Front brake [0-9]|Disc brake [0-9]|Схема [0-9]/i);
});
test('brake categories are assigned by backend from VIN catalogue labels, parking brake first', () => {
  const backend = fs.readFileSync('backend/app/providers/tradesoft_parts_catalogs.py', 'utf8');
  assert.match(backend, /def _schema_brake_category/);
  assert.match(backend, /parking = bool\(re\.search/);
  assert.match(backend, /drum = bool\(re\.search/);
  assert.match(backend, /schema\["catalogCategory"\]/);
});


test('brake category card shows one thumbnail and hides TradeSoft subgroup names', () => {
 const start=html.indexOf('function renderCatalogSchemas('),end=html.indexOf('\n\nasync function lookup(',start);
 const renderer=html.slice(start,end);
 assert.match(renderer,/img\.src=String\(image\)/);
 assert.match(renderer,/title\.textContent=category\.title/);
 assert.match(renderer,/hint\.textContent=category\.hint/);
 assert.match(renderer,/rows\.map\(\(schema,index\)=>\(\{schema,index,score:scoreSchema\(schema\)\}\)\)/);
 assert.match(renderer,/sort\(\(a,b\)=>b\.score-a\.score\|\|b\.index-a\.index\)/);
 assert.doesNotMatch(renderer,/name\+' — схема '/);
});
