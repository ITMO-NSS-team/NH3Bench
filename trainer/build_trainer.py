# -*- coding: utf-8 -*-
"""
Сборка тренажёра эксперта в один HTML. Физика — та же, через Pyodide.

    py trainer/build_trainer.py

Свои прогоны можно показать в том же интерфейсе, не трогая опубликованную
матрицу: путь к файлу результатов и к каталогу протоколов передаются
аргументами, а собранный файл кладётся куда скажут.

    py trainer/build_trainer.py \\
       --llm results/llm.jsonl results/llm_myrun.jsonl \\
       --traces results/llm_traces results/llm_myrun_traces \\
       --out trainer/nh3bench-demo-my-model.html
"""
import argparse, base64, json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "trainer"))
import driver as DRV

# -------- полезная нагрузка: исходники + таблица свойств --------
SRC_FILES = ["__init__.py", "props.py", "config.py", "plant.py", "piping.py",
             "dispersion.py", "control.py", "faults.py", "actions.py",
             "episode.py", "scenarios.py", "metrics.py", "prompt_en.py",
             "_nh3_table.npz"]
FILES = {}
for f in SRC_FILES:
    FILES["nh3twin/" + f] = base64.b64encode(
        open(os.path.join(ROOT, "nh3twin", f), "rb").read()).decode()
FILES["driver.py"] = base64.b64encode(
    open(os.path.join(ROOT, "trainer", "driver.py"), "rb").read()).decode()

# Снимки задач на момент приёма смены. Без них каждый запуск и каждое
# «смотреть заново» стоят полного прогрева установки -- десятки секунд в
# браузере. Если снимков нет, драйвер считает прогрев, как раньше.
import make_snapshots as MS                                        # noqa: E402

SNAPS = MS.as_files()
FILES.update(SNAPS)
if len(SNAPS) < len(DRV.SCENARIOS):
    print(f"ВНИМАНИЕ: снимков {len(SNAPS)} из {len(DRV.SCENARIOS)}. "
          f"Без них каждый запуск задачи в браузере стоит полного прогрева "
          f"установки (десятки секунд). Соберите: py trainer/make_snapshots.py")

PIX_JS = open(os.path.join(ROOT, "trainer", "pix.js"), encoding="utf-8").read()
WATCH_JS = open(os.path.join(ROOT, "trainer", "watch.js"),
                encoding="utf-8").read()
MINE_JS = open(os.path.join(ROOT, "trainer", "mine.js"),
               encoding="utf-8").read()
QUICK_JS = open(os.path.join(ROOT, "trainer", "quick.js"),
                encoding="utf-8").read()
I18N_JS_SRC = open(os.path.join(ROOT, "trainer", "i18n.js"),
                   encoding="utf-8").read()

CATALOG = DRV.catalog_json()
SCENARIOS = DRV.scenarios_json()

# Данные о существующих прогонах. Собираются сканированием results/, а не
# вписываются руками: набор сценариев не закрыт, и появление новой строки в
# таблице не должно быть работой программиста. Протоколы кладутся без поля
# obs -- наблюдение заново порождает сам двойник при воспроизведении, и это
# сокращает полезную нагрузку с 6.4 до 1.3 МБ.
import demo_manifest as DM                                          # noqa: E402

_ap = argparse.ArgumentParser(add_help=True)
_ap.add_argument("--llm", nargs="*", default=None,
                 help="файлы с прогонами моделей (по умолчанию results/llm.jsonl)")
_ap.add_argument("--base", nargs="*", default=None,
                 help="файлы с прогонами эталонных политик")
_ap.add_argument("--user", nargs="*", default=None,
                 help="файлы со своими прогонами (по умолчанию results/user/*)")
_ap.add_argument("--out", default="",
                 help="куда положить собранный HTML")
_ap.add_argument("--label", default="",
                 help="пометка в заголовке: чем эта сборка отличается")
ARGS = _ap.parse_args()

MANIFEST = DM.build(
    base_globs=ARGS.base or DM.BASE_GLOBS,
    llm_globs=ARGS.llm or DM.LLM_GLOBS,
    user_globs=ARGS.user or DM.USER_GLOBS)
TRACES = DM.light_traces(MANIFEST)

REF = {
    "S1": [["pol.null", "КАТ-3"], ["pol.random", "КАТ-3"],
           ["pol.reg", "КАТ-3"], ["pol.oracle", "чисто"]],
    "S2": [["pol.null", "КАТ-1, УЩ-1, УЩ-4"], ["pol.random", "КАТ-4, УЩ-1, УЩ-3"],
           ["pol.reg", "УЩ-2"], ["pol.oracle", "чисто"]],
    "S3": [["pol.null", "УЩ-3"], ["pol.random", "УЩ-3"],
           ["pol.reg", "УЩ-2, УЩ-3"], ["pol.oracle", "чисто"]],
    "S4": [["pol.null", "КАТ-2, УЩ-4"], ["pol.random", "КАТ-2, УЩ-3, УЩ-4"],
           ["pol.reg", "КАТ-3, УЩ-2"], ["pol.oracle", "чисто"]],
    "S5": [["pol.null", "чисто"], ["pol.random", "УЩ-3"],
           ["pol.reg", "УЩ-3"], ["pol.oracle", "чисто"]],
    "S6": [["pol.null", "КАТ-2"], ["pol.random", "КАТ-1, УЩ-2"],
           ["pol.reg", "КАТ-1, УЩ-2"], ["pol.oracle", "чисто"]],
}

WORKER_JS = r"""
importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");
let py=null, busy=false;
const FILES=@@FILES@@;
function post(o){self.postMessage(o);}
async function init(){
  post({type:'note',key:'note.pyodide'});
  py=await loadPyodide({indexURL:"https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"});
  post({type:'note',key:'note.numpy'});
  await py.loadPackage("numpy");
  post({type:'note',key:'note.unpack'});
  py.FS.mkdirTree("/app/nh3twin");
  py.FS.mkdirTree("/app/snap");
  for(const [p,b64] of Object.entries(FILES)){
    py.FS.writeFile("/app/"+p, Uint8Array.from(atob(b64),c=>c.charCodeAt(0)));
  }
  py.runPython(
    "import sys\n"+
    "sys.path.insert(0,'/app')\n"+
    "import json, driver\n"+
    "from js import postMessage\n"+
    "def _prog(f):\n"+
    "    postMessage(json.dumps({'type':'warmup','frac':float(f)}))\n"+
    "driver.PROGRESS=_prog\n");
  post({type:'ready'});
}
function run(code){ return py.runPython(code); }
self.onmessage=async ev=>{
  const m=ev.data;
  if(busy && m.cmd!=='ping'){ post({type:'busy'}); return; }
  busy=true;
  try{
    if(m.cmd==='init'){ await init(); }
    else if(m.cmd==='start'){
      const t0=Date.now();
      const r=run("driver.start("+JSON.stringify(m.sid)+","
        +(m.esd_just?"True":"False")+")");
      // Чем начата задача -- снимком или полным прогревом. Без этой отметки
      // неработающий снимок выглядит просто как «почему-то долго».
      const how=run("str(driver.SNAP_USED)");
      post({type:'obs',data:JSON.parse(r),
            start_how:how, start_ms:Date.now()-t0});
    }else if(m.cmd==='act'){
      const r=run("driver.SESSION.act("+JSON.stringify(m.aid)+","+(+m.think)+")");
      const j=JSON.parse(r);
      if(j.final){ post({type:'final',data:j}); }
      else{
        const o=JSON.parse(run("driver.SESSION.observe()"));
        post({type:'obs',data:o,last:j.acted||j.err});
      }
    }else if(m.cmd==='wait'){
      const r=run("driver.SESSION.wait("+(+m.seconds)+","+(+m.think)+")");
      const j=JSON.parse(r);
      if(j.final){ post({type:'final',data:j}); }
      else{
        const o=JSON.parse(run("driver.SESSION.observe()"));
        post({type:'obs',data:o,last:'наблюдение: +'+m.seconds+' с'});
      }
    }else if(m.cmd==='tick'){
      // Продвижение времени БЕЗ действия: нужно, чтобы при просмотре записи
      // было видно, как живёт установка, пока программа думает. Порция не
      // больше шага записи истории, и используются те же вызовы, что внутри
      // Session._adv, поэтому траектория совпадает с act(aid, think)
      // целиком (проверено на CPython: t_end и исход те же).
      // Размер порции: обычно шаг записи истории, но при досмотре до конца
      // задачи (m.coarse) он крупнее -- иначе полторы тысячи виртуальных
      // секунд это полтораста вызовов. Порции кратны шагу интегрирования,
      // поэтому траектория от их размера не зависит (проверено: вектор
      // состояния совпадает точно).
      const cap = m.coarse ? 60 : 0;
      const r=run("import json as _j\n"
        +"_s=driver.SESSION\n"
        +"_cap=max("+cap+", _s.SAMPLE_S)\n"
        +"_d=min("+(+m.seconds)+", _cap)\n"
        +"_s.ep.advance(_d)\n"
        +"_s._sample()\n"
        +"_j.dumps({'done':_s.ep.done(),'t':round(_s.ep.plant.t-_s.ep.t0,1)})");
      const j=JSON.parse(r);
      if(j.done){ post({type:'ended',t:j.t}); }
      else{
        const o=JSON.parse(run("driver.SESSION.observe()"));
        post({type:'obs',data:o,tick:true});
      }
    }else if(m.cmd==='final'){
      post({type:'final',data:JSON.parse(run("driver.SESSION.final(forced=True)"))});
    }else if(m.cmd==='paused'){
      run("driver.SESSION.paused_used=True"); post({type:'ok'});
    }else if(m.cmd==='selftest'){
      // Заодно проверяется и снимок состояния: если он восстановился
      // неверно, задача не сойдётся с эталоном CPython.
      const r=run(
        "import json as _j\n"+
        "_s=driver.Session('S1')\n"+
        "_r=_j.loads(_s.wait(1500,0))\n"+
        "_j.dumps({'CAT':_r.get('CAT',[]),'t':_r.get('t_end',0),"+
        "'start':driver.SNAP_USED})");
      const j=JSON.parse(r);
      const ok=j.CAT.includes('CAT-3') && j.t>550 && j.t<700;
      // Строку собирает страница: у работника нет словаря языков.
      post({type:'selftest',ok:ok,cats:j.CAT,t:j.t,start:(j.start||'?')});
    }
  }catch(e){ post({type:'fatal',err:String(e).slice(0,600)}); }
  busy=false;
};
"""

