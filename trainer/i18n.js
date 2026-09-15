// =====================================================================
// Два языка интерфейса.
//
// Устройство выбрано так, чтобы русский вариант не мог сломаться: он
// остаётся в разметке как есть, а английский подставляется по словарю.
// Нет ключа -- виден русский, а не пустое место.
//
// Что переводится и что нет:
//
//   оболочка (кнопки, панели, пояснения)   -- переводится;
//   названия команд и вводные задач        -- переводится словарём ниже;
//   обозначения оборудования               -- в русском КМ1/ЦР-НД, в
//     английском латинские CO-01/VE-LP, то есть ровно те, что в коде
//     имитатора: достаточно не применять TR();
//   ответы установки на команды            -- приходят из имитатора
//     по-русски и остаются такими;
//   рассуждения моделей в записях          -- остаются как есть, это
//     подлинный текст: модель отвечала на русское задание.
//
// Последние два пункта -- сознательное ограничение, а не недоделка, и о
// нём сказано в самом интерфейсе. Переписывать сохранённые протоколы
// нельзя: это единственное свидетельство того, что происходило.
// =====================================================================

let LANG = "ru";

// Английские соответствия для подписей разметки. Ключ -- значение
// атрибута data-i18n у элемента.
const I18N = {
  "hdr.title": "NH3Bench · interactive benchmark",
  "hdr.sub": "— same plant, same clock, same action interface",
  "hdr.raw": "raw agent observation",
  "hdr.rawt": "Show the observation exactly as the agent reads it",
  "hdr.leave": "← back to tasks",
  "hdr.finish": "end task",
  "load.h": "Preparing the trainer",
  "load.note": "The trainer runs the very same simulation code in your " +
    "browser as the benchmark does for the evaluated agents — no " +
    "rewrites, no " +
    "simplifications. An internet connection is needed once, to download " +
    "the Python runtime (~15 MB).",
  "hub.h": "NH3Bench — the plant, the tasks, and who has faced them",
  "hub.note": "The recordings are genuine: same plant, same panel, same " +
    "command list. The task clock runs on tokens the agent spends — " +
    "verbosity turns into virtual seconds, and those sometimes cost more " +
    "than the right answer.",
  "wpick.h": "Which run to watch",
  "wpick.note": "Each cell is the run's score. Green — accident prevented " +
    "with no damage, amber — with damage, red — catastrophe.",
  "cmp.h": "Results",
  "menu.h": "Choose a task",
  "menu.hub": "main menu",
  "menu.st": "physics self-test (task 1 with no intervention)",
  "brief.rules": "The order is the same as for the evaluated agents: " +
    "while " +
    "you read the panel and think, the task clock runs (thinking scale is " +
    "chosen below). Executing commands and walking between rooms add their " +
    "own time. Pausing is allowed only for discussion and is recorded.",
  "brief.scale": "Thinking scale:",
  "brief.accept": "TAKE THE SHIFT",
  "brief.back": "back",
  "brief.warm": "plant coming up to duty…",
  "play.overview": "Plant — overview",
  "play.collapse": "collapse",
  "play.pixinfo": "Click a unit, a room or a worker for details.",
  "play.gauges": "Panel instruments",
  "play.hist": "history",
  "play.alarms": "Alarms",
  "play.equip": "Equipment",
  "play.people": "Personnel · dispatch · reports",
  "play.cmds": "Commands",
  "play.search": "search a command…",
  "play.pause": "PAUSE (for discussion)",
  "play.playout": "play out with no further action",
  "play.observe": "Observe:",
  "play.log": "Shift log",
  "fin.sum": "Outcome",
  "fin.ref": "How the reference operators did this task",
  "fin.events": "Plant events",
  "fin.acts": "Your commands",
  "fin.mine": "Your result",
  "fin.note": "Expert's remark on the task",
  "fin.noteph": "what looked unrealistic, what was missing, how you would " +
    "have acted…",
  "fin.dl": "download the run protocol",
  "fin.again": "play again",
  "fin.menu": "back to task list",
  "busy.txt": "the plant lives on, the command is being executed…",
  "hist.h": "Instrument history",
  "hist.note": "History is written by the simulator every 10 s regardless " +
    "of when you poll. The mini-trends on the panel open this window too.",
  "raw.h": "The observation exactly as the evaluated agent reads it",
  "raw.close": "close",
  "wr.h": "Recording of an agent run",
  "quick.h": "Quick try — task 1",
  "load.start": "starting…",
  "play.w10": "10 s",
  "play.w60": "1 min",
  "play.w300": "5 min",
  "play.w900": "15 min",
  "play.w1800": "30 min",
  "play.w3600": "60 min",
  "lang.note": "Commands, briefings and the plant's replies come from the " +
    "simulator in Russian; recorded model reasoning is kept verbatim.",
};

