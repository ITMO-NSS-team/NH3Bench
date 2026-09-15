// =====================================================================
// Watch / Compare -- просмотр сохранённых прогонов моделей.
//
// Надстройка над тренажёром, а не второй тренажёр. Воспроизведение идёт
// теми же командами воркера, которыми играет человек ({cmd:'act', aid,
// think}), и рисуется тем же renderObs(): физика, карта и приборы --
// общие. Отличие одно: действия подаёт не пользователь, а сохранённый
// протокол, и число токенов берётся из него же.
//
// Источник истины -- неизменяемый протокол прогона. Скорость показа не
// влияет ни на одну величину внутри задачи: она меняет лишь то, сколько
// реальных секунд зритель ждёт между решениями. Двадцатикратное ускорение
// показывает те же 20 виртуальных секунд за одну реальную.
// =====================================================================

// Данные прогонов кладёт сборка (build_trainer.py) отдельным объявлением
// перед этим файлом. Здесь они только читаются, с пустым запасным
// значением: файл должен оставаться разбираемым JavaScript сам по себе,
// иначе редактор теряет разбор всего остального.
const MANIFEST = (typeof NH3_MANIFEST !== "undefined") ? NH3_MANIFEST
  : { benchmark: {}, scenarios: [], agents: [], runs: [], esd_just: {} };
const TRACES = (typeof NH3_TRACES !== "undefined") ? NH3_TRACES : {};

// Подписи вынесены в один объект: английская версия добавляется сюда же,
// без охоты за литералами по всему файлу.
const WL = {
  watch: "Смотреть прогон программы",
  play: "Пройти задачу самому",
  compare: "Сравнить результаты",
  demo: "Быстрая проба (задача №1)",
  pickRun: "Выберите программу и задачу",
  noTrace: "протокола нет",
  decision: "решение",
  of: "из",
  tokens: "токенов",
  thinkS: "раздумья",
  reasoning: "Рассуждение программы",
  rawReply: "показать ответ целиком",
  hideReply: "свернуть ответ",
  timeline: "Ход решений",
  speed: "Скорость показа",
  step: "по решениям",
  nextDec: "следующее решение",
  nextAlarm: "до новой сигнализации",
  toEnd: "до конца",
  pause: "пауза",
  resume: "продолжить",
  back: "назад",
  ponr: "точка невозврата",
  ponrTag: "невозврат",
  tlLegend: "толщина отметки — цена раздумий в токенах · приглушённая — " +
            "бездействие · жёлтая — текущее решение · щелчок по полосе " +
            "открывает решение · перемотка — за белый бегунок · красная " +
            "черта — точка невозврата",
  outcome: "Исход",
  score: "балл",
  mean: "среднее",
  regGap: "разрыв с регламентом",
  scen: "Задача",
  agent: "Программа",
  watchThis: "смотреть этот прогон",
  clean: "чисто",
  prevented: "авария предотвращена",
  cat: "КАТАСТРОФА",
  thinkTotal: "всего раздумий",
  decisions: "решений",
  showFinal: "итог задачи",
  again: "смотреть заново",
  playSelf: "пройти самому",
  otherRun: "другой прогон",
  toHub: "главное меню",
  // пояснения на экранах
  hubRecs: "записей",
  hubCmpNote: "программы и опорные политики по всем задачам",
  hubDemoNote: "три-четыре решения, около двух минут",
  hubPlayNote: "шесть задач в тех же условиях, что у программ, и короткая проба",
  beginWatch: "НАЧАТЬ ПРОСМОТР",
  briefTook: "прошла эту задачу за",
  briefThink: "на раздумья ушло",
  briefPlantTime: "времени установки",
  briefOutcome: "Исход",
  briefSame: "Вы увидите то же, что видела она: тот же щит, те же приборы, " +
             "то же время. Команды подаёт запись.",
  damage: "ущерб",
  thinkingNow: "ПРОГРАММА ДУМАЕТ — установка не ждёт",
  ofPlantTime: "с времени установки",
  taskOver: "ЗАДАЧА ОКОНЧЕНА",
  preparing: "готовит",
  endedWhileThinking: "ЗАДАЧА ОКОНЧЕНА, пока программа думала: ответ",
  neverIssued: "так и не был подан (не хватило",
  secondsShort: "с раздумий)",
  stepHint: "пауза в тот момент, когда ответ готов, но ещё не подан",
  command: "команда",
  thinkCost: "раздумья",
  execTime: "исполнение",
  parseStatus: "разбор ответа",
  wallTime: "реальное время вызова",
  wallNote: "(в часах задачи не учитывается)",
  scoreNote: "Балл 0..100: катастрофа обнуляет прогон; люди, экономика и " +
             "дисциплина входят множителями. Разрыв с регламентом -- " +
             "разность с политикой буквального следования инструкции. " +
             "Клетка со знаком ▸ открывает запись прогона.",
  cellNote: "Клетка — балл прогона.",
  partialNote: "строка неполная",
  partialTail: "Среднее по части задач не сравнимо со средним по всем, и " +
               "разрыв с регламентом для такой строки не считается.",
  needFull: "нужен полный набор",
  measuredOf: "измерено",
  ofTasks: "задач",
  langLimit: "Команды, вводные и ответы установки приходят из имитатора " +
             "по-русски; рассуждения моделей сохранены дословно.",
  base: "база",
  leaveAsk: "Выйти из задачи? Прогон не будет засчитан.",
  playOutAsk: "Доиграть задачу до конца без вмешательства? Время " +
              "прокрутится, решения больше подавать нельзя.",
  playOutBusy: "задача доигрывается, установка живёт…",
  diffOpen: "сравнить решения",
  mineOwn: "свой",
  diffTitle: "Чем решения двух программ отличались",
  diffCommon: "совпало команд",
  diffFirst: "первое расхождение",
  diffPonrLine: "точка невозврата — ниже аварию предотвратить уже нельзя",
  diffEnded: "задача окончена",
  diffCat: "КАТАСТРОФА",
  diffNote: "Выравнивание -- по последовательности команд, а не по времени: " +
            "одна и та же команда, поданная позже, остаётся совпадением со " +
            "сдвигом времени. Серые строки -- команда совпала, цветные -- " +
            "разошлись. Времена и токены взяты из сохранённых протоколов.",
  diffNoPair: "для сравнения нужны две записи одной задачи",
  userRuns: "Прогоны через провайдера",
  userNote: "измерены самостоятельно (benchmark.py run); не часть " +
            "опубликованной матрицы",
  baseRuns: "Опубликованная матрица",
  seekBack: "← назад, с перезапуском",
  startedWith: "начало задачи",
  unitS: "с",
  unitKg: "кг",
  thinkingShort: "думает",
  taskOverShort: "задача окончена",
  "g.psucLP": "Р всас НД",
  "g.psucIP": "Р всас СД",
  "g.pcond": "Р конденсации",
  "g.lvlLP": "Уровень ЦР-НД",
  "g.lvlIP": "Уровень ЦР-СД",
  "g.lvlHP": "Уровень РЛ",
  "g.nh3mr": "NH₃ машзал",
  "g.nh3hall": "NH₃ цех",
  "g.milk": "Молоко",
  "g.icewater": "Ледяная вода",
  "g.icestock": "Запас льда",
  "g.chill": "Камера +2",
  "g.lt": "НТ-склад",
  "g.blast": "Морозильная",
  "g.power": "Потребление",
  takeShift: "ПРИНЯТЬ СМЕНУ",
  tokShort: "ток.",
  fewData: "мало данных",
  "grp.observe": "Наблюдение",
  "grp.measure": "Наряды: замеры",
  "grp.manual": "Наряды: ручные операции",
  "grp.defrost": "Оттайка и подача",
  "grp.comp": "Компрессоры",
  "grp.pump": "Насосы",
  "grp.lv": "Клапаны уровня",
  "grp.cond": "Конденсаторы",
  "grp.setpoint": "Уставки",
  "grp.safety": "Аварийные системы и персонал",
  "grp.alarm": "Сигнализация",
  unitP: "кгс/см²",
  unitC: "°С",
  unitT: "т",
  unitKW: "кВт",
  unitMg: "мг/м³",
  unitMin: "мин",
  horizon: "горизонт",
  untilEnd: "до конца задачи",
  pauseBtn: "ПАУЗА (для разбора)",
  resumeBtn: "ПРОДОЛЖИТЬ",
  openHist: "открыть историю показателя",
  "sec.evaps": "Воздухоохладители",
  "sec.pumps": "Насосы аммиачные",
  "err.worker": "Отказ исполнителя",
  "err.generic": "ОШИБКА",
  "busy.progress": "процесс идёт…",
  "st.ok": "СОШЛОСЬ",
  "st.bad": "РАСХОЖДЕНИЕ",
  "st.ref": "эталон CPython: КАТ-3 на 614-й",
  vac: "вак.",
  slide: "золотн.",
  discharge: "нагн.",
  feed: "подача",
  open: "ОТКР",
  closed: "закр",
  coilP: "Р бат.",
  fans: "вент.",
  spray: "орошение",
  on: "вкл",
  off: "ВЫКЛ",
  permit: "НАРЯД-ДОПУСК",
  noAlarms: "активных тревог нет",
  dose: "доза",
  unitDose: "мг/м³·мин",
  scba: "дых. аппарат",
  tasksRunning: "Наряды в работе",
  reports: "Доклады",
  report: "ДОКЛАД",
  busyTxt: "установка живёт, команда исполняется…",
  cmdLog: "КОМАНДА",
  observing: "наблюдение",
  axisTime: "время задачи, мин",
  accident: "АВАРИЯ",
  catPrevented: "КАТАСТРОФА ПРЕДОТВРАЩЕНА",
  ofWhichThink: "из них ваши раздумья",
  pauseUsed: "использовалась пауза",
  endedManually: "завершено вручную",
  esd: "общий стоп",
  yes: "да",
  no: "нет",
  finMine: "Ваш результат",
  finMineRun: "Результат этого прогона",
  maxDose: "Наибольшая доза персонала",
  refOperator: "Опорный оператор",
  stRunning: "проверка идёт (полминуты)…",
  clickHint: "Щёлкните по аппарату, помещению или обходчику.",
  esdBanner: "ОБЩИЙ АВАРИЙНЫЙ СТОП",
  alarmBanner: "ТРЕВОГА",
  expand: "развернуть",
  collapse: "свернуть",
  "pol.null": "Бездействие",
  "pol.random": "Случайный",
  "pol.reg": "Регламент",
  "pol.oracle": "Эталон",
  "note.pyodide": "загрузка исполнителя Python (~15 МБ, один раз)",
  "note.numpy": "загрузка numpy",
  "note.unpack": "разворачивание имитатора",
  legLiquid: "жидкость",
  legSuction: "всас",
  legHotGas: "гор. пар",
  legGas: "газ по датчикам",
  ice: "лёд",
  milk: "молоко",
  roleBooster: "винтовой бустер нижней ступени",
  roleHighStage: "винтовой компрессор верхней ступени",
  stateWord: "Состояние",
  slideWord: "золотник",
  tDischarge: "t нагнетания",
  tripNote: "Блокировка снимается командой после устранения причины.",
  vesHP: "линейный ресивер",
  vesIP: "циркуляционный ресивер-промсосуд, t₀ −10 °С",
  vesLP: "циркуляционный ресивер, t₀ −40 °С",
  pressureWord: "Давление",
  levelRemote: "уровень по дистанционному датчику",
  glassOnlyByDispatch: "Указатель уровня на самом аппарате читается только нарядом.",
  loopLP: "контур НД (−40 °С)",
  loopIP: "контур СД (−10 °С)",
  ammoniaPump: "аммиачный насос",
  evapCondenser: "испарительный конденсатор",
  fansWord: "Вентиляторов",
  sprayOn: "включено",
  sprayOff: "ВЫКЛЮЧЕНО",
  lotoNote: "Действует наряд-допуск: привод насоса обесточен и заперт; дистанционный пуск невозможен до закрытия допуска.",
  modeByController: "Режим по контроллеру",
  feedSolenoid: "соленоид подачи",
  openFull: "ОТКРЫТ",
  closedFull: "закрыт",
  coilPressure: "Р батареи",
  "place.EV-01": "испаритель ледяной воды (машзал)",
  "place.EV-02": "воздухоохладитель камеры +2 °С",
  "place.EV-03": "батарея НТ-склада",
  "place.EV-04": "батарея НТ-склада",
  "place.EV-05": "батарея морозильной",
  "place.EV-06": "батарея морозильной",
  milkTank: "Молочный танк",
  milkTemp: "t молока",
  milkNote: "(граница по регламенту +6 °С). Охлаждается ледяной водой через пластинчатый охладитель.",
  pasteuriser: "Пастеризатор",
  pastNote: "пластинчатый аппарат приёмки молока; секция охлаждения питается ледяной водой от ВО-1.",
  iceBank: "Льдоаккумулятор",
  iceAt: "при ВО-1",
  iceStock: "Запас льда",
  iceNote: "из 34 т. Ночная наморозка покрывает утренний пик приёмки.",
  nh3ByFixed: "NH₃ по стационарному газоанализатору",
  emergencyVent: "Аварийная вытяжка",
  ventRunning: "работает",
  ventOff: "выключена",
  temperatureWord: "Температура",
  personnel: "Персонал",
  nobody: "нет",
  opRole: "машинист-обходчик",
  zoneWord: "Зона",
  doseLimits: "(нормативы: 370 — сверхнорматив, 1060 — поражение)",
  inScba: "В изолирующем дыхательном аппарате.",
  walkingTo: "Идёт в",
  arrivesIn: "прибытие через",
  performing: "Выполняет",
  readyIn: "готовность через",
};

