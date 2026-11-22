/* AI Manager Automotive Language Engine v1
 * Deterministic terminology normalization for RU/UK/EN.
 * Keeps VIN, OE/OEM numbers and part codes untouched.
 */
(function(global){
  'use strict';
  const rows = [
    {id:'control_arm',ru:['рычаг подвески','рычаг передний','передний рычаг','рычаг задний'],uk:['важіль підвіски','передній важіль','задній важіль'],en:['control arm','suspension arm','wishbone']},
    {id:'control_arm_bushing',ru:['сайлентблок','сайлент-блок','резинка рычага','втулка рычага'],uk:['сайлентблок','сайлент-блок','гумка важеля','втулка важеля'],en:['control arm bushing','bushing','rubber bush']},
    {id:'ball_joint',ru:['шаровая','шаровая опора'],uk:['кульова','кульова опора'],en:['ball joint']},
    {id:'wheel_bearing',ru:['ступичный подшипник','подшипник ступицы'],uk:['підшипник маточини','ступичний підшипник'],en:['wheel bearing','hub bearing']},
    {id:'brake_caliper',ru:['суппорт','тормозной суппорт'],uk:['супорт','гальмівний супорт'],en:['brake caliper']},
    {id:'brake_pad',ru:['тормозные колодки','колодки тормозные','тормозная колодка'],uk:['гальмівні колодки','гальмівна колодка'],en:['brake pads','brake pad']},
    {id:'brake_disc',ru:['тормозной диск','диск тормозной'],uk:['гальмівний диск'],en:['brake disc','brake rotor']},
    {id:'cv_joint_outer',ru:['наружный шрус','наружная граната','граната наружная'],uk:['зовнішній шрус','зовнішній шарнір'],en:['outer cv joint','outer cv axle joint']},
    {id:'cv_joint_inner',ru:['внутренний шрус','внутренняя граната'],uk:['внутрішній шрус','внутрішній шарнір'],en:['inner cv joint']},
    {id:'drive_shaft',ru:['привод','приводной вал','полуось'],uk:['привід','приводний вал','піввісь'],en:['drive shaft','axle shaft','half shaft']},
    {id:'tie_rod_end',ru:['рулевой наконечник','наконечник рулевой тяги'],uk:['кермовий наконечник','наконечник кермової тяги'],en:['tie rod end']},
    {id:'tie_rod',ru:['рулевая тяга'],uk:['кермова тяга'],en:['tie rod']},
    {id:'shock_absorber',ru:['амортизатор','стойка амортизатора'],uk:['амортизатор','стійка амортизатора'],en:['shock absorber','damper','strut']},
    {id:'strut_mount',ru:['опора амортизатора','опорный подшипник'],uk:['опора амортизатора','опорний підшипник'],en:['strut mount','strut bearing']},
    {id:'timing_belt_kit',ru:['комплект грм','ремень грм','ремень газораспределения'],uk:['комплект грм','ремінь грм','ремінь газорозподільного механізму'],en:['timing belt kit','timing belt']},
    {id:'water_pump',ru:['помпа','водяной насос'],uk:['помпа','водяний насос'],en:['water pump']},
    {id:'head_gasket',ru:['прокладка гбц','прокладка головки блока'],uk:['прокладка гбц','прокладка головки блока'],en:['cylinder head gasket','head gasket']},
    {id:'oil_filter',ru:['масляный фильтр','фильтр масла'],uk:['масляний фільтр','фільтр оливи'],en:['oil filter']},
    {id:'air_filter',ru:['воздушный фильтр','фильтр воздуха'],uk:['повітряний фільтр'],en:['air filter']},
    {id:'fuel_filter',ru:['топливный фильтр','фильтр топлива'],uk:['паливний фільтр'],en:['fuel filter']},
    {id:'clutch_kit',ru:['комплект сцепления','сцепление в сборе'],uk:['комплект зчеплення','зчеплення в зборі'],en:['clutch kit','clutch assembly']},
    {id:'flywheel',ru:['маховик','двухмассовый маховик'],uk:['маховик','двомасовий маховик'],en:['flywheel','dual mass flywheel']},
    {id:'alternator',ru:['генератор','генератор автомобиля'],uk:['генератор'],en:['alternator']},
    {id:'starter',ru:['стартер'],uk:['стартер'],en:['starter motor','starter']},
    {id:'engine_mount',ru:['подушка двигателя','опора двигателя'],uk:['подушка двигуна','опора двигуна'],en:['engine mount']},
    {id:'thermostat',ru:['термостат'],uk:['термостат'],en:['thermostat']},
    {id:'radiator',ru:['радиатор охлаждения','радиатор двигателя'],uk:['радіатор охолодження','радіатор двигуна'],en:['engine radiator','radiator']},
    {id:'cabin_filter',ru:['салонный фильтр','фильтр салона'],uk:['салонний фільтр','фільтр салону'],en:['cabin filter','pollen filter']},
    {id:'oem_number',ru:['оригинальный номер','номер оригинала','оэ номер','oe номер'],uk:['оригінальний номер','номер оригіналу','oe номер'],en:['oe number','oem number','genuine part number']}
  ];
  const norm=s=>String(s||'').toLocaleLowerCase().replace(/[ё]/g,'е').replace(/[’']/g,'').replace(/[^\\p{L}\\p{N}]+/gu,' ').trim();
  const index=[];
  rows.forEach(row=>['ru','uk','en'].forEach(lang=>(row[lang]||[]).forEach(alias=>index.push({id:row.id,lang,alias,norm:norm(alias)}))));
  function matchTerms(text){
    const source=norm(text), found=new Map();
    for(const item of index){
      if((' '+source+' ').includes(' '+item.norm+' ')&&!found.has(item.id))found.set(item.id,rows.find(r=>r.id===item.id));
    }
    return [...found.values()];
  }
  function expandQuery(text){
    const found=matchTerms(text), aliases=[];
    found.forEach(row=>['ru','uk','en'].forEach(lang=>(row[lang]||[]).slice(0,2).forEach(a=>{if(norm(a)!==norm(text))aliases.push(a)})));
    return [String(text||'').trim(),...aliases].filter(Boolean).join(' | ');
  }
  function termIds(text){return matchTerms(text).map(x=>x.id)}
  global.AIManagerLanguage=Object.freeze({version:'1.0.0',matchTerms,expandQuery,termIds,glossary:rows});
})(window);