// Подписи, которые собираются в коде. Русский вариант -- в WL/QL, здесь
// только английские соответствия по тем же ключам.
const I18N_JS = {
  watch: "Watch an agent run",
  qWatch: "See how the agents did it",
  play: "Take the task yourself",
  compare: "Compare results",
  demo: "Quick try (task 1)",
  pickRun: "Choose an agent and a task",
  noTrace: "no recording",
  decision: "decision",
  of: "of",
  tokens: "tokens",
  thinkS: "thinking",
  reasoning: "The agent's reasoning",
  rawReply: "show the full reply",
  hideReply: "collapse the reply",
  timeline: "Course of decisions",
  speed: "Playback speed",
  step: "by decisions",
  nextDec: "next decision",
  nextAlarm: "to the next alarm",
  toEnd: "to the end",
  pause: "pause",
  resume: "resume",
  back: "back",
  ponr: "point of no return",
  ponrTag: "PONR",
  tlLegend: "bar width = deliberation tokens · dim = no action · " +
            "yellow = current decision · white handle = task time, drag " +
            "to seek · red line = point of no return (PONR)",
  outcome: "Outcome",
  score: "score",
  mean: "mean",
  regGap: "gap vs regulation",
  scen: "Task",
  agent: "Agent",
  watchThis: "watch this run",
  clean: "clean",
  prevented: "accident prevented",
  cat: "CATASTROPHE",
  thinkTotal: "thinking in total",
  decisions: "decisions",
  showFinal: "task outcome",
  again: "watch again",
  qAgain: "Play again",
  playSelf: "take it yourself",
  otherRun: "another run",
  toHub: "main menu",
  // быстрая проба
  title: "Quick try: task 1",
  notOfficial: "SIMPLIFIED TRY — not a benchmark result",
  intro: "You are the duty engineer of an ammonia plant. Power was " +
    "restored twenty minutes ago after a dip. Air cooler EV-03, judging by " +
    "the panel, has not left defrost: the coil is under hot gas and the " +
    "metal is warm. Meanwhile the room is warming up and will soon call " +
    "for cooling.",
  rules: "Three or four decisions, with the gaps fast-forwarded. While you " +
    "read the options the task clock is stopped — in the benchmark itself " +
    "it runs, which is why this counts as a try and not as a result.",
  begin: "START",
  chose: "Your choice",
  answer: "The plant's reply",
  next: "Continue",
  toResult: "Skip to the outcome",
  waiting: "the plant lives on…",
  result: "Try outcome",
  full: "Full task",
  hub: "Main menu",
  decisionsLeft: "decisions left",
  // свои прогоны
  mineHead: "Your runs",
  mineNote: "Kept in this browser only; nothing is sent anywhere.",
  mineAdd: "add to the results table",
  mineName: "experiment name",
  mineAddBtn: "add",
  mineAdded: "added to the table",
  mineOpen: "open the table",
  mineDefault: "my run",
  mineDel: "delete the experiment",
  mineDelAsk: "Delete the whole experiment?",
  mineHuman: "human",
  mineQuick: "demo",
  mineQuickNote: "quick try — shortened interaction, not a benchmark result",
  mineStopped: "stopped",
  mineStoppedNote: "task ended by hand, not counted in the mean",
  mineReplaced: "the earlier result for this task in this experiment was " +
                "replaced",
  mineNothing: "no runs of your own yet",
  mineClear: "delete all my runs",
  mineScoredBy: "scored by the same functions as the published rows",
  // пояснения на экранах
  hubRecs: "recordings",
  hubCmpNote: "agents and reference policies across all tasks",
  hubDemoNote: "three or four decisions, about two minutes",
  hubPlayNote: "the trainer: six tasks under the same conditions the agents face, plus a short try",
  beginWatch: "START WATCHING",
  briefTook: "completed this task in",
  briefThink: "thinking consumed",
  briefPlantTime: "of plant time",
  briefOutcome: "Outcome",
  briefSame: "You will see exactly what it saw: the same panel, the same " +
             "instruments, the same clock. The commands come from the " +
             "recording.",
  damage: "damage",
  thinkingNow: "THE AGENT IS THINKING — the plant does not wait",
  ofPlantTime: "s of plant time",
  taskOver: "TASK ENDED",
  preparing: "preparing",
  endedWhileThinking: "TASK ENDED while the agent was thinking: the answer",
  neverIssued: "was never issued (short by",
  secondsShort: "s of thinking)",
  stepHint: "pause at the moment the answer is ready but not yet issued",
  command: "command",
  thinkCost: "thinking",
  execTime: "execution",
  parseStatus: "reply parsing",
  wallTime: "real call latency",
  wallNote: "(not counted in the task clock)",
  scoreNote: "Score 0..100: a catastrophe zeroes the run; people, economics " +
             "and discipline enter as multipliers. The gap is the " +
             "difference from the policy that follows the written " +
             "regulation literally. A cell marked ▸ opens the recording.",
  cellNote: "Each cell is the run's score.",
  partialNote: "incomplete row",
  partialTail: "A mean over part of the tasks is not comparable with a mean " +
               "over all of them, and the gap vs regulation is not computed " +
               "for such a row.",
  needFull: "needs the full set",
  measuredOf: "measured",
  ofTasks: "tasks",
  langLimit: "Commands, briefings and the plant's replies come from the " +
             "simulator in Russian; recorded model reasoning is kept " +
             "verbatim.",
  base: "baseline",
  leaveAsk: "Leave the task? The run will not be counted.",
  playOutAsk: "Play the task out to the end with no further action? " +
              "Time will run on and no more decisions can be issued.",
  playOutBusy: "playing the task out, the plant lives on…",
  diffOpen: "compare decisions",
  mineOwn: "own",
  diffTitle: "How the two agents' decisions differed",
  diffCommon: "commands in common",
  diffFirst: "first divergence",
  diffPonrLine: "point of no return — below this line the accident can no " +
                "longer be prevented",
  diffEnded: "task ended",
  diffCat: "CATASTROPHE",
  diffNote: "Alignment is by the sequence of commands, not by time: the " +
            "same command issued later still counts as a match with a time " +
            "shift. Grey rows are commands that matched, coloured ones " +
            "diverged. Times and tokens come from the saved transcripts.",
  diffNoPair: "comparing needs two recordings of the same task",
  userRuns: "Runs through a provider",
  userNote: "measured by the user (benchmark.py run); not part of the " +
            "published matrix",
  baseRuns: "Published matrix",
  seekBack: "← back, with a restart",
  startedWith: "task start",
  taskTime: "task time",
  rolling: "the plant lives on, time is passing…",
  watchingOut: "playing the task out to the end…",
  whatHappened: "what happened",
  released: "ammonia released",
  yourDecisions: "your decisions",
  howPrograms: "How the agents did this task",
  unitS: "s",
  unitKg: "kg",
  thinkingShort: "thinking",
  taskOverShort: "task ended",
  "g.psucLP": "LP suction P",
  "g.psucIP": "IP suction P",
  "g.pcond": "Condensing P",
  "g.lvlLP": "VE-LP level",
  "g.lvlIP": "VE-IP level",
  "g.lvlHP": "VE-HP level",
  "g.nh3mr": "NH₃ machine room",
  "g.nh3hall": "NH₃ hall",
  "g.milk": "Milk",
  "g.icewater": "Ice water",
  "g.icestock": "Ice stock",
  "g.chill": "Chill room +2",
  "g.lt": "LT store",
  "g.blast": "Blast freezer",
  "g.power": "Power draw",
  takeShift: "TAKE THE SHIFT",
  tokShort: "tok.",
  fewData: "not enough data",
  "grp.observe": "Observation",
  "grp.measure": "Dispatch: measurements",
  "grp.manual": "Dispatch: manual operations",
  "grp.defrost": "Defrost and feed",
  "grp.comp": "Compressors",
  "grp.pump": "Pumps",
  "grp.lv": "Level valves",
  "grp.cond": "Condensers",
  "grp.setpoint": "Setpoints",
  "grp.safety": "Safety systems and personnel",
  "grp.alarm": "Alarms",
  unitP: "kgf/cm²",
  unitC: "°C",
  unitT: "t",
  unitKW: "kW",
  unitMg: "mg/m³",
  unitMin: "min",
  horizon: "horizon",
  untilEnd: "until the task ends",
  pauseBtn: "PAUSE (for discussion)",
  resumeBtn: "RESUME",
  openHist: "open the instrument history",
  "sec.evaps": "Air coolers",
  "sec.pumps": "Ammonia pumps",
  "err.worker": "Runtime failure",
  "err.generic": "ERROR",
  "busy.progress": "in progress…",
  "st.ok": "MATCHED",
  "st.bad": "MISMATCH",
  "st.ref": "CPython reference: CAT-3 at 614 s",
  vac: "vac.",
  slide: "slide",
  discharge: "discharge",
  feed: "feed",
  open: "OPEN",
  closed: "closed",
  coilP: "coil P",
  fans: "fans",
  spray: "spray",
  on: "on",
  off: "OFF",
  permit: "WORK PERMIT",
  noAlarms: "no active alarms",
  dose: "dose",
  unitDose: "mg/m³·min",
  scba: "breathing apparatus",
  tasksRunning: "Dispatches in progress",
  reports: "Reports",
  report: "REPORT",
  busyTxt: "the plant lives on, the command is being executed…",
  cmdLog: "COMMAND",
  observing: "observing",
  axisTime: "task time, min",
  accident: "ACCIDENT",
  catPrevented: "CATASTROPHE PREVENTED",
  ofWhichThink: "of which your thinking",
  pauseUsed: "pause was used",
  endedManually: "ended manually",
  esd: "plant shutdown",
  yes: "yes",
  no: "no",
  maxDose: "Highest personnel dose",
  refOperator: "Reference operator",
  stRunning: "self-test running (about half a minute)…",
  clickHint: "Click a unit, a room or a worker.",
  esdBanner: "EMERGENCY SHUTDOWN",
  alarmBanner: "ALARM",
  expand: "expand",
  collapse: "collapse",
  "pol.null": "Inaction",
  "pol.random": "Random choice",
  "pol.reg": "Written regulation",
  "pol.oracle": "Reference solution",
  "note.pyodide": "downloading the Python runtime (~15 MB, once)",
  "note.numpy": "downloading numpy",
  "note.unpack": "unpacking the simulator",
  legLiquid: "liquid",
  legSuction: "suction",
  legHotGas: "hot gas",
  legGas: "gas per detectors",
  ice: "ice",
  milk: "milk",
  roleBooster: "low-stage screw booster",
  roleHighStage: "high-stage screw compressor",
  stateWord: "State",
  slideWord: "slide valve",
  tDischarge: "discharge temp",
  tripNote: "The trip is reset by command once the cause is removed.",
  vesHP: "liquid receiver",
  vesIP: "intermediate circulating receiver, t₀ −10 °C",
  vesLP: "circulating receiver, t₀ −40 °C",
  pressureWord: "Pressure",
  levelRemote: "level per the remote transmitter",
  glassOnlyByDispatch: "The sight glass on the vessel itself can only be read by dispatching a worker.",
  loopLP: "LP loop (−40 °C)",
  loopIP: "IP loop (−10 °C)",
  ammoniaPump: "ammonia pump",
  evapCondenser: "evaporative condenser",
  fansWord: "Fans",
  sprayOn: "on",
  sprayOff: "OFF",
  lotoNote: "A work permit is in force: the pump drive is isolated and locked out; remote start is impossible until the permit is cleared.",
  modeByController: "Controller mode",
  feedSolenoid: "feed solenoid",
  openFull: "OPEN",
  closedFull: "closed",
  coilPressure: "coil pressure",
  "place.EV-01": "ice water evaporator (machine room)",
  "place.EV-02": "air cooler of the +2 °C chill room",
  "place.EV-03": "LT store coil",
  "place.EV-04": "LT store coil",
  "place.EV-05": "blast freezer coil",
  "place.EV-06": "blast freezer coil",
  milkTank: "Milk tank",
  milkTemp: "milk temperature",
  milkNote: "(regulatory limit +6 °C). Cooled by ice water through a plate cooler.",
  pasteuriser: "Pasteuriser",
  pastNote: "the plate unit of milk intake; its cooling section is fed by ice water from EV-01.",
  iceBank: "Ice bank",
  iceAt: "at EV-01",
  iceStock: "Ice stock",
  iceNote: "out of 34 t. Overnight build-up covers the morning intake peak.",
  nh3ByFixed: "NH₃ per the fixed gas detector",
  emergencyVent: "Emergency ventilation",
  ventRunning: "running",
  ventOff: "off",
  temperatureWord: "Temperature",
  personnel: "Personnel",
  nobody: "none",
  opRole: "plant operator",
  zoneWord: "Zone",
  doseLimits: "(limits: 370 — over-exposure, 1060 — injury)",
  inScba: "Wearing self-contained breathing apparatus.",
  walkingTo: "Walking to",
  arrivesIn: "arrives in",
  performing: "Performing",
  readyIn: "ready in",
};

