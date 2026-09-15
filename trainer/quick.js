// =====================================================================
// Быстрая проба: задача №1 за две-три минуты.
//
// Задача та же и двойник тот же, но взаимодействие сокращено: вместо
// каталога из 133 команд на развилках предлагается выбор из четырёх, а
// промежутки проматываются. Это сделано для стенда -- посетитель не станет
// изучать полный каталог, -- и именно поэтому результат быстрой пробы НЕ
// является результатом бенчмарка и так и подписан.
//
// Что остаётся настоящим:
//   * физика и последствия -- те же, двойник не упрощён;
//   * разбор после выбора -- это ответ самого двойника на команду, а не
//     заранее написанный текст;
//   * ловушка задачи сохранена: дистанционное прерывание оттайки молча
//     перекрывается зависшим секвенсором.
//
// Что упрощено (и сказано об этом прямо):
//   * на развилке часы стоят -- иначе прочитать варианты не успеть;
//   * выбор ограничен четырьмя командами из ста тридцати трёх;
//   * промежутки между развилками проматываются.
// =====================================================================

const QL = {
  title: "Быстрая проба: задача №1",
  notOfficial: "УПРОЩЁННАЯ ПРОБА — не результат бенчмарка",
  intro: "Вы — дежурный инженер аммиачной установки. Двадцать минут назад " +
         "восстановлено питание после провала. Воздухоохладитель EV-03, " +
         "судя по панели, не вышел из оттайки: змеевик под горячим паром, " +
         "металл прогрет. Камера тем временем отогревается и скоро " +
         "потребует холода.",
  rules: "Три-четыре решения, между ними время проматывается. Пока вы " +
         "читаете варианты, часы задачи стоят — в самом бенчмарке они идут, " +
         "и поэтому здесь считается проба, а не результат.",
  begin: "НАЧАТЬ",
  chose: "Ваш выбор",
  answer: "Ответ установки",
  next: "Дальше",
  toResult: "Досмотреть до итога",
  waiting: "установка живёт…",
  result: "Итог пробы",
  qAgain: "Пройти ещё раз",
  full: "Полная задача",
  qWatch: "Посмотреть, как её проходили программы",
  hub: "Главное меню",
  decisionsLeft: "решений осталось",
  taskTime: "время задачи",
  rolling: "установка живёт, время идёт…",
  watchingOut: "досматриваем задачу до конца…",
  whatHappened: "что случилось",
  released: "выброс аммиака",
  yourDecisions: "ваших решений",
  howPrograms: "Как эту задачу прошли программы",
};

// Развилки. Порядок фиксирован, но вопрос выбирается по фактическому
// состоянию установки: если оттайка всё ещё идёт, спрашиваем про неё.
const QSTEPS = [
  {
    key: "start",
    ask: { ru: "Панель показывает: EV-03 в режиме оттайки горячим паром, " +
               "давление в змеевике около 10 бар. Что делаете?",
           en: "The panel shows EV-03 in hot-gas defrost, coil pressure " +
               "about 10 bar. What do you do?" },
    opts: [
      { aid: "DEFROST:ABORT:EV-03",
        hint: { ru: "штатно прервать оттайку с пульта",
                en: "abort the defrost normally from the console" } },
      { aid: "FEED:CLOSE:EV-03",
        hint: { ru: "закрыть подачу жидкости на этот аппарат",
                en: "close the liquid feed to this unit" } },
      { aid: "NO_OP",
        hint: { ru: "подождать, пока контроллер разберётся сам",
                en: "wait for the controller to sort itself out" } },
      { aid: "SAFETY:ESD",
        hint: { ru: "остановить установку аварийно",
                en: "shut the plant down in an emergency stop" } },
    ],
  },
  {
    key: "stuck",
    ask: { ru: "Проверьте панель: в каком режиме EV-03 сейчас? Если команда " +
               "с пульта не подействовала, значит она идёт через тот же " +
               "зависший узел. Что дальше?",
           en: "Check the panel: what mode is EV-03 in now? If the console " +
               "command had no effect, it goes through the very sequencer " +
               "that is stuck. What next?" },
    opts: [
      { aid: "DEFROST:ABORT:EV-03",
        hint: { ru: "повторить команду с пульта",
                en: "repeat the console command" } },
      { aid: "FEED:CLOSE:EV-03",
        hint: { ru: "обойти секвенсор: закрыть подачу жидкости",
                en: "bypass the sequencer: close the liquid feed" } },
      { aid: "MEASURE:COIL_GAUGE:EV-03",
        hint: { ru: "послать работника снять давление по местному манометру",
                en: "send a worker to read the local pressure gauge" } },
      { aid: "NO_OP",
        hint: { ru: "продолжить наблюдение", en: "keep observing" } },
    ],
  },
  {
    key: "hotgas",
    ask: { ru: "Подача закрыта, но змеевик остаётся под горячим паром, а " +
               "металл прогрет. Через несколько минут контроллер сбросит " +
               "состояние в «охлаждение». Что сделаете?",
           en: "The feed is closed, but the coil is still under hot gas and " +
               "the metal is warm. In a few minutes the controller will " +
               "reset the state to cooling. What do you do?" },
    opts: [
      { aid: "MANUAL:CLOSE_HOTGAS:EV-03",
        hint: { ru: "наряд: закрыть клапан горячего пара вручную",
                en: "dispatch: close the hot gas valve by hand" } },
      { aid: "DEFROST:INHIBIT",
        hint: { ru: "запретить автоматический пуск оттайки",
                en: "inhibit automatic defrost start" } },
      { aid: "ALARM:ACK_ALL",
        hint: { ru: "квитировать тревоги", en: "acknowledge the alarms" } },
      { aid: "NO_OP",
        hint: { ru: "продолжить наблюдение", en: "keep observing" } },
    ],
  },
  {
    key: "lock",
    ask: { ru: "Осталось не дать автоматике снова открыть подачу на " +
               "прогретый змеевик. Последнее решение?",
           en: "What remains is to stop the automation from opening the " +
               "feed onto a warm coil again. Your last decision?" },
    opts: [
      { aid: "DEFROST:INHIBIT",
        hint: { ru: "запретить автоматический пуск оттайки",
                en: "inhibit automatic defrost start" } },
      { aid: "MANUAL:CLOSE_HOTGAS:EV-03",
        hint: { ru: "наряд: закрыть горячий пар вручную",
                en: "dispatch: close the hot gas by hand" } },
      { aid: "NO_OP",
        hint: { ru: "больше ничего не требуется",
                en: "nothing more is needed" } },
      { aid: "COMP:STOP:CO-01",
        hint: { ru: "остановить компрессор", en: "stop the compressor" } },
    ],
  },
];