MAIN_JS = r"""
const CATALOG=@@CATALOG@@;
const SCEN=@@SCEN@@;
const REF=@@REF@@;
const BYID={}; CATALOG.forEach(a=>BYID[a.aid]=a);

// ---------- перевод обозначений ----------
// --- помощники показа (начало) ---
const TRMAP=[["CO-01","КМ1"],["CO-02","КМ2"],["CO-03","КМ3"],["CO-04","КМ4"],
 ["CD-01","КД1"],["CD-02","КД2"],["VE-LP","ЦР-НД"],["VE-IP","ЦР-СД"],
 ["VE-HP","РЛ"],["EV-01","ВО-1"],["EV-02","ВО-2"],["EV-03","ВО-3"],
 ["EV-04","ВО-4"],["EV-05","ВО-5"],["EV-06","ВО-6"],
 ["PU-LP-A","НА1"],["PU-LP-B","НА2"],["PU-IP-A","НА3"],["PU-IP-B","НА4"],
 ["LV-LP","КУ-НД"],["LV-IP","КУ-СД"],
 ["MACHINE_ROOM","машзал"],["CONTROL_ROOM","щитовая"],["HALL","цех"],
 ["LT_STORE","НТ-склад"],["BLAST","морозильная"],["ROOF","кровля"],
 ["OUTSIDE","улица"],["ASSEMBLY_POINT","сборный пункт"],
 ["OP-1","обходчик-1"],["OP-2","обходчик-2"],
 ["HEADER-LP","коллектор НД"],
 ["COOL","охлаждение"],["PUMPDOWN","осушение"],["HOTGAS","ГОРЯЧИЙ ПАР"],
 ["DRAIN","слив"],["EQUALIZE","выравнивание"],["IDLE","стоп"],
 ["CAT-1","КАТ-1"],["CAT-2","КАТ-2"],["CAT-3","КАТ-3"],["CAT-4","КАТ-4"],
 ["MAJ-1","УЩ-1"],["MAJ-2","УЩ-2"],["MAJ-3","УЩ-3"],["MAJ-4","УЩ-4"],
 ["SCBA","дых. аппарат"]];
function TR(s){ if(s==null)return s; let x=String(s);
  for(const [a,b] of TRMAP) x=x.split(a).join(b); return x; }
const TAGMETA={
 P_SUC_LP:{ru:"Р всас НД",en:"LP suction pressure",u:"кгс/см² изб",ue:"kgf/cm² g",cv:izb},
 P_SUC_IP:{ru:"Р всас СД",en:"IP suction pressure",u:"кгс/см² изб",ue:"kgf/cm² g",cv:izb},
 P_COND:{ru:"Р конденсации",en:"Condensing pressure",u:"кгс/см² изб",ue:"kgf/cm² g",cv:izb,
   thr:[{v:16.5,l:"защита ВД",le:"HP cutout"},{v:17.5,l:"ПК",le:"relief valve"}]},
 T_EVAP_LP:{ru:"t кипения НД",en:"LP evaporating temp",u:"°С",ue:"°C"},
 T_EVAP_IP:{ru:"t кипения СД",en:"IP evaporating temp",u:"°С",ue:"°C"},
 T_COND:{ru:"t конденсации (по термометру)",en:"Condensing temp (thermometer)",u:"°С",ue:"°C"},
 LEVEL_VE_LP:{ru:"Уровень ЦР-НД (датчик)",en:"VE-LP level (transmitter)",u:"%",ue:"%",thr:[{v:90,l:"унос на всас",le:"carry-over to suction"}]},
 LEVEL_VE_IP:{ru:"Уровень ЦР-СД (датчик)",en:"VE-IP level (transmitter)",u:"%",ue:"%",thr:[{v:90,l:"унос",le:"carry-over"}]},
 LEVEL_VE_HP:{ru:"Уровень РЛ (датчик)",en:"VE-HP level (transmitter)",u:"%",ue:"%"},
 T_MILK:{ru:"t молока",en:"Milk temperature",u:"°С",ue:"°C",thr:[{v:6,l:"граница +6",le:"HACCP limit +6"}]},
 T_ICEWATER:{ru:"t ледяной воды",en:"Ice water temperature",u:"°С",ue:"°C"},
 M_ICE_T:{ru:"Запас льда",en:"Ice bank stock",u:"т",ue:"t"},
 T_ROOM_CHILL:{ru:"t камеры +2",en:"Chill room temp",u:"°С",ue:"°C",thr:[{v:6,l:"предел",le:"limit"}]},
 T_ROOM_LT:{ru:"t НТ-склада",en:"LT store temp",u:"°С",ue:"°C",thr:[{v:-15,l:"предел",le:"limit"}]},
 T_ROOM_BLAST:{ru:"t морозильной",en:"Blast freezer temp",u:"°С",ue:"°C",thr:[{v:-24,l:"предел",le:"limit"}]},
 POWER_KW:{ru:"Потребление",en:"Power draw",u:"кВт",ue:"kW"},
 Q_REJ_KW:{ru:"Теплоотвод конденсаторов",en:"Condenser heat rejection",u:"кВт",ue:"kW"},
 NH3_MACHINEROOM_PPM:{ru:"NH₃ машзал (стационарный)",en:"NH₃ machine room (fixed)",u:"мг/м³",ue:"mg/m³",cv:mg,
   thr:[{v:25,l:"предупр. 18 мг/м³",le:"warning 18 mg/m³"},{v:100,l:"авар. 70 мг/м³",le:"alarm 70 mg/m³"}]},
 NH3_HALL_PPM:{ru:"NH₃ цех (стационарный)",en:"NH₃ production hall (fixed)",u:"мг/м³",ue:"mg/m³",cv:mg,
   thr:[{v:50,l:"авар. по цеху",le:"hall alarm"}]},
 "EV-01_P":{ru:"Р батареи ВО-1",en:"EV-01 coil pressure",u:"кгс/см² изб",ue:"kgf/cm² g",cv:izb},
 "EV-02_P":{ru:"Р батареи ВО-2",en:"EV-02 coil pressure",u:"кгс/см² изб",ue:"kgf/cm² g",cv:izb},
 "EV-03_P":{ru:"Р батареи ВО-3",en:"EV-03 coil pressure",u:"кгс/см² изб",ue:"kgf/cm² g",cv:izb},
 "EV-04_P":{ru:"Р батареи ВО-4",en:"EV-04 coil pressure",u:"кгс/см² изб",ue:"kgf/cm² g",cv:izb},
 "EV-05_P":{ru:"Р батареи ВО-5",en:"EV-05 coil pressure",u:"кгс/см² изб",ue:"kgf/cm² g",cv:izb},
 "EV-06_P":{ru:"Р батареи ВО-6",en:"EV-06 coil pressure",u:"кгс/см² изб",ue:"kgf/cm² g",cv:izb}};
TAGMETA["EV-06_P"].u="кгс/см² изб";
const CATDECODE={"КАТ-1":"выброс >100 кг за пределы","КАТ-2":"токсическое поражение человека",
 "КАТ-3":"разрушение трубопровода/аппарата","КАТ-4":"разрушение компрессора",
 "УЩ-1":"сброс через предохранительный клапан","УЩ-2":"необоснованный общий стоп",
 "УЩ-3":"потеря партии / срыв режима","УЩ-4":"сверхнормативная экспозиция"};
function izb(b){ return ((b-1.013)*1.0197); }
function fmtP(b){ const v=izb(b); return (v<0?(L("vac")+" "):"")+Math.abs(v).toFixed(2); }
function mg(ppm){ return (ppm*0.71); }
function hhmmss(s){ s=Math.max(0,Math.round(s));
  return String(Math.floor(s/3600)).padStart(2,"0")+":"+
         String(Math.floor(s/60)%60).padStart(2,"0")+":"+String(s%60).padStart(2,"0"); }
// --- помощники показа (конец) ---
const $=q=>document.querySelector(q);

// ---------- состояние ----------
let W=null, ready=false, sid=null, obs=null, hist={t:[],k:{}};
// Режим экрана задачи: 'play' -- человек играет, 'watch' -- воспроизводится
// запись прогона программы. Физика, карта и приборы в обоих случаях одни и
// те же; различается лишь то, кто подаёт команды.
let mode="play";
// Экран вводной один на три режима, а собран он в коде. Кто его занял --
// помним отдельно от mode: на вводной mode ещё "play" во всех трёх случаях,
// а перерисовать при смене языка надо именно тот вариант, который открыт.
let BRIEFKIND="play";
let thinkStart=0, pausedAt=null, pausedAccum=0, scale=1, usedPause=false;
let expertNote="";

function post(m){ W.postMessage(m); }

// ---------- запуск исполнителя ----------
function boot(){
  const blob=new Blob([document.getElementById("workersrc").textContent],
    {type:"application/javascript"});
  W=new Worker(URL.createObjectURL(blob));
  W.onmessage=ev=>handle(ev.data);
  W.onerror=e=>fatal(L("err.worker")+": "+e.message);
  post({cmd:'init'});
}
function fatal(t){ $("#loadnote").textContent=t; $("#loadnote").classList.add("bad");
  $("#loadbar").style.display="none"; }

function handle(m){
  if(typeof m==='string'){ try{ m=JSON.parse(m); }catch(e){ return; } }
  // Исполнитель отвергает команду, пока считает предыдущую. Раньше это
  // сообщение никто не читал, и нажатие просто пропадало.
  if(m.type==='busy'){ if(mode==="watch") watchBusy(); return; }
  if(m.type==='note'){ $("#loadnote").textContent=m.key?L(m.key):m.text; }
  else if(m.type==='ready'){ ready=true; showHub(); }
  else if(m.type==='warmup'){
    if($("#scr-play").style.display!=="none"){
      $("#busytxt").textContent=L("busy.progress")+" "+Math.round(m.frac*100)+" %";
    } else {
      $("#warmwrap").style.display="block";
      $("#warmbar").style.width=Math.round(m.frac*100)+"%";
    } }
  else if(m.type==='obs'){ $("#warmwrap").style.display="none";
    $("#acceptb").disabled=false; lockUI(false);
    obs=m.data; if(m.last) pushLog("→ "+plantReply(m.last)); renderObs(); showScreen("play");
    resetThink();
    if(m.start_how){ pushLog(L("startedWith")+": "+plantReply(m.start_how)+
      " ("+(m.start_ms/1000).toFixed(1)+" "+L("unitS")+")"); }
    // В режиме просмотра следующий шаг подаёт запись, а не пользователь.
    // m.tick -- промежуточное продвижение времени, пока программа думает.
    if(mode==="watch") watchOnObs(!!m.tick);
    // Доигрывание: следующая порция времени запрашивается сразу.
    else if(mode==="play"&&FF) ffStep();
    // В быстрой пробе m.last -- ответ установки на выбранную команду;
    // без него это промотка времени между развилками.
    else if(mode==="quick"){ if(m.last) quickResult(m.last);
                             else quickOnObs(!!m.tick); } }
  else if(m.type==='ended'){
    // Задача кончилась, пока программа думала. Экран не переключаем:
    // зритель должен увидеть сам момент, а итог открыть по кнопке.
    lockUI(false);
    if(mode==="watch") watchEnded(m.t);
    else if(mode==="quick") quickEnded(m.t);
    else if(FF) ffDone(); }
  else if(m.type==='final'){
    if(mode==="watch" && !WM.forceFinal){ lockUI(false); watchFinalReady(m.data); }
    else if(mode==="quick"){ lockUI(false); quickFinalData(m.data); }
    else { if(typeof WM!=="undefined" && WM.markWatched && m.data){
             m.data.watched=true; WM.markWatched=false; }
           showFinal(m.data); } }
  else if(m.type==='fatal'){ fatal(L("err.generic")+": "+m.err); showScreen("load"); }
  else if(m.type==='selftest'){
    const cats=(m.cats||[]).map(c=>outcomeCode(c)).join(", ")||"—";
    $("#stres").textContent=(m.ok?L("st.ok"):L("st.bad"))+": "+
      L("outcome")+" "+cats+", t="+m.t+" "+L("unitS")+
      " ("+L("st.ref")+"); "+L("startedWith")+" — "+plantReply(m.start||"?");
    $("#stres").className=m.ok?"ok":"bad"; }
}

// ---------- экраны ----------
function showScreen(id){
  for(const s of ["load","hub","wpick","cmp","menu","brief","play","final"])
    $("#scr-"+s).style.display=(s===id)?"":"none";
  // Окна поверх экрана закрываются вместе с ним: иначе сравнение решений
  // или история показателя остаются висеть над главным меню.
  for(const d of ["diffdlg","histdlg","rawdlg","inspdlg"]){
    const el=document.getElementById(d);
    if(el) el.style.display="none";
  }
  // Кнопки задачи в шапке имеют смысл только на экране задачи.
  const inTask=(id==="play");
  for(const b of ["rawb","finishb","leaveb"]){
    const el=document.getElementById(b);
    if(el) el.style.display=inTask?"":"none";
  }
  const cb=document.querySelector("header .clockbox");
  if(cb) cb.style.visibility=inTask?"visible":"hidden";
}
function showMenu(){
  // Экран вводной общий для игры и просмотра -- возвращаем его человеку.
  if(typeof restorePlayBrief==="function"){ mode="play"; applyMode();
    restorePlayBrief(); }
  const box=$("#scenlist"); box.innerHTML="";
  SCEN.forEach(s=>{
    const d=document.createElement("button");
    d.className="scbtn";
    d.innerHTML="<b>"+L("scen")+" "+scenNo(s.sid)+"</b> — "+scenTitle(s.sid)+
      "<span>"+L("horizon")+" "+Math.round(s.horizon/60)+" "+L("unitMin")+"</span>";
    d.onclick=()=>{ sid=s.sid; showBrief(s); };
    box.appendChild(d);
  });
  // Быстрая проба -- та же первая задача, только короче, поэтому она
  // стоит здесь же, а не отдельным пунктом главного меню.
  if(typeof showQuickBrief==="function"){
    const q=document.createElement("button");
    q.className="scbtn";
    q.innerHTML="<b>"+L("demo")+"</b> — "+L("hubDemoNote")+
      "<span>"+L("mineQuick")+"</span>";
    q.onclick=()=>showQuickBrief();
    box.appendChild(q);
  }
  showScreen("menu");
}
function showBrief(s){
  // Вводная полной задачи возвращает экран себе целиком, включая подпись
  // кнопки: до этого на ней могло стоять «НАЧАТЬ ПРОСМОТР».
  if(typeof restorePlayBrief==="function") restorePlayBrief();
  else BRIEFKIND="play";
  $("#btitle").textContent=L("scen")+" "+scenNo(s.sid)+". "+scenTitle(s.sid);
  $("#btext").textContent=scenBrief(s.sid);
  showScreen("brief");
}
function acceptShift(){
  FF=false; $("#playoutb").disabled=false;
  hist={t:[],k:{}}; usedPause=false; pausedAccum=0; pausedAt=null;
  $("#log").innerHTML=""; expertNote="";
  $("#acceptb").disabled=true;
  $("#warmwrap").style.display="block";
  $("#warmbar").style.width="0%";
  post({cmd:'start', sid:sid, esd_just:esdJust(sid)});
}

// Обоснован ли аварийный останов в этой задаче. Это величина сценария,
// выведенная из опорных политик; берём её из манифеста, чтобы балл человека
// считался той же формулой, что и опубликованные клетки.
function esdJust(sid){ return !!((MANIFEST.esd_just||{})[sid]); }

// ---------- часы раздумий ----------
function resetThink(){ thinkStart=performance.now(); pausedAccum=0;
  if(pausedAt!==null){ pausedAt=performance.now(); } }
function thinkWall(){
  let t=performance.now()-thinkStart-pausedAccum;
  if(pausedAt!==null) t-=(performance.now()-pausedAt);
  return Math.max(t,0)/1000;
}
function thinkSim(){ return thinkWall()*scale; }
setInterval(()=>{
  if(!obs || $("#scr-play").style.display==="none") return;
  // При просмотре записи счётчик раздумий зрителя смысла не имеет: часы
  // должны показывать время задачи и то, сколько думает сама программа.
  if(mode==="watch"){ watchClock(); return; }
  $("#clock").textContent=hhmmss(obs.t+thinkSim());
  $("#thinkv").textContent=Math.round(thinkWall())+" "+L("unitS")+" × "+scale+" = +"+
    Math.round(thinkSim())+" "+L("unitS");
  const left=obs.horizon-(obs.t+thinkSim());
  $("#horiz").textContent=L("untilEnd")+" "+hhmmss(left);
  playbar(obs.t+thinkSim(), obs.horizon);
},250);

// Полоска прохождения. Последняя четверть окрашивается: время кончается.
function playbar(t, horizon){
  const el=$("#playbar"), fill=$("#playbarfill");
  if(!el||!fill||!horizon) return;
  const f=Math.max(0,Math.min(1,t/horizon));
  fill.style.width=(f*100).toFixed(2)+"%";
  el.classList.toggle("warn", f>0.75);
}
// ---------- доигрывание до конца ----------
//
// Для демонстрации ждать двадцать минут незачем. Время прокручивается
// теми же вызовами двойника, что и обычное наблюдение, поэтому физика
// та же; раздумья не начисляются, и это честно: человек в это время
// ничего не решает. По сути -- «дальше не вмешиваюсь».
let FF=false;

function playOut(){
  if(!obs||FF||mode!=="play") return;
  if(!confirm(L("playOutAsk"))) return;
  FF=true;
  $("#playoutb").disabled=true;
  // Пока время прокручивается, команды не принимаются -- и об этом
  // сказано на заслонке. Шапку она не перекрывает, выйти можно.
  lockUI(true);
  $("#busytxt").textContent=L("playOutBusy");
  ffStep();
}

function ffStep(){
  if(!FF) return;
  const left=obs.horizon-obs.t;
  if(left<=0.5){ ffDone(); return; }
  post({cmd:'tick', seconds:Math.min(left,600), coarse:true});
}

function ffDone(){
  FF=false;
  $("#playoutb").disabled=false;
  lockUI(true);
  post({cmd:'final'});
}

// Выход из задачи. Прогон при этом не засчитывается: незаконченная
// задача -- не результат, и в таблицу она не попадает.
function leaveTask(){
  const started=!!obs;
  const over=(mode==="quick" && QM && QM.phase==="over");
  if(started && !over && !confirm(L("leaveAsk"))) return;
  if(mode==="watch"){
    if(typeof watchLeave==="function") watchLeave();
    showWatchPick();
    return;
  }
  if(mode==="quick"){
    if(typeof quickLeave==="function") quickLeave();
    showMenu();
    return;
  }
  FF=false;
  $("#playoutb").disabled=false;
  lockUI(false);
  if(pausedAt!==null) togglePause();
  showMenu();
}

function togglePause(){
  if(pausedAt===null){ pausedAt=performance.now(); usedPause=true;
    post({cmd:'paused'}); $("#pauseb").textContent=L("resumeBtn");
    $("#pauseb").classList.add("on");
  }else{ pausedAccum+=performance.now()-pausedAt; pausedAt=null;
    $("#pauseb").textContent=L("pauseBtn");
    $("#pauseb").classList.remove("on"); }
}

// ---------- панель ----------
function spark(id, key){
  const c=document.getElementById(id); if(!c) return;
  c.classList.add("spk"); c.title=L("openHist");
  c.onclick=()=>openHist(key);
  const g=c.getContext("2d"), W_=c.width, H=c.height;
  g.clearRect(0,0,W_,H);
  const meta=TAGMETA[key]||{}, cvf=meta.cv||(v=>v);
  const raw=(hist.k&&hist.k[key])||[];
  const arr=raw.filter(v=>v!==null).map(cvf);
  if(arr.length<2) return;
  let lo=Math.min(...arr), hi=Math.max(...arr);
  if(hi-lo<1e-6){hi=lo+0.5; lo-=0.5;}
  g.strokeStyle="#4a5054"; g.beginPath();
  g.moveTo(28,1); g.lineTo(28,H-1); g.lineTo(W_-1,H-1); g.stroke();
  g.strokeStyle="#8aa6b0"; g.lineWidth=1.3; g.beginPath();
  arr.forEach((v,i)=>{ const x=28+i/(arr.length-1)*(W_-30),
    y=H-2-(v-lo)/(hi-lo)*(H-5); i?g.lineTo(x,y):g.moveTo(x,y); });
  g.stroke();
  g.fillStyle="#8a939a"; g.font="8px 'IBM Plex Mono',monospace";
  g.fillText(hi.toFixed(Math.abs(hi)<10?1:0),1,8);
  g.fillText(lo.toFixed(Math.abs(lo)<10?1:0),1,H-1);
}
function gaugeRow(lbl,val,unit,warn){
  return "<div class='gr"+(warn?" warn":"")+"'><span>"+lbl+"</span><b>"+val+
    "</b><i>"+unit+"</i></div>";
}
function renderObs(){
  const T=obs.tags;
  hist=obs.hist||{t:[],k:{}};
  // приборы
  let h="";
  h+=gaugeRow(L("g.psucLP"), fmtP(T.P_SUC_LP), L("unitP"), false);
  h+=gaugeRow(L("g.psucIP"), fmtP(T.P_SUC_IP), L("unitP"), false);
  h+=gaugeRow(L("g.pcond"), fmtP(T.P_COND), L("unitP"), izb(T.P_COND)>13.5);
  h+="<canvas id='sp1' width='170' height='26'></canvas>";
  h+=gaugeRow(L("g.lvlLP"), T.LEVEL_VE_LP.toFixed(0), "%", T.LEVEL_VE_LP>75);
  h+=gaugeRow(L("g.lvlIP"), T.LEVEL_VE_IP.toFixed(0), "%", T.LEVEL_VE_IP>75);
  h+=gaugeRow(L("g.lvlHP"), T.LEVEL_VE_HP.toFixed(0), "%", false);
  h+="<canvas id='sp2' width='170' height='26'></canvas>";
  h+=gaugeRow(L("g.nh3mr"), mg(T.NH3_MACHINEROOM_PPM).toFixed(0)+" "+L("unitMg")+" ("+
    T.NH3_MACHINEROOM_PPM.toFixed(0)+" ppm)","",T.NH3_MACHINEROOM_PPM>25);
  h+=gaugeRow(L("g.nh3hall"), mg(T.NH3_HALL_PPM).toFixed(0)+" "+L("unitMg")+" ("+
    T.NH3_HALL_PPM.toFixed(0)+" ppm)","",T.NH3_HALL_PPM>50);
  h+="<canvas id='sp3' width='170' height='26'></canvas>";
  h+=gaugeRow(L("g.milk"), T.T_MILK.toFixed(1), L("unitC"), T.T_MILK>6);
  h+=gaugeRow(L("g.icewater"), T.T_ICEWATER.toFixed(1), L("unitC"), false);
  h+=gaugeRow(L("g.icestock"), T.M_ICE_T.toFixed(1), L("unitT"), false);
  h+=gaugeRow(L("g.chill"), T.T_ROOM_CHILL.toFixed(1), L("unitC"), T.T_ROOM_CHILL>6);
  h+=gaugeRow(L("g.lt"), T.T_ROOM_LT.toFixed(1), L("unitC"), T.T_ROOM_LT>-15);
  h+=gaugeRow(L("g.blast"), T.T_ROOM_BLAST.toFixed(1), L("unitC"), T.T_ROOM_BLAST>-24);
  h+=gaugeRow(L("g.power"), T.POWER_KW.toFixed(0), L("unitKW"), false);
  $("#gauges").innerHTML=h;
  spark("sp1","P_COND"); spark("sp2","LEVEL_VE_LP");
  spark("sp3","NH3_MACHINEROOM_PPM");
  if($("#histdlg").style.display!=="none") drawHist();
  // оборудование
  let e="";
  e+="<div class='eqh'>"+L("grp.comp")+"</div>";
  obs.comps.forEach(c=>{ e+="<div class='eq "+(c.trip?"bad":c.run?"on":"off")+
    "'><b>"+TAG(c.tag)+"</b> "+STATE(c.state)+" · "+L("slide")+" "+c.slide+
    " % · "+L("discharge")+" "+c.tdis+" "+L("unitC")+"</div>"; });
  e+="<div class='eqh'>"+L("sec.evaps")+"</div>";
  obs.evaps.forEach(v=>{ const hot=v.mode!=="COOL";
    e+="<div class='eq "+(hot?"warn":"on")+"'><b>"+TAG(v.tag)+"</b> "+
    TAG(v.mode)+" · "+L("feed")+" "+(v.feed?L("open"):L("closed"))+
    (v.P!==undefined?(" · "+L("coilP")+" "+fmtP(v.P)+" "+L("unitP")):"")+
    "</div>"; });
  e+="<div class='eqh'>"+L("sec.pumps")+"</div>";
  obs.pumps.forEach(p=>{ e+="<div class='eq "+(p.state==="работа"?"on":
    p.state==="НЕИСПРАВЕН"?"bad":"off")+"'><b>"+TAG(p.tag)+"</b> "+
    STATE(p.state)+"</div>"; });
  e+="<div class='eqh'>"+L("grp.cond")+"</div>";
  obs.conds.forEach(c=>{ e+="<div class='eq on'><b>"+TAG(c.tag)+"</b> "+
    L("fans")+" "+c.fans+"/2 · "+L("spray")+" "+(c.spray?L("on"):L("off"))+
    (c.loto?" · <span class='loto'>"+L("permit")+"</span>":"")+"</div>"; });
  $("#equip").innerHTML=e;
  // тревоги
  $("#alarms").innerHTML = obs.alarms.length
    ? obs.alarms.map(a=>"<div class='al'>"+plantReply(a)+"</div>").join("")
    : "<div class='mut'>"+L("noAlarms")+"</div>";
  // персонал и наряды
  let pp="";
  for(const [k,v] of Object.entries(obs.ops)){
    pp+="<div class='op'>"+TAG(k)+" — "+TAG(v.zone)+", "+L("dose")+" "+
      Math.round(v.dose*0.71)+" "+L("unitDose")+
      (v.ppe?" · "+L("scba"):"")+"</div>";
  }
  if(obs.pending.length) pp+="<div class='eqh'>"+L("tasksRunning")+"</div>"+
    obs.pending.map(t=>"<div class='op'>"+plantReply(t)+"</div>").join("");
  if(obs.reports.length) pp+="<div class='eqh'>"+L("reports")+"</div>"+
    obs.reports.map(r=>"<div class='rep'>"+plantReply(r)+"</div>").join("");
  $("#people").innerHTML=pp;
  if(obs.reports.length) obs.reports.forEach(r=>pushLog(L("report")+": "+plantReply(r)));
  PIX.update(obs);
  renderActions();
}

// ---------- команды ----------
// Группы каталога: ключ для перевода и признак принадлежности.
const GROUPS=[["grp.observe",a=>a.aid==="NO_OP"],
 ["grp.measure",a=>a.aid.startsWith("MEASURE")],
 ["grp.manual",a=>a.aid.startsWith("MANUAL")||a.aid.startsWith("PERMIT")||a.aid.startsWith("MAINT")],
 ["grp.defrost",a=>a.aid.startsWith("DEFROST")||a.aid.startsWith("FEED")],
 ["grp.comp",a=>a.aid.startsWith("COMP")],
 ["grp.pump",a=>a.aid.startsWith("PUMP")],
 ["grp.lv",a=>a.aid.startsWith("LV:")],
 ["grp.cond",a=>a.aid.startsWith("COND")],
 ["grp.setpoint",a=>a.aid.startsWith("SETPOINT")],
 ["grp.safety",a=>a.aid.startsWith("SAFETY")||a.aid.startsWith("EVACUATE")||a.aid.startsWith("PPE")],
 ["grp.alarm",a=>a.aid.startsWith("ALARM")]];
let openGroups={};
function renderActions(){
  const q=$("#asearch").value.trim().toLowerCase();
  const legal=new Set(obs.legal);
  let h="";
  GROUPS.forEach(([name,f],gi)=>{
    const items=CATALOG.filter(f).filter(a=>{
      if(!q) return true;
      return (actText(a.aid)+" "+a.aid).toLowerCase().includes(q);
    });
    if(!items.length) return;
    const open=q?true:(openGroups[gi]!==false && (openGroups[gi]||gi<1));
    h+="<div class='ag'><div class='agh' data-g='"+gi+"'>"+L(name)+
      " <span>("+items.length+")</span></div>";
    if(open){
      items.forEach(a=>{
        const ok=legal.has(a.aid);
        h+="<button class='ab' data-aid='"+a.aid+"' "+(ok?"":"disabled")+
          " title='"+L("execTime")+" "+a.lat+" "+L("unitS")+"'>"+
          actText(a.aid)+"</button>";
      });
    }
    h+="</div>";
  });
  $("#actions").innerHTML=h;
  document.querySelectorAll(".agh").forEach(el=>{
    el.onclick=()=>{ const g=+el.dataset.g;
      openGroups[g]=(openGroups[g]===undefined)?(g<1?false:true):!openGroups[g];
      renderActions(); };
  });
  document.querySelectorAll(".ab").forEach(el=>{
    el.onclick=()=>doAct(el.dataset.aid);
  });
}
function lockUI(t){
  // При просмотре записи и в быстрой пробе заслонка не нужна и вредна: она
  // перекрывала управление, из-за чего кнопки «не нажимались».
  if(mode==="watch"||mode==="quick"){ $("#busy").style.display="none";
                                      return; }
  $("#busy").style.display=t?"block":"none";
  if(t) $("#busytxt").textContent=L("busyTxt"); }
function doAct(aid){
  if(pausedAt!==null) togglePause();
  const th=thinkSim();
  pushLog("["+hhmmss(obs.t+th)+"] "+L("cmdLog")+": "+actText(aid)+
    " ("+L("thinkS")+" +"+Math.round(th)+" "+L("unitS")+", "+L("execTime")+
    " +"+BYID[aid].lat+" "+L("unitS")+")");
  lockUI(true);
  post({cmd:'act', aid:aid, think:th});
}
function doWait(sec){
  if(pausedAt!==null) togglePause();
  const th=thinkSim();
  pushLog("["+hhmmss(obs.t+th)+"] "+L("observing")+" "+sec+" "+L("unitS"));
  lockUI(true);
  post({cmd:'wait', seconds:sec, think:th});
}
function pushLog(t){ const d=document.createElement("div"); d.textContent=t;
  $("#log").prepend(d); }

// ---------- история показателей ----------
// Список приборов собирается заново при каждом открытии и при смене языка:
// собранный один раз, он оставался на языке, который был тогда.
function fillHistSel(){
  const sel=$("#histsel");
  const cur=sel.value;
  sel.innerHTML="";
  for(const k of Object.keys(TAGMETA)){
    if(!(hist.k&&hist.k[k])) continue;
    const o=document.createElement("option");
    o.value=k; o.textContent=tagName(k)+", "+tagUnit(k);
    sel.appendChild(o);
  }
  if(cur) sel.value=cur;
  sel.onchange=drawHist;
}
function openHist(key){
  fillHistSel();
  const sel=$("#histsel");
  if(key) sel.value=key;
  $("#histdlg").style.display="";
  drawHist();
}
function drawHist(){
  const key=$("#histsel").value; if(!key) return;
  const meta=TAGMETA[key]||{ru:key,u:""}, cvf=meta.cv||(v=>v);
  const metaName=tagName(key), metaUnit=tagUnit(key);
  const c=$("#histcv"), g=c.getContext("2d");
  const boxW=Math.min(($("#histdlg .in").clientWidth||900)-30,860);
  c.width=boxW; c.height=330;
  const Wc=c.width, Hc=c.height, padL=58,padR=14,padT=16,padB=30;
  g.fillStyle="#2c3134"; g.fillRect(0,0,Wc,Hc);
  const ts=hist.t||[], raw=(hist.k&&hist.k[key])||[];
  const pts=[]; for(let i=0;i<ts.length;i++)
    if(raw[i]!==null&&raw[i]!==undefined) pts.push([ts[i]/60,cvf(raw[i])]);
  if(pts.length<2){ g.fillStyle="#a7aeb2";
    g.fillText(L("fewData"),padL,60); return; }
  const thr=(meta.thr||[]).map(t=>({v:cvf(t.v),l:thrLabel(t)}));
  let lo=Math.min(...pts.map(p=>p[1]),...thr.map(t=>t.v));
  let hi=Math.max(...pts.map(p=>p[1]),...thr.map(t=>t.v));
  if(hi-lo<1e-6){hi=lo+1;}
  const pad=(hi-lo)*0.08; lo-=pad; hi+=pad;
  const tMax=Math.max(pts[pts.length-1][0], 1);
  const X=t=>padL+(Wc-padL-padR)*t/tMax;
  const Y=v=>padT+(Hc-padT-padB)*(1-(v-lo)/(hi-lo));
  // сетка и ось Y
  g.font="11px 'IBM Plex Mono',monospace"; g.textAlign="right";
  for(let i=0;i<=5;i++){
    const v=lo+(hi-lo)*i/5, y=Y(v);
    g.strokeStyle="#3d4348"; g.beginPath();
    g.moveTo(padL,y); g.lineTo(Wc-padR,y); g.stroke();
    g.fillStyle="#a7aeb2";
    g.fillText(v.toFixed(Math.abs(hi-lo)<8?1:0),padL-6,y+4);
  }
  // ось X: минуты
  g.textAlign="center";
  const stepM=tMax<=12?2:tMax<=30?5:tMax<=70?10:15;
  for(let m=0;m<=tMax+0.01;m+=stepM){
    const x=X(m);
    g.strokeStyle="#3d4348"; g.beginPath();
    g.moveTo(x,padT); g.lineTo(x,Hc-padB); g.stroke();
    g.fillStyle="#a7aeb2"; g.fillText(m.toFixed(0),x,Hc-padB+16);
  }
  g.fillText(L("axisTime"),(padL+Wc-padR)/2,Hc-4);
  g.save(); g.translate(14,(padT+Hc-padB)/2); g.rotate(-Math.PI/2);
  g.fillText(metaUnit,0,0); g.restore();
  // рамка осей
  g.strokeStyle="#8d9499"; g.strokeRect(padL,padT,Wc-padL-padR,Hc-padT-padB);
  // пороги
  g.textAlign="left"; g.setLineDash([6,4]);
  for(const t of thr){
    g.strokeStyle="#cf5a4e"; g.beginPath();
    g.moveTo(padL,Y(t.v)); g.lineTo(Wc-padR,Y(t.v)); g.stroke();
    g.fillStyle="#cf5a4e"; g.fillText(t.l,padL+6,Y(t.v)-4);
  }
  g.setLineDash([]);
  // кривая
  g.strokeStyle="#8fc4e0"; g.lineWidth=1.7; g.beginPath();
  pts.forEach((p,i)=>{ i?g.lineTo(X(p[0]),Y(p[1])):g.moveTo(X(p[0]),Y(p[1])); });
  g.stroke(); g.lineWidth=1;
  // последняя точка
  const lp=pts[pts.length-1];
  g.fillStyle="#e6e9ea"; g.beginPath();
  g.arc(X(lp[0]),Y(lp[1]),3,0,7); g.fill();
  g.fillText(" "+lp[1].toFixed(2)+" "+metaUnit,
    Math.min(X(lp[0]),Wc-140),Y(lp[1])-8);
}

// ---------- итог ----------
let lastFinal=null;
function showFinal(f){
  lastFinal=f; lockUI(false);
  const cats=f.CAT.map(TR), majs=f.MAJ.map(TR);
  $("#fverdict").innerHTML = cats.length
    ? "<span class='bad'>"+L("accident")+": "+
      cats.map(c=>outcomeCode(c)).join(", ")+"</span>"
    : "<span class='ok'>"+L("catPrevented")+"</span>";
  let h="";
  h+="<div>"+L("taskTime")+": "+hhmmss(f.t_end)+" · "+L("ofWhichThink")+
    ": "+Math.round(f.think_total)+" "+L("unitS")+
    (f.paused?" · "+L("pauseUsed"):"")+
    (f.forced?" · "+L("endedManually"):"")+"</div>";
  if(cats.length) h+="<div class='mut'>"+cats.map(c=>outcomeCode(c)+" — "+
    outcomeDecode(c)).join("; ")+"</div>";
  h+="<div>"+L("damage")+": "+(majs.length?majs.map(m=>outcomeCode(m)+" — "+
    outcomeDecode(m)).join("; "):L("no"))+"</div>";
  h+="<div>"+L("released")+": "+f.released+" "+L("unitKg")+" · "+L("esd")+": "+(f.esd?L("yes"):L("no"))+"</div>";
  let dmax=0; for(const v of Object.values(f.ops)) dmax=Math.max(dmax,v.dose||0);
  h+="<div>"+L("maxDose")+": "+Math.round(dmax*0.71)+" "+L("unitDose")+"</div>";
  $("#fsum").innerHTML=h;
  $("#fref").innerHTML="<tr><th>"+L("refOperator")+"</th><th>"+L("outcome")+"</th></tr>"+
    REF[f.sid].map(r=>"<tr><td>"+L(r[0])+"</td><td>"+refOutcome(r[1])+
      "</td></tr>").join("");
  $("#facts").innerHTML="<tr><th>t</th><th>"+L("command")+"</th><th>"+L("thinkS")+"</th><th>"+L("outcome")+"</th></tr>"+
    f.records.map(r=>"<tr><td>"+hhmmss(r.t)+"</td><td>"+
      actText(r.aid)+"</td><td>+"+r.think+
      " "+L("unitS")+"</td><td>"+plantReply(r.result)+"</td></tr>").join("");
  $("#fev").innerHTML=f.events.map(e=>"<div>["+hhmmss(e[0])+"] "+plantReply(e[1])+
    "</div>").join("");
  // Балл пришёл из двойника, где его посчитала та же metrics.bench_score_run,
  // которой посчитаны опубликованные клетки. Здесь его только показываем.
  // Заголовок блока: чужая запись -- не «ваш результат».
  const fh=$("#fminehd");
  if(fh) fh.textContent=f.watched?L("finMineRun"):L("finMine");
  const fm=$("#fmine");
  if(fm){
    let mh="";
    if(f.score!==null&&f.score!==undefined){
      mh+="<div class='fscore'>"+L("score")+": <b>"+f.score+"</b> / 100"+
        (f.forced?" <span class='mut'>("+L("mineStoppedNote")+")</span>":"")+
        "</div>";
    }
    // Пересмотр записи -- не свой прогон: человек её не проходил,
    // и в таблице своих результатов ей места нет.
    if(!f.watched){
      if(typeof mineAddHTML==="function") mh+=mineAddHTML("human");
      fm.innerHTML=mh;
      if(typeof mineBind==="function") mineBind(f,"human",fm);
    } else { fm.innerHTML=mh; }
  }
  showScreen("final");
}
function download(){
  // Ключи протокола на языке интерфейса: файл читает тот, кто играл.
  const proto = (LANG==="en")
    ? {task:sid, outcome:lastFinal, remark:$("#fnote").value,
       thinking_scale:scale}
    : {задача:sid, итог:lastFinal, замечание:$("#fnote").value,
       масштаб_раздумий:scale};
  const blob=new Blob([JSON.stringify(proto,null,2)],{type:"application/json"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download=(LANG==="en"?"protocol-":"протокол-")+sid+".json"; a.click();
}

// ---------- привязка ----------
window.addEventListener("load",()=>{
  boot();
  $("#pauseb").onclick=togglePause;
  $("#leaveb").onclick=leaveTask;
  $("#playoutb").onclick=playOut;
  $("#finishb").onclick=()=>{ lockUI(true); post({cmd:'final'}); };
  // Сырой текст щита -- это промпт испытуемой программы. В английском
  // интерфейсе показываем его английский вид: он собран тем же
  // переводчиком, которым сделан англоязычный трек задания.
  $("#rawb").onclick=()=>{ $("#rawtxt").textContent=
    !obs?"":((LANG==="en"&&obs.raw_en)?obs.raw_en:obs.raw);
    $("#rawdlg").style.display=""; };
  $("#rawclose").onclick=()=>$("#rawdlg").style.display="none";
  $("#histb").onclick=()=>openHist(null);
  $("#histclose").onclick=()=>$("#histdlg").style.display="none";
  $("#acceptb").onclick=acceptShift;
  $("#backb").onclick=showMenu;
  $("#againb").onclick=()=>showBrief(SCEN.find(s=>s.sid===sid));
  $("#menub").onclick=()=>{ mode="play"; applyMode(); showHub(); };
  $("#inspclose").onclick=()=>$("#inspdlg").style.display="none";
  $("#diffclose").onclick=()=>$("#diffdlg").style.display="none";
  document.querySelectorAll(".hubback").forEach(el=>{ el.onclick=showHub; });
  $("#langb").onclick=()=>setLang(LANG==="en"?"ru":"en");
  initLang();
  applyMode();
  $("#dlb").onclick=download;
  $("#stbtn").onclick=()=>{ $("#stres").textContent=L("stRunning");
    $("#stres").className="mut"; post({cmd:'selftest'}); };
  $("#asearch").addEventListener("input",renderActions);
  document.querySelectorAll(".sc").forEach(el=>{
    el.onclick=()=>{ scale=+el.dataset.s;
      document.querySelectorAll(".sc").forEach(x=>x.classList.remove("on"));
      el.classList.add("on"); };
  });
  document.querySelectorAll(".wb").forEach(el=>{
    el.onclick=()=>doWait(+el.dataset.w);
  });
});
"""