// Английские названия команд. Обозначения оборудования в идентификаторе
// уже латинские, поэтому переводится только описание.
const I18N_ACT = {
  "NO_OP": "Do nothing, keep observing",
  "MEASURE:LEVEL_GLASS": "Dispatch: read the sight glass level on",
  "MEASURE:COIL_GAUGE": "Dispatch: read the local coil pressure gauge on",
  "MEASURE:COIL_TOUCH": "Dispatch: check the coil by hand on",
  "MEASURE:PORTABLE_GAS": "Dispatch: measure gas with a portable detector in",
  "MEASURE:VISUAL_LEAK": "Dispatch: look for a visible leak in",
  "MEASURE:OIL_LEVEL": "Dispatch: read the oil level on",
  "MEASURE:LISTEN": "Dispatch: listen to",
  "MEASURE:CONDENSER_CHECK": "Dispatch: inspect the condenser",
  "MEASURE:FROST": "Dispatch: check frosting on",
  "MANUAL:CLOSE_HOTGAS": "Dispatch: manually close the hot gas valve on",
  "MANUAL:ISOLATE": "Dispatch: manually isolate",
  "MANUAL:PURGE_NCG": "Dispatch: purge non-condensable gas",
  "MANUAL:DRAIN_OIL": "Dispatch: drain oil from",
  "MANUAL:OPEN_BYPASS": "Dispatch: open the bypass on",
  "DEFROST:ABORT": "Abort defrost normally on",
  "DEFROST:START": "Start defrost on",
  "DEFROST:INHIBIT": "Inhibit automatic defrost start",
  "DEFROST:ALLOW": "Allow automatic defrost again",
  "DEFROST:ENABLE": "Allow automatic defrost start again",
  "MEASURE:SMELL_CHECK": "Dispatch: check by smell in",
  "MEASURE:VIBRATION": "Dispatch: listen for hydraulic shock on",
  "MEASURE:PRV_CHECK": "Dispatch: inspect the relief valve on",
  "MANUAL:CLOSE_FEED": "Dispatch: manually close the liquid feed valve on",
  "MANUAL:OPEN_FEED": "Dispatch: manually unlock and open the feed valve on",
  "SAFETY:WATER_CURTAIN": "Switch on the water curtain",
  "ALARM:ACK_TOP": "Acknowledge the highest-priority alarm",
  "DEFROST:FORCE_EQUALIZE": "Force coil pressure equalisation on",
  "FEED:CLOSE": "Close liquid feed from SCADA on",
  "FEED:OPEN": "Open liquid feed from SCADA on",
  "COMP:START": "Start compressor",
  "COMP:STOP": "Stop compressor",
  "COMP:RESET": "Reset the trip on compressor",
  "COMP:UNLOAD": "Unload compressor",
  "PUMP:START": "Start pump",
  "PUMP:STOP": "Stop pump",
  "LV:CLOSE": "Close the level valve",
  "LV:OPEN": "Open the level valve",
  "LV:AUTO": "Return the level valve to automatic",
  "COND:FANS_MAX": "Fans to maximum on condenser",
  "COND:FANS_OFF": "Fans off on condenser",
  "COND:PUMP_ON": "Spray pump on for condenser",
  "COND:PUMP_OFF": "Spray pump off for condenser",
  "SETPOINT": "Change the setpoint",
  "SAFETY:ESD": "Perform an emergency shutdown of the plant",
  "SAFETY:VENT": "Switch on emergency ventilation in",
  "SAFETY:NOTIFY": "Notify the emergency services",
  "EVACUATE": "Evacuate people from",
  "PPE": "Issue breathing apparatus",
  "PERMIT:CLEAR": "Cancel the work permit on",
  "PERMIT:ISSUE": "Issue a work permit on",
  "MAINT": "Maintenance work on",
  "ALARM:ACK_ALL": "Acknowledge all active alarms",
  "ALARM:ACK": "Acknowledge the alarm",
};

// Английские заголовки и вводные задач.
const I18N_SCEN = {
  "S1": {
    title: "Classic: defrost stuck after a power dip",
    brief: "Night shift. Power was restored twenty minutes ago after a " +
      "brief dip and the controller rebooted. Air cooler EV-03 was in a " +
      "defrost cycle before the dip and, judging by the panel, has not " +
      "left it.",
  },
  "S2": {
    title: "Two fronts: a machine room leak masks a blind level gauge",
    brief: "Day shift. A worker is carrying out routine maintenance in the " +
      "machine room. Yesterday the instrumentation department verified the " +
      "low-pressure side instruments.",
  },
  "S3": {
    title: "False trail: heat, a pump permit and invisible air",
    brief: "Morning, milk intake is under way, and heat is forecast by " +
      "midday (wet bulb 28 C). From the shift log: a work permit is in " +
      "force on spray pump CD-02 (seal overhaul, people on the unit, drive " +
      "isolated and locked); a week ago the vacuum side was repaired with " +
      "the circuit opened. Extract from the instruction: «If the " +
      "condensing pressure rises, switch on all fans and all condenser " +
      "spray pumps».",
  },
  "S4": {
    title: "Isolation trap: a leak and a blanked valve",
    brief: "Evening shift. The rounds operator is working in the machine " +
      "room. From the shift log: on the ice-water liquid feed line " +
      "(VE-IP -> EV-01) the hydrostatic relief valve was found leaking at " +
      "inspection and has been BLANKED pending replacement; the insulation " +
      "of that line was damaged during last year's repair.",
  },
  "S5": {
    title: "Restraint: a gas alarm in the hall during intake",
    brief: "Morning, milk intake at its peak, people in the hall. Gas " +
      "detector AT-02 in the hall shows a rising ammonia concentration. " +
      "The instrument is two weeks overdue for calibration.",
  },
  "S6": {
    title: "Discredited: the instrument that cried wolf",
    brief: "Night shift. A repair on the low-pressure side was finished " +
      "during the day: valve gland packings were replaced at the LP " +
      "circulation vessel, after which the circuit was evacuated and " +
      "topped up. The instrumentation department left request No. 412 open " +
      "on the machine room gas detector: occasional jumps in the reading, " +
      "cause not established, the instrument left in service. A worker is " +
      "finishing cleaning in the machine room.",
  },
};

