"""Self-hosted Argos translation with automotive terminology and identifier protection."""
from __future__ import annotations
import os, re, threading
from typing import Any

os.environ.setdefault("XDG_DATA_HOME", "/tmp/ai-manager-argos")
SUPPORTED_CORE = {"ru", "uk", "en"}
LANGUAGE_NAMES = {"ru":"Russian","uk":"Ukrainian","en":"English","pl":"Polish","de":"German","fr":"French","es":"Spanish","it":"Italian","cs":"Czech","ro":"Romanian","tr":"Turkish","nl":"Dutch","pt":"Portuguese","ar":"Arabic","zh":"Chinese","ja":"Japanese","ko":"Korean"}
TERMS = [
(["сайлентблок","сайлент-блок","резинка рычага","втулка рычага"],["сайлентблок","гумометалева втулка","втулка важеля"],["control arm bushing"]),
(["рычаг подвески","передний рычаг","задний рычаг"],["важіль підвіски","передній важіль","задній важіль"],["control arm","suspension arm","wishbone"]),
(["шаровая","шаровая опора"],["кульова опора","кульова"],["ball joint"]),
(["ступичный подшипник","подшипник ступицы"],["підшипник маточини","ступичний підшипник"],["wheel bearing","hub bearing"]),
(["тормозные колодки","тормозная колодка"],["гальмівні колодки","гальмівна колодка"],["brake pads","brake pad"]),
(["тормозной диск","диск тормозной"],["гальмівний диск"],["brake disc","brake rotor"]),
(["суппорт","тормозной суппорт"],["супорт","гальмівний супорт"],["brake caliper"]),
(["наружный шрус","наружная граната","граната наружная"],["зовнішній шрус","зовнішній шарнір"],["outer CV joint"]),
(["внутренний шрус","внутренняя граната"],["внутрішній шрус","внутрішній шарнір"],["inner CV joint"]),
(["амортизатор","стойка амортизатора"],["амортизатор","стійка амортизатора"],["shock absorber","damper","strut"]),
(["опора амортизатора","опорный подшипник"],["опора амортизатора","опорний підшипник"],["strut mount","strut bearing"]),
(["рулевой наконечник","наконечник рулевой тяги"],["кермовий наконечник","наконечник кермової тяги"],["tie rod end"]),
(["рулевая тяга"],["кермова тяга"],["tie rod"]),
(["комплект грм","ремень грм","ремень газораспределения"],["комплект грм","ремінь грм","ремінь газорозподільного механізму"],["timing belt kit","timing belt"]),
(["помпа","водяной насос"],["помпа","водяний насос"],["water pump"]),
(["прокладка гбц","прокладка головки блока"],["прокладка гбц","прокладка головки блока"],["cylinder head gasket","head gasket"]),
(["масляный фильтр","фильтр масла"],["масляний фільтр","фільтр оливи"],["oil filter"]),
(["воздушный фильтр","фильтр воздуха"],["повітряний фільтр"],["air filter"]),
(["топливный фильтр","фильтр топлива"],["паливний фільтр"],["fuel filter"]),
(["салонный фильтр","фильтр салона"],["салонний фільтр","фільтр салону"],["cabin filter","pollen filter"]),
(["комплект сцепления","сцепление в сборе"],["комплект зчеплення","зчеплення в зборі"],["clutch kit","clutch assembly"]),
(["маховик","двухмассовый маховик"],["маховик","двомасовий маховик"],["flywheel","dual-mass flywheel"]),
(["подушка двигателя","опора двигателя"],["подушка двигуна","опора двигуна"],["engine mount"]),
(["генератор автомобиля"],["генератор"],["alternator"]),
(["стартер"],["стартер"],["starter motor"]),
(["радиатор охлаждения","радиатор двигателя"],["радіатор охолодження","радіатор двигуна"],["engine radiator"]),
(["термостат"],["термостат"],["thermostat"]),
(["оригинальный номер","номер оригинала","оэ номер","oe номер"],["оригінальний номер","номер оригіналу","oe номер"],["OE number","OEM number","genuine part number"]),
]
TARGET_TERM = {"ru":[r[0][0] for r in TERMS],"uk":[r[1][0] for r in TERMS],"en":[r[2][0] for r in TERMS]}
LOCK=threading.RLock()
_PACKAGES=None
_INSTALLED=set()
IDENTIFIERS=[
re.compile(r"(?<![A-Z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-Z0-9])",re.I),
re.compile(r"(?<![A-Z0-9])[A-Z0-9]{1,5}(?:[-./][A-Z0-9]{1,12}){1,4}(?![A-Z0-9])",re.I),
re.compile(r"(?<!\w)\d{2,3}\s+\d{2,3}\s+\d{2,3}\s+[A-Z]{1,3}(?!\w)",re.I),
re.compile(r"(?<!\w)\d+(?:[.,]\d+)?\s?(?:mm|cm|m|kw|hp|cc|nm|bar|psi|l|л)(?!\w)",re.I),
re.compile(r"(?<!\w)[A-Z]{2,8}\d{0,3}(?!\w)"),
]
def _detect(text:str)->str:
    try:
        from langdetect import DetectorFactory, detect
        DetectorFactory.seed=0
        code=detect(text)
        if code in {"ru","uk","en"}: return code
    except Exception: pass
    low=text.lower()
    if re.search(r"[іїєґ]",low): return "uk"
    if re.search(r"[ыэъё]",low): return "ru"
    if re.search(r"[а-я]",low): return "ru"
    return "en"