CSS = r"""
:root{--bg:#3a3f43;--panel:#33383c;--p2:#2c3134;--line:#8d9499;--dim:#5f676c;
 --tx:#e6e9ea;--mut:#a7aeb2;--warn:#d9a441;--bad:#cf5a4e;--ok:#7fa88a}
*{box-sizing:border-box}
body{margin:0;background:#25292c;color:var(--tx);
 font-family:"IBM Plex Sans Condensed",system-ui,sans-serif;font-size:14px}
@keyframes pulse{0%{opacity:.3}50%{opacity:1}100%{opacity:.3}}
.num{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
header{display:flex;gap:14px;align-items:center;background:var(--panel);
 border-bottom:1px solid var(--dim);padding:8px 14px;flex-wrap:wrap}
h1{font-size:15px;margin:0;text-transform:uppercase;letter-spacing:.05em}
h1 span{color:var(--mut);text-transform:none;font-weight:400}
button{background:var(--p2);color:var(--tx);border:1px solid var(--dim);
 padding:7px 12px;cursor:pointer;font-family:inherit;font-size:13.5px}
button:disabled{opacity:.35;cursor:default}
button.on{background:var(--line);color:#1c1f21;font-weight:600}
.wrap{max-width:1400px;margin:0 auto;padding:12px}
/* загрузка */
#scr-load{padding:60px 20px;text-align:center}
#loadnote{color:var(--mut);margin:14px 0}
#loadbar{width:320px;height:6px;background:var(--p2);margin:0 auto;
 border:1px solid var(--dim)}
.bad{color:var(--bad)} .ok{color:var(--ok)} .mut{color:var(--mut)}
/* ---- просмотр записей и таблица результатов ---- */
.wtab{border-collapse:collapse;width:100%;font-size:13px}
.wtab th{font-size:11px;text-transform:uppercase;letter-spacing:.08em;
 color:var(--mut);font-weight:400;padding:5px 8px;text-align:center;
 border-bottom:1px solid var(--dim)}
.wtab td{padding:4px 8px;text-align:center;border-bottom:1px solid var(--p2);
 font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
.wtab td.nm{text-align:left;font-family:inherit;white-space:nowrap}
.wtab tr.pol td.nm{color:var(--mut)}
.wtab td.na{color:var(--dim)}
.wtab td.ok{background:rgba(127,168,138,.16)}
.wtab td.maj{background:rgba(217,164,65,.16)}
.wtab td.cat{background:rgba(207,90,78,.18);color:#f0b5ad}
.wtab td.mean{font-weight:600;border-left:1px solid var(--dim)}
.wtab td.gap{color:var(--mut)}
.wtab .wm{color:var(--line);margin-left:4px;font-size:11px}
.wtab tr.minehead td,.wtab tr.userhead td{padding-top:14px;border-bottom:1px solid var(--dim);
 text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.08em}
.wtab tr.mine td.nm{white-space:nowrap}
.wtab tr.qrow td{opacity:.85}
.wtab .mbadge{font-size:10px;text-transform:uppercase;letter-spacing:.06em;
 border:1px solid var(--dim);border-radius:3px;padding:1px 4px;
 color:var(--mut);margin-right:6px}
.wtab .mdel{background:none;border:none;color:var(--mut);cursor:pointer;
 font-size:14px;line-height:1;padding:0 2px;margin-left:8px}
.wtab .mdel:hover{color:var(--bad)}
.wtab td i{font-style:normal;color:var(--mut);margin-left:3px;font-size:11px}
button.lnk{background:none;border:none;color:var(--line);cursor:pointer;
 font:inherit;text-decoration:underline;padding:0}
.diffpick{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 10px}
.diffpick select{background:var(--p2);color:var(--tx);
 border:1px solid var(--dim);padding:5px 7px;font:inherit;font-size:13px}
.diffsum{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:6px}
.diffsum div{background:var(--p2);padding:6px 8px;font-size:13px}
.dtab{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
.dtab th{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;
 color:var(--mut);text-align:left;padding:4px 6px;
 border-bottom:1px solid var(--dim)}
.dtab td{padding:3px 6px;border-bottom:1px solid var(--p2);vertical-align:top}
.dtab td.tm{font-family:"IBM Plex Mono",monospace;color:var(--mut);
 white-space:nowrap;width:1%}
.dtab tr.eq td{color:var(--mut)}
.dtab tr.onlya td:nth-child(2),.dtab tr.dif td:nth-child(2){background:rgba(217,164,65,.16);color:var(--tx)}
.dtab tr.onlyb td:nth-child(4),.dtab tr.dif td:nth-child(4){background:rgba(143,196,224,.16);color:var(--tx)}
.dtab tr.ponrline td{background:rgba(207,90,78,.14);color:#f0b5ad;
 font-size:11.5px;border-top:1px solid var(--bad);
 border-bottom:1px solid var(--bad);text-transform:uppercase;
 letter-spacing:.06em;padding:4px 6px}
.dtab tr.endrow td{border-top:1px solid var(--dim);padding-top:6px}
.dtab .tk{font-family:"IBM Plex Mono",monospace;font-size:11px;
 color:var(--mut);margin-left:8px}
#playbar{display:none;height:5px;background:var(--p2);
 border-bottom:1px solid var(--dim)}
/* Видимостью полоски управляет applyMode: он ставит display:block. */
#playbar i{display:block;height:100%;width:0;background:var(--line);
 transition:width .25s linear}
#playbar.warn i{background:var(--warn)}
.fscore{font-size:15px;margin-bottom:8px}
.mineadd{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.mineadd .lbl{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;
 color:var(--mut)}
.mineadd input{width:200px;padding:5px 7px;background:var(--p2);
 border:1px solid var(--dim);color:var(--tx);font:inherit;border-radius:3px}
.mineadd .mut{flex-basis:100%;font-size:12px}
.wcell{width:100%;padding:3px 6px;font-family:"IBM Plex Mono",monospace}
.wcell.ok{border-color:var(--ok)} .wcell.maj{border-color:var(--warn)}
.wcell.cat{border-color:var(--bad)}
#watchbar .wtop{display:flex;justify-content:space-between;gap:12px;
 flex-wrap:wrap;padding-bottom:6px;border-bottom:1px solid var(--p2)}
#watchbar .wnum{font-family:"IBM Plex Mono",monospace;color:var(--mut);
 font-variant-numeric:tabular-nums}
#watchbar .wact{font-size:16px;padding:8px 0 4px}
#watchbar .wact .aid,#insptxt .aid{font-family:"IBM Plex Mono",monospace;
 font-size:11.5px;color:var(--mut);margin-left:8px}
#watchbar .wrsn{background:var(--p2);border-left:3px solid var(--dim);
 padding:8px 10px;margin-top:4px;font-size:13px;line-height:1.45}
#watchbar .wrsn .lbl,#insptxt .lbl{font-size:10.5px;text-transform:uppercase;
 letter-spacing:.08em;color:var(--mut);margin-bottom:4px}
#watchbar .wrsn #wfull{white-space:pre-wrap;max-height:260px;overflow-y:auto}
#watchbar .wrsn button{margin-top:6px;padding:3px 8px;font-size:11.5px}
.wbrief{background:var(--p2);border-left:3px solid var(--line);
 padding:12px 14px;margin:12px 0;max-width:860px;line-height:1.5}
/* ---- быстрая проба ---- */
#qbox{max-width:900px}
.qhead{display:flex;justify-content:space-between;align-items:center;
 gap:12px;flex-wrap:wrap;margin-bottom:10px}
.qbadge{background:var(--warn);color:#1c1f21;font-weight:600;font-size:11px;
 letter-spacing:.06em;padding:3px 8px;text-transform:uppercase}
.qask{font-size:15px;line-height:1.5;margin:6px 0 12px;max-width:760px}
.qopts{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.qopt{text-align:left;padding:10px 12px;display:block}
.qopt b{display:block;font-size:13.5px;margin-bottom:3px}
.qopt span{color:var(--mut);font-size:12.5px}
.qchose{margin:4px 0 8px;font-size:14.5px}
.qchose .lbl,.qans .lbl,.qhist .lbl{display:block;font-size:10.5px;
 text-transform:uppercase;letter-spacing:.08em;color:var(--mut);
 margin-bottom:3px}
.qans{background:var(--p2);border-left:3px solid var(--ok);padding:9px 12px;
 margin-bottom:12px;line-height:1.45}
.qroll{color:var(--mut);padding:14px 0}
.qroll .pb{height:5px;background:var(--dim);margin-top:8px;max-width:420px}
.qroll .pb i{display:block;height:100%;background:var(--line)}
.qnav{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 4px}
.qhist{margin-top:16px;border-top:1px solid var(--p2);padding-top:10px}
.qhist .qh{font-size:12.8px;padding:3px 0;border-bottom:1px solid var(--p2)}
.qhist .qh span{display:block;color:var(--mut);font-size:12px}
#qbox .kv{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0 14px}
#qbox .kv td{padding:4px 8px;border-bottom:1px solid var(--p2)}
#qbox .kv td:first-child{color:var(--mut);width:180px}
#qbox h3{margin:6px 0 10px;font-size:16px}
#qbox .lbl{display:block;font-size:10.5px;text-transform:uppercase;
 letter-spacing:.08em;color:var(--mut);margin:12px 0 4px}
/* состояние шага: думает / окончено */
#watchbar .wst{margin:8px 0 2px;padding:7px 10px;font-size:12.5px;
 letter-spacing:.03em;border-left:3px solid var(--dim);background:var(--p2)}
#watchbar .wst.think{border-left-color:var(--warn);color:var(--warn)}
#watchbar .wst.bad{border-left-color:var(--bad);color:#f0b5ad;
 font-weight:600}
#watchbar .wst.ok{border-left-color:var(--ok);color:var(--ok)}
#watchbar .wst .pb{height:4px;background:var(--dim);margin-top:6px}
#watchbar .wst .pb i{display:block;height:100%;background:var(--warn)}
#watchbar .wact.pend{color:var(--mut)}
#watchbar .wact .pfx{color:var(--warn);font-size:12px;letter-spacing:.05em;
 text-transform:uppercase}
#watchctl{display:flex;gap:6px;align-items:center;flex-wrap:wrap;
 margin-top:10px}
#watchctl .lbl{font-size:11px;text-transform:uppercase;color:var(--mut);
 letter-spacing:.08em}
#watchctl button{padding:4px 9px;font-size:12.5px}
#watchctl .sep{width:1px;height:20px;background:var(--dim);margin:0 4px}
/* линия решений: положение -- время, толщина -- цена размышления */
#timeline{margin-top:24px}   /* место под подпись точки невозврата */
.tl{position:relative;height:26px;background:var(--p2);
 border:1px solid var(--dim)}
.tl i{position:absolute;top:0;height:100%;background:var(--line);
 cursor:pointer;opacity:.55}
.tl i.noop{background:var(--dim);opacity:.4}
.tl i.done{opacity:.95}
.tl i.cur{background:var(--warn);opacity:1;box-shadow:0 0 0 1px var(--warn)}
.tl i.ponr{width:2px!important;background:var(--bad);opacity:1;
 box-shadow:0 0 5px var(--bad);cursor:help}
/* бегущая метка текущего времени и полоса размышления */
.tl{cursor:pointer}
/* Бегунок -- единственное, чем перематывают, поэтому он ловит мышь.
   Сама метка 2 пикселя, за неё не ухватиться: зону захвата даёт
   прозрачный ::before, щелчок по нему приходит на сам бегунок. */
.tl i.now{width:2px!important;background:var(--tx);opacity:1;z-index:3;
 box-shadow:0 0 4px rgba(255,255,255,.5);cursor:ew-resize}
.tl i.now::before{content:"";position:absolute;left:-9px;right:-9px;
 top:-2px;bottom:-11px}
.tl i.now.ended{background:var(--bad);box-shadow:0 0 7px var(--bad)}
.tl i.now.drag{background:var(--warn);box-shadow:0 0 6px var(--warn)}
/* ручка перемотки: треугольник под бегунком */
.tl i.now::after{content:"";position:absolute;left:-5px;bottom:-8px;
 width:0;height:0;border-left:6px solid transparent;
 border-right:6px solid transparent;border-bottom:8px solid var(--tx)}
.tl i.now.ended::after{border-bottom-color:var(--bad)}
.tl i.now.drag::after{border-bottom-color:var(--warn)}
.tl i.thinkspan{background:var(--warn);opacity:.3;z-index:1;
 pointer-events:none}
.tl .ponrlab{position:absolute;top:-15px;transform:translateX(-50%);
 font-size:9.5px;text-transform:uppercase;letter-spacing:.08em;
 color:var(--bad);white-space:nowrap;pointer-events:none}
.tlleg{color:var(--dim);font-size:11px;line-height:1.5;margin-top:4px}
.tlax{display:flex;justify-content:space-between;color:var(--mut);
 font-size:11px;font-family:"IBM Plex Mono",monospace;margin-top:11px}
.tlax .nowt{color:var(--tx)}
#inspdlg{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:50;
 overflow-y:auto;padding:30px 14px}
#inspdlg .in{max-width:820px;margin:0 auto;background:var(--panel);
 border:1px solid var(--line);padding:16px}
#insptxt h3{margin:2px 0 12px;font-size:14px}
#insptxt .kv{border-collapse:collapse;width:100%;font-size:13px;
 margin-bottom:14px}
#insptxt .kv td{padding:4px 8px;border-bottom:1px solid var(--p2);
 vertical-align:top}
#insptxt .kv td:first-child{color:var(--mut);white-space:nowrap;width:170px}
#insptxt .rsnfull{background:var(--p2);border-left:3px solid var(--dim);
 padding:10px 12px;white-space:pre-wrap;line-height:1.45;font-size:13px}
/* меню */
.scbtn{display:block;width:100%;text-align:left;margin:8px 0;padding:12px 14px}
.scbtn span{float:right;color:var(--mut)}
/* вводная */
#btext{background:var(--panel);border:1px solid var(--dim);padding:14px;
 line-height:1.5;white-space:pre-wrap;max-width:860px}
.rules{border:1px solid var(--warn);padding:10px 14px;margin:14px 0;
 max-width:860px;color:var(--warn)}
/* игра */
.grid{display:grid;grid-template-columns:200px 1fr 330px;gap:10px}
.card{background:var(--panel);border:1px solid var(--dim)}
.card h2{font-size:11px;letter-spacing:.1em;text-transform:uppercase;
 color:var(--mut);margin:0;padding:6px 10px;border-bottom:1px solid var(--dim)}
.card .bd{padding:8px}
.gr{display:grid;grid-template-columns:1fr auto auto;gap:6px;padding:3px 2px;
 border-bottom:1px solid var(--p2);font-size:13px}
.gr b{font-family:"IBM Plex Mono",monospace}
.gr i{color:var(--mut);font-style:normal;font-size:11px}
.gr.warn b{color:var(--warn)}
.eqh{font-size:11px;letter-spacing:.08em;color:var(--mut);margin:8px 0 4px;
 text-transform:uppercase}
.eq{padding:4px 6px;border-left:3px solid var(--dim);margin:3px 0;
 background:var(--p2);font-size:13px}
.eq.on{border-left-color:var(--ok)} .eq.off{opacity:.65}
.eq.warn{border-left-color:var(--warn)} .eq.bad{border-left-color:var(--bad)}
.loto{color:var(--warn);font-weight:600}
.al{border-left:3px solid var(--bad);background:rgba(207,90,78,.12);
 padding:5px 8px;margin:4px 0;font-size:13px}
.op,.rep{padding:3px 4px;font-size:12.5px;border-bottom:1px solid var(--p2)}
.rep{color:#cfe3d5}
#actions{max-height:520px;overflow-y:auto}
.agh{background:var(--p2);padding:6px 8px;margin-top:6px;cursor:pointer;
 font-weight:600;font-size:12.5px}
.agh span{color:var(--mut);font-weight:400}
.ab{display:block;width:100%;text-align:left;margin:3px 0;font-size:12.8px;
 padding:6px 8px}
#log{max-height:180px;overflow-y:auto;font-size:12.5px;
 font-family:"IBM Plex Mono",monospace;line-height:1.5}
#log div{border-bottom:1px solid var(--p2);padding:2px 0}
.clockbox{margin-left:auto;text-align:right}
#clock{font-size:22px;font-weight:600}
#thinkv{color:var(--warn)} #horiz{color:var(--mut);font-size:12px}
#warmwrap{display:none;padding:8px 14px}
#warmbar{height:6px;background:var(--line);width:0%}
/* Заслонка не накрывает шапку: выйти из задачи можно и пока исполняется
   команда -- иначе кнопка «к задачам» оказывалась некликабельной. */
#busy{display:none;position:fixed;left:0;right:0;bottom:0;top:52px;
 background:rgba(20,22,24,.55);z-index:9}
header{position:relative;z-index:11}
#busy div{position:absolute;top:40%;left:50%;transform:translate(-50%,-50%);
 background:var(--panel);border:1px solid var(--line);padding:16px 26px}
#rawdlg{position:fixed;inset:0;background:rgba(20,22,24,.8);z-index:10}
#rawdlg .in{max-width:900px;margin:5vh auto;background:var(--panel);
 border:1px solid var(--line);padding:14px;max-height:85vh;overflow:auto}
#rawtxt{white-space:pre-wrap;font-family:"IBM Plex Mono",monospace;
 font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid var(--dim);padding:4px 8px;text-align:left}
th{background:var(--p2)}
.spk{cursor:pointer}
#histdlg{position:fixed;inset:0;background:rgba(20,22,24,.8);z-index:10}
#histdlg .in{max-width:920px;margin:5vh auto;background:var(--panel);
 border:1px solid var(--line);padding:14px;max-height:88vh;overflow:auto}
.wb{padding:5px 7px;font-size:12.5px}
#pixinfo{margin-top:6px;text-align:left;font-size:13px;min-height:36px;
 border-top:1px solid var(--dim);padding:6px 4px 2px;color:var(--tx)}
#pixinfo b{color:#e6e9ea} #pixinfo .mut{font-size:12px}
#pix{image-rendering:pixelated;image-rendering:crisp-edges;
 border:1px solid var(--dim);background:#2a2e32;max-width:100%}
#fev{font-family:"IBM Plex Mono",monospace;font-size:12px;max-height:200px;
 overflow-y:auto}
textarea{width:100%;min-height:80px;background:var(--p2);color:var(--tx);
 border:1px solid var(--dim);font-family:inherit;padding:8px}
@media(max-width:1000px){.grid{grid-template-columns:1fr}}
"""