// Скорости: во сколько раз виртуальное время быстрее реального.
const SPEEDS = [1, 5, 20];

let WM = {            // состояние просмотра
  runId: null,
  steps: [],
  i: 0,                // сколько решений уже подано
  playing: false,
  speed: 5,
  stepMode: false,
  timer: null,
  jumpTo: null,        // 'alarm' | 'end' | null
  lastAlarmCount: 0,
  t0wall: 0,
  // Фаза шага: программа сначала думает (часы идут, установка живёт, команды
  // ещё нет), потом действует. Без этого разделения просмотр выглядел
  // скачками и было непонятно, почему время уходит.
  phase: "idle",       // 'think' | 'act' | 'over'
  thinkLeft: 0,        // сколько виртуальных секунд раздумий осталось
  thinkTotal: 0,
  tNow: 0,             // время задачи по последнему наблюдению
  finalData: null,
  forceFinal: false,
  endedAt: null,       // момент катастрофы, если она застала размышление
  pending: false,      // ждём ответа исполнителя
  retry: false,
  // Пошаговый режим: доехать до готовности ответа и встать. Взведённый
  // «шаг» переживает занятость исполнителя, поэтому нажатие не теряется.
  stepArmed: false,
  seekTo: null,        // цель перемотки, виртуальные секунды
  tPrev: 0,            // время на прошлом наблюдении -- для плавной метки
  tPrevWall: 0,
};

function wRun(id) {
  // Свой прогон живёт в браузере, а не в манифесте.
  return MANIFEST.runs.find(r => r.id === id) ||
    ((typeof mineDiffRunById === "function") ? mineDiffRunById(id) : null);
}
function wScen(sid) { return MANIFEST.scenarios.find(s => s.sid === sid); }

// ---------------------------------------------------------------------
// Главное меню
// ---------------------------------------------------------------------

function showHub() {
  const box = $("#hubbox");
  box.innerHTML = "";
  const nWatch = MANIFEST.runs.filter(r => r.watchable).length;
  // Быстрая проба переехала в список задач: это та же задача 1, короче.
  const items = [
    ["watch", L("watch"), L("hubRecs") + ": " + nWatch, false],
    ["compare", L("compare"), L("hubCmpNote"), false],
    ["play", L("play"), L("hubPlayNote"), false],
  ];
  items.forEach(([key, title, note, soon]) => {
    const b = document.createElement("button");
    b.className = "scbtn";
    b.innerHTML = "<b>" + title + "</b><span>" + note + "</span>";
    b.disabled = !!soon;
    b.onclick = () => {
      if (key === "watch") showWatchPick();
      else if (key === "compare") showCompare();
      else showMenu();
    };
    box.appendChild(b);
  });
  showScreen("hub");
}

// ---------------------------------------------------------------------
// Выбор прогона
// ---------------------------------------------------------------------