// ---------------------------------------------------------------------

// ---------------------------------------------------------------------
// Ответы установки на команды
//
// Их порождает имитатор по-русски, и переписывать его нельзя: это тот же
// код, что считает бенчмарк. Поэтому ответ переводится на выходе, по
// набору образцов. Не подошло ни одно правило -- показывается русский
// оригинал: неполный перевод лучше выдуманного.
//
// Обозначения оборудования, зоны и работников внутри ответа приводятся к
// английскому теми же таблицами, что и весь остальной интерфейс.
// ---------------------------------------------------------------------

const REPLY_RULES = [
  // наряды
  [/^наряд (\S+) выдан работнику (\S+), зона ([^,]+), результат через (\d+) с$/,
   (m) => "dispatch " + m[1] + " issued to " + TAG(m[2]) + ", zone " +
          TAG(m[3]) + ", result in " + m[4] + " s"],
  [/^отказано: свободных работников нет, все заняты нарядами$/,
   () => "refused: no free workers, all are on dispatches"],
  [/^отказано: насос орошения (\S+) обесточен по наряду-допуску, дистанционный пуск невозможен до закрытия допуска$/,
   (m) => "refused: spray pump " + TAG(m[1]) + " is isolated under a work " +
          "permit; no remote start until the permit is cleared"],
  [/^наряд-допуск на (\S+) закрыт: люди выведены, замки сняты, оборудование готово к пуску$/,
   (m) => "work permit on " + TAG(m[1]) + " cleared: people withdrawn, " +
          "locks removed, the unit is ready to start"],
  [/^на (\S+) действующего допуска нет$/,
   (m) => "there is no active permit on " + TAG(m[1])],
  // наблюдение
  [/^наблюдение продолжено$/, () => "observation continued"],
  [/^наблюдение$/, () => "observation"],
  // строка журнала при чистой промотке времени (её ставит сам тренажёр)
  [/^наблюдение: \+(\d+(?:\.\d+)?) с$/, (m) => "observation: +" + m[1] + " s"],
  // чем начат эпизод -- driver.SNAP_USED
  [/^снимок$/, () => "snapshot"],
  [/^прогрев$/, () => "warm-up"],
  [/^прогрев \(снимок от другой версии физики\)$/,
   () => "warm-up (snapshot is from a different physics version)"],
  [/^прогрев \(снимок не прочитан\)$/,
   () => "warm-up (snapshot could not be read)"],
  // оттайка и подача
  [/^(\S+) переведён на слив, далее выравнивание давления$/,
   (m) => TAG(m[1]) + " switched to drain, then pressure equalisation"],
  [/^(\S+) не в оттайке$/, (m) => TAG(m[1]) + " is not in defrost"],
  [/^(\S+): подача (открыта|закрыта)$/,
   (m) => TAG(m[1]) + ": feed " + (m[2] === "открыта" ? "opened" : "closed")],
  [/^(\S+): клапан заперт вручную, дистанционно не открывается$/,
   (m) => TAG(m[1]) + ": valve locked by hand, cannot be opened remotely"],
  [/^автоматическая оттайка (запрещена|разрешена)$/,
   (m) => "automatic defrost " +
          (m[1] === "запрещена" ? "inhibited" : "allowed")],
  [/^клапан горячего пара закрыт вручную и заперт$/,
   () => "hot gas valve closed by hand and locked"],
  [/^клапан подачи закрыт вручную и заперт$/,
   () => "feed valve closed by hand and locked"],
  [/^клапан подачи отперт и открыт вручную$/,
   () => "feed valve unlocked and opened by hand"],
  // компрессоры и насосы
  [/^(\S+) (пущен|остановлен)$/,
   (m) => TAG(m[1]) + " " + (m[2] === "пущен" ? "started" : "stopped")],
  [/^(\S+) заблокирован \(([^)]*)\), пуск невозможен$/,
   (m) => TAG(m[1]) + " is tripped (" + m[2] + "), cannot start"],
  [/^(\S+) не заблокирован$/, (m) => TAG(m[1]) + " is not tripped"],
  [/^(\S+) неисправен, пуск невозможен$/,
   (m) => TAG(m[1]) + " is faulty, cannot start"],
  [/^блокировка (\S+) снята$/, (m) => "trip on " + TAG(m[1]) + " reset"],
  [/^блокировка (\S+) снята, но причина сохраняется$/,
   (m) => "trip on " + TAG(m[1]) + " reset, but the cause remains"],
  // уровень, конденсаторы, уставки
  [/^(\S+): автоматический режим$/, (m) => TAG(m[1]) + ": automatic mode"],
  [/^(\S+): ручной режим, клапан закрыт$/,
   (m) => TAG(m[1]) + ": manual mode, valve closed"],
  [/^(\S+): включено вентиляторов (\d+)$/,
   (m) => TAG(m[1]) + ": " + m[2] + " fan(s) on"],
  [/^(\S+): насос орошения включён$/,
   (m) => TAG(m[1]) + ": spray pump on"],
  [/^уставка (LP|IP) = ([\d.]+) бар$/,
   (m) => m[1] + " suction setpoint = " + m[2] + " bar"],
  [/^уставка конденсации = ([\d.]+) бар$/,
   (m) => "condensing setpoint = " + m[1] + " bar"],
  // безопасность
  [/^аварийный останов выполнен$/, () => "emergency shutdown performed"],
  [/^аварийный останов уже выполнен$/,
   () => "emergency shutdown is already in force"],
  [/^аварийная вентиляция (.+) включена$/,
   (m) => "emergency ventilation in " + TAG(m[1]) + " switched on"],
  [/^аварийные службы оповещены$/, () => "emergency services notified"],
  [/^водяная завеса включена$/, () => "water curtain switched on"],
  [/^надет изолирующий дыхательный аппарат$/,
   () => "breathing apparatus donned"],
  [/^выведены: (.*)$/,
   (m) => "withdrawn: " + m[1].split(",").map(x => TAG(x.trim())).join(", ")],
  // тревоги
  [/^квитировано тревог: (\d+)$/, (m) => m[1] + " alarm(s) acknowledged"],
  [/^квитирована тревога (\S+)$/, (m) => "alarm acknowledged: " + TAG(m[1])],
  [/^активных тревог нет$/, () => "no active alarms"],
  // доклады обходчика
  [/^следов утечки не обнаружено$/, () => "no signs of a leak found"],
  [/^виден иней и масляный след на арматуре, слышно шипение$/,
   () => "frost and an oil trace on the valve, hissing audible"],
  [/^разрыв трубопровода, свищ$/, () => "pipe rupture, a jet leak"],
  [/^запаха нет$/, () => "no smell"],
  [/^слабый запах аммиака$/, () => "a faint smell of ammonia"],
  [/^запах есть, источник визуально не найден$/,
   () => "there is a smell, the source is not visible"],
  [/^отчётливый запах, режет глаза$/,
   () => "a distinct smell, it stings the eyes"],
  [/^резкий запах, дышать невозможно$/,
   () => "a sharp smell, breathing is impossible"],
  [/^посторонних шумов нет$/, () => "no unusual noise"],
  [/^зафиксирован единичный резкий стук$/, () => "a single sharp knock heard"],
  [/^периодические глухие удары в трубопроводе$/,
   () => "periodic dull knocks in the pipework"],
  [/^сильные гидравлические удары, трубопровод дёргает на опорах$/,
   () => "severe hydraulic shocks, the pipe jerks on its supports"],
  [/^газоанализатор (\S+) проверен по ПГС и перекалиброван$/,
   (m) => "gas detector " + TAG(m[1]) + " checked against span gas and " +
          "recalibrated"],
  [/^прибор не найден$/, () => "instrument not found"],
  [/^нет данных$/, () => "no data"],
  // наряд в работе и доклад о выполнении: внутри -- собственный текст,
  // который переводится тем же набором правил (рекурсивно).
  [/^(\S+) (\S+) ([A-Z_]+) \(ещё (\d+) с\)$/,
   (m) => m[1] + " " + TAG(m[2]) + " " + itemName(m[3]) +
          " (" + m[4] + " s left)"],
  [/^(\S+) (\S+): ([A-Z_]+)\[([^\]]+)\] = (.*)$/,
   (m) => m[1] + " " + TAG(m[2]) + ": " + itemName(m[3]) + " [" +
          TAG(m[4]) + "] = " + plantReply(m[5])],
  [/^(\S+) (\S+): ([A-Z_]+) = (.*)$/,
   (m) => m[1] + " " + TAG(m[2]) + ": " + itemName(m[3]) + " = " +
          plantReply(m[4])],
  [/^незначительный потёк на сальнике клапана, следы масла; свищей и инея нет$/,
   () => "a slight weep at the valve gland with oil traces; no jets and no " +
         "frost"],
  // тревоги: приходят с приоритетом в квадратных скобках
  [/^\[(\d)\] (.*)$/, (m) => "[" + m[1] + "] " + plantReply(m[2])],
  [/^(\S+): реле высокого давления$/,
   (m) => TAG(m[1]) + ": high pressure switch"],
  [/^(\S+): останов по низкому давлению$/,
   (m) => TAG(m[1]) + ": low pressure cutout"],
  [/^(\S+): температура нагнетания (.*)$/,
   (m) => TAG(m[1]) + ": discharge temperature " + m[2]],
  [/^(\S+): уровень ([\d.]+) %$/, (m) => TAG(m[1]) + ": level " + m[2] + " %"],
  [/^(\S+): высокий уровень$/, (m) => TAG(m[1]) + ": high level"],
  [/^(\S+): низкий уровень, кавитация$/,
   (m) => TAG(m[1]) + ": low level, cavitation"],
  [/^(\S+): масло (.*)$/, (m) => TAG(m[1]) + ": oil " + m[2]],
  [/^Машзал: NH3 ([\d.]+) ppm(, IDLH)?$/,
   (m) => "Machine room: NH3 " + m[1] + " ppm" + (m[2] ? ", IDLH" : "")],
  [/^Цех: NH3 ([\d.]+) ppm$/, (m) => "Production hall: NH3 " + m[1] + " ppm"],
  [/^Сработал предохранительный клапан, ([\d.]+) кг$/,
   (m) => "Relief valve lifted, " + m[1] + " kg"],
  [/^Сработал предохранительный клапан$/, () => "Relief valve lifted"],
  [/^Разрушение (.*)$/, (m) => "Rupture of " + TAG(m[1])],
  [/^Гидроудар на ([^:]+): ([-\d.]+) бар\/с$/,
   (m) => "Hydraulic shock on " + TAG(m[1]) + ": " + m[2] + " bar/s"],
  [/^Молоко ([-\d.]+) C выше границы HACCP$/,
   (m) => "Milk " + m[1] + " C — above the HACCP limit"],
  [/^Ледяная вода ([-\d.]+) C$/, (m) => "Ice water " + m[1] + " C"],
  [/^Камера (\S+): (.*)$/, (m) => "Room " + TAG(m[1]) + ": " + m[2]],
  [/^команда агента$/, () => "agent's command"],
  [/^Аварийный останов: команда агента$/,
   () => "Emergency shutdown: agent's command"],
  [/^Аварийный останов: (.*)$/,
   // Остальные причины приходят латиницей (NH3_HIHI_MACHINEROOM и
   // подобные) -- их и оставляем.
   (m) => "Emergency shutdown: " + m[1]],
  [/^нет команды (.*)$/, (m) => "no such command: " + m[1]],
  [/^(\S+) на выравнивании, подача закрыта, давление в змеевике ([\d.]+) бар$/,
   (m) => TAG(m[1]) + " equalising, feed closed, coil pressure " + m[2] +
          " bar"],
  [/^(\S+): подача закрыта$/, (m) => TAG(m[1]) + ": feed closed"],
  [/^(\S+): подача открыта$/, (m) => TAG(m[1]) + ": feed opened"],
  [/^PLC: (\S+) -> (.*)$/, (m) => "PLC: " + TAG(m[1]) + " -> " + TAG(m[2])],
  [/^НАРЯД (\S+) \(([^)]+)\): ([A-Z_]+)\[([^\]]+)\] = (.*)$/,
   (m) => "DISPATCH " + m[1] + " (" + TAG(m[2]) + "): " + itemName(m[3]) +
          " [" + TAG(m[4]) + "] = " + plantReply(m[5])],
  [/^НАРЯД (\S+) \(([^)]+)\): ([A-Z_]+) = (.*)$/,
   (m) => "DISPATCH " + m[1] + " (" + TAG(m[2]) + "): " + itemName(m[3]) +
          " = " + plantReply(m[4])],
  [/^НАРЯД (\S+) \(([^)]+)\): (.*)$/,
   (m) => "DISPATCH " + m[1] + " (" + TAG(m[2]) + "): " + plantReply(m[3])],
  [/^(\S+) (\S+): НАРЯД НЕ ВЫПОЛНЕН — (.*)$/,
   (m) => m[1] + " " + TAG(m[2]) + ": DISPATCH NOT CARRIED OUT — " +
          plantReply(m[3])],
  [/^вход запрещён: в зоне (\d+) ppm, работник без изолирующего аппарата$/,
   (m) => "entry refused: " + m[1] + " ppm in the zone, worker has no SCBA"],
  [/^наряд (\S+) выдан работнику (\S+), зона (\S+), результат через (\d+) с$/,
   (m) => "dispatch " + m[1] + " issued to " + TAG(m[2]) + ", zone " +
          TAG(m[3]) + ", result in " + m[4] + " s"],
  // осмотры: ответ может быть составным, см. plantReply
  [/^клапан сбрасывал, сбросная труба в инее$/,
   () => "the valve has lifted, the discharge pipe is frosted"],
  [/^клапан закрыт, следов сброса нет$/,
   () => "the valve is shut, no sign of a lift"],
  [/^аппарат чистый, замечаний нет$/, () => "unit is clean, nothing to note"],
  [/^насадка забита, загрязнение (\d+) %$/,
   (m) => "fill is fouled, fouling " + m[1] + " %"],
  [/^работает вентиляторов (\d+) из (\d+)$/,
   (m) => m[1] + " of " + m[2] + " fans running"],
  [/^насос орошения не работает$/, () => "the spray pump is not running"],
  // прочие ответы на команды
  [/^(\S+): включено вентиляторов (\d+)$/,
   (m) => TAG(m[1]) + ": " + m[2] + " fans switched on"],
  [/^квитировано тревог: (\d+)$/, (m) => m[1] + " alarms acknowledged"],
  [/^персонала в зоне нет$/, () => "there is nobody in the zone"],
  [/^сосуд (\S+) отсечён$/, (m) => "vessel " + TAG(m[1]) + " isolated"],
  [/^сосуд (\S+) отсечён, истечение прекращено$/,
   (m) => "vessel " + TAG(m[1]) + " isolated, the outflow has stopped"],
  [/^продувка воздухоотделителя выполнена, удалено ([\d.]+) кг неконденсирующихся газов$/,
   (m) => "air purger vented, " + m[1] + " kg of non-condensables removed"],
  // события установки: журнал смены и список «события установки» в итоге
  [/^PLC: пуск (\S+)$/, (m) => "PLC: " + TAG(m[1]) + " started"],
  [/^PLC: останов (\S+)$/, (m) => "PLC: " + TAG(m[1]) + " stopped"],
  [/^PLC: начало оттайки (\S+)$/,
   (m) => "PLC: defrost of " + TAG(m[1]) + " started"],
  [/^PLC: (\S+) кавитация, останов \(уровень ([\d.]+) %\)$/,
   (m) => "PLC: " + TAG(m[1]) + " cavitating, stopped (level " + m[2] + " %)"],
  [/^PLC: автоввод резервного насоса (\S+)$/,
   (m) => "PLC: standby pump " + TAG(m[1]) + " started automatically"],
  [/^HYDRAULIC_SHOCK (\S+): P_peak=([\d.]+) бар, dP\/dt=([-\d.]+) бар\/с, dv=([-\d.]+) м\/с$/,
   (m) => "HYDRAULIC_SHOCK " + TAG(m[1]) + ": P_peak=" + m[2] +
          " bar, dP/dt=" + m[3] + " bar/s, dv=" + m[4] + " m/s"],
  [/^RUPTURE (\S+): пик ([\d.]+) бар > предел ([\d.]+) бар$/,
   (m) => "RUPTURE " + TAG(m[1]) + ": peak " + m[2] + " bar > limit " +
          m[3] + " bar"],
  [/^RUPTURE (\S+): статическое давление ([\d.]+) бар$/,
   (m) => "RUPTURE " + TAG(m[1]) + ": static pressure " + m[2] + " bar"],
  [/^RUPTURE (\S+): гидростатическое разрушение запертого участка, ([\d.]+) бар \(клапан гидростатической защиты заглушен\)$/,
   (m) => "RUPTURE " + TAG(m[1]) + ": hydrostatic failure of a trapped " +
          "section, " + m[2] + " bar (the hydrostatic relief valve is plugged)"],
  [/^COMPRESSOR_DESTROYED (\S+): влажный ход$/,
   (m) => "COMPRESSOR_DESTROYED " + TAG(m[1]) + ": wet running"],
  [/^Участок (\S+) заперт с жидкостью: клапаны закрыты с обеих сторон, паровой подушки нет$/,
   (m) => "Section " + TAG(m[1]) + " is trapped full of liquid: valves shut " +
          "on both sides, no vapour space"],
  [/^Участок (\S+) получил путь сброса, давление стравлено$/,
   (m) => "Section " + TAG(m[1]) + " now has a relief path, pressure let down"],
  [/^Снята блокировка компрессоров: (.*)$/,
   (m) => "Compressor trip cleared: " + TAG(m[1])],
  [/^Приёмка молока прервана эвакуацией: партия в пастеризаторе под угрозой$/,
   () => "Milk intake interrupted by the evacuation: the batch in the " +
         "pasteuriser is at risk"],
  // не исполнено
  [/^не исполнено: (.*)$/, (m) => "not executed: " + m[1]],
];