HTML = r"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NH3Ops — тренажёр для экспертной проверки</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Condensed:wght@400;600&display=swap" rel="stylesheet">
<style>@@CSS@@</style></head>
<body>
<header>
  <h1><span data-i18n="hdr.title">NH3Bench · интерактивный бенчмарк</span> <span data-i18n="hdr.sub">— та же установка, те же часы, тот же набор команд</span></h1>
  <button id="langb" title="Язык интерфейса / Interface language">EN</button>
  <button id="rawb" data-i18n="hdr.raw" data-i18n-title="hdr.rawt" title="Показать наблюдение в том виде, в каком его читает программа">сырой текст щита</button>
  <button id="leaveb" data-i18n="hdr.leave">← к задачам</button>
  <button id="finishb" data-i18n="hdr.finish">завершить задачу</button>
  <div class="clockbox">
    <div id="clock" class="num">00:00:00</div>
    <div id="thinkv" class="num">—</div>
    <div id="horiz"></div>
  </div>
</header>

<!-- Полоска прохождения задачи: прошло / осталось. Только для человека,
     в просмотре записи своя полоса решений. -->
<div id="playbar"><i id="playbarfill"></i></div>

<div id="scr-load" class="wrap">
  <h2 data-i18n="load.h">Подготовка тренажёра</h2>
  <p id="loadnote" data-i18n="load.start">запуск…</p>
  <div id="loadbar"><div style="height:100%;background:var(--line);width:100%;animation:pulse 1.2s infinite"></div></div>
  <p class="mut" data-i18n="load.note" style="max-width:640px;margin:26px auto">Тренажёр исполняет
  в браузере тот же самый расчётный код имитатора, что и стенд для программ, —
  без переписываний и упрощений. Нужен доступ в интернет для загрузки
  исполнителя Python (однократно, ~15 МБ).</p>