// Текст развилки на языке интерфейса.
function qt(v) {
  if (v && typeof v === "object") return v[LANG] || v.ru || "";
  return v || "";
}

const MAX_Q = 4;               // столько развилок показываем посетителю
const GAP_S = 60;              // сколько виртуальных секунд между развилками

let QM = {
  on: false,
  i: 0,                        // сколько развилок пройдено
  asked: [],                   // какие развилки уже показаны
  picks: [],                   // {aid, result, t}
  pending: false,
  phase: "idle",               // 'ask' | 'roll' | 'over'
  rollLeft: 0,
  finalData: null,
  tNow: 0,
};

// Вводная: тот же экран, что у полной задачи, но с честным предупреждением,
// что взаимодействие сокращено и результат не является результатом бенчмарка.
function showQuickBrief() {
  const s = SCEN.find(x => x.sid === "S1");
  BRIEFKIND = "quick";
  $("#btitle").textContent = L("title");
  $("#btext").textContent = L("intro");
  $("#wbrief").innerHTML = "<b>" + L("notOfficial") + "</b><br>" + L("rules");
  $("#wbrief").style.display = "";
  $("#brules").style.display = "none";
  $("#scalewrap").style.display = "none";
  $("#acceptb").textContent = L("begin");
  $("#acceptb").disabled = false;
  $("#acceptb").onclick = startQuick;
  $("#backb").onclick = showHub;
  sid = "S1";
  showScreen("brief");
  return s;
}

function startQuick() {
  QM = { on: true, i: 0, asked: [], picks: [], pending: false,
         phase: "idle", rollLeft: 0, finalData: null, tNow: 0 };
  mode = "quick";
  sid = "S1";
  hist = { t: [], k: {} };
  $("#log").innerHTML = "";
  applyMode();
  $("#qbox").innerHTML = "<p class='mut'>" + L("waiting") + "</p>";
  $("#busy").style.display = "none";
  QM.pending = true;
  post({ cmd: "start", sid: "S1",
         esd_just: (typeof esdJust === "function") ? esdJust("S1")
                                                   : false });
}

// Вызывается из handle() на каждом наблюдении, пока идёт проба.
function quickOnObs(isTick) {
  QM.pending = false;
  QM.tNow = obs ? obs.t : QM.tNow;
  if (QM.phase === "roll" && QM.rollLeft > 1e-6) { quickRoll(); return; }
  // Досмотр до конца задачи продолжается порциями, пока двойник не скажет,
  // что задача окончена.
  if (QM.phase === "over") { quickFastForward(); return; }
  quickAsk();
}