function showWatchPick() {
  const box = $("#wpickbox");
  // Свои прогоны тоже смотрятся: у них есть протокол, а значит и запись.
  const models = MANIFEST.agents.filter(
    a => a.kind === "model" || a.kind === "user");
  const sids = MANIFEST.scenarios.map(s => s.sid);
  let h = "<table class='wtab'><tr><th></th>";
  sids.forEach(s => { h += "<th>" + scenNo(s) + "</th>"; });
  h += "</tr>";
  models.forEach(m => {
    // Две записи одной модели на разных языках задания различаются только
    // пометкой -- без неё в списке два одинаковых имени.
    h += "<tr><td class='nm'>" +
         (m.kind === "user"
          ? "<span class='mbadge'>" + L("mineOwn") + "</span>" : "") +
         (m.prompt_lang && m.prompt_lang !== "ru"
          ? "<span class='mbadge'>" + m.prompt_lang.toUpperCase() +
            "</span>" : "") +
         esc(m.id) + "</td>";
    sids.forEach(sid => {
      const r = MANIFEST.runs.find(
        x => x.agent === m.id && x.kind === m.kind && x.scenario === sid
             && x.prompt_lang === m.prompt_lang);
      if (!r || !r.watchable) { h += "<td class='na'>—</td>"; return; }
      const cls = r.CAT.length ? "cat" : (r.clean ? "ok" : "maj");
      h += "<td><button class='wcell " + cls + "' data-run='" + r.id + "'>" +
           r.score + "</button></td>";
    });
    h += "</tr>";
  });
  h += "</table>";
  box.innerHTML = h;
  box.querySelectorAll(".wcell").forEach(el => {
    el.onclick = () => showWatchBrief(el.dataset.run);
  });
  showScreen("wpick");
}

// ---------------------------------------------------------------------
// Воспроизведение
// ---------------------------------------------------------------------

// Подготовка просмотра: тот же экран вводной, что у человека, но принимается
// не смена, а запись прогона.
function showWatchBrief(runId) {
  const r = wRun(runId);
  if (!r || !TRACES[runId]) { alert(L("noTrace")); return; }
  WM.runId = runId;
  BRIEFKIND = "watch";
  const s = wScen(r.scenario);
  const ts = r.trace_stats || {};
  $("#btitle").textContent = L("scen") + " " + scenNo(r.scenario) +
    ". " + scenTitle(r.scenario) + " — " + r.agent;
  $("#btext").textContent = scenBrief(r.scenario);
  $("#wbrief").innerHTML =
    "<b>" + r.agent + "</b> " + L("briefTook") + " <b>" +
    (ts.n_decisions || 0) + "</b> " + L("decisions") + "; " + L("briefThink") + " <b>" +
    hhmmss(ts.think_s_total || 0) + "</b> " + L("briefPlantTime") + " (" +
    (ts.tokens_total || 0) + " " + L("tokens") + "). " + L("briefOutcome") + ": " +
    outcomeText(r) + ".<br>" + L("briefSame");
  $("#wbrief").style.display = "";
  $("#brules").style.display = "none";
  $("#scalewrap").style.display = "none";
  $("#acceptb").textContent = L("beginWatch");
  $("#acceptb").onclick = () => startWatch(WM.runId);
  $("#backb").onclick = showWatchPick;
  showScreen("brief");
}

function outcomeText(r) {
  const code = c => outcomeCode(c);
  if (r.CAT.length) {
    return L("cat") + " (" + r.CAT.map(code).join("+") + ")";
  }
  if (r.MAJ.length) {
    return L("prevented") + ", " + L("damage") + " " + r.MAJ.map(code).join("+");
  }
  return L("clean");
}

function startWatch(runId, seekAfter) {
  const r = wRun(runId);
  if (!r || !TRACES[runId]) { alert(L("noTrace")); return; }
  clearTimeout(WM.timer);
  if (WM.anim) { cancelAnimationFrame(WM.anim); WM.anim = null; }
  WM = Object.assign({}, WM, {
    runId: runId, steps: TRACES[runId], i: 0,
    playing: true, stepMode: false, jumpTo: null, lastAlarmCount: 0,
    phase: "idle", thinkLeft: 0, thinkTotal: 0, tNow: 0,
    finalData: null, forceFinal: false, endedAt: null,
    pending: false, dragging: false, dragT: null,
    // Кадровая анимация отменена выше -- обнуляем и признак, иначе
    // requestNowAnim решит, что она уже идёт, и бегунок замрёт.
    anim: null, retry: false, stepArmed: false,
    // Цель перемотки назад: до неё доигрываем на максимальной скорости.
    seekTo: (typeof seekAfter === "number" && seekAfter > 0)
            ? seekAfter : null,
  });
  mode = "watch";
  sid = r.scenario;
  hist = { t: [], k: {} };
  $("#log").innerHTML = "";
  applyMode();
  // Прогрев показывается полосой на экране вводной -- ровно так же, как при
  // приёме смены человеком. Заслонка поверх экрана здесь не нужна.
  $("#busy").style.display = "none";
  $("#acceptb").disabled = true;
  $("#warmwrap").style.display = "block";
  $("#warmbar").style.width = "0%";
  WM.pending = true;
  post({ cmd: "start", sid: sid });
}

// Исполнитель занят: запоминаем намерение и повторяем, когда освободится.
function watchBusy() {
  WM.retry = true;
  clearTimeout(WM.timer);
  WM.timer = setTimeout(() => { WM.retry = false; watchOnObs(false); }, 120);
}

// ---------------------------------------------------------------------
// Ход просмотра
//
// Шаг решения разложен на две фазы. Сначала программа думает: часы задачи
// идут, установка живёт, приборы обновляются, команды ещё нет. Потом
// команда исполняется. Физика при этом ровно та же, что при подаче
// act(aid, think) целиком -- порции продвижения совпадают с внутренними
// порциями Session._adv, и совпадение исхода проверено на CPython.
// ---------------------------------------------------------------------

function watchOnObs(isTick) {
  WM.pending = false;
  if (obs) {
    WM.tPrev = WM.tNow;
    WM.tNow = obs.t;
    WM.tPrevWall = performance.now();
    WM.lastAlarmCount0 = WM.lastAlarmCount;
    WM.lastAlarmCount = obs.alarms.length;
  }
  if (WM.jumpTo === "alarm" && obs &&
      obs.alarms.length > (WM.lastAlarmCount0 || 0)) {
    WM.jumpTo = null; WM.playing = false;
  }
  // Перемотка достигла цели.
  if (WM.seekTo !== null && WM.tNow >= WM.seekTo) {
    WM.seekTo = null; WM.playing = false; WM.jumpTo = null;
  }

  renderWatchBar();
  renderTimeline();
  if (WM.phase !== "over") requestNowAnim();

  if (!WM.playing) return;
  const fast = (WM.jumpTo === "end" || WM.seekTo !== null);
  const spent = performance.now() - WM.t0wall;

  if (WM.phase === "think" && WM.thinkLeft > 1e-6) {
    // Ещё думает: продвигаем время порциями и показываем это.
    const chunk = Math.min(10, WM.thinkLeft);
    const target = fast ? 0 : (chunk / WM.speed) * 1000;
    clearTimeout(WM.timer);
    WM.timer = setTimeout(() => watchTick(chunk),
                          Math.max(0, target - spent));
    return;
  }
  if (WM.phase === "think") {
    // Ответ готов, но ещё не подан -- осмысленная точка останова.
    if (WM.stepArmed) {
      WM.stepArmed = false; WM.playing = false;
      renderWatchBar(); renderWatchCtl(); return;
    }
    clearTimeout(WM.timer);
    WM.timer = setTimeout(watchDoAct, 0);
    return;
  }
  // Команда исполнена (или это самое начало): переходим к следующей.
  if (WM.i >= WM.steps.length) {
    WM.phase = "over"; WM.playing = false;
    renderWatchBar(); renderWatchCtl(); return;
  }
  const st = WM.steps[WM.i];
  const gap = Math.max(0, st.t_rel - WM.tNow);   // ожидание до опроса щита
  const target = fast ? 0 : (gap / WM.speed) * 1000;
  clearTimeout(WM.timer);
  WM.timer = setTimeout(watchBeginThink, Math.max(0, target - spent));
}

