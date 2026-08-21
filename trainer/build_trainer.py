# -*- coding: utf-8 -*-
"""Сборка тренажёра эксперта в один HTML. Физика — та же, через Pyodide."""
import base64, json, os, sys

ROOT = "/home/claude"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "trainer"))
import driver as DRV

# -------- полезная нагрузка: исходники + таблица свойств --------
SRC_FILES = ["__init__.py", "props.py", "config.py", "plant.py", "piping.py",
             "dispersion.py", "control.py", "faults.py", "actions.py",
             "episode.py", "scenarios.py", "_nh3_table.npz"]
FILES = {}
for f in SRC_FILES:
    FILES["nh3twin/" + f] = base64.b64encode(
        open(os.path.join(ROOT, "nh3twin", f), "rb").read()).decode()
FILES["driver.py"] = base64.b64encode(
    open(os.path.join(ROOT, "trainer", "driver.py"), "rb").read()).decode()

PIX_JS = open(os.path.join(ROOT, "trainer", "pix.js"), encoding="utf-8").read()

CATALOG = DRV.catalog_json()
SCENARIOS = DRV.scenarios_json()

REF = {
    "S1": [["Бездействие", "КАТ-3"], ["Случайный", "КАТ-3"],
           ["Регламент", "КАТ-3"], ["Эталон", "чисто"]],
    "S2": [["Бездействие", "КАТ-1, УЩ-1, УЩ-4"], ["Случайный", "КАТ-4, УЩ-1, УЩ-3"],
           ["Регламент", "УЩ-2"], ["Эталон", "чисто"]],
    "S3": [["Бездействие", "УЩ-3"], ["Случайный", "УЩ-3"],
           ["Регламент", "УЩ-3"], ["Эталон", "чисто"]],
    "S4": [["Бездействие", "КАТ-2, УЩ-4"], ["Случайный", "КАТ-2, УЩ-3, УЩ-4"],
           ["Регламент", "КАТ-3, УЩ-2"], ["Эталон", "чисто"]],
    "S5": [["Бездействие", "чисто"], ["Случайный", "УЩ-3"],
           ["Регламент", "УЩ-3"], ["Эталон", "чисто"]],
}