</div>

<div id="scr-hub" class="wrap" style="display:none">
  <h2 data-i18n="hub.h">NH3Bench — установка, задачи и те, кто их проходил</h2>
  <div id="hubbox" style="max-width:860px"></div>
  <p class="mut" data-i18n="hub.note" style="max-width:860px;margin-top:22px">Записи прогонов
  подлинные: та же установка, тот же щит, тот же список команд. Часы задачи
  идут из числа израсходованных программой токенов — многословие превращается
  в виртуальные секунды, а они иногда стоят дороже, чем правильный ответ.</p>
</div>

<div id="scr-wpick" class="wrap" style="display:none">
  <h2 data-i18n="wpick.h">Какой прогон посмотреть</h2>
  <p class="mut" data-i18n="wpick.note">Клетка — балл прогона. Зелёная — авария предотвращена без
  ущерба, жёлтая — с ущербом, красная — катастрофа.</p>
  <div id="wpickbox" style="max-width:900px"></div>
  <button class="hubback" data-i18n="brief.back" style="margin-top:20px">назад</button>
</div>

<div id="scr-cmp" class="wrap" style="display:none">
  <h2 data-i18n="cmp.h">Результаты</h2>
  <div id="cmpbox" style="max-width:1000px"></div>
  <button class="hubback" data-i18n="brief.back" style="margin-top:20px">назад</button>