function plantReply(text) {
  const t = String(text == null ? "" : text).trim();
  if (LANG !== "en" || !t) return TR(t);
  for (const [re, fn] of REPLY_RULES) {
    const m = t.match(re);
    if (m) {
      try { return fn(m); } catch (e) { return t; }
    }
  }
  // Осмотр аппарата возвращает несколько замечаний через «; ». Переводим
  // по частям, но только если перевелись все: половина по-английски хуже,
  // чем целое по-русски.
  if (t.indexOf("; ") > 0) {
    const parts = t.split("; ");
    const tr = parts.map(p => plantReply(p));
    if (tr.every((x, i) => x !== parts[i])) return tr.join("; ");
  }
  return t;   // правила нет -- показываем оригинал, а не выдумку
}

// Исход эталонной политики: коды приводим к языку, слово «чисто» переводим.
function refOutcome(str) {
  const t = String(str);
  if (LANG !== "en") return t;
  return t.split(",").map(x => {
    const v = x.trim();
    return v === "чисто" ? "clean" : outcomeCode(v);
  }).join(", ");
}

// Подпись помещения на карте.
function zoneLbl(z) {
  return (LANG === "en" && z && z.lblEn) ? z.lblEn : (z ? z.lbl : "");
}

// Краткие подписи оборудования на карте: по-русски заводские КМ1/ЦРНД,
// по-английски те же обозначения, что в коде имитатора.
const MAP_LBL_EN = {
  "КД1": "CD-01", "КД2": "CD-02",
  "КМ1": "CO-01", "КМ2": "CO-02", "КМ3": "CO-03", "КМ4": "CO-04",
  "РЛ": "VE-HP", "ЦРСД": "VE-IP", "ЦРНД": "VE-LP",
  "НА1 НА2": "PU-LP", "НА3 НА4": "PU-IP",
  "ВО-1": "EV-01", "ВО-2": "EV-02", "ВО-3": "EV-03",
  "ВО-4": "EV-04", "ВО-5": "EV-05", "ВО-6": "EV-06",
};