function watchBeginThink() {
  const st = WM.steps[WM.i];
  if (!st) { WM.phase = "over"; WM.playing = false; renderWatchBar(); return; }
  WM.thinkTotal = (st.tokens || 0) / MANIFEST.benchmark.think_rate_tok_per_s;
  WM.thinkLeft = WM.thinkTotal;
  WM.phase = "think";
  WM.t0wall = performance.now();
  renderWatchBar();
  watchOnObs(false);
}

function watchTick(seconds) {
  WM.thinkLeft = Math.max(0, WM.thinkLeft - seconds);
  WM.t0wall = performance.now();
  WM.pending = true;
  post({ cmd: "tick", seconds: seconds });
}

function watchDoAct() {
  const st = WM.steps[WM.i];
  if (!st) return;
  WM.i += 1;
  WM.phase = "act";
  WM.thinkLeft = 0;
  // Название команды -- через actText: TR переводит только обозначения
  // оборудования, поэтому в английском журнале оставался русский текст.
  pushLog("[" + hhmmss(WM.tNow) + "] " + actText(st.action) +
    "  (" + (st.tokens || 0) + " " + L("tokens") + ", " +
    L("thinkS") + " " + Math.round(WM.thinkTotal) + " " +
    L("unitS") + ")");
  WM.t0wall = performance.now();
  WM.pending = true;
  // Раздумья уже отыграны порциями, поэтому здесь они нулевые.
  post({ cmd: "act", aid: st.action, think: 0 });
}

// Задача кончилась во время размышления: показываем сам момент, а не итог.
function watchEnded(t) {
  WM.phase = "over";
  WM.playing = false;
  WM.endedAt = t;
  clearTimeout(WM.timer);
  const st = WM.steps[WM.i];
  if (st) {
    pushLog("[" + hhmmss(t) + "] " + L("endedWhileThinking") + " «" +
      actText(st.action) + "» " + L("neverIssued") + " " +
      Math.round(WM.thinkLeft) + " " + L("secondsShort"));
  }
  renderWatchBar();
  renderTimeline();
}

function watchFinalReady(data) {
  // Признак «это итог записи» едет вместе с данными: mode к моменту
  // показа итога уже переключён обратно на игру.
  if (data) data.watched = true;
  WM.finalData = data;
  WM.phase = "over";
  WM.playing = false;
  clearTimeout(WM.timer);
  renderWatchBar();
  renderTimeline();
}

// Часы в заголовке: время задачи и то, чем занята программа.
function watchClock() {
  const t = WM.tNow;
  $("#clock").textContent = hhmmss(t);
  if (WM.phase === "think") {
    const done = WM.thinkTotal - WM.thinkLeft;
    $("#thinkv").textContent = L("thinkingShort") + " " + Math.round(done) +
      " / " + Math.round(WM.thinkTotal) + " " + L("unitS");
  } else if (WM.phase === "over") {
    $("#thinkv").textContent = L("taskOverShort");
  } else {
    $("#thinkv").textContent = "—";
  }
  const r = wRun(WM.runId);
  const hz = (r && r.horizon_s) || (obs && obs.horizon) || 1800;
  $("#horiz").textContent = L("untilEnd") + " " + hhmmss(Math.max(0, hz - t));
}

// ---------------------------------------------------------------------
// Панель просмотра
// ---------------------------------------------------------------------

function renderWatchBar() {
  const r = wRun(WM.runId);
  if (!r) return;
  // Пока программа думает, показываем ТО решение, которое она готовит;
  // после исполнения -- то, которое подала.
  const thinking = WM.phase === "think";
  const idx = thinking ? WM.i : Math.max(0, WM.i - 1);
  const st = WM.steps[idx] || WM.steps[WM.steps.length - 1];
  if (!st) return;
  const think = (st.tokens || 0) / MANIFEST.benchmark.think_rate_tok_per_s;
  const totTok = WM.steps.slice(0, WM.i)
    .reduce((a, s) => a + (s.tokens || 0), 0);

  let h = "<div class='wtop'><div>";
  h += "<b>" + r.agent + "</b> · " + L("scen") + " " +
       scenNo(r.scenario) + " · " +
       L("decision") + " " + (idx + 1) + " " + L("of") + " " + WM.steps.length;
  h += "</div><div class='wnum'>" +
       (st.tokens || 0) + " " + L("tokens") + " · " + L("thinkS") + " " +
       Math.round(think) + " " + L("unitS") + " · " + L("thinkTotal") + " " +
       Math.round(totTok / MANIFEST.benchmark.think_rate_tok_per_s) + " " + L("unitS") +
       "</div></div>";

  // Состояние шага -- главное, чего не хватало: без него ускоренный показ
  // выглядел необъяснимыми скачками времени.
  if (WM.phase === "over") {
    const cat = (WM.finalData && WM.finalData.CAT) || r.CAT || [];
    h += "<div class='wst " + (cat.length ? "bad" : "ok") + "'>" +
         (cat.length ? L("taskOver") + ": " + cat.join("+") +
                       ", " + hhmmss(WM.endedAt || r.t_end_s || 0)
                     : L("taskOver") + ": " + outcomeText(r)) + "</div>";
  } else if (thinking) {
    const done = WM.thinkTotal - WM.thinkLeft;
    const pct = WM.thinkTotal > 0 ? 100 * done / WM.thinkTotal : 100;
    h += "<div class='wst think'>" + L("thinkingNow") + ": " +
         Math.round(done) + " " + L("of") + " " + Math.round(WM.thinkTotal) +
         " " + L("ofPlantTime") +
         "<div class='pb'><i style='width:" +
         pct.toFixed(1) + "%'></i></div></div>";
  }

  h += "<div class='wact" + (thinking ? " pend" : "") + "'>" +
    (thinking ? "<span class='pfx'>" + L("preparing") + ": </span>" : "") +
    actText(st.action) +
    "<span class='aid'>" + st.action + "</span></div>";

  const reply = (st.reply || "").trim();
  if (reply && !thinking) {
    // По умолчанию показывается короткая выжимка: на стенде длинное
    // рассуждение никто не читает, но возможность увидеть подлинный
    // ответ целиком должна остаться -- иначе это уже не протокол.
    const short = replyExcerpt(reply, 400);
    const full = replyMarks(reply);
    h += "<div class='wrsn'><div class='lbl'>" + L("reasoning") + "</div>" +
         "<div id='wshort'>" + esc(short) +
         (full.length > short.length ? "…" : "") + "</div>" +
         "<div id='wfull' style='display:none'>" + esc(full) + "</div>" +
         "<button id='wtog'>" + L("rawReply") + "</button></div>";
  }

  $("#watchbar").innerHTML = h;
  const tog = $("#wtog");
  if (tog) tog.onclick = () => {
    const f = $("#wfull"), s = $("#wshort");
    const open = f.style.display === "none";
    f.style.display = open ? "" : "none";
    s.style.display = open ? "none" : "";
    tog.textContent = open ? L("hideReply") : L("rawReply");
  };
  renderWatchCtl();
}