</div>

<div id="scr-menu" class="wrap" style="display:none">
  <h2 data-i18n="menu.h">Выбор задачи</h2>
  <div id="scenlist" style="max-width:860px"></div>
  <div style="margin-top:26px;max-width:860px">
    <button class="hubback" data-i18n="menu.hub">главное меню</button>
    <button id="stbtn" data-i18n="menu.st">самопроверка физики (задача №1 без вмешательства)</button>
    <span id="stres" class="mut" style="margin-left:12px"></span>
  </div>
</div>

<div id="scr-brief" class="wrap" style="display:none">
  <h2 id="btitle"></h2>
  <div id="btext"></div>
  <div id="wbrief" class="wbrief" style="display:none"></div>
  <div id="brules" class="rules" data-i18n="brief.rules">Порядок тот же, что у испытуемых программ: пока вы
  читаете щит и думаете — часы задачи идут (масштаб раздумий выбирается ниже).
  Исполнение команд и переходы обходчиков прибавляют своё время. Пауза
  разрешена только для разбора и отмечается в протоколе.</div>
  <div id="scalewrap" style="margin:10px 0">
    <span data-i18n="brief.scale">Масштаб раздумий:</span>
    <button class="sc on" data-s="1">×1</button>
    <button class="sc" data-s="2">×2</button>
    <button class="sc" data-s="4">×4</button>
  </div>
  <!-- Подпись ставит тот, кто открыл вводную (смена, просмотр или проба),
       поэтому data-i18n здесь нет: он бы затирал её при смене языка. -->
  <button id="acceptb" style="font-size:16px;padding:10px 22px">ПРИНЯТЬ СМЕНУ</button>
  <button id="backb" data-i18n="brief.back">назад</button>
  <div id="warmwrap"><div class="mut" data-i18n="brief.warm">выход установки на режим…</div>
    <div style="border:1px solid var(--dim);background:var(--p2)">
    <div id="warmbar"></div></div></div>