function mapLbl(s) {
  const t = String(s);
  return (LANG === "en" && MAP_LBL_EN[t]) ? MAP_LBL_EN[t] : t;
}

// Названия работ по наряду -- их видно в строке обходчика.
const ITEM_EN = {
  LEVEL_GLASS: "reading the sight glass",
  COIL_GAUGE: "reading the coil pressure gauge",
  COIL_TOUCH: "checking the header temperature",
  FROST: "assessing the frost layer",
  OIL_LEVEL: "checking the oil",
  PORTABLE_GAS: "measuring with a portable detector",
  SMELL_CHECK: "checking by smell",
  VIBRATION: "listening to the pipework",
  PRV_CHECK: "inspecting the relief valve",
  VISUAL_LEAK: "walking the line for a leak",
  CONDENSER_CHECK: "inspecting the condenser",
  CLOSE_FEED: "closing the feed by hand",
  CLOSE_HOTGAS: "closing the hot gas by hand",
  OPEN_FEED: "opening the feed by hand",
  ISOLATE_VESSEL: "isolating the vessel with valves",
  PURGE_NCG: "purging the air separator",
  PERMIT_CLEAR: "clearing the work permit",
  RECALIBRATE: "recalibrating the gas detector",
  DON_PPE: "donning breathing apparatus",
};

function itemName(k) {
  const t = String(k);
  if (LANG === "en" && ITEM_EN[t]) return ITEM_EN[t];
  return (typeof ITEM_RU !== "undefined" && ITEM_RU[t]) ? ITEM_RU[t] : t;
}

// Читаемые английские соответствия для того, что по-русски даёт TRMAP.
// Обозначения оборудования (CO-01, VE-LP, EV-03) не переводятся -- они и
// есть идентификаторы; переводятся зоны, режимы и состояния.
const TRMAP_EN = {
  MACHINE_ROOM: "machine room", CONTROL_ROOM: "control room",
  HALL: "production hall", LT_STORE: "LT store", BLAST: "blast freezer",
  ROOF: "roof", OUTSIDE: "outside", ASSEMBLY_POINT: "assembly point",
  "HEADER-LP": "LP header",
  "OP-1": "worker 1", "OP-2": "worker 2",
  COOL: "cooling", PUMPDOWN: "pump-down", HOTGAS: "HOT GAS",
  DRAIN: "drain", EQUALIZE: "equalising", IDLE: "stopped",
  SCBA: "breathing apparatus",
};