function renderWatchCtl() {
  const over = WM.phase === "over";
  let h = "";
  if (!over) {
    h += "<span class='lbl'>" + L("speed") + "</span>";
    SPEEDS.forEach(s => {
      h += "<button class='wsp" +
           (s === WM.speed && !WM.stepMode ? " on" : "") +
           "' data-sp='" + s + "'>×" + s + "</button>";
    });
    h += "<button class='wsp" + (WM.stepMode ? " on" : "") +
         "' data-sp='step' title='" + L("stepHint") + "'>" +
         L("step") + "</button>";
    h += "<span class='sep'></span>";
    h += "<button id='wpp'>" + (WM.playing ? L("pause") : L("resume")) +
         "</button>";
    h += "<button id='wnext'>" + L("nextDec") + "</button>";
    h += "<button id='walarm'>" + L("nextAlarm") + "</button>";
    h += "<button id='wend'>" + L("toEnd") + "</button>";
    h += "<span class='sep'></span>";
  }
  // По завершении -- то, чего не хватало: внятный выбор, что делать дальше.
  if (over) h += "<button id='wfin' class='on'>" + L("showFinal") + "</button>";
  h += "<button id='wagain'>" + L("again") + "</button>";
  h += "<button id='wself'>" + L("playSelf") + "</button>";
  h += "<button id='wpick'>" + L("otherRun") + "</button>";
  h += "<button id='wback'>" + L("toHub") + "</button>";
  $("#watchctl").innerHTML = h;

  $("#watchctl").querySelectorAll(".wsp").forEach(el => {
    el.onclick = () => {
      if (el.dataset.sp === "step") {
        // Пошаговый режим не «ставит на паузу здесь», а доезжает до
        // следующей готовности ответа и встаёт там.
        WM.stepMode = true; WM.stepArmed = true; WM.playing = true;
        WM.jumpTo = null; WM.seekTo = null; WM.t0wall = 0;
      } else {
        WM.stepMode = false; WM.stepArmed = false;
        WM.speed = +el.dataset.sp; WM.playing = true;
        WM.t0wall = performance.now();
      }
      renderWatchCtl();
      if (!WM.pending) watchOnObs(false);
    };
  });
  const pp = $("#wpp");
  if (pp) pp.onclick = () => {
    WM.playing = !WM.playing;
    if (WM.playing) { WM.t0wall = performance.now();
                      if (WM.stepMode) WM.stepArmed = true;
                      renderWatchCtl();
                      if (!WM.pending) watchOnObs(false); }
    else { clearTimeout(WM.timer); renderWatchCtl(); }
  };
  const nx = $("#wnext");
  if (nx) nx.onclick = () => {
    // «Следующее решение»: домотать до момента, когда ответ готов, и встать.
    // Взведённый шаг переживает занятость исполнителя, поэтому нажатие не
    // теряется, даже если Pyodide в этот миг считает порцию.
    clearTimeout(WM.timer);
    WM.stepMode = true; WM.playing = true;
    WM.jumpTo = null; WM.seekTo = null; WM.t0wall = 0;
    // Если стоим ровно на готовом ответе -- подать его и встать на следующем.
    const atReady = WM.phase === "think" && WM.thinkLeft <= 1e-6;
    WM.stepArmed = true;
    renderWatchCtl();
    if (WM.pending) return;
    if (atReady) watchDoAct(); else watchOnObs(false);
  };
  const al = $("#walarm");
  if (al) al.onclick = () => {
    WM.jumpTo = "alarm"; WM.playing = true; WM.stepMode = false;
    WM.stepArmed = false; WM.speed = 20; WM.t0wall = 0;
    renderWatchCtl();
    if (!WM.pending) watchOnObs(false);
  };
  const en = $("#wend");
  if (en) en.onclick = () => {
    WM.jumpTo = "end"; WM.playing = true; WM.stepMode = false;
    WM.stepArmed = false; WM.t0wall = 0;
    renderWatchCtl();
    if (!WM.pending) watchOnObs(false);
  };
  const fin = $("#wfin");
  if (fin) fin.onclick = () => {
    // Уходя на итог, возвращаем экран задачи человеку: иначе кнопки
    // «пройти заново» и «к списку задач» на итоговом экране не работали.
    const data = WM.finalData;
    WM.forceFinal = true;
    watchLeave();
    if (data) showFinal(data);
    // Итог ещё не запрошен: помечаем разово, чтобы пометку получил именно
    // этот ответ двойника, а не следующий итог человека.
    else { WM.markWatched = true; lockUI(true); post({ cmd: "final" }); }
  };
  $("#wagain").onclick = () => { clearTimeout(WM.timer);
                                 startWatch(WM.runId); };
  $("#wself").onclick = () => {
    clearTimeout(WM.timer); WM.playing = false;
    watchLeave();
    const s = SCEN.find(x => x.sid === sid);
    if (s) showBrief(s); else showMenu();
  };
  $("#wpick").onclick = () => { clearTimeout(WM.timer); WM.playing = false;
                                watchLeave(); showWatchPick(); };
  $("#wback").onclick = () => { clearTimeout(WM.timer); WM.playing = false;
                                watchLeave(); showHub(); };
}

// Возврат экрана задачи в состояние «играет человек». Без этого после
// просмотра оставался гибрид: каталога нет, кнопки не действуют.
function watchLeave() {
  clearTimeout(WM.timer);
  WM.playing = false;
  WM.phase = "idle";
  mode = "play";
  applyMode();
  restorePlayBrief();
}

// Экран вводной обслуживает и просмотр, и игру, поэтому его надо возвращать
// в исходный вид: иначе на нём остаётся кнопка «НАЧАТЬ ПРОСМОТР».
function restorePlayBrief() {
  BRIEFKIND = "play";
  const wb = $("#wbrief"); if (wb) wb.style.display = "none";
  const br = $("#brules"); if (br) br.style.display = "";
  const sw = $("#scalewrap"); if (sw) sw.style.display = "";
  const ab = $("#acceptb");
  if (ab) { ab.textContent = L("takeShift"); ab.onclick = acceptShift;
            ab.disabled = false; }
  const bb = $("#backb"); if (bb) bb.onclick = showMenu;
}

// ---------------------------------------------------------------------
// Таймлайн решений
// ---------------------------------------------------------------------

function renderTimeline() {
  const r = wRun(WM.runId);
  if (!r) return;
  // Во время перетаскивания разметку не трогаем: подмена элемента под курсором
  // и ломала перемотку.
  if (WM.dragging) { drawNow(WM.dragT, true); return; }
  const sc = wScen(r.scenario);
  const hz = r.horizon_s || (sc && sc.horizon_s) || 1800;
  const ponr = sc && sc.ponr_cat_s;
  let h = "<div class='tl'>";
  WM.steps.forEach((s, i) => {
    const x = Math.min(100, 100 * s.t_rel / hz);
    const cls = (i < WM.i ? "d done" : "d") +
      (s.action === "NO_OP" ? " noop" : "") +
      (i === WM.i - 1 ? " cur" : "");
    // Толщина отметки -- цена размышления: сколько виртуальных секунд
    // стоило это решение. Так видно, где программа думала дорого.
    const w = Math.max(2, Math.min(14, (s.tokens || 0) / 400));
    h += "<i class='" + cls + "' style='left:" + x.toFixed(2) +
         "%;width:" + w.toFixed(1) + "px' data-i='" + i + "' title='" +
         hhmmss(s.t_rel) + " · " + s.action + " · " + (s.tokens || 0) +
         " " + L("tokShort") + "'></i>";
  });
  if (ponr) {
    const px = Math.min(100, 100 * ponr / hz);
    h += "<i class='ponr' style='left:" + px.toFixed(2) + "%' title='" +
         L("ponr") + " " + hhmmss(ponr) + "'></i>";
    // Красную черту подписываем: на видео подсказку мышью не покажешь.
    h += "<span class='ponrlab' style='left:" + px.toFixed(2) + "%'>" +
         L("ponrTag") + "</span>";
  }
  // Полоса размышления и бегунок рисуются один раз, а двигаются потом через
  // style без перерисовки разметки: перерисовка innerHTML на каждой порции
  // и была причиной рывков.
  h += "<i class='thinkspan' style='display:none'></i>";
  h += "<i class='now'></i>";
  h += "</div><div class='tlax'><span>00:00</span><span class='nowt'>" +
       hhmmss(WM.tNow) + "</span><span>" + hhmmss(hz) + "</span></div>" +
       "<div class='tlleg'>" + L("tlLegend") + "</div>";
  $("#timeline").innerHTML = h;
  $("#timeline").querySelectorAll(".d").forEach(el => {
    el.onclick = (e) => { e.stopPropagation(); inspectStep(+el.dataset.i); };
  });
  bindSeek();
  drawNow(WM.tNow, false);
}