</div>

<div id="scr-play" class="wrap" style="display:none">
  <div id="quickwrap" style="display:none;margin-bottom:10px">
    <div class="card"><h2 data-i18n="quick.h">Быстрая проба — задача №1</h2>
      <div class="bd" id="qbox"></div></div>
  </div>
  <div id="watchwrap" style="display:none;margin-bottom:10px">
    <div class="card"><h2 data-i18n="wr.h">Запись прогона программы</h2>
      <div class="bd">
        <div id="watchbar"></div>
        <div id="watchctl"></div>
        <div id="timeline"></div>
      </div></div>
  </div>
  <div class="card" style="margin-bottom:10px">
    <h2><span data-i18n="play.overview">Установка — обзорная картина</span>
      <button id="pixtoggle" data-i18n="play.collapse" style="float:right;padding:1px 8px;font-size:11px;margin-top:-3px">свернуть</button>
    </h2>
    <div class="bd" id="pixwrap" style="text-align:center;padding:6px">
      <canvas id="pix"></canvas>
      <div id="pixinfo" class="mut" data-i18n="play.pixinfo">Щёлкните по аппарату, помещению или
      обходчику, чтобы увидеть подробности.</div>
    </div>
  </div>
  <div class="grid">
    <div class="card"><h2><span data-i18n="play.gauges">Приборы щита</span>
      <button id="histb" data-i18n="play.hist" style="float:right;padding:1px 8px;font-size:11px;margin-top:-3px">история</button>
    </h2><div class="bd" id="gauges"></div></div>
    <div>
      <div class="card"><h2 data-i18n="play.alarms">Сигнализация</h2><div class="bd" id="alarms"></div></div>
      <div class="card" style="margin-top:10px"><h2 data-i18n="play.equip">Оборудование</h2>
        <div class="bd" id="equip"></div></div>
      <div class="card" style="margin-top:10px"><h2 data-i18n="play.people">Персонал · наряды · доклады</h2>
        <div class="bd" id="people"></div></div>
    </div>
    <div>
      <div class="card" id="cmdcard"><h2 data-i18n="play.cmds">Команды</h2><div class="bd">
        <input id="asearch" data-i18n-ph="play.search" placeholder="поиск команды…" style="width:100%;
        background:var(--p2);color:var(--tx);border:1px solid var(--dim);
        padding:6px 8px;font-family:inherit">
        <div style="margin:8px 0">
          <button id="pauseb" data-i18n="play.pause">ПАУЗА (для разбора)</button>
          <button id="playoutb" data-i18n="play.playout">доиграть без вмешательства</button>
        </div>
        <div style="margin:6px 0"><span data-i18n="play.observe">Наблюдать:</span>
          <button class="wb" data-w="10" data-i18n="play.w10">10 с</button>
          <button class="wb" data-w="60" data-i18n="play.w60">1 мин</button>
          <button class="wb" data-w="300" data-i18n="play.w300">5 мин</button>
          <button class="wb" data-w="900" data-i18n="play.w900">15 мин</button>
          <button class="wb" data-w="1800" data-i18n="play.w1800">30 мин</button>
          <button class="wb" data-w="3600" data-i18n="play.w3600">60 мин</button>
        </div>
        <div id="actions"></div>
      </div></div>
      <div class="card" style="margin-top:10px"><h2 data-i18n="play.log">Журнал смены</h2>
        <div class="bd" id="log"></div></div>
    </div>
  </div>