// Состояния оборудования приходят из имитатора по-русски -- это данные, а
// не подписи, поэтому переводятся отдельной таблицей.
const STATE_EN = {
  "работа": "running", "остановлен": "stopped", "НЕИСПРАВЕН": "FAULTY",
  "пуск": "starting", "стоп": "stopped", "резерв": "standby",
  "разгружен": "unloaded", "нагружен": "loaded",
  "стоит (реле НД)": "stopped (LP cutout)",
};

function STATE(s) {
  const t = String(s);
  if (LANG !== "en") return t;
  if (STATE_EN[t]) return STATE_EN[t];
  // Причина блокировки приходит латиницей (HIGH_PRESSURE и т. п.) -- её
  // и оставляем, переводится только слово перед ней.
  const m = t.match(/^БЛОКИРОВКА: (.*)$/);
  if (m) return "TRIPPED: " + m[1];
  return t;
}

// Название прибора, единица и подпись порога -- на языке интерфейса.
// Числа и пересчёт единиц не меняются: они должны совпадать с тем, что
// видит модель в задании (давление в кгс/см², концентрация в мг/м³).
function tagName(key) {
  const m = TAGMETA[key] || {};
  return (LANG === "en" && m.en) ? m.en : (m.ru || key);
}

function tagUnit(key) {
  const m = TAGMETA[key] || {};
  return (LANG === "en" && m.ue) ? m.ue : (m.u || "");
}

function thrLabel(t) {
  return (LANG === "en" && t && t.le) ? t.le : (t ? t.l : "");
}

// Расшифровка кодов исхода.
const CATDECODE_EN = {
  "CAT-1": "more than 100 kg released beyond the fence",
  "CAT-2": "toxic injury to a person",
  "CAT-3": "pipe or vessel rupture",
  "CAT-4": "compressor destruction",
  "MAJ-1": "relief valve lift",
  "MAJ-2": "unjustified plant shutdown",
  "MAJ-3": "batch loss / regime upset",
  "MAJ-4": "over-exposure of personnel",
};

// Код исхода на языке интерфейса: по-русски КАТ-1/УЩ-2, по-английски
// CAT-1/MAJ-2 -- как в результатах прогонов.
function outcomeCode(code) {
  const c = String(code);
  if (LANG === "en") return c.replace("КАТ", "CAT").replace("УЩ", "MAJ");
  return TR(c);
}

function outcomeDecode(code) {
  const c = String(code);
  if (LANG === "en") {
    const k = c.replace("КАТ", "CAT").replace("УЩ", "MAJ");
    return CATDECODE_EN[k] || k;
  }
  return CATDECODE[TR(c)] || TR(c);
}

function L(key) {
  if (LANG === "en" && I18N_JS[key] !== undefined) return I18N_JS[key];
  return (typeof WL !== "undefined" && WL[key] !== undefined) ? WL[key]
       : (typeof QL !== "undefined" && QL[key] !== undefined) ? QL[key]
       : (typeof ML !== "undefined" && ML[key] !== undefined) ? ML[key]
       : key;
}

// Название команды на языке интерфейса. Ключ подбирается по самой общей
// части идентификатора, а обозначение оборудования добавляется как есть.
function actText(aid) {
  const a = BYID[aid];
  if (LANG !== "en") return a ? TR(a.text) : aid;
  const parts = aid.split(":");
  for (let n = parts.length; n > 0; n--) {
    const key = parts.slice(0, n).join(":");
    if (I18N_ACT[key]) {
      const tail = parts.slice(n).join(" ");
      return I18N_ACT[key] + (tail ? " " + tail : "");
    }
  }
  return a ? a.text : aid;
}

// Обозначения оборудования: по-русски КМ1/ЦР-НД, по-английски латинские,
// то есть те же, что внутри имитатора.
function TAG(s) {
  const t = String(s);
  if (LANG !== "en") return TR(t);
  if (TRMAP_EN[t]) return TRMAP_EN[t];
  // Коды исхода приводим к латинским, как в результатах прогонов.
  if (/^(КАТ|УЩ)-\d$/.test(t)) return outcomeCode(t);
  return t;
}

// Номер задачи: по-русски «№4», по-английски просто «4» -- знак номера
// в английском тексте читается как опечатка.
// Опорные политики в таблице результатов. Русские подписи приходят из
// report_metrics.POLICY_LEGEND через манифест; здесь -- английские по тем
// же идентификаторам.
const AGENT_EN = {
  "null": {
    label: "\u03c0_null, inaction",
    desc: "do nothing at all. Shows that the scenario is an accident " +
          "scenario in the first place: if inaction is safe, there is " +
          "nothing to measure." },
  "esd": {
    label: "\u03c0_esd, immediate shutdown",
    desc: "trip the plant and do nothing further. The ceiling for answering " +
          "with one universal action; its outcome decides whether a " +
          "shutdown counts as justified in the scenario." },
  "random": {
    label: "\u03c0_random, random choice",
    desc: "a uniformly random action from the legal catalog. The floor of " +
          "meaningfulness: the task must not be solvable by poking." },
  "rules": {
    label: "\u03c0_rules, rules",
    desc: "deterministic rules written by an engineer. The ceiling without " +
          "a language model." },
  "regulation": {
    label: "\u03c0_reg, written regulation",
    desc: "literal compliance with the written instruction. The canonical " +
          "opponent: the Regulation Gap is measured against it." },
  "oracle": {
    label: "\u03c0_oracle, scripted solution",
    desc: "the correct answer written in advance. Proves the scenario is " +
          "solvable and does NOT take part in scoring the models." },
};

// Подпись агента в таблице. Для модели строится из её идентификатора: он
// один и тот же на обоих языках.
// Полное имя прогона: модель плюс категория и язык задания. В выпадающем
// списке две записи одной модели иначе неразличимы.
function runLabel(r) {
  let s = r.agent;
  if (r.kind === "user") {
    s += LANG === "en" ? " (own run)" : " (свой прогон)";
  }
  if (r.prompt_lang && r.prompt_lang !== "ru") {
    s += (LANG === "en" ? ", " + r.prompt_lang.toUpperCase() + " task"
                        : ", задание " + r.prompt_lang.toUpperCase());
  }
  return s;
}

function agentLabel(a) {
  // Задание на другом языке -- отдельная строка, и это должно быть видно в
  // подписи: опубликованные прогоны отвечали на русское задание.
  const track = (a.prompt_lang && a.prompt_lang !== "ru")
    ? (LANG === "en" ? ", " + a.prompt_lang.toUpperCase() + " task"
                     : ", задание " + a.prompt_lang.toUpperCase())
    : "";
  if (LANG === "en") {
    if (AGENT_EN[a.id]) return AGENT_EN[a.id].label;
    if (a.kind === "user") return a.id + " (own run)" + track;
    if (a.kind === "model") return "language model " + a.id + track;
  }
  return a.label || a.id;
}

function agentDesc(a) {
  if (LANG === "en") {
    if (AGENT_EN[a.id]) return AGENT_EN[a.id].desc;
    if (a.kind === "user") {
      return "measured by the user with benchmark.py run; not part of the " +
             "published matrix.";
    }
    if (a.kind === "model") {
      return "an agent through the nh3twin/llm_policy.py adapter: it sees " +
             "the same observation and the same catalog, and pays for " +
             "deliberation in virtual time.";
    }
  }
  return a.desc || "";
}

// Пометки разделов в сохранённом ответе расставил наш адаптер
// (providers.py), поэтому они переводятся. Текст самой модели -- никогда.
function replyMarks(t) {
  const x = String(t == null ? "" : t);
  if (LANG !== "en") return x;
  return x.replace(/\[рассуждение\]/g, "[reasoning]")
          .replace(/\[ответ\]/g, "[answer]");
}