def _available_packages():
    global _PACKAGES
    with LOCK:
        if _PACKAGES is None:
            import argostranslate.package
            _PACKAGES=argostranslate.package.get_available_packages()
        return _PACKAGES
def _installed(source,target):
    import argostranslate.translate
    langs=argostranslate.translate.get_installed_languages()
    a=next((x for x in langs if x.code==source),None)
    b=next((x for x in langs if x.code==target),None)
    return a.get_translation(b) if a and b else None
def _ensure_pair(source,target):
    import argostranslate.package
    if (source,target) in _INSTALLED or _installed(source,target):
        _INSTALLED.add((source,target)); return
    model=next((p for p in _available_packages() if p.from_code==source and p.to_code==target),None)
    if model is None: raise ValueError(f"No open translation model is available for {source}->{target}.")
    argostranslate.package.install_from_path(model.download())
    _INSTALLED.add((source,target))
def _get_translation(source,target):
    if source==target: return None
    with LOCK:
        existing=_installed(source,target)
        if existing: return existing
        try: _ensure_pair(source,target)
        except ValueError:
            if source!="en" and target!="en":
                _ensure_pair(source,"en"); _ensure_pair("en",target)
            else: raise
        result=_installed(source,target)
        if result is None: raise RuntimeError(f"Argos route {source}->{target} is not installed.")
        return result
def _protect(text,target,automotive):
    saved={}
    def hold(match):
        key=f"QZXID{len(saved):04d}ZXQ"; saved[key]=match.group(0); return key
    value=text
    for pattern in IDENTIFIERS: value=pattern.sub(hold,value)
    if automotive and target in TARGET_TERM:
        aliases=[]
        for idx,row in enumerate(TERMS):
            for group in row:
                aliases.extend((alias,idx) for alias in group)
        aliases.sort(key=lambda item:len(item[0]),reverse=True)
        for alias,idx in aliases:
            pat=re.compile(r"(?<!\w)"+re.escape(alias)+r"(?!\w)",re.I)
            def replace_term(match,term_idx=idx):
                key=f"QZXTM{len(saved):04d}ZXQ"; saved[key]=TARGET_TERM[target][term_idx]; return key
            value=pat.sub(replace_term,value)
    return value,saved
def _one(text,source,target,automotive):
    original=str(text)
    if not original.strip(): return {"text":original,"detected_language":target if source=="auto" else source,"translated":False}
    detected=_detect(original) if source=="auto" else source
    if detected==target: return {"text":original,"detected_language":detected,"translated":False}
    protected,saved=_protect(original,target,automotive)
    translation=_get_translation(detected,target)
    translated=translation.translate(protected) if translation else protected
    for key,value in saved.items(): translated=translated.replace(key,value)
    return {"text":translated,"detected_language":detected,"translated":True}
def translate_texts(texts:list[str],source:str,target:str,domain:str="general")->list[dict[str,Any]]:
    if target not in LANGUAGE_NAMES: raise ValueError(f"Unsupported target language: {target}")
    if source!="auto" and source not in LANGUAGE_NAMES: raise ValueError(f"Unsupported source language: {source}")
    if domain not in {"general","automotive"}: raise ValueError("Unsupported translation domain.")
    return [_one(str(text),source,target,domain=="automotive") for text in texts]
def language_catalog()->dict[str,Any]:
    try:
        packages=_available_packages()
        codes=sorted({p.from_code for p in packages}|{p.to_code for p in packages}|SUPPORTED_CORE)
        status="ok"
    except Exception:
        codes=sorted(LANGUAGE_NAMES); status="package_index_unavailable"
    return {"engine":"argos_translate","mode":"self_hosted_open_source","core_languages":[{"code":c,"name":LANGUAGE_NAMES[c]} for c in sorted(SUPPORTED_CORE)],"available_model_languages":[{"code":c,"name":LANGUAGE_NAMES.get(c,c)} for c in codes],"models_downloaded_on_first_use":True,"catalog_status":status}
