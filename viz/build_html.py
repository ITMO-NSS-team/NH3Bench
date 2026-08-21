"""Сборка автономного HTML с мнемосхемой и трендами."""
import json, os

D = os.path.dirname(os.path.abspath(__file__))
DATA = open(os.path.join(D, "packed.json"), encoding="utf-8").read()

HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NH3Ops — цифровой двойник аммиачной холодильной установки</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@400;500;600&display=swap" rel="stylesheet">
<style>
/* ------------------------------------------------------------------
   Оформление по ISA-101 (high-performance HMI):
   фон нейтрально-серый, оборудование контуром, цвет ТОЛЬКО у отклонений.
   ------------------------------------------------------------------ */
:root{
  --bg:#3a3f43;          /* фон мнемосхемы */
  --panel:#33383c;
  --panel-2:#2c3134;
  --line:#8d9499;        /* контуры оборудования */
  --line-dim:#5f676c;
  --text:#e6e9ea;
  --text-dim:#a7aeb2;
  --fill:#474d51;        /* заливка аппаратов */
  --ok:#7fa88a;          /* норма — приглушённый, почти незаметный */
  --warn:#d9a441;        /* предупреждение */
  --alarm:#cf5a4e;       /* авария */
  --liquid:#6d9bb5;      /* жидкостная линия */
  --suction:#8aa6b0;     /* всасывание */
  --discharge:#b5806d;   /* нагнетание */
  --hotgas:#c98f4e;      /* горячий пар оттайки */
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:#25292c;color:var(--text);
  font-family:"IBM Plex Sans Condensed",system-ui,sans-serif}
body{padding:12px;font-size:14px}
.num{font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}

/* ---------- шапка ---------- */
header{display:flex;align-items:center;gap:18px;flex-wrap:wrap;
  background:var(--panel);border:1px solid var(--line-dim);padding:10px 14px;margin-bottom:10px}
h1{font-size:15px;font-weight:600;margin:0;letter-spacing:.04em;text-transform:uppercase}
h1 span{color:var(--text-dim);font-weight:400;text-transform:none;letter-spacing:0}
.scen{display:flex;gap:0;border:1px solid var(--line-dim)}
.scen button{background:var(--panel-2);color:var(--text-dim);border:0;
  border-right:1px solid var(--line-dim);padding:6px 14px;cursor:pointer;
  font-family:inherit;font-size:13px}
.scen button:last-child{border-right:0}
.scen button[aria-pressed="true"]{background:var(--line);color:#1c1f21;font-weight:600}
.scen button:focus-visible{outline:2px solid var(--warn);outline-offset:-2px}
.status{margin-left:auto;display:flex;align-items:center;gap:10px}
.badge{padding:5px 12px;border:1px solid var(--line);letter-spacing:.08em;
  font-weight:600;font-size:13px}
.badge.norm{border-color:var(--line-dim);color:var(--text-dim)}
.badge.warn{border-color:var(--warn);color:var(--warn)}
.badge.alarm{border-color:var(--alarm);color:var(--alarm);background:rgba(207,90,78,.12)}
.clock{font-size:20px;font-weight:500}

/* ---------- сетка ---------- */
.grid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:10px}
.card{background:var(--panel);border:1px solid var(--line-dim)}
.card h2{font-size:11px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
  color:var(--text-dim);margin:0;padding:7px 12px;border-bottom:1px solid var(--line-dim)}
.card .body{padding:8px}