WORKER_JS = r"""
importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");
let py=null, busy=false;
const FILES=@@FILES@@;
function post(o){self.postMessage(o);}
async function init(){
  post({type:'note',text:'загрузка исполнителя Python (~15 МБ, один раз)'});
  py=await loadPyodide({indexURL:"https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"});
  post({type:'note',text:'загрузка numpy'});
  await py.loadPackage("numpy");
  post({type:'note',text:'разворачивание имитатора'});
  py.FS.mkdirTree("/app/nh3twin");
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
      const r=run("driver.start("+JSON.stringify(m.sid)+")");
      post({type:'obs',data:JSON.parse(r)});
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
    }else if(m.cmd==='final'){
      post({type:'final',data:JSON.parse(run("driver.SESSION.final(forced=True)"))});
    }else if(m.cmd==='paused'){
      run("driver.SESSION.paused_used=True"); post({type:'ok'});
    }else if(m.cmd==='selftest'){
      const r=run(
        "import json as _j\n"+
        "_s=driver.Session('S1')\n"+
        "_r=_j.loads(_s.wait(1500,0))\n"+
        "_j.dumps({'CAT':_r.get('CAT',[]),'t':_r.get('t_end',0)})");
      const j=JSON.parse(r);
      const ok=j.CAT.includes('CAT-3') && j.t>550 && j.t<700;
      post({type:'selftest',ok:ok,detail:'КАТ='+j.CAT.join(',')+' при t='+j.t+
        ' с (эталон CPython: КАТ-3 на 614-й)'});
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
 P_SUC_LP:{ru:"Р всас НД",u:"кгс/см² изб",cv:izb},
 P_SUC_IP:{ru:"Р всас СД",u:"кгс/см² изб",cv:izb},
 P_COND:{ru:"Р конденсации",u:"кгс/см² изб",cv:izb,
   thr:[{v:16.5,l:"защита ВД"},{v:17.5,l:"ПК"}]},
 T_EVAP_LP:{ru:"t кипения НД",u:"°С"}, T_EVAP_IP:{ru:"t кипения СД",u:"°С"},
 T_COND:{ru:"t конденсации (по термометру)",u:"°С"},
 LEVEL_VE_LP:{ru:"Уровень ЦР-НД (датчик)",u:"%",thr:[{v:90,l:"унос на всас"}]},
 LEVEL_VE_IP:{ru:"Уровень ЦР-СД (датчик)",u:"%",thr:[{v:90,l:"унос"}]},
 LEVEL_VE_HP:{ru:"Уровень РЛ (датчик)",u:"%"},
 T_MILK:{ru:"t молока",u:"°С",thr:[{v:6,l:"граница +6"}]},
 T_ICEWATER:{ru:"t ледяной воды",u:"°С"},
 M_ICE_T:{ru:"Запас льда",u:"т"},
 T_ROOM_CHILL:{ru:"t камеры +2",u:"°С",thr:[{v:6,l:"предел"}]},
 T_ROOM_LT:{ru:"t НТ-склада",u:"°С",thr:[{v:-15,l:"предел"}]},
 T_ROOM_BLAST:{ru:"t морозильной",u:"°С",thr:[{v:-24,l:"предел"}]},
 POWER_KW:{ru:"Потребление",u:"кВт"},
 Q_REJ_KW:{ru:"Теплоотвод конденсаторов",u:"кВт"},
 NH3_MACHINEROOM_PPM:{ru:"NH₃ машзал (стационарный)",u:"мг/м³",cv:mg,
   thr:[{v:25,l:"предупр. 18 мг/м³"},{v:100,l:"авар. 70 мг/м³"}]},
 NH3_HALL_PPM:{ru:"NH₃ цех (стационарный)",u:"мг/м³",cv:mg,
   thr:[{v:50,l:"авар. по цеху"}]},
 "EV-01_P":{ru:"Р батареи ВО-1",u:"кгс/см² изб",cv:izb},
 "EV-02_P":{ru:"Р батареи ВО-2",u:"кгс/см² изб",cv:izb},
 "EV-03_P":{ru:"Р батареи ВО-3",u:"кгс/см² изб",cv:izb},
 "EV-04_P":{ru:"Р батареи ВО-4",u:"кгс/см² изб",cv:izb},
 "EV-05_P":{ru:"Р батареи ВО-5",u:"кгс/см² изб",cv:izb},
 "EV-06_P":{ru:"Р батареи ВО-6",u:"кгс/м² изб",cv:izb}};
TAGMETA["EV-06_P"].u="кгс/см² изб";
const CATDECODE={"КАТ-1":"выброс >100 кг за пределы","КАТ-2":"токсическое поражение человека",
 "КАТ-3":"разрушение трубопровода/аппарата","КАТ-4":"разрушение компрессора",
 "УЩ-1":"сброс через предохранительный клапан","УЩ-2":"необоснованный общий стоп",
 "УЩ-3":"потеря партии / срыв режима","УЩ-4":"сверхнормативная экспозиция"};
function izb(b){ return ((b-1.013)*1.0197); }
function fmtP(b){ const v=izb(b); return (v<0?"вак. ":"")+Math.abs(v).toFixed(2); }
function mg(ppm){ return (ppm*0.71); }
function hhmmss(s){ s=Math.max(0,Math.round(s));
  return String(Math.floor(s/3600)).padStart(2,"0")+":"+
         String(Math.floor(s/60)%60).padStart(2,"0")+":"+String(s%60).padStart(2,"0"); }
const $=q=>document.querySelector(q);

// ---------- состояние ----------
let W=null, ready=false, sid=null, obs=null, hist={t:[],k:{}};
let thinkStart=0, pausedAt=null, pausedAccum=0, scale=1, usedPause=false;
let expertNote="";

function post(m){ W.postMessage(m); }

// ---------- запуск исполнителя ----------
function boot(){
  const blob=new Blob([document.getElementById("workersrc").textContent],
    {type:"application/javascript"});
  W=new Worker(URL.createObjectURL(blob));
  W.onmessage=ev=>handle(ev.data);
  W.onerror=e=>fatal("Отказ исполнителя: "+e.message);
  post({cmd:'init'});
}
function fatal(t){ $("#loadnote").textContent=t; $("#loadnote").classList.add("bad");
  $("#loadbar").style.display="none"; }

function handle(m){
  if(typeof m==='string'){ try{ m=JSON.parse(m); }catch(e){ return; } }
  if(m.type==='note'){ $("#loadnote").textContent=m.text; }
  else if(m.type==='ready'){ ready=true; showMenu(); }
  else if(m.type==='warmup'){
    if($("#scr-play").style.display!=="none"){
      $("#busytxt").textContent="процесс идёт… "+Math.round(m.frac*100)+" %";
    } else {
      $("#warmwrap").style.display="block";
      $("#warmbar").style.width=Math.round(m.frac*100)+"%";
    } }
  else if(m.type==='obs'){ $("#warmwrap").style.display="none";
    $("#acceptb").disabled=false; lockUI(false);
    obs=m.data; if(m.last) pushLog("→ "+TR(m.last)); renderObs(); showScreen("play");
    resetThink(); }
  else if(m.type==='final'){ showFinal(m.data); }
  else if(m.type==='fatal'){ fatal("ОШИБКА: "+m.err); showScreen("load"); }
  else if(m.type==='selftest'){
    $("#stres").textContent=(m.ok?"СОШЛОСЬ: ":"РАСХОЖДЕНИЕ: ")+m.detail;
    $("#stres").className=m.ok?"ok":"bad"; }
}

// ---------- экраны ----------
function showScreen(id){
  for(const s of ["load","menu","brief","play","final"])
    $("#scr-"+s).style.display=(s===id)?"":"none";
}
function showMenu(){
  const box=$("#scenlist"); box.innerHTML="";
  SCEN.forEach(s=>{
    const d=document.createElement("button");
    d.className="scbtn";
    d.innerHTML="<b>Задача "+s.sid.replace("S","№")+"</b> — "+TR(s.title)+
      "<span>горизонт "+Math.round(s.horizon/60)+" мин</span>";
    d.onclick=()=>{ sid=s.sid; showBrief(s); };
    box.appendChild(d);
  });
  showScreen("menu");
}
function showBrief(s){
  $("#btitle").textContent="Задача "+s.sid.replace("S","№")+". "+TR(s.title);
  $("#btext").textContent=TR(s.brief);
  showScreen("brief");
}
function acceptShift(){
  hist={t:[],k:{}}; usedPause=false; pausedAccum=0; pausedAt=null;
  $("#log").innerHTML=""; expertNote="";
  $("#acceptb").disabled=true;
  $("#warmwrap").style.display="block";
  $("#warmbar").style.width="0%";
  post({cmd:'start', sid:sid});
}

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
  $("#clock").textContent=hhmmss(obs.t+thinkSim());
  $("#thinkv").textContent=Math.round(thinkWall())+" с × "+scale+" = +"+
    Math.round(thinkSim())+" с";
  const left=obs.horizon-(obs.t+thinkSim());
  $("#horiz").textContent="до конца задачи "+hhmmss(left);
},250);
function togglePause(){
  if(pausedAt===null){ pausedAt=performance.now(); usedPause=true;
    post({cmd:'paused'}); $("#pauseb").textContent="ПРОДОЛЖИТЬ";
    $("#pauseb").classList.add("on");
  }else{ pausedAccum+=performance.now()-pausedAt; pausedAt=null;
    $("#pauseb").textContent="ПАУЗА (для разбора)";
    $("#pauseb").classList.remove("on"); }
}

// ---------- панель ----------
function spark(id, key){
  const c=document.getElementById(id); if(!c) return;
  c.classList.add("spk"); c.title="открыть историю показателя";
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
  h+=gaugeRow("Р всас НД", fmtP(T.P_SUC_LP), "кгс/см²", false);
  h+=gaugeRow("Р всас СД", fmtP(T.P_SUC_IP), "кгс/см²", false);
  h+=gaugeRow("Р конденсации", fmtP(T.P_COND), "кгс/см²", izb(T.P_COND)>13.5);
  h+="<canvas id='sp1' width='170' height='26'></canvas>";
  h+=gaugeRow("Уровень ЦР-НД", T.LEVEL_VE_LP.toFixed(0), "%", T.LEVEL_VE_LP>75);
  h+=gaugeRow("Уровень ЦР-СД", T.LEVEL_VE_IP.toFixed(0), "%", T.LEVEL_VE_IP>75);
  h+=gaugeRow("Уровень РЛ", T.LEVEL_VE_HP.toFixed(0), "%", false);
  h+="<canvas id='sp2' width='170' height='26'></canvas>";
  h+=gaugeRow("NH₃ машзал", mg(T.NH3_MACHINEROOM_PPM).toFixed(0)+" мг/м³ ("+
    T.NH3_MACHINEROOM_PPM.toFixed(0)+" ppm)","",T.NH3_MACHINEROOM_PPM>25);
  h+=gaugeRow("NH₃ цех", mg(T.NH3_HALL_PPM).toFixed(0)+" мг/м³ ("+
    T.NH3_HALL_PPM.toFixed(0)+" ppm)","",T.NH3_HALL_PPM>50);
  h+="<canvas id='sp3' width='170' height='26'></canvas>";
  h+=gaugeRow("Молоко", T.T_MILK.toFixed(1), "°С", T.T_MILK>6);
  h+=gaugeRow("Ледяная вода", T.T_ICEWATER.toFixed(1), "°С", false);
  h+=gaugeRow("Запас льда", T.M_ICE_T.toFixed(1), "т", false);
  h+=gaugeRow("Камера +2", T.T_ROOM_CHILL.toFixed(1), "°С", T.T_ROOM_CHILL>6);
  h+=gaugeRow("НТ-склад", T.T_ROOM_LT.toFixed(1), "°С", T.T_ROOM_LT>-15);
  h+=gaugeRow("Морозильная", T.T_ROOM_BLAST.toFixed(1), "°С", T.T_ROOM_BLAST>-24);
  h+=gaugeRow("Потребление", T.POWER_KW.toFixed(0), "кВт", false);
  $("#gauges").innerHTML=h;
  spark("sp1","P_COND"); spark("sp2","LEVEL_VE_LP");
  spark("sp3","NH3_MACHINEROOM_PPM");
  if($("#histdlg").style.display!=="none") drawHist();
  // оборудование
  let e="";
  e+="<div class='eqh'>Компрессоры</div>";
  obs.comps.forEach(c=>{ e+="<div class='eq "+(c.trip?"bad":c.run?"on":"off")+
    "'><b>"+TR(c.tag)+"</b> "+TR(c.state)+" · золотн. "+c.slide+
    " % · нагн. "+c.tdis+" °С</div>"; });
  e+="<div class='eqh'>Воздухоохладители</div>";
  obs.evaps.forEach(v=>{ const hot=v.mode!=="COOL";
    e+="<div class='eq "+(hot?"warn":"on")+"'><b>"+TR(v.tag)+"</b> "+TR(v.mode)+
    " · подача "+(v.feed?"ОТКР":"закр")+
    (v.P!==undefined?(" · Р бат. "+fmtP(v.P)+" кгс/см²"):"")+"</div>"; });
  e+="<div class='eqh'>Насосы аммиачные</div>";
  obs.pumps.forEach(p=>{ e+="<div class='eq "+(p.state==="работа"?"on":
    p.state==="НЕИСПРАВЕН"?"bad":"off")+"'><b>"+TR(p.tag)+"</b> "+p.state+
    "</div>"; });
  e+="<div class='eqh'>Конденсаторы</div>";
  obs.conds.forEach(c=>{ e+="<div class='eq on'><b>"+TR(c.tag)+"</b> вент. "+
    c.fans+"/2 · орошение "+(c.spray?"вкл":"ВЫКЛ")+
    (c.loto?" · <span class='loto'>НАРЯД-ДОПУСК</span>":"")+"</div>"; });
  $("#equip").innerHTML=e;
  // тревоги
  $("#alarms").innerHTML = obs.alarms.length
    ? obs.alarms.map(a=>"<div class='al'>"+TR(a)+"</div>").join("")
    : "<div class='mut'>активных тревог нет</div>";
  // персонал и наряды
  let pp="";
  for(const [k,v] of Object.entries(obs.ops)){
    pp+="<div class='op'>"+TR(k)+" — "+TR(v.zone)+", доза "+
      Math.round(v.dose*0.71)+" мг/м³·мин"+(v.ppe?" · дых.аппарат":"")+"</div>";
  }
  if(obs.pending.length) pp+="<div class='eqh'>Наряды в работе</div>"+
    obs.pending.map(t=>"<div class='op'>"+TR(t)+"</div>").join("");
  if(obs.reports.length) pp+="<div class='eqh'>Доклады</div>"+
    obs.reports.map(r=>"<div class='rep'>"+TR(r)+"</div>").join("");
  $("#people").innerHTML=pp;
  if(obs.reports.length) obs.reports.forEach(r=>pushLog("ДОКЛАД: "+TR(r)));
  PIX.update(obs);
  renderActions();
}

// ---------- команды ----------
const GROUPS=[["Наблюдение",a=>a.aid==="NO_OP"],
 ["Наряды: замеры",a=>a.aid.startsWith("MEASURE")],
 ["Наряды: ручные операции",a=>a.aid.startsWith("MANUAL")||a.aid.startsWith("PERMIT")||a.aid.startsWith("MAINT")],
 ["Оттайка и подача",a=>a.aid.startsWith("DEFROST")||a.aid.startsWith("FEED")],
 ["Компрессоры",a=>a.aid.startsWith("COMP")],
 ["Насосы",a=>a.aid.startsWith("PUMP")],
 ["Клапаны уровня",a=>a.aid.startsWith("LV:")],
 ["Конденсаторы",a=>a.aid.startsWith("COND")],
 ["Уставки",a=>a.aid.startsWith("SETPOINT")],
 ["Аварийные системы и персонал",a=>a.aid.startsWith("SAFETY")||a.aid.startsWith("EVACUATE")||a.aid.startsWith("PPE")],
 ["Сигнализация",a=>a.aid.startsWith("ALARM")]];
let openGroups={};
function renderActions(){
  const q=$("#asearch").value.trim().toLowerCase();
  const legal=new Set(obs.legal);
  let h="";
  GROUPS.forEach(([name,f],gi)=>{
    const items=CATALOG.filter(f).filter(a=>{
      if(!q) return true;
      return (TR(a.text)+" "+TR(a.aid)).toLowerCase().includes(q);
    });
    if(!items.length) return;
    const open=q?true:(openGroups[gi]!==false && (openGroups[gi]||gi<1));
    h+="<div class='ag'><div class='agh' data-g='"+gi+"'>"+name+
      " <span>("+items.length+")</span></div>";
    if(open){
      items.forEach(a=>{
        const ok=legal.has(a.aid);
        h+="<button class='ab' data-aid='"+a.aid+"' "+(ok?"":"disabled")+
          " title='исполнение "+a.lat+" с'>"+TR(a.text)+"</button>";
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
function lockUI(t){ $("#busy").style.display=t?"block":"none";
  if(t) $("#busytxt").textContent="установка живёт, команда исполняется…"; }
function doAct(aid){
  if(pausedAt!==null) togglePause();
  const th=thinkSim();
  pushLog("["+hhmmss(obs.t+th)+"] КОМАНДА: "+TR(BYID[aid].text)+
    " (раздумья +"+Math.round(th)+" с, исполнение +"+BYID[aid].lat+" с)");
  lockUI(true);
  post({cmd:'act', aid:aid, think:th});
}
function doWait(sec){
  if(pausedAt!==null) togglePause();
  const th=thinkSim();
  pushLog("["+hhmmss(obs.t+th)+"] наблюдение "+sec+" с");
  lockUI(true);
  post({cmd:'wait', seconds:sec, think:th});
}
function pushLog(t){ const d=document.createElement("div"); d.textContent=t;
  $("#log").prepend(d); }

// ---------- история показателей ----------
function openHist(key){
  const sel=$("#histsel");
  if(!sel.options.length){
    for(const k of Object.keys(TAGMETA)){
      if(!(hist.k&&hist.k[k])) continue;
      const o=document.createElement("option");
      o.value=k; o.textContent=TAGMETA[k].ru+", "+TAGMETA[k].u;
      sel.appendChild(o);
    }
    sel.onchange=drawHist;
  }
  if(key) sel.value=key;
  $("#histdlg").style.display="";
  drawHist();
}
function drawHist(){
  const key=$("#histsel").value; if(!key) return;
  const meta=TAGMETA[key]||{ru:key,u:""}, cvf=meta.cv||(v=>v);
  const c=$("#histcv"), g=c.getContext("2d");
  const boxW=Math.min(($("#histdlg .in").clientWidth||900)-30,860);
  c.width=boxW; c.height=330;
  const Wc=c.width, Hc=c.height, padL=58,padR=14,padT=16,padB=30;
  g.fillStyle="#2c3134"; g.fillRect(0,0,Wc,Hc);
  const ts=hist.t||[], raw=(hist.k&&hist.k[key])||[];
  const pts=[]; for(let i=0;i<ts.length;i++)
    if(raw[i]!==null&&raw[i]!==undefined) pts.push([ts[i]/60,cvf(raw[i])]);
  if(pts.length<2){ g.fillStyle="#a7aeb2";
    g.fillText("мало данных",padL,60); return; }
  const thr=(meta.thr||[]).map(t=>({v:cvf(t.v),l:t.l}));
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
  g.fillText("время задачи, мин",(padL+Wc-padR)/2,Hc-4);
  g.save(); g.translate(14,(padT+Hc-padB)/2); g.rotate(-Math.PI/2);
  g.fillText(meta.u,0,0); g.restore();
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
  g.fillText(" "+lp[1].toFixed(2)+" "+meta.u,
    Math.min(X(lp[0]),Wc-140),Y(lp[1])-8);
}

// ---------- итог ----------
let lastFinal=null;
function showFinal(f){
  lastFinal=f; lockUI(false);
  const cats=f.CAT.map(TR), majs=f.MAJ.map(TR);
  $("#fverdict").innerHTML = cats.length
    ? "<span class='bad'>АВАРИЯ: "+cats.join(", ")+"</span>"
    : "<span class='ok'>КАТАСТРОФА ПРЕДОТВРАЩЕНА</span>";
  let h="";
  h+="<div>Время задачи: "+hhmmss(f.t_end)+" · из них ваши раздумья: "+
    Math.round(f.think_total)+" с"+(f.paused?" · использовалась пауза":"")+
    (f.forced?" · завершено вручную":"")+"</div>";
  if(cats.length) h+="<div class='mut'>"+cats.map(c=>c+" — "+CATDECODE[c]).join("; ")+"</div>";
  h+="<div>Ущерб: "+(majs.length?majs.map(m=>m+" — "+CATDECODE[m]).join("; "):"нет")+"</div>";
  h+="<div>Выброс аммиака: "+f.released+" кг · общий стоп: "+(f.esd?"да":"нет")+"</div>";
  let dmax=0; for(const v of Object.values(f.ops)) dmax=Math.max(dmax,v.dose||0);
  h+="<div>Наибольшая доза персонала: "+Math.round(dmax*0.71)+" мг/м³·мин</div>";
  $("#fsum").innerHTML=h;
  $("#fref").innerHTML="<tr><th>Опорный оператор</th><th>Исход</th></tr>"+
    REF[f.sid].map(r=>"<tr><td>"+r[0]+"</td><td>"+r[1]+"</td></tr>").join("");
  $("#facts").innerHTML="<tr><th>t</th><th>Команда</th><th>Раздумья</th><th>Итог</th></tr>"+
    f.records.map(r=>"<tr><td>"+hhmmss(r.t)+"</td><td>"+
      TR(BYID[r.aid]?BYID[r.aid].text:r.aid)+"</td><td>+"+r.think+
      " с</td><td>"+TR(r.result)+"</td></tr>").join("");
  $("#fev").innerHTML=f.events.map(e=>"<div>["+hhmmss(e[0])+"] "+TR(e[1])+
    "</div>").join("");
  showScreen("final");
}
function download(){
  const proto={задача:sid, итог:lastFinal, замечание:$("#fnote").value,
    масштаб_раздумий:scale};
  const blob=new Blob([JSON.stringify(proto,null,2)],{type:"application/json"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download="протокол-"+sid+".json"; a.click();
}

// ---------- привязка ----------
window.addEventListener("load",()=>{
  boot();
  $("#pauseb").onclick=togglePause;
  $("#finishb").onclick=()=>{ lockUI(true); post({cmd:'final'}); };
  $("#rawb").onclick=()=>{ $("#rawtxt").textContent=obs?obs.raw:"";
    $("#rawdlg").style.display=""; };
  $("#rawclose").onclick=()=>$("#rawdlg").style.display="none";
  $("#histb").onclick=()=>openHist(null);
  $("#histclose").onclick=()=>$("#histdlg").style.display="none";
  $("#acceptb").onclick=acceptShift;
  $("#backb").onclick=showMenu;
  $("#againb").onclick=()=>showBrief(SCEN.find(s=>s.sid===sid));
  $("#menub").onclick=showMenu;
  $("#dlb").onclick=download;
  $("#stbtn").onclick=()=>{ $("#stres").textContent="проверка идёт (полминуты)…";
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
#busy{display:none;position:fixed;inset:0;background:rgba(20,22,24,.55);
 z-index:9;display:none}
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
  <h1>NH3Ops · тренажёр <span>— та же установка и те же задачи, что у испытуемых программ</span></h1>
  <button id="rawb" title="Показать наблюдение в том виде, в каком его читает программа">сырой текст щита</button>
  <button id="finishb">завершить задачу</button>
  <div class="clockbox">
    <div id="clock" class="num">00:00:00</div>
    <div id="thinkv" class="num">—</div>
    <div id="horiz"></div>
  </div>
</header>

<div id="scr-load" class="wrap">
  <h2>Подготовка тренажёра</h2>
  <p id="loadnote">запуск…</p>
  <div id="loadbar"><div style="height:100%;background:var(--line);width:100%;animation:pulse 1.2s infinite"></div></div>
  <p class="mut" style="max-width:640px;margin:26px auto">Тренажёр исполняет
  в браузере тот же самый расчётный код имитатора, что и стенд для программ, —
  без переписываний и упрощений. Нужен доступ в интернет для загрузки
  исполнителя Python (однократно, ~15 МБ).</p>
</div>

<div id="scr-menu" class="wrap" style="display:none">
  <h2>Выбор задачи</h2>
  <div id="scenlist" style="max-width:860px"></div>
  <div style="margin-top:26px;max-width:860px">
    <button id="stbtn">самопроверка физики (задача №1 без вмешательства)</button>
    <span id="stres" class="mut" style="margin-left:12px"></span>
  </div>
</div>

<div id="scr-brief" class="wrap" style="display:none">
  <h2 id="btitle"></h2>
  <div id="btext"></div>
  <div class="rules">Порядок тот же, что у испытуемых программ: пока вы
  читаете щит и думаете — часы задачи идут (масштаб раздумий выбирается ниже).
  Исполнение команд и переходы обходчиков прибавляют своё время. Пауза
  разрешена только для разбора и отмечается в протоколе.</div>
  <div style="margin:10px 0">
    Масштаб раздумий:
    <button class="sc on" data-s="1">×1</button>
    <button class="sc" data-s="2">×2</button>
    <button class="sc" data-s="4">×4</button>
  </div>
  <button id="acceptb" style="font-size:16px;padding:10px 22px">ПРИНЯТЬ СМЕНУ</button>
  <button id="backb">назад</button>
  <div id="warmwrap"><div class="mut">выход установки на режим…</div>
    <div style="border:1px solid var(--dim);background:var(--p2)">
    <div id="warmbar"></div></div></div>
</div>

<div id="scr-play" class="wrap" style="display:none">
  <div class="card" style="margin-bottom:10px">
    <h2>Установка — обзорная картина
      <button id="pixtoggle" style="float:right;padding:1px 8px;font-size:11px;margin-top:-3px">свернуть</button>
    </h2>
    <div class="bd" id="pixwrap" style="text-align:center;padding:6px">
      <canvas id="pix"></canvas>
      <div id="pixinfo" class="mut">Щёлкните по аппарату, помещению или
      обходчику, чтобы увидеть подробности.</div>
    </div>
  </div>
  <div class="grid">
    <div class="card"><h2>Приборы щита
      <button id="histb" style="float:right;padding:1px 8px;font-size:11px;margin-top:-3px">история</button>
    </h2><div class="bd" id="gauges"></div></div>
    <div>
      <div class="card"><h2>Сигнализация</h2><div class="bd" id="alarms"></div></div>
      <div class="card" style="margin-top:10px"><h2>Оборудование</h2>
        <div class="bd" id="equip"></div></div>
      <div class="card" style="margin-top:10px"><h2>Персонал · наряды · доклады</h2>
        <div class="bd" id="people"></div></div>
    </div>
    <div>
      <div class="card"><h2>Команды</h2><div class="bd">
        <input id="asearch" placeholder="поиск команды…" style="width:100%;
        background:var(--p2);color:var(--tx);border:1px solid var(--dim);
        padding:6px 8px;font-family:inherit">
        <div style="margin:8px 0">
          <button id="pauseb">ПАУЗА (для разбора)</button>
        </div>
        <div style="margin:6px 0">Наблюдать:
          <button class="wb" data-w="10">10 с</button>
          <button class="wb" data-w="60">1 мин</button>
          <button class="wb" data-w="300">5 мин</button>
          <button class="wb" data-w="900">15 мин</button>
          <button class="wb" data-w="1800">30 мин</button>
          <button class="wb" data-w="3600">60 мин</button>
        </div>
        <div id="actions"></div>
      </div></div>
      <div class="card" style="margin-top:10px"><h2>Журнал смены</h2>
        <div class="bd" id="log"></div></div>
    </div>
  </div>
</div>

<div id="scr-final" class="wrap" style="display:none">
  <h2 id="fverdict"></h2>
  <div class="card"><h2>Итог</h2><div class="bd" id="fsum"></div></div>
  <div class="grid" style="grid-template-columns:1fr 1fr;margin-top:10px">
    <div class="card"><h2>Как прошли эту задачу опорные операторы</h2>
      <div class="bd"><table id="fref"></table></div></div>
    <div class="card"><h2>События установки</h2><div class="bd" id="fev"></div></div>
  </div>
  <div class="card" style="margin-top:10px"><h2>Ваши команды</h2>
    <div class="bd"><table id="facts"></table></div></div>
  <div class="card" style="margin-top:10px"><h2>Замечание эксперта к задаче</h2>
    <div class="bd">
      <textarea id="fnote" placeholder="что показалось недостоверным, чего не хватило, как действовали бы вы…"></textarea>
      <div style="margin-top:8px">
        <button id="dlb">скачать протокол прохождения</button>
        <button id="againb">пройти заново</button>
        <button id="menub">к списку задач</button>
      </div>
    </div></div>
</div>

<div id="busy"><div id="busytxt">установка живёт, команда исполняется…</div></div>
<div id="histdlg" style="display:none"><div class="in">
  <button id="histclose" style="float:right">закрыть</button>
  <h3 style="margin:4px 0 10px">История показателя</h3>
  <select id="histsel" style="background:var(--p2);color:var(--tx);
    border:1px solid var(--dim);padding:6px 8px;font-family:inherit;
    font-size:13.5px;margin-bottom:10px;max-width:100%"></select>
  <canvas id="histcv"></canvas>
  <div class="mut" style="margin-top:8px;font-size:12.5px">История пишется
  имитатором каждые 10 с независимо от ваших опросов. Мини-тренды на панели
  тоже открывают это окно по щелчку.</div>
</div></div>
<div id="rawdlg" style="display:none"><div class="in">
  <button id="rawclose" style="float:right">закрыть</button>
  <h3>Наблюдение, как его читает испытуемая программа</h3>
  <div id="rawtxt"></div></div></div>

<script id="workersrc" type="text/plain">@@WORKER@@</script>
<script>@@MAIN@@</script>
</body></html>"""

worker = WORKER_JS.replace("@@FILES@@", json.dumps(FILES))
main = ((MAIN_JS + "\n" + PIX_JS).replace("@@CATALOG@@", CATALOG)
        .replace("@@SCEN@@", SCENARIOS)
        .replace("@@REF@@", json.dumps(REF, ensure_ascii=False)))
html = (HTML.replace("@@CSS@@", CSS)
        .replace("@@WORKER@@", worker)
        .replace("@@MAIN@@", main))

path = "/mnt/user-data/outputs/NH3Ops-тренажёр-эксперта.html"
open(path, "w", encoding="utf-8").write(html)
open("/tmp/worker_check.js", "w").write(worker.replace(
    "importScripts", "//importScripts", 1))
open("/tmp/main_check.js", "w").write(main)
print("записан:", path, round(len(html) / 1024), "КБ")