// Перемотка. Обработчики навешиваются на постоянный контейнер один раз:
// раньше они висели на самой линии, а её разметка перерисовывалась при
// каждом наблюдении -- и в середине перетаскивания обработчик считал
// координаты по элементу, уже удалённому из DOM. Получался NaN, проверка
// «назад нельзя» его пропускала, и просмотр уезжал до конца задачи.
function bindSeek() {
  const box = $("#timeline");
  if (!box || box.dataset.bound) return;
  box.dataset.bound = "1";

  const hzOf = () => {
    const r = wRun(WM.runId);
    const sc = r && wScen(r.scenario);
    return (r && r.horizon_s) || (sc && sc.horizon_s) || 1800;
  };
  const pick = (ev) => {
    const tl = box.querySelector(".tl");
    if (!tl) return null;
    const b = tl.getBoundingClientRect();
    if (!b.width) return null;
    const f = Math.max(0, Math.min(1, (ev.clientX - b.left) / b.width));
    const t = f * hzOf();
    return isFinite(t) ? t : null;
  };

  // Щелчок по полосе открывает ближайшее решение: отметка шириной
  // две-четыре точки, попасть в неё мышью трудно, а спросить «что здесь
  // происходило» хочется именно так. Сразу после перетаскивания щелчок
  // не считается -- иначе отпускание бегунка открывало бы карточку.
  box.addEventListener("click", (ev) => {
    if (Date.now() - (WM.dragEnd || 0) < 250) return;
    const cl = ev.target.classList;
    if (cl.contains("d") || cl.contains("now")) return;
    const t = pick(ev);
    if (t === null) return;
    const i = nearestStep(t);
    if (i >= 0) inspectStep(i);
  });

  box.addEventListener("mousedown", (ev) => {
    // Перемотка -- только за бегунок. Пока она висела на всей полосе,
    // промах по отметке решения уводил просмотр вперёд.
    if (!ev.target.classList.contains("now")) return;
    if (!box.querySelector(".tl")) return;
    const t0 = pick(ev);
    if (t0 === null) return;
    ev.preventDefault();
    WM.dragging = true;
    WM.dragT = t0;
    drawNow(t0, true);

    const move = (e2) => {
      if (!WM.dragging) return;
      const t = pick(e2);
      if (t === null) return;
      WM.dragT = t;
      drawNow(t, true);
      const lbl = box.querySelector(".nowt");
      if (lbl) {
        lbl.textContent = hhmmss(t) +
          (t < WM.tNow - 1 ? " " + L("seekBack") : "");
      }
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      if (!WM.dragging) return;
      WM.dragging = false;
      WM.dragEnd = Date.now();
      const t = WM.dragT;
      WM.dragT = null;
      if (t !== null && isFinite(t)) seekTo(t);
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  });
}

// Ближайшее к моменту t решение -- для щелчка по полосе.
function nearestStep(t) {
  let best = -1, bd = Infinity;
  WM.steps.forEach((s, i) => {
    const d = Math.abs((s.t_rel || 0) - t);
    if (d < bd) { bd = d; best = i; }
  });
  return best;
}

// Перемотка к заданному времени задачи.
function seekTo(t) {
  if (!isFinite(t)) { drawNow(WM.tNow, false); return; }
  const r = wRun(WM.runId);
  const sc = r && wScen(r.scenario);
  const hz = (r && r.horizon_s) || (sc && sc.horizon_s) || 1800;
  t = Math.max(0, Math.min(hz, t));

  if (t < WM.tNow - 1 || WM.phase === "over") {
    // Назад двойник отмотать не может -- физика необратима. Но начало задачи
    // восстанавливается из снимка мгновенно, поэтому «назад» делается
    // перезапуском и прокруткой до нужной секунды.
    startWatch(WM.runId, t);
    return;
  }
  if (t <= WM.tNow + 1) { drawNow(WM.tNow, false); return; }
  WM.seekTo = t;
  WM.stepArmed = false;
  WM.stepMode = false;
  WM.playing = true;
  WM.t0wall = 0;
  renderWatchCtl();
  if (!WM.pending) watchOnObs(false);
}

// Положение бегунка. Между порциями время оценивается по прошедшему
// реальному времени и скорости -- так метка идёт ровно, а не рывками.
function drawNow(t, forced) {
  const tl = $("#timeline") && $("#timeline").querySelector(".tl");
  if (!tl) return;
  const r = wRun(WM.runId);
  const sc = r && wScen(r.scenario);
  const hz = (r && r.horizon_s) || (sc && sc.horizon_s) || 1800;
  const now = tl.querySelector(".now");
  const span = tl.querySelector(".thinkspan");
  if (!now) return;
  const cx = Math.max(0, Math.min(100, 100 * t / hz));
  now.style.left = cx.toFixed(3) + "%";
  now.className = "now" + (WM.phase === "over" ? " ended" : "") +
                  (forced ? " drag" : "");
  if (!forced && WM.phase === "think" && WM.thinkTotal > 0) {
    const t0 = Math.max(0, t - (WM.thinkTotal - WM.thinkLeft));
    const x0 = Math.max(0, Math.min(100, 100 * t0 / hz));
    span.style.display = "";
    span.style.left = x0.toFixed(3) + "%";
    span.style.width = Math.max(0.3, cx - x0).toFixed(3) + "%";
  } else if (span && !forced) {
    span.style.display = "none";
  }
  const lbl = $("#timeline").querySelector(".nowt");
  if (lbl && !WM.dragging) lbl.textContent = hhmmss(t);
}

// Кадровая анимация бегунка между порциями продвижения.
function requestNowAnim() {
  if (WM.anim) return;
  const frame = () => {
    WM.anim = null;
    if (mode !== "watch" || WM.phase === "over") { drawNow(WM.tNow, false);
                                                   return; }
    if (WM.dragging) { WM.anim = requestAnimationFrame(frame); return; }
    let t = WM.tNow;
    if (WM.playing && WM.pending) {
      // Порция уже отправлена: время идёт, наблюдения ещё нет.
      const dt = (performance.now() - WM.tPrevWall) / 1000 * WM.speed;
      t = Math.min(WM.tNow + 10, WM.tNow + Math.max(0, dt));
    }
    drawNow(t, false);
    WM.anim = requestAnimationFrame(frame);
  };
  WM.anim = requestAnimationFrame(frame);
}

function inspectStep(i) {
  const s = WM.steps[i];
  if (!s) return;
  const think = (s.tokens || 0) / MANIFEST.benchmark.think_rate_tok_per_s;
  // Задержка исполнения команды -- из каталога: в записи прогона её нет.
  const a = BYID[s.action];
  let h = "<h3>" + L("decision") + " " + (i + 1) + " · " + hhmmss(s.t_rel) +
          "</h3>";
  h += "<table class='kv'>";
  h += "<tr><td>" + L("command") + "</td><td>" + actText(s.action) +
       " <span class='aid'>" + s.action + "</span></td></tr>";
  h += "<tr><td>" + L("tokens") + "</td><td>" + (s.tokens || 0) + "</td></tr>";
  h += "<tr><td>" + L("thinkCost") + "</td><td>+" + think.toFixed(1) + " " + L("unitS") +
       " (" + hhmmss(s.t_rel) + " → " + hhmmss(s.t_rel + think) + ")</td></tr>";
  if (a) h += "<tr><td>" + L("execTime") + "</td><td>+" + a.lat + " " + L("unitS") + "</td></tr>";
  h += "<tr><td>" + L("parseStatus") + "</td><td>" + (s.status || "—") + "</td></tr>";
  // Реальная задержка вызова показывается отдельно и НЕ участвует в часах
  // задачи: иначе быстрый канал связи давал бы программе преимущество.
  h += "<tr><td>" + L("wallTime") + "</td><td>" + (s.wall_s || 0) +
       " " + L("unitS") + " <span class='mut'>" + L("wallNote") + "</span></td></tr>";
  h += "</table>";
  h += "<div class='lbl'>" + L("reasoning") + "</div><div class='rsnfull'>" +
       esc(replyMarks((s.reply || "").trim()) || "—") + "</div>";
  $("#insptxt").innerHTML = h;
  $("#inspdlg").style.display = "";
}

// ---------------------------------------------------------------------
// Сравнение решений двух прогонов
//
// Отвечает на один вопрос: где две программы разошлись. Последовательности
// команд выравниваются наибольшей общей подпоследовательностью -- там, где
// они совпадают, строки стоят рядом; где разошлись, каждая в своей
// половине. Поэтому «одно и то же, но на минуту позже» видно как
// совпадение со сдвигом времени, а не как полное расхождение.
//
// Ничего не пересчитывается: времена, команды и токены берутся из
// сохранённых протоколов.
// ---------------------------------------------------------------------

// Решения прогона из его протокола: время наблюдения, команда, токены.
function diffSteps(runId) {
  const tr = TRACES[runId];
  if (!tr && typeof mineDiffSteps === "function") {
    const m = mineDiffSteps(runId);
    if (m) return m;
  }
  return (tr || []).map((s, i) => ({
    i: i + 1,
    t: s.t_rel,
    aid: s.action || "",
    tokens: s.tokens || 0,
    status: s.status || "",
  })).filter(s => s.aid);
}

// Наибольшая общая подпоследовательность по идентификаторам команд.
function diffAlign(A, B) {
  const n = A.length, m = B.length;
  const dp = [];
  for (let i = 0; i <= n; i++) dp.push(new Int32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = (A[i].aid === B[j].aid)
        ? dp[i + 1][j + 1] + 1
        : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const rows = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (A[i].aid === B[j].aid) { rows.push({ a: A[i], b: B[j], same: true });
                                 i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { rows.push({ a: A[i], b: null });
                                             i++; }
    else { rows.push({ a: null, b: B[j] }); j++; }
  }
  while (i < n) { rows.push({ a: A[i++], b: null }); }
  while (j < m) { rows.push({ a: null, b: B[j++] }); }
  return rows;
}

// Расхождение показывается парами, а не двумя списками подряд.
//
// Выравнивание по НОП даёт блоки «только A», потом «только B», и времена в
// двух половинах идут вразнобой: у A девятая минута, у B первая. Внутри
// блока расхождения решения ставятся рядом по порядку, поэтому в каждом
// столбце время возрастает, а строка читается как «A сделал это, B то».
function diffPairBlocks(rows) {
  const out = [];
  let i = 0;
  while (i < rows.length) {
    if (rows[i].same) { out.push(rows[i++]); continue; }
    const a = [], b = [];
    while (i < rows.length && !rows[i].same) {
      if (rows[i].a) a.push(rows[i].a);
      if (rows[i].b) b.push(rows[i].b);
      i++;
    }
    const n = Math.max(a.length, b.length);
    for (let k = 0; k < n; k++) {
      out.push({ a: a[k] || null, b: b[k] || null, same: false });
    }
  }
  return out;
}

// Прогоны, у которых есть протокол, по задачам.
function diffRuns(sid) {
  const pub = MANIFEST.runs.filter(r => r.scenario === sid && r.watchable);
  // Своё прохождение сравнимо с любым прогоном: установка та же, набор
  // команд тот же, выравнивание идёт по командам.
  const mine = (typeof mineDiffRuns === "function") ? mineDiffRuns(sid) : [];
  return pub.concat(mine);
}

function showDiff(sid, idA, idB) {
  const sids = MANIFEST.scenarios.map(s => s.sid)
    .filter(s => diffRuns(s).length >= 2);
  if (!sids.length) { alert(L("diffNoPair")); return; }
  DIFF.sid = sids.indexOf(sid) >= 0 ? sid : sids[0];
  const runs = diffRuns(DIFF.sid);
  const has = id => runs.some(r => r.id === id);
  DIFF.a = has(idA) ? idA : runs[0].id;
  DIFF.b = has(idB) && idB !== DIFF.a
    ? idB : (runs.find(r => r.id !== DIFF.a) || runs[0]).id;

  const sel = (id, val, opts) =>
    "<select id='" + id + "'>" + opts.map(o =>
      "<option value='" + esc(o[0]) + "'" +
      (o[0] === val ? " selected" : "") + ">" + esc(o[1]) + "</option>"
    ).join("") + "</select>";

  const rA = wRun(DIFF.a), rB = wRun(DIFF.b);
  const sc = wScen(DIFF.sid);
  const A = diffSteps(DIFF.a), B = diffSteps(DIFF.b);
  const rows = diffPairBlocks(diffAlign(A, B));

  let h = "<h3>" + L("diffTitle") + "</h3>";
  h += "<div class='diffpick'>" +
    sel("dfs", DIFF.sid, sids.map(s => [s, L("scen") + " " + scenNo(s)])) +
    sel("dfa", DIFF.a, runs.map(r => [r.id, runLabel(r)])) +
    sel("dfb", DIFF.b, runs.map(r => [r.id, runLabel(r)])) +
    "</div>";

  // Итоги обоих прогонов рядом: расхождение в решениях интересно ровно
  // потому, что исходы разные.
  // Исход берётся из кодов прогона, а не из готовой строки манифеста: в
  // отчётах ущерб пишется как МАЙn, а в тренажёре -- кодами КАТ/УЩ (и
  // CAT/MAJ по-английски), и смешивать два обозначения в одной таблице
  // нельзя.
  const head = r => "<b>" + esc(runLabel(r)) + "</b> · " + L("score") + " " +
    r.score + " · " +
    (r.CAT.length ? "<span class='bad'>" + outcomeText(r) + "</span>"
                  : outcomeText(r)) + " · " +
    L("decisions") + " " + ((r.trace_stats || {}).n_decisions || 0);
  h += "<div class='diffsum'><div>" + head(rA) + "</div><div>" +
       head(rB) + "</div></div>";

  const same = rows.filter(x => x.same).length;
  const first = rows.find(x => !x.same);
  const firstT = first ? (first.a ? first.a.t : first.b.t) : null;
  h += "<div class='mut'>" + L("diffCommon") + ": " + same + " " +
       L("of") + " " + Math.max(A.length, B.length) +
       (firstT !== null ? " · " + L("diffFirst") + " " + hhmmss(firstT) : "") +
       (sc && sc.ponr_cat_s !== null && sc.ponr_cat_s !== undefined
        ? " · " + L("ponr") + " " + hhmmss(sc.ponr_cat_s) : "") +
       "</div>";

  h += "<table class='dtab'><tr><th>t</th><th>" + esc(runLabel(rA)) +
       "</th><th>t</th><th>" + esc(runLabel(rB)) + "</th></tr>";
  const ponr = sc ? sc.ponr_cat_s : null;
  let ponrShown = (ponr === null || ponr === undefined);
  rows.forEach(x => {
    // Разделитель ставится перед первым решением, которое уже за точкой
    // невозврата: выравнивание идёт по командам, поэтому черта проводится
    // по первому из двух столбцов, который её пересёк.
    const t = Math.min(x.a ? x.a.t : Infinity, x.b ? x.b.t : Infinity);
    if (!ponrShown && t > ponr) {
      ponrShown = true;
      h += "<tr class='ponrline'><td colspan='4'>" + hhmmss(ponr) + " — " +
           L("diffPonrLine") + "</td></tr>";
    }
    const cls = x.same ? "eq"
      : (x.a && x.b) ? "dif" : (x.a ? "onlya" : "onlyb");
    const cell = s => s
      ? "<td class='tm'>" + hhmmss(s.t) + "</td><td>" + actText(s.aid) +
        "<span class='tk'>" + (s.secs === undefined
          ? s.tokens + " " + L("tokShort")
          : "+" + s.secs + " " + L("unitS")) + "</span></td>"
      : "<td class='tm'></td><td class='na'></td>";
    h += "<tr class='" + cls + "'>" + cell(x.a) + cell(x.b) + "</tr>";
  });
  // Чем кончилось -- в той же таблице и под своим столбцом: ради этого
  // расхождение в решениях и смотрят.
  const endCell = r => {
    const code = r.CAT.length ? r.CAT.map(outcomeCode).join("+") : "";
    return "<td class='tm'>" + hhmmss(r.t_end_s) + "</td><td>" +
      (code ? "<b class='bad'>" + L("diffCat") + " " + code + "</b>"
            : L("diffEnded") + ", " + outcomeText(r)) + "</td>";
  };
  h += "<tr class='endrow'>" + endCell(rA) + endCell(rB) + "</tr>";
  h += "</table>";
  h += "<p class='mut'>" + L("diffNote") + "</p>";

  $("#difftxt").innerHTML = h;
  $("#diffdlg").style.display = "";
  $("#dfs").onchange = () => showDiff($("#dfs").value, null, null);
  $("#dfa").onchange = () => showDiff(DIFF.sid, $("#dfa").value, DIFF.b);
  $("#dfb").onchange = () => showDiff(DIFF.sid, DIFF.a, $("#dfb").value);
}

let DIFF = { sid: null, a: null, b: null };

// ---------------------------------------------------------------------
// Сравнение
// ---------------------------------------------------------------------

function showCompare() {
  const sids = MANIFEST.scenarios.map(s => s.sid);
  let h = "<table class='wtab'><tr><th>" + L("agent") + "</th>";
  sids.forEach(s => { h += "<th>" + scenNo(s) + "</th>"; });
  h += "<th>" + L("mean") + "</th><th>" + L("regGap") + "</th></tr>";
  let lastKind = null;
  MANIFEST.agents.forEach(a => {
    // Опубликованная матрица и свои прогоны -- разные вещи, и это должно
    // быть видно в таблице, а не только в описании.
    if (a.kind === "user" && lastKind !== "user") {
      h += "<tr class='userhead'><td class='nm'>" + L("userRuns") +
           "</td><td colspan='" + (sids.length + 2) + "' class='mut'>" +
           L("userNote") + "</td></tr>";
    }
    lastKind = a.kind;
    h += "<tr class='" + (a.kind === "policy" ? "pol" : "mdl") + "'>" +
         "<td class='nm' title='" + esc(agentDesc(a)) + "'>" +
         esc(agentLabel(a)) + "</td>";
    sids.forEach(sid => {
      const r = MANIFEST.runs.find(
        x => x.agent === a.id && x.kind === a.kind && x.scenario === sid
             && x.prompt_lang === a.prompt_lang);
      if (!r) { h += "<td class='na'>—</td>"; return; }
      const cls = r.CAT.length ? "cat" : (r.clean ? "ok" : "maj");
      const badge = r.CAT.length ? r.CAT.map(outcomeCode).join("+")
        : (r.MAJ.length ? r.MAJ.map(outcomeCode).join("+") : L("clean"));
      h += "<td class='" + cls + "'" +
           (r.watchable ? " data-run='" + r.id + "'" : "") +
           " title='" + badge + "'>" + r.score +
           (r.watchable ? "<span class='wm'>▸</span>" : "") + "</td>";
    });
    // Неполная строка помечается: её среднее нельзя ставить рядом с полным
    // как равное.
    const part = !a.complete;
    h += "<td class='mean" + (part ? " part" : "") + "'>" +
         (a.score_mean == null ? "—" : a.score_mean) +
         (part ? "<i title='" + L("measuredOf") + " " + a.n_scored + " " +
                 L("of") + " " + a.n_total + " " + L("ofTasks") +
                 "'>*</i>" : "") +
         "</td><td class='gap'>" +
         (a.reg_gap == null
          ? (part ? "<span class='mut'>" + L("needFull") + "</span>" : "—")
          : (a.id === "regulation" ? L("base")
             : (a.reg_gap > 0 ? "+" : "") + a.reg_gap)) + "</td></tr>";
  });
  // Свои прогоны -- теми же правилами, что и опубликованные строки, но
  // отдельным разделом: это не часть опубликованного набора.
  const mine = (typeof mineAgents === "function") ? mineAgents() : [];
  if (mine.length) {
    h += "<tr class='minehead'><td class='nm'>" + L("mineHead") +
         "</td><td colspan='" + (sids.length + 2) + "' class='mut'>" +
         L("mineNote") + "</td></tr>";
    mine.forEach(a => {
      const q = a.kind === "quick";
      h += "<tr class='mine" + (q ? " qrow" : "") + "'><td class='nm'>" +
           "<span class='mbadge'>" + (q ? L("mineQuick") : L("mineHuman")) +
           "</span> " + esc(a.id) +
           "<button class='mdel' data-kind='" + a.kind + "' data-agent='" +
           esc(a.id) + "' title='" + esc(L("mineDel")) + "'>×</button></td>";
      sids.forEach(sid => {
        const r = a.runs[sid];
        if (!r) { h += "<td class='na'>—</td>"; return; }
        const cls = (r.CAT || []).length ? "cat"
          : ((r.MAJ || []).length ? "maj" : "ok");
        const badge = (r.CAT || []).length ? r.CAT.map(outcomeCode).join("+")
          : ((r.MAJ || []).length ? r.MAJ.map(outcomeCode).join("+")
                                  : L("clean"));
        const mark = r.forced ? "<i title='" + esc(L("mineStoppedNote")) +
                                "'>⏹</i>"
                   : (q ? "<i title='" + esc(L("mineQuickNote")) + "'>~</i>"
                        : "");
        h += "<td class='" + cls + "' title='" + esc(badge + " · " + r.when) +
             "'>" + (r.score === null ? "—" : r.score) + mark + "</td>";
      });
      const part = !a.complete;
      h += "<td class='mean" + (part ? " part" : "") + "'>" +
           (a.score_mean === null ? "—" : a.score_mean) +
           (part ? "<i title='" + L("measuredOf") + " " + a.n_scored + " " +
                   L("of") + " " + a.n_total + " " + L("ofTasks") +
                   "'>*</i>" : "") +
           "</td><td class='gap'>" +
           (a.reg_gap === null
            ? "<span class='mut'>" + (q ? L("mineQuick") : L("needFull")) +
              "</span>"
            : (a.reg_gap > 0 ? "+" : "") + a.reg_gap) + "</td></tr>";
    });
  }
  h += "</table>";
  if (mine.length) {
    h += "<p class='mut'><button class='lnk' id='mineclr'>" + L("mineClear") +
         "</button></p>";
  }
  const partial = MANIFEST.agents.filter(a => !a.complete && a.n_scored);
  if (partial.length) {
    h += "<p class='mut'>* " + L("partialNote") + ": " +
         partial.map(a => esc(a.id) + " — " + a.n_scored + " " + L("of") +
                          " " + a.n_total).join("; ") +
         ". " + L("partialTail") + "</p>";
  }
  h += "<p><button class='lnk' id='diffb'>" + L("diffOpen") + "</button></p>";
  h += "<p class='mut'>" + L("scoreNote") + "</p>";
  // Пометка сборки: если в таблицу добавлены свои прогоны, об этом должно
  // быть сказано на самой таблице, а не только в команде сборки.
  if (MANIFEST.label) {
    h += "<p class='qbadge' style='display:inline-block'>" +
         esc(MANIFEST.label) + "</p>";
  }
  h += "<p class='mut'>" + L("langLimit") + "<br>" +
       (LANG === "en" ? "Task language: " : "Язык задания: ") +
       MANIFEST.benchmark.prompt_lang +
       (LANG === "en" ? "; token accounting: " : "; учёт токенов: ") +
       MANIFEST.benchmark.token_accounting +
       (LANG === "en" ? "; version: " : "; версия: ") +
       MANIFEST.benchmark.commit + ".</p>";
  $("#cmpbox").innerHTML = h;
  $("#cmpbox").querySelectorAll("td[data-run]").forEach(el => {
    el.style.cursor = "pointer";
    el.onclick = () => showWatchBrief(el.dataset.run);
  });
  $("#cmpbox").querySelectorAll(".mdel").forEach(el => {
    el.onclick = ev => {
      ev.stopPropagation();
      if (!confirm(L("mineDelAsk") + " " + el.dataset.agent)) return;
      mineDelAgent(el.dataset.kind, el.dataset.agent);
      showCompare();
    };
  });
  const db = $("#diffb");
  if (db) db.onclick = () => showDiff(DIFF.sid, DIFF.a, DIFF.b);
  const clr = $("#mineclr");
  if (clr) clr.onclick = () => {
    if (!confirm(L("mineClear") + "?")) return;
    mineClear(); showCompare();
  };
  showScreen("cmp");
}

// ---------------------------------------------------------------------
// Режим экрана задачи: игра или просмотр
// ---------------------------------------------------------------------

function applyMode() {
  const w = mode === "watch";
  const q = mode === "quick";
  $("#watchwrap").style.display = w ? "" : "none";
  $("#quickwrap").style.display = q ? "" : "none";
  // Доигрывание -- только в полной задаче: в пробе время и так
  // проматывается, в записи для этого есть «до конца».
  const po = $("#playoutb");
  if (po) po.style.display = (!w && !q) ? "" : "none";
  // Полоска прохождения -- человеку. В просмотре записи её роль играет
  // полоса решений, там она подробнее.
  const pb = $("#playbar");
  if (pb) pb.style.display = w ? "none" : "block";
  // Каталог из 133 команд скрыт и при просмотре записи, и в быстрой пробе:
  // там команды подаёт запись, здесь -- выбор из четырёх.
  $("#cmdcard").style.display = (w || q) ? "none" : "";
  $("#finishb").style.display = (w || q) ? "none" : "";
  $("#rawb").style.display = (w || q) ? "none" : "";
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
