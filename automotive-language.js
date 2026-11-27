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
    {id:'brake_pad',ru:['тормозные колодки','колодки тормозные','тормозная колодка','передние тормозные колодки'],uk:['гальмівні колодки','гальмівна колодка','передні гальмівні колодки'],en:['brake pads','brake pad','front brake pads']},
    {id:'brake_disc',ru:['тормозной диск','диск тормозной','тормозные диски','диски тормозные'],uk:['гальмівний диск','гальмівні диски'],en:['brake disc','brake rotor','brake discs','brake rotors']},
    {id:'cv_joint_outer',ru:['наружный шрус','наружная граната','граната наружная'],uk:['зовнішній шрус','зовнішній шарнір'],en:['outer cv joint','outer cv axle joint']},
    {id:'cv_joint_inner',ru:['внутренний шрус','внутренняя граната'],uk:['внутрішній шрус','внутрішній шарнір'],en:['inner cv joint']},
    {id:'drive_shaft',ru:['привод','приводной вал','полуось'],uk:['привід','приводний вал','піввісь'],en:['drive shaft','axle shaft','half shaft']},
    {id:'tie_rod_end',ru:['рулевой наконечник','наконечник рулевой тяги'],uk:['кермовий наконечник','наконечник кермової тяги'],en:['tie rod end']},
    {id:'tie_rod',ru:['рулевая тяга'],uk:['кермова тяга'],en:['tie rod']},
    {id:'shock_absorber',ru:['амортизатор','амортизаторы','передний амортизатор','передние амортизаторы','стойка амортизатора','передние стойки амортизатора'],uk:['амортизатор','амортизатори','передній амортизатор','передні амортизатори','стійка амортизатора'],en:['shock absorber','shock absorbers','front shock absorber','front shock absorbers','damper','strut','front struts']},
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
    {id:'engine_piston',ru:['поршень двигателя','поршень мотора','поршень двс','поршень цилиндра','поршень','поршни двигателя','поршни','поршневая группа','поршень в сборе','поршня двигателя'],uk:['поршень двигуна','поршень мотора','поршень циліндра','поршень','поршні двигуна','поршні','поршнева група'],en:['engine piston','piston','piston assembly','cylinder piston','engine pistons']},
    {id:'piston_ring',ru:['поршневые кольца','кольца поршневые','кольца двигателя','кольца на поршень'],uk:['поршневі кільця','кільця поршневі','кільця двигуна'],en:['piston rings','engine piston rings','piston ring set']},
    {id:'connecting_rod',ru:['шатун двигателя','шатун','шатуны','шатунный механизм'],uk:['шатун двигуна','шатун','шатуни'],en:['connecting rod','con rod','engine connecting rod']},
    {id:'crankshaft',ru:['коленвал','коленчатый вал','вал коленчатый'],uk:['колінвал','колінчастий вал'],en:['crankshaft','crank shaft']},
    {id:'cylinder_block',ru:['блок цилиндров','блок двигателя','блок цилиндра','гбц блок'],uk:['блок циліндрів','блок двигуна'],en:['cylinder block','engine block','cylinder case']},
    {id:'cylinder_head',ru:['головка блока цилиндров','головка блока','головка двигателя','гбц'],uk:['головка блока циліндрів','головка блока','гбц'],en:['cylinder head','engine head','head assembly']},
    {id:'engine_valve',ru:['клапан двигателя','клапан впускной','клапан выпускной','впускной клапан','выпускной клапан','клапана двигателя'],uk:['клапан двигуна','впускний клапан','випускний клапан','клапани двигуна'],en:['engine valve','intake valve','exhaust valve','inlet valve']},
    {id:'camshaft',ru:['распредвал','распределительный вал','вал распределительный'],uk:['розпредвал','розподільний вал'],en:['camshaft','cam shaft']},
    {id:'timing_chain',ru:['цепь грм','цепь газораспределения','цепь двигателя','комплект цепи грм'],uk:['ланцюг грм','ланцюг газорозподілу','ланцюг двигуна'],en:['timing chain','engine timing chain','timing chain kit']},
    {id:'oil_pump',ru:['масляный насос','насос масла','маслонасос'],uk:['масляний насос','насос оливи'],en:['oil pump','engine oil pump']},
    {id:'turbocharger',ru:['турбина','турбокомпрессор','турбонагнетатель'],uk:['турбіна','турбокомпресор'],en:['turbocharger','turbo','turbo unit']},
    {id:'fuel_injector',ru:['форсунка','топливная форсунка','дизельная форсунка','инжектор'],uk:['форсунка','паливна форсунка','дизельна форсунка'],en:['fuel injector','injector','diesel injector']},
    {id:'spark_plug',ru:['свеча зажигания','свечи зажигания','свеча','свечи'],uk:['свічка запалювання','свічки запалювання'],en:['spark plug','spark plugs','ignition plug']},
    {id:'glow_plug',ru:['свеча накала','свечи накала','свеча накаливания'],uk:['свічка розжарювання','свічки розжарювання'],en:['glow plug','glow plugs']},
    {id:'ignition_coil',ru:['катушка зажигания','катушка','катушки зажигания'],uk:['котушка запалювання','котушки запалювання'],en:['ignition coil','coil pack','ignition coils']},
    {id:'brake_shoe',ru:['тормозные барабанные колодки','барабанные колодки','тормозная колодка барабана'],uk:['барабанні гальмівні колодки','гальмівні колодки барабана'],en:['brake shoes','drum brake shoes','brake shoe']},
    {id:'parking_brake_shoe',ru:['колодки ручника','колодка ручника','колодки стояночного тормоза','колодка стояночного тормоза','колодки ручного тормоза'],uk:['колодки ручника','колодки стоянкового гальма','колодка стоянкового гальма'],en:['parking brake shoes','handbrake shoes','parking brake shoe']},
    {id:'brake_caliper_piston',ru:['поршень суппорта','поршень тормозного суппорта','поршень тормоза'],uk:['поршень супорта','поршень гальмівного супорта'],en:['brake caliper piston','caliper piston']},
    {id:'brake_master_cylinder',ru:['главный тормозной цилиндр','гтц','тормозной цилиндр главный'],uk:['головний гальмівний циліндр','гтц'],en:['brake master cylinder','master cylinder']},
    {id:'wheel_cylinder',ru:['тормозной цилиндр колеса','рабочий тормозной цилиндр','колесный цилиндр'],uk:['робочий гальмівний циліндр','колісний циліндр'],en:['wheel cylinder','brake wheel cylinder']},
    {id:'stabilizer_link',ru:['стойка стабилизатора','тяга стабилизатора','линк стабилизатора'],uk:['стійка стабілізатора','тяга стабілізатора'],en:['stabilizer link','sway bar link','anti-roll bar link']},
    {id:'stabilizer_bushing',ru:['втулка стабилизатора','резинка стабилизатора','втулки стабилизатора'],uk:['втулка стабілізатора','гумка стабілізатора'],en:['stabilizer bushing','sway bar bushing','anti-roll bar bush']},
    {id:'steering_rack',ru:['рулевая рейка','рейка рулевая','рулевой механизм'],uk:['кермова рейка','рейка кермова'],en:['steering rack','steering gear rack']},
    {id:'wheel_hub',ru:['ступица колеса','ступица','ступичный узел'],uk:['маточина колеса','маточина'],en:['wheel hub','hub assembly']},
    {id:'coil_spring',ru:['пружина подвески','пружина амортизатора','пружина'],uk:['пружина підвіски','пружина амортизатора'],en:['coil spring','suspension spring']},
    {id:'engine_belt',ru:['ремень двигателя','приводной ремень','ремень генератора','поликлиновый ремень'],uk:['ремінь двигуна','привідний ремінь','ремінь генератора'],en:['serpentine belt','drive belt','accessory belt','engine belt']},
    {id:'exhaust_manifold',ru:['выпускной коллектор','коллектор выпуска'],uk:['випускний колектор'],en:['exhaust manifold']},
    {id:'intake_manifold',ru:['впускной коллектор','коллектор впуска'],uk:['впускний колектор'],en:['intake manifold','inlet manifold']},
    {id:'oxygen_sensor',ru:['лямбда зонд','датчик кислорода','кислородный датчик'],uk:['лямбда зонд','датчик кисню'],en:['oxygen sensor','lambda sensor','o2 sensor']},
  const norm=s=>String(s||'').toLocaleLowerCase().replace(/[ё]/g,'е').replace(/[’']/g,'').replace(/[^\p{L}\p{N}]+/gu,' ').trim();
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
    const original=String(text||'').trim();
    if(!original)return '';
    const found=matchTerms(original), aliases=[];
    const source=norm(original);
    const axle=/(^|\\s)(задн\\w*|rear|back)(\\s|$)/i.test(source)?{ru:'задний',uk:'задній',en:'rear'}:
      (/(^|\\s)(передн\\w*|front)(\\s|$)/i.test(source)?{ru:'передний',uk:'передній',en:'front'}:null);
    const brakeContext=/(тормоз|гальм|brake|суппорт|супорт)/i.test(source);
    found.forEach(row=>{
      if(row.id==='engine_piston'&&brakeContext)return;
      ['ru','uk','en'].forEach(lang=>(row[lang]||[]).forEach(alias=>{
        if(norm(alias)===source)return;
        const variant=axle&&!/(передн|задн|front|rear|back)/i.test(alias)?axle[lang]+' '+alias:alias;
        if(!aliases.some(item=>norm(item)===norm(variant)))aliases.push(variant);
      }));
    });
    const compact=[original,...aliases].filter(Boolean).slice(0,7);
    let output=compact.join(' | ');
    while(output.length>580&&compact.length>2){compact.pop();output=compact.join(' | ')}
    return output;
  }
  function termIds(text){return matchTerms(text).map(x=>x.id)}
  global.AIManagerLanguage=Object.freeze({version:'1.0.0',matchTerms,expandQuery,termIds,glossary:rows});
})(window);