// Выбор следующего вопроса по фактическому состоянию, а не по счётчику:
// человек мог закрыть подачу первым же решением, и спрашивать про
// зависший секвенсор тогда незачем.
function quickPickStep() {
  const ev = (obs && obs.evaps || []).find(v => v.tag === "EV-03");
  const hot = ev && ev.mode !== "COOL";
  const used = new Set(QM.asked);
  const feedClosed = QM.picks.some(p => p.aid === "FEED:CLOSE:EV-03");
  const hotClosed = QM.picks.some(p => p.aid === "MANUAL:CLOSE_HOTGAS:EV-03");

  if (!used.has("start")) return QSTEPS[0];
  if (hot && !feedClosed && !used.has("stuck")) return QSTEPS[1];
  if (hot && !hotClosed && !used.has("hotgas")) return QSTEPS[2];
  if (!used.has("lock")) return QSTEPS[3];
  return null;
}

function quickAsk() {
  if (QM.i >= MAX_Q) { quickFinish(); return; }
  const step = quickPickStep();
  if (!step) { quickFinish(); return; }
  QM.phase = "ask";
  const left = MAX_Q - QM.i;
  let h = "<div class='qhead'><span class='qbadge'>" + L("notOfficial") +
          "</span><span class='mut'>" + L("decisionsLeft") + ": " + left +
          " · " + L("taskTime") + " " + hhmmss(QM.tNow) + "</span></div>";
  h += "<div class='qask'>" + qt(step.ask) + "</div>";
  h += "<div class='qopts'>";
  step.opts.forEach((o, k) => {
    h += "<button class='qopt' data-k='" + k + "'><b>" +
         actText(o.aid) + "</b><span>" + qt(o.hint) + "</span></button>";
  });
  h += "</div>";
  h += quickHistoryHTML();
  $("#qbox").innerHTML = h;
  $("#qbox").querySelectorAll(".qopt").forEach(el => {
    el.onclick = () => quickChoose(step, +el.dataset.k);
  });
}

function quickChoose(step, k) {
  if (QM.pending) return;
  const o = step.opts[k];
  QM.asked.push(step.key);
  QM.i += 1;
  QM.pendingPick = o.aid;
  QM.pending = true;
  $("#qbox").innerHTML = "<p class='mut'>" + L("waiting") + "</p>";
  // Раздумья не начисляются -- это и есть упрощение пробы.
  post({ cmd: "act", aid: o.aid, think: 0 });
}

// Ответ двойника на команду: подлинный текст, не заготовка.
function quickResult(resultText) {
  const aid = QM.pendingPick;
  QM.pendingPick = null;
  QM.picks.push({ aid: aid, result: resultText || "", t: QM.tNow });
  QM.phase = "answer";
  quickShowAnswer();
}

// Ответ нарисован отдельно от его получения: переключение языка должно
// перерисовать этот экран, а второй раз спросить двойник нельзя.
function quickShowAnswer() {
  const p = QM.picks[QM.picks.length - 1];
  if (!p) return;
  const aid = p.aid, resultText = p.result;
  let h = "<div class='qhead'><span class='qbadge'>" + L("notOfficial") +
          "</span><span class='mut'>" + L("taskTime") + " " + hhmmss(p.t) +
          "</span></div>";
  h += "<div class='qchose'><span class='lbl'>" + L("chose") + "</span>" +
       actText(aid) + "</div>";
  h += "<div class='qans'><span class='lbl'>" + L("answer") + "</span>" +
       plantReply(resultText || "—") + "</div>";
  h += "<div class='qnav'><button id='qnext'>" + L("next") + "</button>" +
       "<button id='qskip'>" + L("toResult") + "</button></div>";
  h += quickHistoryHTML();
  $("#qbox").innerHTML = h;
  $("#qnext").onclick = () => quickBeginRoll();
  $("#qskip").onclick = () => { QM.i = MAX_Q; quickBeginRoll(); };
}

// Промотка между развилками: установка живёт, посетитель не ждёт.
function quickBeginRoll() {
  QM.phase = "roll";
  QM.rollLeft = GAP_S;
  $("#qbox").innerHTML = "<div class='qroll'>" + L("rolling") +
    "<div class='pb'><i id='qpb' style='width:0%'></i></div></div>";
  quickRoll();
}

function quickRoll() {
  if (QM.rollLeft <= 1e-6) { QM.phase = "ask"; quickAsk(); return; }
  const chunk = Math.min(10, QM.rollLeft);
  QM.rollLeft -= chunk;
  const pb = $("#qpb");
  if (pb) pb.style.width = (100 * (GAP_S - QM.rollLeft) / GAP_S).toFixed(0) + "%";
  QM.pending = true;
  post({ cmd: "tick", seconds: chunk });
}

// Досмотр до конца задачи: остаток проматывается без участия человека.
function quickFinish() {
  QM.phase = "over";
  $("#qbox").innerHTML = "<div class='qroll'>" + L("watchingOut") +
    "<div class='pb'><i id='qpb' style='width:0%'></i></div></div>";
  quickFastForward();
}