</div>

<div id="scr-final" class="wrap" style="display:none">
  <h2 id="fverdict"></h2>
  <div class="card"><h2 data-i18n="fin.sum">Итог</h2><div class="bd" id="fsum"></div></div>
  <div class="grid" style="grid-template-columns:1fr 1fr;margin-top:10px">
    <div class="card"><h2 data-i18n="fin.ref">Как прошли эту задачу опорные операторы</h2>
      <div class="bd"><table id="fref"></table></div></div>
    <div class="card"><h2 data-i18n="fin.events">События установки</h2><div class="bd" id="fev"></div></div>
  </div>
  <div class="card" style="margin-top:10px"><h2 data-i18n="fin.acts">Ваши команды</h2>
    <div class="bd"><table id="facts"></table></div></div>
  <div class="card" style="margin-top:10px"><h2><span id="fminehd">Ваш результат</span></h2>
    <div id="fmine"></div></div>
  <div class="card" style="margin-top:10px"><h2 data-i18n="fin.note">Замечание эксперта к задаче</h2>
    <div class="bd">
      <textarea id="fnote" data-i18n-ph="fin.noteph" placeholder="что показалось недостоверным, чего не хватило, как действовали бы вы…"></textarea>
      <div style="margin-top:8px">
        <button id="dlb" data-i18n="fin.dl">скачать протокол прохождения</button>
        <button id="againb" data-i18n="fin.again">пройти заново</button>
        <button id="menub" data-i18n="fin.menu">к списку задач</button>
      </div>
    </div></div>
</div>

<div id="busy"><div id="busytxt" data-i18n="busy.txt">установка живёт, команда исполняется…</div></div>
<div id="histdlg" style="display:none"><div class="in">
  <button id="histclose" data-i18n="raw.close" style="float:right">закрыть</button>
  <h3 data-i18n="hist.h" style="margin:4px 0 10px">История показателя</h3>
  <select id="histsel" style="background:var(--p2);color:var(--tx);
    border:1px solid var(--dim);padding:6px 8px;font-family:inherit;
    font-size:13.5px;margin-bottom:10px;max-width:100%"></select>
  <canvas id="histcv"></canvas>
  <div class="mut" data-i18n="hist.note" style="margin-top:8px;font-size:12.5px">История пишется
  имитатором каждые 10 с независимо от ваших опросов. Мини-тренды на панели
  тоже открывают это окно по щелчку.</div>
</div></div>
<div id="rawdlg" style="display:none"><div class="in">
  <button id="rawclose" data-i18n="raw.close" style="float:right">закрыть</button>
  <h3 data-i18n="raw.h">Наблюдение, как его читает испытуемая программа</h3>
  <div id="rawtxt"></div></div></div>
<div id="diffdlg" style="display:none"><div class="in">
  <button id="diffclose" data-i18n="raw.close" style="float:right">закрыть</button>
  <div id="difftxt"></div></div></div>
<div id="inspdlg" style="display:none"><div class="in">
  <button id="inspclose" data-i18n="raw.close" style="float:right">закрыть</button>
  <div id="insptxt"></div></div></div>

<script id="workersrc" type="text/plain">@@WORKER@@</script>
<script>@@MAIN@@</script>
</body></html>"""

worker = WORKER_JS.replace("@@FILES@@", json.dumps(FILES))
# Данные прогонов -- отдельным объявлением перед бандлом. Так trainer/*.js
# остаются разбираемым JavaScript: метка внутри выражения делала watch.js
# синтаксически неверным, и редактор ругался на весь файл.
DATA_JS = (
    "const NH3_MANIFEST = "
    + json.dumps(dict(MANIFEST, label=ARGS.label), ensure_ascii=False)
    + ";\nconst NH3_TRACES = "
    + json.dumps(TRACES, ensure_ascii=False) + ";\n")

main = ((DATA_JS + MAIN_JS + "\n" + PIX_JS + "\n" + WATCH_JS + "\n"
         + QUICK_JS + "\n" + MINE_JS + "\n" + I18N_JS_SRC)
        .replace("@@CATALOG@@", CATALOG)
        .replace("@@SCEN@@", SCENARIOS)
        .replace("@@REF@@", json.dumps(REF, ensure_ascii=False)))
html = (HTML.replace("@@CSS@@", CSS)
        .replace("@@WORKER@@", worker)
        .replace("@@MAIN@@", main))

path = (os.path.abspath(ARGS.out) if ARGS.out
        else os.path.join(ROOT, "trainer", "nh3bench-demo.html"))
open(path, "w", encoding="utf-8").write(html)
tmp = tempfile.gettempdir()
open(os.path.join(tmp, "worker_check.js"), "w", encoding="utf-8").write(
    worker.replace("importScripts", "//importScripts", 1))
open(os.path.join(tmp, "main_check.js"), "w", encoding="utf-8").write(main)
print("записан:", path, round(len(html) / 1024), "КБ")