/* ---------- мнемосхема ---------- */
svg.mimic{width:100%;height:auto;display:block;background:var(--bg)}
.eq{fill:var(--fill);stroke:var(--line);stroke-width:1.4}
.eq.off{fill:#3f4448;stroke:var(--line-dim)}
.eq.alarm{stroke:var(--alarm);stroke-width:2.2}
.eq.warn{stroke:var(--warn);stroke-width:2}
.tag{font:600 11px "IBM Plex Sans Condensed";fill:var(--text-dim);letter-spacing:.06em}
.val{font:500 13px "IBM Plex Mono";fill:var(--text)}
.val.sm{font-size:11px}
.unit{font:400 10px "IBM Plex Sans Condensed";fill:var(--text-dim)}
.val.alarm{fill:var(--alarm)}
.val.warn{fill:var(--warn)}
.pipe{fill:none;stroke-width:2.5;stroke-linecap:round}
.pipe.dash{stroke-dasharray:7 6}
.lvl{fill:var(--liquid);opacity:.55}
.lvl.hi{fill:var(--alarm);opacity:.5}
.lvl.lo{fill:var(--warn);opacity:.5}
.zone{fill:none;stroke:var(--line-dim);stroke-width:1;stroke-dasharray:3 4}
.zonelbl{font:500 10px "IBM Plex Sans Condensed";fill:var(--text-dim);letter-spacing:.1em}

/* ---------- тревоги ---------- */
.alist{max-height:330px;overflow-y:auto}
.arow{display:grid;grid-template-columns:52px 1fr;gap:8px;padding:6px 10px;
  border-bottom:1px solid var(--panel-2);font-size:12.5px;line-height:1.35}
.arow .t{color:var(--text-dim);font-family:"IBM Plex Mono";font-size:11.5px}
.arow.p1{border-left:3px solid var(--alarm)}
.arow.p2{border-left:3px solid var(--warn)}
.arow.p3{border-left:3px solid var(--line-dim)}
.empty{padding:16px 12px;color:var(--text-dim);font-size:12.5px}

/* ---------- сводка ---------- */
.kv{display:grid;grid-template-columns:1fr auto;gap:2px 10px;padding:8px 12px;font-size:12.5px}
.kv dt{color:var(--text-dim)}
.kv dd{margin:0;font-family:"IBM Plex Mono";font-size:12.5px}
.kv dd.bad{color:var(--alarm)}

/* ---------- шкала времени ---------- */
.timeline{margin-top:10px}
.tl-row{display:flex;align-items:center;gap:12px;padding:8px 12px}
.tl-row button{background:var(--panel-2);color:var(--text);border:1px solid var(--line-dim);
  width:38px;height:30px;cursor:pointer;font-size:14px;font-family:inherit}
.tl-row button:focus-visible{outline:2px solid var(--warn);outline-offset:1px}
input[type=range]{flex:1;accent-color:var(--line);height:26px}
.speed{background:var(--panel-2);color:var(--text);border:1px solid var(--line-dim);
  padding:5px 8px;font-family:inherit;font-size:12.5px}
.marks{position:relative;height:26px;margin:0 12px 6px 62px}
.mark{position:absolute;top:0;width:1px;height:12px;background:var(--warn)}
.mark.crit{background:var(--alarm);height:18px;width:2px}
.mark span{position:absolute;left:3px;top:-1px;font-size:10px;color:var(--text-dim);
  white-space:nowrap}

/* ---------- тренды ---------- */
.trends{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:10px;margin-top:10px}
canvas{width:100%;height:150px;display:block}
.legend{display:flex;gap:12px;flex-wrap:wrap;padding:0 12px 8px;font-size:11.5px;color:var(--text-dim)}
.legend i{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:5px}
footer{margin-top:12px;color:var(--text-dim);font-size:11.5px;line-height:1.6}
@media (max-width:900px){.grid{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>

<header>
  <h1>NH3Ops <span>— цифровой двойник аммиачной холодильной установки молокозавода</span></h1>
  <div class="scen" role="group" aria-label="Сценарий">
    <button id="btn-normal" aria-pressed="true">Штатный режим</button>
    <button id="btn-d1" aria-pressed="false">D1 · Гидроудар</button>
  </div>
  <div class="status">
    <span class="clock num" id="clock">00:00:00</span>
    <span class="badge norm" id="badge">НОРМА</span>
  </div>
</header>

<div class="grid">
  <div class="card">
    <h2 id="mimic-title">Мнемосхема — двухступенчатая насосно-циркуляционная схема, R717</h2>
    <div class="body" style="padding:0">
      <svg class="mimic" viewBox="0 0 1240 600" role="img" aria-label="Мнемосхема установки">
        <!-- зоны -->
        <rect class="zone" x="12" y="360" width="500" height="226"/>
        <text class="zonelbl" x="20" y="376">ХОЛОДИЛЬНЫЕ КАМЕРЫ И КОНТУР ЛЕДЯНОЙ ВОДЫ</text>
        <rect class="zone" x="528" y="12" width="700" height="336"/>
        <text class="zonelbl" x="536" y="28">МАШИННЫЙ ЗАЛ</text>

        <!-- ================= ИСПАРИТЕЛИ ================= -->
        <g id="g-EV-01"></g><g id="g-EV-02"></g><g id="g-EV-03"></g>
        <g id="g-EV-04"></g><g id="g-EV-05"></g><g id="g-EV-06"></g>

        <!-- ================= ТРУБОПРОВОДЫ ================= -->
        <!-- всасывание НД: испарители -> VE-LP -->
        <path id="p-lp-suc" class="pipe dash" stroke="var(--suction)"
              d="M 300 400 L 470 400 L 470 250 L 545 250"/>
        <!-- всасывание СД -->
        <path id="p-ip-suc" class="pipe dash" stroke="var(--suction)"
              d="M 300 470 L 500 470 L 500 320 L 700 320 L 700 250 L 745 250"/>
        <!-- НД компрессоры -> VE-IP -->
        <path id="p-lp-dis" class="pipe dash" stroke="var(--discharge)"
              d="M 620 210 L 620 150 L 700 150 L 700 210 L 745 210"/>
        <!-- ВД компрессоры -> конденсаторы -->
        <path id="p-hp-dis" class="pipe dash" stroke="var(--discharge)"
              d="M 900 210 L 900 100 L 1010 100"/>
        <!-- конденсаторы -> ресивер -->
        <path id="p-cond-liq" class="pipe dash" stroke="var(--liquid)"
              d="M 1130 130 L 1170 130 L 1170 200"/>
        <!-- ресивер -> VE-IP (LV-IP) -->
        <path id="p-hp-ip" class="pipe dash" stroke="var(--liquid)"
              d="M 1120 250 L 1000 250 L 1000 285 L 845 285"/>
        <!-- VE-IP -> VE-LP (LV-LP) -->
        <path id="p-ip-lp" class="pipe dash" stroke="var(--liquid)"
              d="M 745 285 L 660 285 L 660 300 L 645 300"/>
        <!-- VE-LP -> испарители (насос) -->
        <path id="p-lp-feed" class="pipe dash" stroke="var(--liquid)"
              d="M 560 300 L 530 300 L 530 440 L 300 440"/>
        <!-- VE-IP -> испарители (насос) -->
        <path id="p-ip-feed" class="pipe dash" stroke="var(--liquid)"
              d="M 760 300 L 760 345 L 515 345 L 515 510 L 300 510"/>
        <!-- горячий пар на оттайку -->
        <path id="p-hotgas" class="pipe dash" stroke="var(--hotgas)" opacity="0.25"
              d="M 940 100 L 940 360 L 250 360 L 250 380"/>

        <!-- подписи линий -->
        <text class="tag" x="352" y="393">ВСАС. НД</text>
        <text class="tag" x="352" y="463">ВСАС. СД</text>
        <text class="tag" x="352" y="433">ПОДАЧА НД</text>
        <text class="tag" x="352" y="503">ПОДАЧА СД</text>
        <text class="tag" x="266" y="356">ГОР. ПАР</text>

        <!-- ================= СОСУДЫ ================= -->
        <g id="g-VE-LP"></g><g id="g-VE-IP"></g><g id="g-VE-HP"></g>
        <!-- ================= КОМПРЕССОРЫ ================= -->
        <g id="g-CO-01"></g><g id="g-CO-02"></g><g id="g-CO-03"></g><g id="g-CO-04"></g>
        <!-- ================= КОНДЕНСАТОРЫ ================= -->
        <g id="g-CD"></g>
        <!-- ================= ГАЗОВЫЙ КОНТРОЛЬ ================= -->
        <g id="g-gas"></g>
      </svg>
    </div>
  </div>

  <div>
    <div class="card">
      <h2>Активные тревоги</h2>
      <div class="alist" id="alarms"><div class="empty">Активных тревог нет</div></div>
    </div>
    <div class="card" style="margin-top:10px">
      <h2>Технологический контроль</h2>
      <dl class="kv" id="kv"></dl>
    </div>
  </div>
</div>

<div class="card timeline">
  <h2>Хронология прогона</h2>
  <div class="marks" id="marks"></div>
  <div class="tl-row">
    <button id="play" aria-label="Воспроизведение">▶</button>
    <input type="range" id="scrub" min="0" max="100" value="0" aria-label="Время прогона">
    <select class="speed" id="speed" aria-label="Скорость">
      <option value="1">1×</option><option value="4" selected>4×</option>
      <option value="16">16×</option><option value="60">60×</option>
    </select>
  </div>
</div>

<div class="trends" id="trends"></div>

<footer id="foot"></footer>

<script>
const RUNS = __DATA__;
let cur = "normal", idx = 0, playing = false, timer = null;

/* ============ утилиты ============ */
const $ = s => document.querySelector(s);
const NS = "http://www.w3.org/2000/svg";
function el(t, a, parent){const e=document.createElementNS(NS,t);
  for(const k in a) e.setAttribute(k,a[k]); if(parent) parent.appendChild(e); return e;}
function txt(parent,x,y,s,cls,extra){const t=el("text",Object.assign({x,y,class:cls||"val"},extra||{}),parent);
  t.textContent=s; return t;}
const col = k => RUNS[cur].cols[k];
const v = k => {const c=col(k); return c ? c[Math.min(idx,c.length-1)] : null;};
function fmt(x,d){return x===null||x===undefined?"—":Number(x).toFixed(d===undefined?1:d);}
function hhmmss(h){const s=Math.round(h*3600);
  return String(Math.floor(s/3600)).padStart(2,"0")+":"+
         String(Math.floor(s/60)%60).padStart(2,"0")+":"+String(s%60).padStart(2,"0");}

/* ============ построение мнемосхемы ============ */
const EVAPS = [
  {tag:"EV-01", x:60,  y:490, w:240, h:40, name:"Ледяная вода",  src:"СД"},
  {tag:"EV-02", x:60,  y:440, w:240, h:40, name:"Камера +2 °C",  src:"СД"},
  {tag:"EV-03", x:60,  y:390, w:115, h:40, name:"НТ-склад A",    src:"НД"},
  {tag:"EV-04", x:185, y:390, w:115, h:40, name:"НТ-склад Б",    src:"НД"},
  {tag:"EV-05", x:60,  y:540, w:115, h:40, name:"Морозильник A", src:"НД"},
  {tag:"EV-06", x:185, y:540, w:115, h:40, name:"Морозильник Б", src:"НД"},
];
const VESSELS = [
  {tag:"VE-LP", x:545, y:225, w:100, h:150, name:"Циркуляц. ресивер НД", set:"−40 °C"},
  {tag:"VE-IP", x:745, y:195, w:100, h:150, name:"Циркуляц. ресивер СД", set:"−10 °C"},
  {tag:"VE-HP", x:1120,y:200, w:100, h:130, name:"Линейный ресивер",     set:"конденсат"},
];
const COMPS = [
  {tag:"CO-01", x:560, y:165, st:"НД"}, {tag:"CO-02", x:560, y:60, st:"НД"},
  {tag:"CO-03", x:840, y:165, st:"ВД"}, {tag:"CO-04", x:840, y:60, st:"ВД"},
];

function buildStatic(){
  /* испарители */
  EVAPS.forEach(e=>{
    const g=$("#g-"+e.tag); g.innerHTML="";
    el("rect",{x:e.x,y:e.y,width:e.w,height:e.h,class:"eq",id:"r-"+e.tag},g);
    /* оребрение — узнаваемый символ воздухоохладителя */
    for(let i=1;i<6;i++){
      const xx=e.x+e.w*i/6;
      el("line",{x1:xx,y1:e.y+4,x2:xx,y2:e.y+e.h-4,stroke:"var(--line-dim)","stroke-width":1},g);
    }
    txt(g,e.x+3,e.y-4,e.tag+"  "+e.name,"tag");
    txt(g,e.x+e.w-4,e.y+16,"","val sm",{"text-anchor":"end",id:"m-"+e.tag});
    txt(g,e.x+e.w-4,e.y+32,"","val sm",{"text-anchor":"end",id:"p-"+e.tag});
  });
  /* сосуды */
  VESSELS.forEach(s=>{
    const g=$("#g-"+s.tag); g.innerHTML="";
    el("rect",{x:s.x,y:s.y,width:s.w,height:s.h,rx:14,class:"eq",id:"r-"+s.tag},g);
    el("rect",{x:s.x+1,y:s.y,width:s.w-2,height:0,rx:8,class:"lvl",id:"l-"+s.tag},g);
    txt(g,s.x,s.y-18,s.tag,"tag");
    txt(g,s.x,s.y-6,s.name,"unit");
    txt(g,s.x+s.w/2,s.y+s.h/2-8,"","val",{"text-anchor":"middle",id:"pv-"+s.tag});
    txt(g,s.x+s.w/2,s.y+s.h/2+8,"","val sm",{"text-anchor":"middle",id:"tv-"+s.tag});
    txt(g,s.x+s.w/2,s.y+s.h/2+26,"","val sm",{"text-anchor":"middle",id:"lv-"+s.tag});
  });
  /* компрессоры */
  COMPS.forEach(c=>{
    const g=$("#g-"+c.tag); g.innerHTML="";
    el("circle",{cx:c.x+30,cy:c.y+22,r:22,class:"eq",id:"r-"+c.tag},g);
    el("path",{d:`M ${c.x+20} ${c.y+12} L ${c.x+42} ${c.y+22} L ${c.x+20} ${c.y+32} Z`,
      fill:"var(--line-dim)",id:"t-"+c.tag},g);
    txt(g,c.x+58,c.y+12,c.tag,"tag");
    txt(g,c.x+58,c.y+26,"","val sm",{id:"s-"+c.tag});
    txt(g,c.x+58,c.y+40,"","val sm",{id:"k-"+c.tag});
  });
  /* конденсаторы */
  const g=$("#g-CD"); g.innerHTML="";
  [0,1].forEach(i=>{
    const x=1010+i*62, y=60;
    el("rect",{x,y,width:54,height:70,class:"eq",id:"r-CD-0"+(i+1)},g);
    for(let j=0;j<3;j++) el("line",{x1:x+6,y1:y+16+j*18,x2:x+48,y2:y+16+j*18,
      stroke:"var(--line-dim)","stroke-width":1},g);
    txt(g,x,y-6,"CD-0"+(i+1),"tag");
  });
  txt(g,1010,150,"","val sm",{id:"cd-info"});
  txt(g,1010,166,"","val sm",{id:"cd-info2"});
  /* газовый контроль */
  const gg=$("#g-gas"); gg.innerHTML="";
  el("rect",{x:545,y:400,width:200,height:56,class:"eq",id:"r-gas-mr"},gg);
  txt(gg,553,418,"AT-01  МАШЗАЛ, NH₃","tag");
  txt(gg,553,442,"","val",{id:"gas-mr"});
  el("rect",{x:760,y:400,width:200,height:56,class:"eq",id:"r-gas-hall"},gg);
  txt(gg,768,418,"AT-02  ЦЕХ, NH₃","tag");
  txt(gg,768,442,"","val",{id:"gas-hall"});
  el("rect",{x:975,y:400,width:250,height:56,class:"eq",id:"r-rel"},gg);
  txt(gg,983,418,"ВЫБРОС В АТМОСФЕРУ","tag");
  txt(gg,983,442,"","val",{id:"rel-kg"});
}

/* ============ обновление кадра ============ */
function setCls(id,cls){const e=document.getElementById(id); if(e) e.setAttribute("class",cls);}
function setTxt(id,s,cls){const e=document.getElementById(id); if(!e)return;
  e.textContent=s; if(cls!==undefined) e.setAttribute("class",cls);}

const MODE_RU={COOL:"ОХЛАЖД.",PUMPDOWN:"ОСУШЕНИЕ",HOTGAS:"ОТТАЙКА",
  DRAIN:"СЛИВ",EQUALIZE:"ВЫРАВН.",IDLE:"СТОП"};

function render(){
  const R=RUNS[cur];
  $("#clock").textContent=hhmmss(v("TIME_H")-R.cols.TIME_H[0]);

  /* --- испарители --- */
  EVAPS.forEach(e=>{
    const mode=v(e.tag+"_MODE")||"COOL", P=v(e.tag+"_P"), Tm=v(e.tag+"_TMETAL");
    setTxt("m-"+e.tag, MODE_RU[mode]||mode, mode==="HOTGAS"?"val sm warn":"val sm");
    setTxt("p-"+e.tag, fmt(P,2)+" бар · "+fmt(Tm,0)+" °C", "val sm");
    let cls="eq";
    if(mode==="HOTGAS"||mode==="DRAIN") cls="eq warn";
    if(mode==="IDLE") cls="eq off";
    setCls("r-"+e.tag,cls);
  });

  /* --- сосуды --- */
  const lvKeys={"VE-LP":"LEVEL_VE_LP","VE-IP":"LEVEL_VE_IP","VE-HP":"LEVEL_VE_HP"};
  const pKeys={"VE-LP":"P_SUC_LP","VE-IP":"P_SUC_IP","VE-HP":"P_COND"};
  const tKeys={"VE-LP":"T_EVAP_LP","VE-IP":"T_EVAP_IP","VE-HP":"T_COND"};
  VESSELS.forEach(s=>{
    const L=v(lvKeys[s.tag]), P=v(pKeys[s.tag]), T=v(tKeys[s.tag]);
    const h=Math.max(0,Math.min(100,L))/100*s.h;
    const bar=document.getElementById("l-"+s.tag);
    bar.setAttribute("y",s.y+s.h-h); bar.setAttribute("height",h);
    let lcls="lvl", ecls="eq";
    if(L>75){lcls="lvl hi"; ecls="eq alarm";} else if(L<20){lcls="lvl lo"; ecls="eq warn";}
    bar.setAttribute("class",lcls); setCls("r-"+s.tag,ecls);
    setTxt("pv-"+s.tag, fmt(P,2)+" бар");
    setTxt("tv-"+s.tag, fmt(T,1)+" °C","val sm");
    setTxt("lv-"+s.tag, "L "+fmt(L,0)+" %","val sm"+(L>75?" alarm":L<20?" warn":""));
  });

  /* --- компрессоры --- */
  COMPS.forEach(c=>{
    const run=v(c.tag+"_RUN"), sl=v(c.tag+"_SLIDE"), kw=v(c.tag+"_KW"), td=v(c.tag+"_TDIS");
    setCls("r-"+c.tag, run? (td>95?"eq alarm":"eq") : "eq off");
    document.getElementById("t-"+c.tag)
      .setAttribute("fill", run?"var(--ok)":"var(--line-dim)");
    setTxt("s-"+c.tag, run? ("золотник "+fmt(sl,0)+" %") : "остановлен",
      run?"val sm":"val sm");
    setTxt("k-"+c.tag, run? (fmt(kw,0)+" кВт · "+fmt(td,0)+" °C") : "",
      td>95?"val sm alarm":"val sm");
  });

  /* --- конденсаторы --- */
  setTxt("cd-info", "Отвод "+fmt(v("Q_REJ_KW"),0)+" кВт");
  setTxt("cd-info2","T конд. "+fmt(v("T_COND"),1)+" °C");

  /* --- газовый контроль --- */
  const mr=v("NH3_MACHINEROOM_PPM"), hall=v("NH3_HALL_PPM"), rel=v("NH3_RELEASED_KG");
  setTxt("gas-mr", fmt(mr,0)+" ppm", mr>300?"val alarm":mr>25?"val warn":"val");
  setCls("r-gas-mr", mr>300?"eq alarm":mr>25?"eq warn":"eq");
  setTxt("gas-hall", fmt(hall,0)+" ppm", hall>50?"val alarm":hall>25?"val warn":"val");
  setCls("r-gas-hall", hall>50?"eq alarm":hall>25?"eq warn":"eq");
  setTxt("rel-kg", fmt(rel,0)+" кг", rel>100?"val alarm":rel>0?"val warn":"val");
  setCls("r-rel", rel>100?"eq alarm":rel>0?"eq warn":"eq");

  /* --- анимация потоков: скорость пропорциональна расходу --- */
  const anim=(id,active,speed)=>{const p=document.getElementById(id); if(!p)return;
    p.style.opacity = active? 1 : .18;
    p.style.animation = active? `flow ${Math.max(.35,2.2/Math.max(speed,.2))}s linear infinite` : "none";};
  const lpRun=(v("CO-01_RUN")||0)+(v("CO-02_RUN")||0);
  const hpRun=(v("CO-03_RUN")||0)+(v("CO-04_RUN")||0);
  anim("p-lp-suc",lpRun>0,lpRun); anim("p-lp-dis",lpRun>0,lpRun);
  anim("p-ip-suc",hpRun>0,hpRun); anim("p-hp-dis",hpRun>0,hpRun);
  anim("p-cond-liq",hpRun>0,hpRun); anim("p-hp-ip",hpRun>0,1);
  anim("p-ip-lp",lpRun>0,1); anim("p-lp-feed",lpRun>0,1); anim("p-ip-feed",hpRun>0,1);
  const anyHot=EVAPS.some(e=>v(e.tag+"_MODE")==="HOTGAS");
  anim("p-hotgas",anyHot,1);

  renderAlarms(); renderKV(); renderBadge(); drawTrends();
}

/* --- тревоги на текущий момент --- */
function renderAlarms(){
  const R=RUNS[cur], t=v("TIME_H")*3600 - R.cols.TIME_H[0]*3600;
  const act=new Map();
  R.alarms.forEach(a=>{
    if(a.t>t+0.5) return;
    if(a.act==="RAISE") act.set(a.tag,a);
    else if(a.act==="CLEAR") act.delete(a.tag);
  });
  const box=$("#alarms");
  if(!act.size){box.innerHTML='<div class="empty">Активных тревог нет</div>'; return;}
  const pr=tag=>/NH3|ESD|RUPTURE|SHOCK|PRV|HP_TRIP|TDIS|HACCP|HIHI/.test(tag)?1:
    /CUTOUT|OIL/.test(tag)?3:2;
  box.innerHTML=[...act.values()].sort((a,b)=>pr(a.tag)-pr(b.tag))
    .map(a=>`<div class="arow p${pr(a.tag)}"><span class="t">${hhmmss(a.t/3600)
      .slice(3)}</span><span>${a.text||a.tag}</span></div>`).join("");
}

/* --- технологический контроль --- */
function renderKV(){
  const rows=[
    ["Молоко в танке", fmt(v("T_MILK"),2)+" °C", v("T_MILK")>6],
    ["Ледяная вода",   fmt(v("T_ICEWATER"),2)+" °C", v("T_ICEWATER")>4],
    ["Запас льда",     fmt(v("M_ICE_T"),1)+" т", false],
    ["Камера +2 °C",   fmt(v("T_ROOM_CHILL"),1)+" °C", v("T_ROOM_CHILL")>6],
    ["НТ-склад",       fmt(v("T_ROOM_LT"),1)+" °C", v("T_ROOM_LT")>-15],
    ["Морозильник",    fmt(v("T_ROOM_BLAST"),1)+" °C", v("T_ROOM_BLAST")>-24],
    ["Потребление",    fmt(v("POWER_KW"),0)+" кВт", false],
    ["Аварийный останов", v("ESD")?"АКТИВЕН":"нет", !!v("ESD")],
  ];
  $("#kv").innerHTML=rows.map(r=>
    `<dt>${r[0]}</dt><dd class="${r[2]?'bad':''}">${r[1]}</dd>`).join("");
}

function renderBadge(){
  const b=$("#badge"), R=RUNS[cur];
  const t=(v("TIME_H")-R.cols.TIME_H[0])*3600;
  const crit=R.events.some(e=>e.t<=t && /RUPTURE|ESD|SHOCK/.test(e.text));
  const rel=v("NH3_RELEASED_KG")>0.5, esd=v("ESD");
  if(crit||rel||esd){b.className="badge alarm"; b.textContent="АВАРИЯ";}
  else if(v("NH3_MACHINEROOM_PPM")>25||EVAPS.some(e=>v(e.tag+"_MODE")==="HOTGAS")){
    b.className="badge warn"; b.textContent="ОТКЛОНЕНИЕ";}
  else {b.className="badge norm"; b.textContent="НОРМА";}
}

/* ============ тренды ============ */
const TRENDS=[
  {title:"Давления, бар абс", series:[
    ["P_SUC_LP","НД","#8aa6b0"],["P_SUC_IP","СД","#6d9bb5"],["P_COND","конденсации","#b5806d"]]},
  {title:"Уровни в сосудах, %", series:[
    ["LEVEL_VE_LP","VE-LP","#8aa6b0"],["LEVEL_VE_IP","VE-IP","#6d9bb5"],
    ["LEVEL_VE_HP","VE-HP","#b5806d"]]},
  {title:"Температуры камер, °C", series:[
    ["T_ROOM_CHILL","+2 °C","#7fa88a"],["T_ROOM_LT","НТ-склад","#6d9bb5"],
    ["T_ROOM_BLAST","морозильник","#8aa6b0"]]},
  {title:"Аммиак и продукт", series:[
    ["NH3_MACHINEROOM_PPM","машзал, ppm","#cf5a4e"],
    ["NH3_RELEASED_KG","выброс, кг","#d9a441"],
    ["T_MILK","молоко, °C","#7fa88a"]]},
];
function buildTrends(){
  $("#trends").innerHTML=TRENDS.map((t,i)=>
    `<div class="card"><h2>${t.title}</h2><canvas id="cv${i}"></canvas>
     <div class="legend">${t.series.map(s=>
       `<span><i style="background:${s[2]}"></i>${s[1]}</span>`).join("")}</div></div>`).join("");
}
function drawTrends(){
  const R=RUNS[cur], n=R.n;
  TRENDS.forEach((t,i)=>{
    const cv=document.getElementById("cv"+i); if(!cv) return;
    const dpr=window.devicePixelRatio||1, W=cv.clientWidth, H=150;
    cv.width=W*dpr; cv.height=H*dpr;
    const g=cv.getContext("2d"); g.setTransform(dpr,0,0,dpr,0,0);
    g.clearRect(0,0,W,H);
    const pad={l:44,r:8,t:10,b:16};
    let lo=Infinity, hi=-Infinity;
    t.series.forEach(s=>{const c=R.cols[s[0]]; if(!c)return;
      c.forEach(x=>{if(x<lo)lo=x; if(x>hi)hi=x;});});
    if(!isFinite(lo)){lo=0;hi=1;}
    if(hi-lo<1e-6){hi=lo+1;}
    const pd=(hi-lo)*0.08; lo-=pd; hi+=pd;
    const X=k=>pad.l+(W-pad.l-pad.r)*k/Math.max(n-1,1);
    const Y=y=>pad.t+(H-pad.t-pad.b)*(1-(y-lo)/(hi-lo));
    /* сетка */
    g.strokeStyle="#4a5054"; g.lineWidth=1; g.font='10px "IBM Plex Mono"';
    g.fillStyle="#a7aeb2";
    for(let j=0;j<=3;j++){
      const yv=lo+(hi-lo)*j/3, y=Y(yv);
      g.beginPath(); g.moveTo(pad.l,y); g.lineTo(W-pad.r,y); g.stroke();
      g.fillText(yv.toFixed(Math.abs(hi-lo)<10?1:0), 4, y+3);
    }
    /* кривые */
    t.series.forEach(s=>{
      const c=R.cols[s[0]]; if(!c) return;
      g.strokeStyle=s[2]; g.lineWidth=1.6; g.beginPath();
      c.forEach((y,k)=>{k?g.lineTo(X(k),Y(y)):g.moveTo(X(k),Y(y));});
      g.stroke();
    });
    /* курсор */
    g.strokeStyle="#e6e9ea"; g.lineWidth=1; g.setLineDash([3,3]);
    g.beginPath(); g.moveTo(X(idx),pad.t); g.lineTo(X(idx),H-pad.b); g.stroke();
    g.setLineDash([]);
  });
}

/* ============ шкала времени и события ============ */
function buildMarks(){
  const R=RUNS[cur], T=(R.cols.TIME_H[R.n-1]-R.cols.TIME_H[0])*3600||1;
  const keep=R.events.filter(e=>/FAULT ACTIVE|F-CTRL|RUPTURE|SHOCK|ESD|оттайки|BARRIER|кавитация/.test(e.text));
  $("#marks").innerHTML=keep.slice(0,14).map(e=>{
    const crit=/RUPTURE|SHOCK|ESD/.test(e.text);
    const label=e.text.replace(/^FAULT ACTIVE: /,"").replace(/ \(.*\)$/,"").slice(0,34);
    return `<span class="mark${crit?' crit':''}" style="left:${(e.t/T*100).toFixed(2)}%">
      <span>${label}</span></span>`;}).join("");
}

function setScenario(name){
  cur=name; idx=0;
  $("#btn-normal").setAttribute("aria-pressed", name==="normal");
  $("#btn-d1").setAttribute("aria-pressed", name==="d1");
  $("#mimic-title").textContent="Мнемосхема — "+RUNS[name].title;
  $("#scrub").max=RUNS[name].n-1; $("#scrub").value=0;
  const s=RUNS[name].summary;
  $("#foot").innerHTML=
    `Исход прогона: CAT ${s.CAT.length?s.CAT.join(", "):"нет"} · `+
    `MAJ ${s.MAJ.length?s.MAJ.join(", "):"нет"} · выброс ${s.released_kg} кг · `+
    `разрушено ${s.ruptured.length?s.ruptured.join(", "):"нет"} · `+
    `гидроударов ${s.shock_events}<br>`+
    `Шаг интегрирования 0.5 с, RK4. Цвет по ISA-101: отклонение — янтарный, `+
    `авария — красный; штатное состояние цветом не выделяется.`;
  buildMarks(); render();
}

/* ============ управление ============ */
function tick(){
  const sp=parseInt($("#speed").value,10);
  idx+=Math.max(1,Math.round(sp/4));
  if(idx>=RUNS[cur].n){idx=RUNS[cur].n-1; stop();}
  $("#scrub").value=idx; render();
}
function play(){playing=true; $("#play").textContent="❚❚";
  timer=setInterval(tick, 120);}
function stop(){playing=false; $("#play").textContent="▶"; clearInterval(timer);}

$("#play").onclick=()=>playing?stop():play();
$("#scrub").oninput=e=>{idx=+e.target.value; render();};
$("#btn-normal").onclick=()=>{stop(); setScenario("normal");};
$("#btn-d1").onclick=()=>{stop(); setScenario("d1");};
$("#speed").onchange=()=>{if(playing){stop();play();}};
window.addEventListener("resize", drawTrends);

/* стиль анимации потоков */
const st=document.createElement("style");
st.textContent="@keyframes flow{to{stroke-dashoffset:-26}}";
document.head.appendChild(st);

buildStatic(); buildTrends(); setScenario("normal");
</script>
</body>
</html>"""

out = HTML.replace("__DATA__", DATA)
path = "/mnt/user-data/outputs/nh3twin-hmi.html"
os.makedirs(os.path.dirname(path), exist_ok=True)
open(path, "w", encoding="utf-8").write(out)
print("записано:", path, round(len(out) / 1024), "КБ")
