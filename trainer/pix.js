// ===================== ПИКСЕЛЬНАЯ КАРТИНА УСТАНОВКИ (v2) =====================
// 384x216 логических пикселей. Рисуется процедурно, только из тех данных,
// что видны программе-испытуемому. Трубная обвязка анимирована потоками,
// обходчики ходят по коридорам в реальном времени раздумий.

const PIX = (function(){
  const W=384, H=216, SPINE=158;
  let S=3, cv=null, cx=null, off=null, ox=null, obs=null, fc=0, open=true;
  let bg=null, bgReady=false, sel=null;
  const wpos={};   // последние координаты обходчиков для попадания кликом

  // ---------- палитра ----------
  const C={
    yard:"#26292d", yard2:"#2b2f33",
    wallTop:"#171a1d", wallFace:"#343b41", wallHi:"#4c545c",
    cor:"#3b4046", corStripe:"#454b51",
    mr:"#4a5158", mr2:"#454c53", roof:"#3f464d", roof2:"#3a4148",
    hall:"#544e46", hall2:"#4e4841", ctrl:"#4a564d", ctrl2:"#445046",
    lt:"#57697a", lt2:"#516274", blast:"#4c6072", blast2:"#465a6c",
    asm:"#3d5540", asm2:"#38503b",
    steelL:"#aab3ba", steel:"#7c858d", steelD:"#4e565e", body:"#3f454b",
    run:"#83b28e", warn:"#e0ac45", bad:"#d4584a",
    liq:"#5f9ec2", suc:"#8fa8b4", hot:"#d98a3f",
    haze:"#86df8f", frost:"#cfe0ee", white:"#e8ecef",
    skin:"#e0b58a", mask:"#4fd1c5", grey:"#9aa0a6", pants:"#33383d",
    vest:"#d97f36", vest2:"#5f8fc2", stripe:"#ffe08a",
    milk:"#cfe3d5", milkBad:"#d98b7f", glass:"#7fb0c9"
  };

  // ---------- планировка ----------
  const ZONES={
    ROOF:{x:8,y:6,w:192,h:40,f:C.roof,f2:C.roof2,lbl:"КРОВЛЯ"},
    MACHINE_ROOM:{x:8,y:54,w:180,h:96,f:C.mr,f2:C.mr2,lbl:"МАШИННОЕ ОТДЕЛЕНИЕ"},
    CONTROL_ROOM:{x:210,y:88,w:60,h:46,f:C.ctrl,f2:C.ctrl2,lbl:"ЩИТОВАЯ"},
    HALL:{x:278,y:54,w:98,h:96,f:C.hall,f2:C.hall2,lbl:"ЦЕХ"},
    LT_STORE:{x:210,y:172,w:78,h:40,f:C.lt,f2:C.lt2,lbl:"НТ-СКЛАД −20°"},
    BLAST:{x:296,y:172,w:80,h:40,f:C.blast,f2:C.blast2,lbl:"МОРОЗИЛЬНАЯ −30°"},
    ASSEMBLY_POINT:{x:8,y:176,w:66,h:34,f:C.asm,f2:C.asm2,lbl:"СБОРНЫЙ ПУНКТ"}
  };
  const DOORS=[ [100,150,12,4],[186,150,8,4],[236,134,10,4],[236,150,10,8],
    [322,150,12,4],[244,168,10,4],[332,168,10,4],[38,172,10,4] ];

  const CH={
    MACHINE_ROOM:[[106,140],[106,SPINE]],
    CONTROL_ROOM:[[240,118],[240,SPINE]],
    HALL:[[328,132],[328,SPINE]],
    LT_STORE:[[249,192],[249,SPINE]],
    BLAST:[[337,192],[337,SPINE]],
    ASSEMBLY_POINT:[[40,194],[40,SPINE]],
    OUTSIDE:[[16,160],[16,SPINE]],
    ROOF:[[56,30],[194,30],[194,SPINE]]
  };

  // ---------- база ----------
  function px(x,y,c){ ox.fillStyle=c; ox.fillRect(x|0,y|0,1,1); }
  function rc(x,y,w,h,c){ ox.fillStyle=c; ox.fillRect(x,y,w,h); }
  function frame(x,y,w,h,c){ rc(x,y,w,1,c); rc(x,y+h-1,w,1,c);
    rc(x,y,1,h,c); rc(x+w-1,y,1,h,c); }
  function rnd(n){ let s=(n*1103515245+12345)&0x7fffffff; return (s%1000)/1000; }
  function dither(x,y,w,h,c1,c2){
    rc(x,y,w,h,c1);
    for(let j=y;j<y+h;j++) for(let i=x+(j&1);i<x+w;i+=2) px(i,j,c2);
  }

  // ---------- трубы ----------
  function pipe(pts, color, opt){
    opt=opt||{};
    const dashOn=opt.dash||0, sp=opt.anim?(opt.speed||1):0;
    let dist=0;
    for(let s2=1;s2<pts.length;s2++){
      const [x0,y0]=pts[s2-1], [x1,y1]=pts[s2];
      const dx=Math.sign(x1-x0), dy=Math.sign(y1-y0);
      const len=Math.abs(x1-x0)+Math.abs(y1-y0);
      for(let i=0;i<=len;i++){
        const xx=x0+dx*i, yy=y0+dy*i, d=dist+i;
        if(dashOn){
          const ph=((d - ((fc*sp)>>1)) % (dashOn*2) + dashOn*2)%(dashOn*2);
          if(ph<dashOn) px(xx,yy,color); else px(xx,yy,opt.back||"#31363b");
        } else {
          px(xx,yy,color);
          if(opt.anim && ((d-((fc*sp)>>1))%7+7)%7===0) px(xx,yy,C.white);
        }
      }
      dist+=len;
    }
  }
  function valve(x,y,c){ px(x-1,y-1,c); px(x-1,y+1,c); px(x+1,y-1,c);
    px(x+1,y+1,c); px(x,y,c); }

  // ---------- агрегаты ----------
  function comp(x,y,st,name){
    // рама
    rc(x,y+18,38,3,C.steelD);
    // электродвигатель
    rc(x+2,y+6,12,11,"#55606a"); frame(x+2,y+6,12,11,C.steelD);
    rc(x+3,y+7,10,2,C.steel);
    for(let i=0;i<4;i++) rc(x+3+i*3,y+9,1,7,"#49535c");
    // муфта и винтовой блок
    rc(x+14,y+9,3,5,C.steelD);
    rc(x+17,y+5,18,13,C.steel); frame(x+17,y+5,18,13,C.steelD);
    rc(x+18,y+6,16,3,C.steelL);
    // маслоотделитель
    rc(x+30,y+2,5,3,C.steelD);
    // патрубки
    rc(x+22,y+2,3,3,C.steelD); rc(x+8,y+3,3,3,C.steelD);
    // вращение муфты
    if(st.run){
      const ph=Math.floor(fc/3)%4;
      const d=[[0,-1],[1,0],[0,1],[-1,0]][ph];
      px(x+15+d[0],y+11+d[1],C.run);
      // дрожь работающего агрегата
      if(fc%16===0){} // (визуальная пауза)
      px(x+4,y+7,C.run);
      // тепло над нагнетанием
      if(st.tdis>80 && Math.floor(fc/4)%3!==0)
        px(x+23+((fc>>2)%2),y+(fc>>3)%2, "rgba(217,138,63,.6)");
    } else {
      px(x+4,y+7, st.trip?C.bad:"#5a636b");
    }
    if(st.trip){
      for(let i=0;i<12;i++){ px(x+13+i,y+5+i*0.9|0,C.bad);
        px(x+24-i*0.9|0,y+5+i,C.bad); }
    }
    if(st.state && st.state.indexOf("реле")>=0){
      if(Math.floor(fc/10)%2) px(x+4,y+7,C.warn);
    }
  }

  function vessel(x,y,w,h,lv,pTag,pVal,pMax){
    // опоры
    rc(x+4,y+h,3,3,C.steelD); rc(x+w-7,y+h,3,3,C.steelD);
    // корпус с торцами
    rc(x+1,y,w-2,h,"#31373c"); rc(x,y+1,1,h-2,"#31373c");
    rc(x+w-1,y+1,1,h-2,"#31373c");
    // заливка по датчику
    const fh=Math.max(0,Math.min(1,lv/100))*(h-2);
    rc(x+1,y+h-1-fh,w-2,fh,C.liq);
    rc(x+1,y+h-1-fh,w-2,1,"#8fc4e0");
    frame(x,y,w,h,lv>75?C.bad:C.steel);
    px(x,y,C.steelD); px(x+w-1,y,C.steelD);
    px(x,y+h-1,C.steelD); px(x+w-1,y+h-1,C.steelD);
    rc(x+1,y+1,w-2,1,"#5a636b");
    // указатель уровня (по тому же датчику -- честно)
    rc(x+w+1,y,2,h,"#20242a"); rc(x+w+1,y+h-fh,2,fh,C.glass);
    frame(x+w,y-1,4,h+2,C.steelD);
    // манометр со стрелкой
    const gx=x+5, gy=y-5;
    rc(gx-2,gy-2,5,5,"#20242a"); frame(gx-2,gy-2,5,5,C.steel);
    const a=Math.max(0,Math.min(1,pVal/pMax))*Math.PI*1.5-Math.PI*1.25;
    px(gx+Math.round(Math.cos(a)*1.6), gy+Math.round(Math.sin(a)*1.6),
       pVal/pMax>0.85?C.bad:C.white);
    px(gx,gy,C.steel);
    rc(gx,gy+3,1,2,C.steelD);
  }

  function evap(x,y,w,h,mode,feed){
    let body="#3b4c57", fin=C.liq, hot=(mode==="HOTGAS");
    if(hot){ body="#5c4326"; fin=C.warn; }
    else if(mode==="IDLE"){ body="#40464c"; fin=C.steelD; }
    else if(mode && mode!=="COOL"){ body="#4d4a35"; fin="#b9a15a"; }
    // подвес
    rc(x+2,y-2,1,2,C.steelD); rc(x+w-3,y-2,1,2,C.steelD);
    rc(x,y,w,h,body); frame(x,y,w,h,C.steelD);
    for(let i=x+2;i<x+w-2;i+=2) rc(i,y+1,1,h-4,fin);
    // вентиляторы аппарата
    const nf=Math.max(1,Math.floor(w/14));
    for(let k=0;k<nf;k++){
      const fx=x+Math.floor(w*(k+0.5)/nf), fy=y+h-2;
      if(mode==="COOL"){ px(fx-1+(Math.floor(fc/3)%2),fy,C.steelL);
        px(fx+(Math.floor(fc/3+1)%2)-1,fy,C.steel); }
      else px(fx-1,fy,C.steelD), px(fx,fy,C.steelD);
    }
    // капель при оттайке
    if(hot){
      const j=Math.floor(rnd(fc*7+x)*(w-2));
      px(x+1+j,y-1,C.warn); px(x+((j+5)%(w-2))+1,y-2,"#e8863f");
      if(Math.floor(fc/5)%2) px(x+w-3,y+h+((fc>>2)%2),C.glass);
    }
    // соленоид подачи
    valve(x-3,y+Math.floor(h/2), feed?C.run:C.bad);
  }

  function cond(x,y,st){
    // корпус градирни
    rc(x,y+8,44,18,C.steel); frame(x,y+8,44,18,C.steelD);
    rc(x+1,y+9,42,2,C.steelL);
    // каплеотбойники
    for(let i=0;i<6;i++) rc(x+3+i*7,y+13,5,1,C.steelD);
    // поддон с водой
    rc(x+1,y+22,42,3,"#2e5063");
    if(st.spray){ const ph=Math.floor(fc/3)%4;
      for(let i=0;i<7;i++){
        px(x+4+i*6, y+15+((ph+i)%4), C.glass); }
      px(x+2+((fc>>2)%40), y+23, "#7fc4de");
    }
    // два вентоблока сверху
    for(let k=0;k<2;k++){
      const cxx=x+11+k*22, cyy=y+3;
      rc(cxx-6,y,13,8,C.steelD); frame(cxx-6,y,13,8,"#333a40");
      const on=st.fans>k;
      if(on){
        const ph=Math.floor(fc/2+k)%4;
        if(ph===0||ph===2){ rc(cxx-3,cyy,7,1,C.steelL); px(cxx,cyy-2,C.steelL); px(cxx,cyy+2,C.steelL); }
        else { px(cxx-2,cyy-2,C.steelL); px(cxx+2,cyy+2,C.steelL);
               px(cxx+2,cyy-2,C.steelL); px(cxx-2,cyy+2,C.steelL); px(cxx,cyy,C.steelL);}
        // выброс тёплого воздуха
        if(Math.floor(fc/3)%2) px(cxx,y-2-((fc>>3)%2),"rgba(170,180,190,.5)");
      } else { px(cxx,cyy,C.steelD); rc(cxx-3,cyy,7,1,"#3d444b"); }
    }
    if(st.loto){
      rc(x+38,y+18,4,4,C.warn); px(x+39,y+17,C.warn); px(x+40,y+17,C.warn);
      px(x+39,y+19,"#6b4f1c");
    }
  }

  function pumpU(x,y,st,tag){
    rc(x,y+7,12,2,C.steelD);
    rc(x,y+1,7,6,"#55606a"); frame(x,y+1,7,6,C.steelD);
    rc(x+7,y+2,5,5,C.steel); frame(x+7,y+2,5,5,C.steelD);
    if(st==="работа"){ const ph=Math.floor(fc/3)%4;
      const d=[[0,-1],[1,0],[0,1],[-1,0]][ph];
      px(x+9+d[0],y+4+d[1],C.run); px(x+1,y+2,C.run); }
    else if(st==="НЕИСПРАВЕН"){ px(x+8,y+3,C.bad); px(x+10,y+5,C.bad);
      px(x+10,y+3,C.bad); px(x+8,y+5,C.bad); }
    else px(x+1,y+2,"#5a636b");
  }

  // ---------- обходчик ----------
  function worker(xf,yf,o){
    const x=Math.round(xf), y=Math.round(yf);
    const stepPh=o.walk?Math.floor(fc/4)%4:0;
    const bob=(o.walk&&(stepPh===1||stepPh===3))?-1:0;
    // ноги: 4 фазы
    if(o.walk){
      if(stepPh===0){ rc(x-2,y-4,2,4,C.pants); rc(x+1,y-4,2,4,C.pants); }
      else if(stepPh===1){ rc(x-3,y-4,2,3,C.pants); rc(x+1,y-4,2,4,C.pants);
        px(x-3,y-1,C.pants); }
      else if(stepPh===2){ rc(x-1,y-4,2,4,C.pants); rc(x,y-4,2,4,C.pants); }
      else { rc(x-2,y-4,2,4,C.pants); rc(x+2,y-4,2,3,C.pants);
        px(x+2,y-1,C.pants); }
    } else { rc(x-2,y-4,2,4,C.pants); rc(x+1,y-4,2,4,C.pants); }
    // ботинки
    px(x-2,y-1,"#20242a"); px(x+2,y-1,"#20242a");
    // туловище-жилет
    rc(x-2,y-10+bob,5,6,o.vest);
    rc(x-2,y-8+bob,5,1,C.stripe);
    // руки
    if(o.work){
      const ph=Math.floor(fc/5)%2;
      rc(x+3,y-9+bob+ph,2,1,o.vest); px(x+5,y-8+bob+ph,C.skin);
      // инструмент
      if(o.tool==="wrench"){ px(x+6,y-8+bob+ph,C.steelL);
        px(x+7,y-7+bob+ph,C.steelL);
        if(rnd(fc*13+x)>0.85){ px(x+7,y-9,C.stripe); px(x+8,y-8,"#fff2c0"); } }
      else if(o.tool==="meter"){ rc(x+6,y-9+bob,3,4,"#30363c");
        px(x+7,y-8+bob,(Math.floor(fc/8)%2)?C.run:"#245530"); }
    } else {
      rc(x-3,y-9+bob,1,3,o.vest); rc(x+3,y-9+bob,1,3,o.vest);
    }
    // СИЗ: баллон за спиной
    if(o.ppe){ rc(x-4,y-10+bob,2,5,"#5f8fa8"); px(x-4,y-11+bob,C.steelD); }
    // голова
    px(x,y-11+bob,o.ppe?C.mask:C.skin); px(x+1,y-11+bob,o.ppe?C.mask:C.skin);
    if(o.ppe) px(x+2,y-11+bob,"#3aa89c");
    // каска с козырьком
    rc(x-1,y-13+bob,4,2,o.helm); px(x+3,y-12+bob,o.helm);
    px(x,y-14+bob,o.helm);
    // ход работы
    if(o.work && o.prog!==null){
      rc(x-5,y-17,11,2,"#20242a"); frame(x-5,y-17,11,2,C.steelD);
      rc(x-4,y-16,Math.round(9*Math.min(o.prog,1)),0.5+0.5,C.warn);
    }
    if(o.warnDose && Math.floor(fc/7)%2){
      frame(x-6,y-16,13,17,C.bad);
    }
  }

  // ---------- клики и сведения ----------
  const HITS=[
    {id:"CO-01",k:"comp",x:14,y:60,w:38,h:22},{id:"CO-02",k:"comp",x:58,y:60,w:38,h:22},
    {id:"CO-03",k:"comp",x:102,y:60,w:38,h:22},{id:"CO-04",k:"comp",x:146,y:60,w:38,h:22},
    {id:"VE-HP",k:"ves",x:14,y:94,w:58,h:24},{id:"VE-IP",k:"ves",x:76,y:94,w:50,h:24},
    {id:"VE-LP",k:"ves",x:128,y:94,w:50,h:24},
    {id:"PU-IP-A",k:"pump",x:82,y:124,w:13,h:12},{id:"PU-IP-B",k:"pump",x:100,y:124,w:13,h:12},
    {id:"PU-LP-A",k:"pump",x:134,y:124,w:13,h:12},{id:"PU-LP-B",k:"pump",x:152,y:124,w:13,h:12},
    {id:"CD-01",k:"cond",x:18,y:10,w:44,h:26},{id:"CD-02",k:"cond",x:96,y:10,w:44,h:26},
    {id:"EV-01",k:"evap",x:18,y:116,w:24,h:13},{id:"EV-02",k:"evap",x:284,y:56,w:40,h:15},
    {id:"EV-03",k:"evap",x:214,y:176,w:34,h:17},{id:"EV-04",k:"evap",x:250,y:176,w:34,h:17},
    {id:"EV-05",k:"evap",x:300,y:176,w:34,h:17},{id:"EV-06",k:"evap",x:336,y:176,w:34,h:17},
    {id:"MILK",k:"milk",x:322,y:64,w:26,h:24},{id:"PAST",k:"past",x:286,y:64,w:22,h:26},
    {id:"ICE",k:"ice",x:14,y:128,w:58,h:20},
    {id:"MACHINE_ROOM",k:"zone",x:8,y:54,w:180,h:96},
    {id:"ROOF",k:"zone",x:8,y:6,w:192,h:40},
    {id:"CONTROL_ROOM",k:"zone",x:210,y:88,w:60,h:46},
    {id:"HALL",k:"zone",x:278,y:54,w:98,h:96},
    {id:"LT_STORE",k:"zone",x:210,y:172,w:78,h:40},
    {id:"BLAST",k:"zone",x:296,y:172,w:80,h:40},
    {id:"ASSEMBLY_POINT",k:"zone",x:8,y:176,w:66,h:34}
  ];
  const ITEM_RU={LEVEL_GLASS:"сверка указателя уровня",COIL_GAUGE:"замер по манометру батареи",
    COIL_TOUCH:"замер температуры коллектора",FROST:"оценка снеговой шубы",
    OIL_LEVEL:"проверка масла",PORTABLE_GAS:"замер переносным газоанализатором",
    SMELL_CHECK:"проверка по запаху",VIBRATION:"прослушивание трубопровода",
    PRV_CHECK:"осмотр предохранительного клапана",VISUAL_LEAK:"обход в поисках утечки",
    CONDENSER_CHECK:"осмотр конденсатора",CLOSE_FEED:"ручное закрытие подачи",
    CLOSE_HOTGAS:"ручное закрытие горячего пара",OPEN_FEED:"ручное открытие подачи",
    ISOLATE_VESSEL:"отсечение сосуда арматурой",PURGE_NCG:"продувка воздухоотделителя",
    PERMIT_CLEAR:"закрытие наряда-допуска",RECALIBRATE:"перекалибровка газоанализатора",
    DON_PPE:"надевание дыхательного аппарата"};
  const ZONE_T={LT_STORE:"T_ROOM_LT",BLAST:"T_ROOM_BLAST",HALL:"T_ROOM_CHILL"};

  function hit(lx,ly){
    for(const [op,p] of Object.entries(wpos)){
      if(Math.abs(lx-p[0])<=6 && ly>=p[1]-16 && ly<=p[1]+3)
        return {id:op,k:"op"};
    }
    for(const h of HITS){
      if(h.k==="zone") continue;
      if(lx>=h.x&&lx<h.x+h.w&&ly>=h.y&&ly<h.y+h.h) return h;
    }
    for(const h of HITS){
      if(h.k!=="zone") continue;
      if(lx>=h.x&&lx<h.x+h.w&&ly>=h.y&&ly<h.y+h.h) return h;
    }
    return null;
  }

  function infoHTML(sl){
    if(!sl||!obs) return "Щёлкните по аппарату, помещению или обходчику.";
    const T=obs.tags||{};
    const nm=t=>(typeof TR==="function")?TR(t):t;
    const P=(v,mx)=>(typeof izb==="function"?
      ((izb(v)<0?"вак. ":"")+Math.abs(izb(v)).toFixed(2)+" кгс/см²"):v);
    if(sl.k==="comp"){
      const c=(obs.comps||[]).find(x=>x.tag===sl.id)||{};
      const role=(sl.id==="CO-01"||sl.id==="CO-02")?
        "винтовой бустер нижней ступени":"винтовой компрессор верхней ступени";
      return "<b>"+nm(sl.id)+"</b> — "+role+".<br>Состояние: "+nm(c.state||"—")+
        " · золотник "+ (c.slide!=null?c.slide+" %":"—")+
        " · t нагнетания "+(c.tdis!=null?c.tdis+" °С":"—")+
        (c.trip?"<br><span style='color:var(--bad)'>Блокировка снимается командой после устранения причины.</span>":"");
    }
    if(sl.k==="ves"){
      const map={ "VE-HP":["РЛ","линейный ресивер",T.P_COND,"P_COND"],
        "VE-IP":["ЦР-СД","циркуляционный ресивер-промсосуд, t₀ −10 °С",T.P_SUC_IP],
        "VE-LP":["ЦР-НД","циркуляционный ресивер, t₀ −40 °С",T.P_SUC_LP]};
      const m=map[sl.id];
      const lv=T["LEVEL_"+sl.id.replace("-","_")];
      return "<b>"+m[0]+"</b> — "+m[1]+".<br>Давление "+P(m[2])+
        " · уровень по дистанционному датчику "+(lv!=null?lv.toFixed(0)+" %":"—")+
        ".<br><span class='mut'>Указатель уровня на самом аппарате читается только нарядом.</span>";
    }
    if(sl.k==="pump"){
      const p2=(obs.pumps||[]).find(x=>x.tag===sl.id)||{};
      const loop=sl.id.indexOf("LP")>0?"контур НД (−40 °С)":"контур СД (−10 °С)";
      return "<b>"+nm(sl.id)+"</b> — аммиачный насос, "+loop+
        ". Состояние: "+ (p2.state||"—")+".";
    }
    if(sl.k==="cond"){
      const c=(obs.conds||[]).find(x=>x.tag===sl.id)||{};
      return "<b>"+nm(sl.id)+"</b> — испарительный конденсатор.<br>Вентиляторов "+
        (c.fans!=null?c.fans:"—")+"/2 · орошение "+(c.spray?"включено":"ВЫКЛЮЧЕНО")+
        (c.loto?"<br><span style='color:var(--warn)'>Действует наряд-допуск: привод насоса обесточен и заперт; дистанционный пуск невозможен до закрытия допуска.</span>":"");
    }
    if(sl.k==="evap"){
      const e=(obs.evaps||[]).find(x=>x.tag===sl.id)||{};
      const place={ "EV-01":"испаритель ледяной воды (машзал)",
        "EV-02":"воздухоохладитель камеры +2 °С","EV-03":"батарея НТ-склада",
        "EV-04":"батарея НТ-склада","EV-05":"батарея морозильной",
        "EV-06":"батарея морозильной"}[sl.id];
      return "<b>"+nm(sl.id)+"</b> — "+place+".<br>Режим по контроллеру: "+
        nm(e.mode||"—")+" · соленоид подачи "+(e.feed?"ОТКРЫТ":"закрыт")+
        (e.P!=null?" · Р батареи "+P(e.P):"")+".";
    }
    if(sl.k==="milk") return "<b>Молочный танк</b>. t молока "+
      (T.T_MILK!=null?T.T_MILK.toFixed(1):"—")+
      " °С (граница по регламенту +6 °С). Охлаждается ледяной водой через пластинчатый охладитель.";
    if(sl.k==="past") return "<b>Пастеризатор</b> — пластинчатый аппарат приёмки молока; секция охлаждения питается ледяной водой от ВО-1.";
    if(sl.k==="ice") return "<b>Льдоаккумулятор</b> при ВО-1. Запас льда "+
      (T.M_ICE_T!=null?T.M_ICE_T.toFixed(1):"—")+
      " т из 34 т. Ночная наморозка покрывает утренний пик приёмки.";
    if(sl.k==="zone"){
      const z=ZONES[sl.id];
      let out="<b>"+z.lbl+"</b>.";
      if(sl.id==="MACHINE_ROOM"||sl.id==="HALL"){
        const ppm=sl.id==="MACHINE_ROOM"?(T.NH3_MACHINEROOM_PPM||0):(T.NH3_HALL_PPM||0);
        out+=" NH₃ по стационарному газоанализатору "+(ppm*0.71).toFixed(0)+
          " мг/м³ ("+ppm.toFixed(0)+" ppm)."+
          " Аварийная вытяжка "+(((obs.vents||{})[sl.id])?"работает":"выключена")+".";
      }
      if(ZONE_T[sl.id]&&T[ZONE_T[sl.id]]!=null)
        out+=" Температура "+T[ZONE_T[sl.id]].toFixed(1)+" °С.";
      const here=Object.entries(obs.ops||{}).filter(([k,v])=>v.zone===sl.id)
        .map(([k])=>nm(k));
      out+=" Персонал: "+(here.length?here.join(", "):"нет")+".";
      return out;
    }
    if(sl.k==="op"){
      const st=(obs.ops||{})[sl.id]||{};
      const tk=(obs.wf||[]).find(t=>t.op===sl.id);
      const now=obs.t+(typeof thinkSim==="function"?thinkSim():0);
      let out="<b>"+nm(sl.id)+"</b> — машинист-обходчик. Зона: "+nm(st.zone||"—")+
        ". Доза "+Math.round((st.dose||0)*0.71)+
        " мг/м³·мин (нормативы: 370 — сверхнорматив, 1060 — поражение)."+
        (st.ppe?" В изолирующем дыхательном аппарате.":"");
      if(tk){
        const what=ITEM_RU[tk.item]||tk.item;
        out+= now<tk.ta ?
          "<br>Идёт в "+nm(tk.zone)+": "+what+
            (tk.target?" ("+nm(tk.target)+")":"")+
            ", прибытие через "+Math.max(0,tk.ta-now).toFixed(0)+" с.":
          "<br>Выполняет: "+what+(tk.target?" ("+nm(tk.target)+")":"")+
            ", готовность через "+Math.max(0,tk.td-now).toFixed(0)+" с.";
      }
      return out;
    }
    return "";
  }

  function renderInfo(){
    const el=document.getElementById("pixinfo");
    if(el) el.innerHTML=infoHTML(sel);
  }

  // ---------- маршруты ----------
  function route(a,b){
    const A=CH[a]||CH.CONTROL_ROOM, B=CH[b]||CH.CONTROL_ROOM;
    const pts=A.slice();
    pts.push([B[B.length-1][0],SPINE]);
    for(let i=B.length-1;i>=0;i--) pts.push(B[i]);
    let L=0, seg=[0];
    for(let i=1;i<pts.length;i++){
      L+=Math.abs(pts[i][0]-pts[i-1][0])+Math.abs(pts[i][1]-pts[i-1][1]);
      seg.push(L);
    }
    return {pts,seg,L:Math.max(L,1)};
  }
  function along(r,f){
    const d=f*r.L;
    for(let i=1;i<r.pts.length;i++){
      if(d<=r.seg[i]){
        const t=(d-r.seg[i-1])/Math.max(r.seg[i]-r.seg[i-1],1e-6);
        return [r.pts[i-1][0]+(r.pts[i][0]-r.pts[i-1][0])*t,
                r.pts[i-1][1]+(r.pts[i][1]-r.pts[i-1][1])*t];
      }
    }
    return r.pts[r.pts.length-1];
  }

  // ---------- статичная сцена (рисуется один раз в кэш) ----------
  function renderStatic(){
    const keep=ox; ox=bg.getContext("2d");
    // двор
    dither(0,0,W,H,C.yard,C.yard2);
    for(let i=0;i<60;i++)
      px(Math.floor(rnd(i*97)*W), Math.floor(rnd(i*53)*H), "#22252a");
    // коридор с разметкой
    rc(8,152,368,14,C.cor);
    for(let i=12;i<372;i+=8) rc(i,164,4,1,C.corStripe);
    frame(7,151,370,16,C.wallTop);
    // помещения: пол + стены с "высотой"
    for(const z of Object.values(ZONES)){
      dither(z.x,z.y,z.w,z.h,z.f,z.f2);
      frame(z.x-1,z.y-1,z.w+2,z.h+2,C.wallTop);
      rc(z.x,z.y,z.w,1,C.wallHi);
      rc(z.x,z.y+z.h-1,z.w,1,C.wallFace);
    }
    // проёмы дверей
    for(const d of DOORS) rc(d[0],d[1],d[2],d[3],C.cor);
    // лестница на кровлю (наружная, x194)
    for(let yy=48;yy<152;yy+=4){ rc(192,yy,5,1,C.steel); }
    rc(192,46,1,108,C.steelD); rc(196,46,1,108,C.steelD);
    // иней в холодных камерах (базовый слой)
    for(let i=0;i<70;i++){
      const z=(i%2)?ZONES.LT_STORE:ZONES.BLAST;
      px(z.x+2+Math.floor(rnd(i*7)*(z.w-4)),
         z.y+2+Math.floor(rnd(i*13)*(z.h-4)),
         "rgba(207,224,238,.55)");
    }
    // стеллажи в камерах
    for(const z of [ZONES.LT_STORE,ZONES.BLAST]){
      for(let k=0;k<3;k++){
        const sx=z.x+8+k*24;
        rc(sx,z.y+20,16,8,"#5b5348"); frame(sx,z.y+20,16,8,"#403a32");
        rc(sx,z.y+23,16,1,"#403a32");
      }
    }
    // сборный пункт: знак и ограждение
    rc(12,180,3,10,C.steel); rc(10,178,7,6,C.run);
    px(13,180,C.white); px(13,181,C.white); px(12,182,C.white); px(14,182,C.white);
    for(let i=24;i<70;i+=6) rc(i,208,4,1,C.steel);
    // щитовая: пульт, корпуса экранов, тумба
    rc(216,96,48,4,C.steelD);
    for(let k=0;k<3;k++){
      const mx=218+k*16;
      rc(mx,90,12,8,"#20242a"); frame(mx,90,12,8,C.steelD);
    }
    rc(214,126,10,6,"#5b5348");
    // пастеризатор и корпус молочного танка (статика)
    rc(286,64,22,26,C.steel); frame(286,64,22,26,C.steelD);
    for(let i=0;i<9;i++) rc(288+i*2,66,1,22,i%2?C.steelL:"#6a747c");
    rc(322,66,26,22,"#38424a");
    rc(322,64,26,3,C.steelL); rc(321,66,28,1,C.steel);
    frame(322,64,26,24,C.steelD);
    // корпус льдоаккумулятора
    rc(14,128,58,20,"#31414d"); frame(14,128,58,20,C.steelD);
    rc(16,132,54,12,"#274050");
    ox=keep; bgReady=true;
  }

  function drawDynamicBits(){
    // живые линии на экранах щитовой
    for(let k=0;k<3;k++){
      const mx=218+k*16;
      rc(mx+1,91,10,6,"#20242a");
      for(let i=0;i<4;i++){
        const yy=91+Math.floor(rnd((fc>>3)+k*17+i*3)*6);
        px(mx+2+i*2+((fc>>3)%2),yy,k===2?C.warn:C.run);
      }
    }
    // мерцание инея (лёгкое, поверх статичной наледи)
    for(let i=0;i<10;i++){
      const z=(i%2)?ZONES.LT_STORE:ZONES.BLAST;
      if(rnd(i*31+(fc>>3))>0.6)
        px(z.x+2+Math.floor(rnd(i*7+(fc>>4))*(z.w-4)),
           z.y+2+Math.floor(rnd(i*13+(fc>>5))*(z.h-4)),C.white);
    }
  }

  function drawHallFixed(T){
    const bad=(T.T_MILK||0)>6;
    rc(324,70,22,16,bad?C.milkBad:C.milk);
    // мешалка
    const ph=Math.floor(fc/4)%4;
    rc(334,66,1,6,C.steelD);
    if(ph===0) rc(330,72,9,1,"#b9d4c2");
    else if(ph===2) rc(333,70,3,3,"#b9d4c2");
    else { px(332+((ph===1)?0:4),71,"#b9d4c2"); px(336-((ph===1)?0:4),73,"#b9d4c2"); }
    // трубка к пастеризатору
    pipe([[308,80],[322,80]],bad?C.milkBad:C.milk,{anim:true,speed:1});
  }

  function drawPipes(o,T){
    const cm={}; (o.comps||[]).forEach(c=>cm[c.tag]=c);
    const pu={}; (o.pumps||[]).forEach(p=>pu[p.tag]=p.state);
    const ev={}; (o.evaps||[]).forEach(e=>ev[e.tag]=e);
    const lpRun=(cm["CO-01"]&&cm["CO-01"].run)||(cm["CO-02"]&&cm["CO-02"].run);
    const hpRun=(cm["CO-03"]&&cm["CO-03"].run)||(cm["CO-04"]&&cm["CO-04"].run);
    const naND=(pu["PU-LP-A"]==="работа")||(pu["PU-LP-B"]==="работа");
    const naSD=(pu["PU-IP-A"]==="работа")||(pu["PU-IP-B"]==="работа");
    const hotAny=(o.evaps||[]).some(e=>e.mode==="HOTGAS");

    // всас НД: ЦРНД -> КМ1, КМ2
    pipe([[152,100],[152,92],[26,92],[26,84]],C.suc,{dash:3,anim:lpRun,speed:2});
    pipe([[70,92],[70,84]],C.suc,{dash:3,anim:lpRun,speed:2});
    // нагнетание НД -> ЦРСД
    pipe([[80,60],[80,52],[100,52],[100,96]],"#c9976a",{anim:lpRun,speed:2});
    // всас СД: ЦРСД -> КМ3, КМ4
    pipe([[112,100],[112,96]],C.suc,{dash:3,anim:hpRun,speed:2});
    pipe([[112,96],[124,96],[124,84]],C.suc,{dash:3,anim:hpRun,speed:2});
    pipe([[124,96],[168,96],[168,84]],C.suc,{dash:3,anim:hpRun,speed:2});
    // нагнетание ВД на кровлю
    pipe([[172,60],[172,50],[184,50],[184,26],[168,26]],C.hot,
      {anim:hpRun,speed:3});
    pipe([[168,26],[110,26],[110,20]],C.hot,{anim:hpRun,speed:3});
    pipe([[140,26],[140,30]],C.hot,{anim:hpRun,speed:3});
    // конденсат вниз в РЛ
    pipe([[64,32],[64,40],[12,40],[12,96],[20,96]],C.liq,{anim:hpRun,speed:2});
    // жидкость РЛ -> ЦРСД (КУ-СД) -> ЦРНД (КУ-НД)
    pipe([[68,108],[74,108]],C.liq,{anim:hpRun,speed:1});
    valve(71,108,C.steelL);
    pipe([[122,108],[128,108]],C.liq,{anim:lpRun,speed:1});
    valve(125,108,C.steelL);
    // насосная подача СД: к ВО-1 и в цех к ВО-2
    pipe([[88,133],[78,133],[74,133]],C.liq,{anim:naSD,speed:2});
    pipe([[102,133],[102,146],[240,146],[240,150]],C.liq,{anim:naSD,speed:2});
    pipe([[240,150],[276,150],[276,70],[283,70]],C.liq,{anim:naSD,speed:2});
    // насосная подача НД: в холодные камеры
    pipe([[140,133],[140,142],[254,142]],C.liq,{anim:naND,speed:2});
    pipe([[254,142],[254,170]],C.liq,{anim:naND,speed:2});
    pipe([[254,142],[342,142],[342,170]],C.liq,{anim:naND,speed:2});
    // горячий пар на оттайку
    pipe([[178,50],[178,148],[262,148],[262,170]],C.hot,
      {dash:4,anim:hotAny,speed:3});
    pipe([[262,148],[350,148],[350,170]],C.hot,{dash:4,anim:hotAny,speed:3});
  }

  function drawVents(o){
    function fan(zx,zy,on){
      rc(zx,zy,9,7,C.steelD); frame(zx,zy,9,7,"#2b3036");
      const cxx=zx+4, cyy=zy+3;
      if(on){
        const ph=Math.floor(fc/2)%2;
        if(ph){ rc(cxx-2,cyy,5,1,C.warn); }
        else { rc(cxx,cyy-2,1,5,C.warn); }
        for(let k=0;k<3;k++){
          const yy=zy-2-((Math.floor(fc/2)+k*3)%8);
          px(cxx-2+k*2,yy,"rgba(224,172,69,.7)");
        }
      } else px(cxx,cyy,C.steelD);
    }
    fan(150,50,(o.vents||{}).MACHINE_ROOM);
    fan(330,50,(o.vents||{}).HALL);
  }

  function drawHaze(z,ppm){
    const zz=ZONES[z];
    const n=Math.min(Math.round(ppm/140*260),320);
    for(let i=0;i<n;i++){
      const bx=rnd(i*29)* (zz.w-6);
      const drift=((fc*0.4+i*11)%(zz.h-6));
      const xx=zz.x+3+((bx+Math.sin((fc/14+i))*2+zz.w)% (zz.w-6));
      const yy=zz.y+zz.h-4-drift;
      const a=0.25+0.3*rnd(i*7+(fc>>2));
      px(xx,yy,"rgba(134,223,143,"+a.toFixed(2)+")");
      if(rnd(i*13)>0.7) px(xx+1,yy,"rgba(134,223,143,"+(a*0.6).toFixed(2)+")");
    }
  }

  // ---------- кадр ----------
  function draw(){
    fc++;
    requestAnimationFrame(draw);
    if(!cv||!open||!obs) return;
    if(document.getElementById("scr-play").style.display==="none") return;
    const now=obs.t+(typeof thinkSim==="function"?thinkSim():0);
    const T=obs.tags||{};

    if(!bgReady) renderStatic();
    ox.drawImage(bg,0,0);
    drawDynamicBits();
    drawPipes(obs,T);

    // конденсаторы
    const cd={}; (obs.conds||[]).forEach(c=>cd[c.tag]=c);
    cond(18,10, cd["CD-01"]||{fans:0}); cond(96,10, cd["CD-02"]||{fans:0});

    // компрессоры
    const cm={}; (obs.comps||[]).forEach(c=>cm[c.tag]=c);
    comp(14,60, cm["CO-01"]||{}); comp(58,60, cm["CO-02"]||{});
    comp(102,60, cm["CO-03"]||{}); comp(146,60, cm["CO-04"]||{});

    // сосуды с манометрами (шкалы: РЛ до 20, ЦРСД до 8, ЦРНД до 4 бар абс)
    vessel(16,100,52,16, T.LEVEL_VE_HP||0, "РЛ", T.P_COND||0, 20);
    vessel(78,100,44,16, T.LEVEL_VE_IP||0, "ЦРСД", T.P_SUC_IP||0, 8);
    vessel(130,100,44,16, T.LEVEL_VE_LP||0, "ЦРНД", T.P_SUC_LP||0, 4);

    // насосы
    const pu={}; (obs.pumps||[]).forEach(p=>pu[p.tag]=p.state);
    pumpU(82,126,pu["PU-IP-A"]); pumpU(100,126,pu["PU-IP-B"]);
    pumpU(134,126,pu["PU-LP-A"]); pumpU(152,126,pu["PU-LP-B"]);

    // испарители
    const ev={}; (obs.evaps||[]).forEach(e=>ev[e.tag]=e);
    const e1=ev["EV-01"]||{};
    // лёд в аккумуляторе
    const iceW=Math.round(((T.M_ICE_T||0)/34)*54);
    rc(16,132,54,12,"#274050");
    rc(16,132,iceW,12,"#bfd6e8");
    for(let i=0;i<iceW;i+=4) px(16+i,133+((i>>2)%3),C.white);
    evap(20,118,20,9, e1.mode, e1.feed);
    const e2=ev["EV-02"]||{};
    evap(286,58,36,12, e2.mode, e2.feed);
    evap(216,178,30,14,(ev["EV-03"]||{}).mode,(ev["EV-03"]||{}).feed);
    evap(252,178,30,14,(ev["EV-04"]||{}).mode,(ev["EV-04"]||{}).feed);
    evap(302,178,30,14,(ev["EV-05"]||{}).mode,(ev["EV-05"]||{}).feed);
    evap(338,178,30,14,(ev["EV-06"]||{}).mode,(ev["EV-06"]||{}).feed);

    drawHallFixed(T);
    drawVents(obs);
    drawHaze("MACHINE_ROOM", T.NH3_MACHINEROOM_PPM||0);
    drawHaze("HALL", T.NH3_HALL_PPM||0);

    // проблесковые маячки
    const swp=Math.floor(fc/5)%4;
    function beacon(x,y,on,c){
      rc(x,y+2,5,2,C.steelD);
      if(!on){ rc(x+1,y,3,2,"#4a2f2c"); return; }
      rc(x+1,y,3,2,c);
      const d=[[-2,0],[0,-2],[2,0],[0,2]][swp];
      px(x+2+d[0],y+1+d[1],"rgba(255,220,200,.85)");
    }
    beacon(178,56,(T.NH3_MACHINEROOM_PPM||0)>25,C.bad);
    beacon(360,56,(T.NH3_HALL_PPM||0)>50,C.bad);
    beacon(258,90,(obs.alarms||[]).length>0,C.warn);

    // обходчики
    const tasks={}; (obs.wf||[]).forEach(t=>tasks[t.op]=t);
    const wcfg=[{helm:"#e8863f",vest:C.vest},{helm:"#5f8fc2",vest:C.vest2}];
    let idx=0;
    const labels=[];
    for(const [op,st] of Object.entries(obs.ops||{})){
      const tk=tasks[op]; let x,y,walk=false,work=false,prog=null,tool=null;
      if(tk && now<tk.ta && tk.ta>tk.t0+0.5){
        const r=route(tk.from,tk.zone);
        const f=Math.max(0,Math.min((now-tk.t0)/(tk.ta-tk.t0),1));
        [x,y]=along(r,f); walk=true;
      } else if(tk){
        const a=(CH[tk.zone]||CH.CONTROL_ROOM)[0];
        x=a[0]+idx*12-6; y=a[1];
        work=now<tk.td;
        prog=work?(now-tk.ta)/Math.max(tk.td-tk.ta,1):null;
        tool=/CLOSE|OPEN|ISOLATE|PERMIT|RECAL/.test(tk.item)?"wrench":"meter";
      } else {
        const a=(CH[st.zone]||CH.CONTROL_ROOM)[0];
        x=a[0]+idx*12-6; y=a[1];
      }
      worker(x,y,{helm:wcfg[idx%2].helm,vest:wcfg[idx%2].vest,ppe:st.ppe,
        walk,work,prog,tool,warnDose:(st.dose*0.71)>370});
      labels.push([op,x,y,wcfg[idx%2].helm]);
      wpos[op]=[x,y];
      idx++;
    }

    // подсветка выбранного объекта
    if(sel){
      let bx2=null;
      if(sel.k==="op"&&wpos[sel.id]){
        const p2=wpos[sel.id]; bx2={x:p2[0]-6,y:p2[1]-17,w:13,h:20};
      } else if(sel.x!==undefined) bx2=sel;
      if(bx2){
        const c2=C.warn;
        const per=2*(bx2.w+bx2.h);
        for(let d=0;d<per;d+=2){
          if(((d+(fc>>1))%6)>=3) continue;
          let xx,yy;
          if(d<bx2.w){ xx=bx2.x+d; yy=bx2.y-1; }
          else if(d<bx2.w+bx2.h){ xx=bx2.x+bx2.w; yy=bx2.y-1+(d-bx2.w); }
          else if(d<2*bx2.w+bx2.h){ xx=bx2.x+bx2.w-(d-bx2.w-bx2.h); yy=bx2.y+bx2.h; }
          else { xx=bx2.x-1; yy=bx2.y+bx2.h-(d-2*bx2.w-bx2.h); }
          px(xx,yy,c2);
        }
      }
    }

    // общий стоп: пульсирующая рамка
    if(obs.esd){
      const a=0.35+0.3*Math.abs(Math.sin(fc/12));
      ox.fillStyle="rgba(212,88,74,"+a.toFixed(2)+")";
      ox.fillRect(0,0,W,2); ox.fillRect(0,H-2,W,2);
      ox.fillRect(0,0,2,H); ox.fillRect(W-2,0,2,H);
    }

    // ---------- вывод и подписи ----------
    cx.imageSmoothingEnabled=false;
    cx.clearRect(0,0,cv.width,cv.height);
    cx.drawImage(off,0,0,W*S,H*S);

    function plate(t,x,y,fg){
      cx.font='600 '+(S>=3?11:10)+'px "IBM Plex Sans Condensed",sans-serif';
      const w=cx.measureText(t).width;
      cx.fillStyle="rgba(18,20,23,.72)";
      cx.fillRect(x*S-2,(y-3.2)*S,w+6,4*S);
      cx.fillStyle=fg||"#c9d1d6"; cx.fillText(t,x*S+1,(y)*S);
    }
    for(const z of Object.values(ZONES)) plate(z.lbl, z.x+2, z.y+4.6);
    cx.fillStyle="#98a1a8";
    cx.font='500 '+(S>=3?10:9)+'px "IBM Plex Mono",monospace';
    const L=(t,x,y,c)=>{ if(c)cx.fillStyle=c; cx.fillText(t,x*S,y*S); };
    L("КД1",19,9.4); L("КД2",97,9.4,"#98a1a8");
    L("КМ1",16,59.2); L("КМ2",60,59.2); L("КМ3",104,59.2); L("КМ4",148,59.2);
    L("РЛ",17,99); L("ЦРСД",79,99); L("ЦРНД",131,99);
    const T2=obs.tags||{};
    L((T2.LEVEL_VE_HP||0).toFixed(0)+"%",34,124,"#8fc4e0");
    L((T2.LEVEL_VE_IP||0).toFixed(0)+"%",92,124);
    L((T2.LEVEL_VE_LP||0).toFixed(0)+"%",144,124);
    L("НА3 НА4",84,141,"#98a1a8"); L("НА1 НА2",136,141);
    L("ВО-1 · лёд "+(T2.M_ICE_T!==undefined?T2.M_ICE_T.toFixed(0):"—")+" т",
      16,156.5);
    L("ВО-2",287,57); L("ВО-3",218,177); L("ВО-4",254,177);
    L("ВО-5",304,177); L("ВО-6",340,177);
    plate("молоко "+(T2.T_MILK!==undefined?T2.T_MILK.toFixed(1):"—")+" °С",
      322,62.5,(T2.T_MILK||0)>6?"#e8a89b":"#cfe3d5");
    const mr=(T2.NH3_MACHINEROOM_PPM||0)*0.71, hl=(T2.NH3_HALL_PPM||0)*0.71;
    plate("NH₃ "+mr.toFixed(0)+" мг/м³",130,60.5,
      mr>18?"#e8a89b":"#9fb3a5");
    plate("NH₃ "+hl.toFixed(0)+" мг/м³",332,150.5, hl>36?"#e8a89b":"#9fb3a5");
    for(const [op,x,y,c] of labels){
      cx.font='600 '+(S>=3?10:9)+'px "IBM Plex Sans Condensed",sans-serif';
      const t=op.replace("OP-","О-");
      cx.fillStyle="rgba(18,20,23,.7)";
      cx.fillRect((x-4)*S,(y+1)*S,cx.measureText(t).width+4,3.4*S);
      cx.fillStyle=c; cx.fillText(t,(x-3.5)*S,(y+3.8)*S);
    }
    // легенда
    cx.font='500 '+(S>=3?10:9)+'px "IBM Plex Sans Condensed",sans-serif';
    const leg=[["— жидкость",C.liq],["– – всас",C.suc],["— гор. пар",C.hot],
      ["· газ по датчикам",C.haze]];
    let lx=10*S;
    cx.fillStyle="rgba(18,20,23,.72)"; cx.fillRect(lx-4,(H-4.6)*S,118*S/ (S>=3?1.05:0.85),3.8*S);
    for(const [t,c] of leg){ cx.fillStyle=c; cx.fillText(t,lx,(H-1.6)*S);
      lx+=cx.measureText(t).width+10; }
    if(obs.esd){
      cx.fillStyle=C.bad;
      cx.font='700 '+(S>=3?13:11)+'px "IBM Plex Sans Condensed",sans-serif';
      if(Math.floor(fc/10)%2)
        cx.fillText("ОБЩИЙ АВАРИЙНЫЙ СТОП",(W/2-34)*S,4.4*S);
    }
  }

  // ---------- инициализация ----------
  function fit(){
    if(!cv) return;
    const box=document.getElementById("pixwrap");
    S=Math.max(2,Math.min(4,Math.floor((box.clientWidth-10)/W)));
    cv.width=W*S; cv.height=H*S;
  }
  function init(){
    cv=document.getElementById("pix");
    if(!cv) return;
    cx=cv.getContext("2d");
    off=document.createElement("canvas"); off.width=W; off.height=H;
    ox=off.getContext("2d");
    bg=document.createElement("canvas"); bg.width=W; bg.height=H;
    fit();
    window.addEventListener("resize",fit);
    cv.addEventListener("click",ev=>{
      const r=cv.getBoundingClientRect();
      const lx=(ev.clientX-r.left)*(cv.width/r.width)/S;
      const ly=(ev.clientY-r.top)*(cv.height/r.height)/S;
      const h=hit(lx,ly);
      sel=(sel&&h&&sel.id===h.id&&sel.k===h.k)?null:h;
      renderInfo();
    });
    const tg=document.getElementById("pixtoggle");
    if(tg) tg.onclick=()=>{ open=!open;
      document.getElementById("pixwrap").style.display=open?"":"none";
      tg.textContent=open?"свернуть":"развернуть"; };
    requestAnimationFrame(draw);
  }
  return { init, hit, update:o=>{obs=o; renderInfo();} };
})();
window.addEventListener("load",()=>PIX.init());