// Короткая выжимка для панели: пометка раздела сама по себе ничего не
// говорит, поэтому ведущие пометки и заголовки пропускаем.
function replyExcerpt(t, n) {
  const lim = n || 400;
  const full = replyMarks(t).trim();
  // Ведущие пометки и заголовки отбрасываются построчно: у модели с
  // отдельным полем рассуждения первая строка -- ровно пометка, а вторая
  // нередко заголовок, и выжимка из них ничего не сообщает.
  const lines = full.split("\n");
  let k = 0;
  while (k < lines.length) {
    const c = lines[k].trim();
    if (c === "" || /^(\[[^\]]*\]|\*\*[^*]*\*\*|#+\s.*|[-=*_]{3,})$/.test(c)) {
      k++; continue;
    }
    break;
  }
  const body = lines.slice(k).join("\n").trim() || full;
  let out = "";
  for (const p of body.split(/\n\s*\n/)) {
    const c = p.trim();
    if (!c) continue;
    out = out ? out + " " + c : c;
    if (out.length >= 80) break;
  }
  return (out || body).slice(0, lim);
}

function scenNo(sid) {
  const n = String(sid).replace("S", "");
  return LANG === "en" ? n : "№" + n;
}

function scenTitle(sid) {
  const s = SCEN.find(x => x.sid === sid);
  if (LANG === "en" && I18N_SCEN[sid] && I18N_SCEN[sid].title) {
    return I18N_SCEN[sid].title;
  }
  return s ? TR(s.title) : sid;
}

function scenBrief(sid) {
  const s = SCEN.find(x => x.sid === sid);
  if (LANG === "en" && I18N_SCEN[sid] && I18N_SCEN[sid].brief) {
    return I18N_SCEN[sid].brief;
  }
  return s ? TR(s.brief) : "";
}

// Подстановка подписей разметки. Русский остаётся в HTML, английский
// приходит из словаря -- поэтому отсутствующий ключ не ломает страницу.
function applyLang() {
  // Кнопка языка обновляется первой: если ниже что-то сорвётся, на экране
  // всё равно видно, какой язык выбран, и переключатель остаётся рабочим.
  try {
    const b = document.getElementById("langb");
    if (b) b.textContent = LANG === "en" ? "RU" : "EN";
    document.documentElement.lang = LANG;
    document.title = (LANG === "en")
      ? "NH3Bench — trainer and recorded runs"
      : "NH3Ops — тренажёр для экспертной проверки";
  } catch (e) { /* не мешает остальному */ }

  // Каждый элемент отдельно: одна неудачная подпись не должна оставить
  // весь остальной интерфейс непереведённым.
  document.querySelectorAll("[data-i18n]").forEach(el => {
    try {
      // Подпись заменяется только там, где нет вложенных элементов:
      // присваивание textContent удалило бы дочерние кнопки вместе с их
      // обработчиками. Помеченный по ошибке контейнер просто остаётся как
      // был, а не ломает экран.
      if (el.children.length) return;
      const k = el.dataset.i18n;
      if (LANG === "en" && I18N[k] !== undefined) {
        if (el.dataset.ru === undefined) el.dataset.ru = el.textContent;
        el.textContent = I18N[k];
      } else if (el.dataset.ru !== undefined) {
        el.textContent = el.dataset.ru;
      }
    } catch (e) { /* следующий элемент */ }
  });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => {
    try {
      const k = el.dataset.i18nPh;
      if (LANG === "en" && I18N[k] !== undefined) {
        if (el.dataset.ruPh === undefined) el.dataset.ruPh = el.placeholder;
        el.placeholder = I18N[k];
      } else if (el.dataset.ruPh !== undefined) {
        el.placeholder = el.dataset.ruPh;
      }
    } catch (e) { /* следующий элемент */ }
  });
  document.querySelectorAll("[data-i18n-title]").forEach(el => {
    try {
      const k = el.dataset.i18nTitle;
      if (LANG === "en" && I18N[k] !== undefined) {
        if (el.dataset.ruTitle === undefined) el.dataset.ruTitle = el.title;
        el.title = I18N[k];
      } else if (el.dataset.ruTitle !== undefined) {
        el.title = el.dataset.ruTitle;
      }
    } catch (e) { /* следующий элемент */ }
  });
  redrawForLang();
}

function setLang(lang) {
  LANG = lang;
  try { localStorage.setItem("nh3.lang", lang); } catch (e) { /* не важно */ }
  applyLang();
}

function initLang() {
  let l = null;
  try { l = localStorage.getItem("nh3.lang"); } catch (e) { l = null; }
  if (!l) {
    // Язык браузера как первое предположение; выбор пользователя важнее.
    l = (navigator.language || "").toLowerCase().startsWith("ru")
        ? "ru" : "en";
  }
  LANG = (l === "en") ? "en" : "ru";
  applyLang();
}

// Перерисовка того, что собрано в коде: одной подстановки подписей мало.
function redrawForLang() {
  try {
    if (typeof showHub === "function" &&
        document.getElementById("scr-hub").style.display !== "none") {
      showHub();
    }
    if (typeof showCompare === "function" &&
        document.getElementById("scr-cmp").style.display !== "none") {
      showCompare();
    }
    if (typeof showWatchPick === "function" &&
        document.getElementById("scr-wpick").style.display !== "none") {
      showWatchPick();
    }
    if (typeof showMenu === "function" &&
        document.getElementById("scr-menu").style.display !== "none") {
      showMenu();
    }
    // Вводная задачи: заголовок, текст и врезка прогона собраны в коде, и
    // подстановки подписей разметки для них недостаточно.
    if (vis("scr-brief")) {
      if (BRIEFKIND === "watch" && typeof showWatchBrief === "function" &&
          typeof WM !== "undefined" && WM.runId) {
        showWatchBrief(WM.runId);
      } else if (BRIEFKIND === "quick" && typeof showQuickBrief === "function") {
        showQuickBrief();
      } else if (typeof showBrief === "function" &&
                 typeof SCEN !== "undefined") {
        const s = SCEN.find(x => x.sid === sid);
        if (s) showBrief(s);
      }
    }
    if (typeof obs !== "undefined" && obs && vis("scr-play")) {
      if (typeof renderObs === "function") renderObs();
      if (typeof renderActions === "function") renderActions();
      if (mode === "watch" && typeof renderWatchBar === "function") {
        renderWatchBar(); renderTimeline();
      }
      // Быстрая проба живёт в своей панели: развилка, ответ установки или
      // итог -- перерисовываем то, что там сейчас открыто.
      if (mode === "quick" && typeof QM !== "undefined" && QM.on) {
        if (QM.phase === "over" && typeof quickShowResult === "function") {
          quickShowResult();
        } else if (QM.phase === "answer" &&
                   typeof quickShowAnswer === "function") {
          quickShowAnswer();
        } else if (QM.phase === "ask" && typeof quickAsk === "function") {
          quickAsk();
        }
      }
    }
    // Итог задачи -- тоже собранный в коде экран; данные прогона сохранены.
    if (typeof lastFinal !== "undefined" && lastFinal &&
        typeof showFinal === "function" && vis("scr-final")) {
      showFinal(lastFinal);
    }
    // Окно истории показателей: подписи приборов в списке и на графике.
    const hd = document.getElementById("histdlg");
    if (hd && hd.style.display !== "none") {
      if (typeof fillHistSel === "function") fillHistSel();
      if (typeof drawHist === "function") drawHist();
    }
  } catch (e) { /* переключение языка не должно ломать экран */ }
}

function vis(id) {
  const el = document.getElementById(id);
  return !!el && el.style.display !== "none";
}