function quickFastForward() {
  if (QM.finalData) { quickShowResult(); return; }
  const r = wScen && wScen("S1");
  const hz = (r && r.horizon_s) || 1800;
  const pb = $("#qpb");
  if (pb) pb.style.width = (100 * Math.min(1, QM.tNow / hz)).toFixed(0) + "%";
  QM.pending = true;
  // Крупная порция: остаток задачи бывает больше двадцати минут, и мелкими
  // шагами это сотни вызовов. Исход от размера порции не зависит.
  post({ cmd: "tick", seconds: 60, coarse: true });
}

function quickEnded(t) {
  QM.tNow = t;
  QM.phase = "over";
  QM.pending = true;
  post({ cmd: "final" });
}

function quickFinalData(data) {
  QM.finalData = data;
  QM.phase = "over";
  quickShowResult();
}

function quickShowResult() {
  const d = QM.finalData || {};
  const cat = d.CAT || [];
  const maj = d.MAJ || [];
  let h = "<div class='qhead'><span class='qbadge'>" + L("notOfficial") +
          "</span></div>";
  h += "<h3 class='" + (cat.length ? "bad" : "ok") + "'>" +
       (cat.length ? L("cat") + ": " + cat.map(c => outcomeCode(c)).join(", ")
                   : L("prevented")) + "</h3>";
  h += "<table class='kv'>";
  h += "<tr><td>" + L("taskTime") + "</td><td>" + hhmmss(d.t_end || QM.tNow) +
       "</td></tr>";
  if (cat.length) {
    h += "<tr><td>" + L("whatHappened") + "</td><td>" +
         cat.map(c => outcomeDecode(c)).join("; ") + "</td></tr>";
  }
  if (maj.length) {
    h += "<tr><td>" + L("damage") + "</td><td>" + maj.map(m => outcomeCode(m)).join(", ") +
         "</td></tr>";
  }
  h += "<tr><td>" + L("released") + "</td><td>" + (d.released || 0).toFixed(1) +
       " " + L("unitKg") + "</td></tr>";
  h += "<tr><td>" + L("yourDecisions") + "</td><td>" + QM.picks.length + "</td></tr>";
  h += "</table>";

  // Сравнение с программами на этой же задаче -- из того же манифеста, что
  // и таблица результатов.
  const runs = MANIFEST.runs.filter(x => x.scenario === "S1" &&
                                         x.kind === "model");
  if (runs.length) {
    h += "<div class='lbl'>" + L("howPrograms") + "</div>";
    h += "<table class='kv'>";
    runs.forEach(x => {
      h += "<tr><td>" + x.agent + "</td><td>" +
           (x.CAT.length ? L("cat") + " " + x.CAT.map(outcomeCode).join("+")
                         : (x.MAJ.length ? L("damage") + " " +
                                           x.MAJ.map(outcomeCode).join("+")
                                         : L("clean"))) +
           " · " + L("score") + " " + x.score + "</td></tr>";
    });
    h += "</table>";
  }
  h += "<p class='mut'>" + L("rules") + "</p>";
  // Результат пробы тоже можно положить в таблицу -- но только пометкой
  // «демо»: взаимодействие сокращено, и это не результат бенчмарка.
  if (typeof mineAddHTML === "function" && QM.finalData) {
    h += mineAddHTML("quick");
  }
  h += quickHistoryHTML();
  h += "<div class='qnav'>" +
       "<button id='qagain'>" + L("qAgain") + "</button>" +
       "<button id='qfull'>" + L("full") + "</button>" +
       "<button id='qwatch'>" + L("qWatch") + "</button>" +
       "<button id='qhub'>" + L("hub") + "</button></div>";
  $("#qbox").innerHTML = h;
  if (typeof mineBind === "function" && QM.finalData) {
    mineBind(Object.assign({ sid: "S1" }, QM.finalData), "quick");
  }
  $("#qagain").onclick = startQuick;
  $("#qfull").onclick = () => { quickLeave();
                                const s = SCEN.find(x => x.sid === "S1");
                                if (s) { sid = "S1"; showBrief(s); } };
  $("#qwatch").onclick = () => { quickLeave(); showWatchPick(); };
  $("#qhub").onclick = () => { quickLeave(); showHub(); };
}

function quickHistoryHTML() {
  if (!QM.picks.length) return "";
  let h = "<div class='qhist'><div class='lbl'>" + L("yourDecisions") + "</div>";
  QM.picks.forEach((p, i) => {
    h += "<div class='qh'><b>" + (i + 1) + ".</b> " +
         actText(p.aid) +
         "<span>" + plantReply(p.result || "") + "</span></div>";
  });
  h += "</div>";
  return h;
}

function quickLeave() {
  QM.on = false;
  QM.phase = "idle";
  mode = "play";
  applyMode();
  restorePlayBrief();
}
