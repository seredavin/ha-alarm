/*
 * Wake-up Alarm card — shipped and served by the wakeup_alarm integration.
 * Vanilla Web Component, no build step and no external dependencies.
 */

const DOMAIN = "wakeup_alarm";
const CARD_TYPE = "wakeup-alarm-card";
const EDITOR_TYPE = "wakeup-alarm-card-editor";
const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const ACTIVE = ["sunrise", "ringing", "snoozed"];
const PENDING_TIMEOUT = 5000;

const MAIN_SLIDERS = [
  ["fade_duration", "mdi:weather-sunset-up"],
  ["media_lead", "mdi:speaker-play"],
  ["max_volume", "mdi:volume-high"],
  ["cover_lead", "mdi:curtains"],
];
const MORE_SLIDERS = [
  ["snooze_duration", "mdi:alarm-snooze"],
  ["auto_stop", "mdi:timer-off-outline"],
];

const STRINGS = {
  en: {
    card_name: "Wake-up Alarm",
    card_description: "Sunrise alarm: wake time, weekdays, sunrise, speaker and covers in one card.",
    not_found: "Alarm not found. Select an alarm device in the card settings.",
    days: ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
    days_full: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    enabled: "Enabled",
    wake_time: "Wake time",
    fade_duration: "Sunrise",
    media_lead: "Speaker",
    max_volume: "Volume",
    cover_lead: "Covers before",
    snooze_duration: "Snooze for",
    auto_stop: "Auto stop",
    skip_next: "Skip next",
    cover_sun_only: "Only after sunrise",
    more: "More",
    stop: "Stop",
    snooze: "Snooze",
    test: "Test",
    min: "min",
    never: "off",
    states: {
      off: "Off",
      scheduled: "Scheduled",
      sunrise: "Sunrise",
      ringing: "Ringing",
      snoozed: "Snoozed",
    },
    sunrise_until: "Sunrise until {time}",
    today: "today at {time}",
    tomorrow: "tomorrow at {time}",
    on_date: "{date} at {time}",
    skipping: "Next one skipped",
    then: "then {when}",
    editor_device: "Alarm",
    editor_title: "Title (optional)",
  },
  ru: {
    card_name: "Будильник",
    card_description: "Будильник с рассветом: время, дни недели, свет, Станция и шторы в одной карточке.",
    not_found: "Будильник не найден. Выберите устройство будильника в настройках карточки.",
    days: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
    days_full: ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
    enabled: "Включён",
    wake_time: "Время подъёма",
    fade_duration: "Рассвет",
    media_lead: "Станция за",
    max_volume: "Громкость",
    cover_lead: "Шторы за",
    snooze_duration: "Отложить на",
    auto_stop: "Автостоп",
    skip_next: "Пропустить следующий",
    cover_sun_only: "Только после восхода",
    more: "Ещё",
    stop: "Стоп",
    snooze: "Отложить",
    test: "Тест",
    min: "мин",
    never: "выкл",
    states: {
      off: "Выключен",
      scheduled: "Запланирован",
      sunrise: "Рассвет",
      ringing: "Звонит",
      snoozed: "Отложен",
    },
    sunrise_until: "Рассвет до {time}",
    today: "сегодня в {time}",
    tomorrow: "завтра в {time}",
    on_date: "{date} в {time}",
    skipping: "Ближайший пропускается",
    then: "следующий {when}",
    editor_device: "Будильник",
    editor_title: "Заголовок (необязательно)",
  },
};

function storedLanguage() {
  // HA keeps the user's language in localStorage as a JSON string, e.g. "\"ru\"".
  try {
    const value = window.localStorage.getItem("selectedLanguage");
    return value ? JSON.parse(value) : undefined;
  } catch (_err) {
    return undefined;
  }
}

function language(hass) {
  const lang = (hass && ((hass.locale && hass.locale.language) || hass.language)) ||
    storedLanguage() || navigator.language || document.documentElement.lang || "en";
  return String(lang).toLowerCase().startsWith("ru") ? "ru" : "en";
}

function strings(hass) {
  return STRINGS[language(hass)];
}

function fill(template, values) {
  return template.replace(/\{(\w+)\}/g, (_, key) => (key in values ? values[key] : ""));
}

function capitalize(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

function findAlarmEntities(hass, deviceId) {
  const result = {};
  if (!hass || !hass.entities || !deviceId) return result;
  for (const entry of Object.values(hass.entities)) {
    if (entry.platform === DOMAIN && entry.device_id === deviceId && entry.translation_key) {
      result[entry.translation_key] = entry.entity_id;
    }
  }
  return result;
}

function firstAlarmDevice(hass) {
  if (!hass || !hass.entities) return undefined;
  const entry = Object.values(hass.entities).find((e) => e.platform === DOMAIN && e.device_id);
  return entry ? entry.device_id : undefined;
}

const STYLE = `
  :host { display: block; }
  [hidden] { display: none !important; }
  ha-card {
    padding: 16px;
    transition: box-shadow 0.3s, border-color 0.3s;
    overflow: hidden;
  }
  ha-card.mode-sunrise { border: 2px solid var(--warning-color, #ffa600); }
  ha-card.mode-ringing { border: 2px solid var(--error-color, #db4437); }
  ha-card.mode-snoozed { border: 2px solid var(--info-color, #039be5); }
  ha-card.mode-ringing .glow {
    position: absolute; inset: 0; pointer-events: none;
    background: var(--error-color, #db4437); opacity: 0.08;
    animation: pulse 1.6s ease-in-out infinite;
  }
  ha-card.mode-sunrise .glow {
    position: absolute; inset: 0; pointer-events: none;
    background: linear-gradient(180deg, var(--warning-color, #ffa600), transparent 70%);
    opacity: 0.12;
  }
  @keyframes pulse { 0%, 100% { opacity: 0.04; } 50% { opacity: 0.16; } }
  .wrap { position: relative; display: flex; flex-direction: column; gap: 14px; }
  .error { color: var(--error-color, #db4437); padding: 8px 0; }

  .header { display: flex; align-items: center; gap: 12px; }
  .header ha-icon {
    --mdc-icon-size: 22px;
    color: var(--state-icon-color, var(--secondary-text-color));
    background: var(--secondary-background-color, rgba(127,127,127,0.12));
    border-radius: 50%; padding: 8px; flex: none;
  }
  .header.on ha-icon { color: var(--primary-color); }
  .name { flex: 1; font-size: 16px; font-weight: 500; color: var(--primary-text-color); line-height: 1.3; }

  .switch {
    position: relative; flex: none; width: 46px; height: 26px; border-radius: 13px; border: none;
    background: var(--switch-unchecked-track-color, rgba(127,127,127,0.45)); cursor: pointer; padding: 0;
    transition: background 0.2s;
  }
  .switch::after {
    content: ""; position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%;
    background: var(--switch-unchecked-button-color, #fff); box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    transition: transform 0.2s;
  }
  .switch[aria-checked="true"] { background: var(--switch-checked-track-color, var(--primary-color)); }
  .switch[aria-checked="true"]::after { transform: translateX(20px); background: var(--switch-checked-button-color, #fff); }
  .switch:disabled { opacity: 0.4; cursor: default; }

  .time {
    display: block; width: 100%; box-sizing: border-box; text-align: center;
    font-size: 52px; font-weight: 300; line-height: 1.1; letter-spacing: 1px;
    color: var(--primary-text-color); background: transparent; border: none; outline: none;
    font-family: inherit; padding: 4px 0; cursor: pointer; border-radius: 12px;
    font-variant-numeric: tabular-nums;
  }
  .time:hover, .time:focus { background: var(--secondary-background-color, rgba(127,127,127,0.08)); }
  .time::-webkit-calendar-picker-indicator { display: none; }
  .off .time { color: var(--disabled-text-color, var(--secondary-text-color)); }

  .days { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; }
  .chip {
    height: 36px; border-radius: 18px; border: 1px solid var(--divider-color, rgba(127,127,127,0.3));
    background: transparent; color: var(--secondary-text-color); font: inherit; font-size: 13px;
    font-weight: 500; cursor: pointer; padding: 0; transition: background 0.15s, color 0.15s;
  }
  .chip.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .chip:disabled { opacity: 0.4; cursor: default; }

  .status {
    display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 8px;
    font-size: 14px; color: var(--secondary-text-color); text-align: center; min-height: 24px;
  }
  .badge {
    padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500;
    background: var(--secondary-background-color, rgba(127,127,127,0.12)); color: var(--primary-text-color);
  }
  .badge.scheduled { background: rgba(var(--rgb-primary-color, 3,169,244), 0.15); color: var(--primary-color); }
  .badge.sunrise { background: var(--warning-color, #ffa600); color: #fff; }
  .badge.ringing { background: var(--error-color, #db4437); color: #fff; }
  .badge.snoozed { background: var(--info-color, #039be5); color: #fff; }

  .sliders { display: flex; flex-direction: column; gap: 6px; }
  .row { display: grid; grid-template-columns: 24px minmax(110px, 1.2fr) minmax(90px, 2fr) 64px; align-items: center; gap: 10px; min-height: 36px; }
  .row ha-icon { --mdc-icon-size: 20px; color: var(--secondary-text-color); }
  .row .label { font-size: 14px; color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .row .value { font-size: 14px; color: var(--secondary-text-color); text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .row.disabled { opacity: 0.4; }
  input[type="range"] { width: 100%; margin: 0; accent-color: var(--primary-color); cursor: pointer; height: 24px; }
  .row.toggle-row { grid-template-columns: 24px 1fr auto; }

  details { border-top: 1px solid var(--divider-color, rgba(127,127,127,0.2)); padding-top: 6px; }
  summary {
    cursor: pointer; list-style: none; font-size: 14px; color: var(--secondary-text-color);
    display: flex; align-items: center; gap: 6px; padding: 6px 0; user-select: none;
  }
  summary::-webkit-details-marker { display: none; }
  summary ha-icon { --mdc-icon-size: 18px; transition: transform 0.2s; }
  details[open] summary ha-icon { transform: rotate(90deg); }
  details .sliders { padding-top: 4px; }

  .actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .btn {
    display: flex; align-items: center; justify-content: center; gap: 6px; height: 40px; border-radius: 20px;
    border: 1px solid var(--divider-color, rgba(127,127,127,0.3)); background: transparent;
    color: var(--primary-text-color); font: inherit; font-size: 14px; font-weight: 500; cursor: pointer;
    transition: background 0.15s, transform 0.1s;
  }
  .btn ha-icon { --mdc-icon-size: 18px; }
  .btn:hover:not(:disabled) { background: var(--secondary-background-color, rgba(127,127,127,0.1)); }
  .btn:active:not(:disabled) { transform: scale(0.97); }
  .btn:disabled { opacity: 0.35; cursor: default; }
  .actions.alert { grid-template-columns: 2fr 1.4fr 1fr; }
  .actions.alert .btn { height: 52px; font-size: 16px; }
  .actions.alert .btn.stop { background: var(--error-color, #db4437); border-color: transparent; color: #fff; }
  .actions.alert .btn.snooze:not(:disabled) { background: var(--info-color, #039be5); border-color: transparent; color: #fff; }

  @media (max-width: 420px) {
    .time { font-size: 44px; }
    .row { grid-template-columns: 22px minmax(70px, 1fr) minmax(80px, 1.6fr) 56px; gap: 8px; }
  }
`;

class WakeupAlarmCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement(EDITOR_TYPE);
  }

  static getStubConfig(hass) {
    const deviceId = firstAlarmDevice(hass);
    return deviceId ? { device_id: deviceId } : { device_id: "" };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._pending = {};
    this._dragging = null;
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    this._config = { ...config };
    this._built = false;
    if (this._hass) this._render();
  }

  set hass(hass) {
    const old = this._hass;
    this._hass = hass;
    if (!this._config) return;
    if (!this._built || !old || old.entities !== hass.entities || old.locale !== hass.locale) {
      this._render();
      return;
    }
    if (Object.values(this._ids).some((id) => old.states[id] !== hass.states[id])) this._update();
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return 7;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  // ---------------------------------------------------------------- render

  _render() {
    const hass = this._hass;
    const t = strings(hass);
    this._t = t;
    this._ids = findAlarmEntities(hass, this._config.device_id);
    const root = this.shadowRoot;
    root.innerHTML = "";
    const style = document.createElement("style");
    style.textContent = STYLE;
    root.appendChild(style);
    const card = document.createElement("ha-card");
    root.appendChild(card);
    this._card = card;

    if (!this._ids.enabled || !this._ids.wake_time) {
      card.innerHTML = `<div class="error">${t.not_found}</div>`;
      this._built = true;
      this._ids = {};
      return;
    }

    card.innerHTML = `
      <div class="glow"></div>
      <div class="wrap">
        <div class="header">
          <ha-icon icon="mdi:alarm"></ha-icon>
          <div class="name"></div>
          <button class="switch" role="switch" data-switch="enabled" aria-label="${t.enabled}"></button>
        </div>
        <input class="time" type="time" step="60" aria-label="${t.wake_time}">
        <div class="days">
          ${WEEKDAYS.map((d, i) => `<button class="chip" data-switch="weekday_${d}" title="${t.days_full[i]}">${t.days[i]}</button>`).join("")}
        </div>
        <div class="status"><span class="badge"></span><span class="next"></span></div>
        <div class="sliders">
          ${MAIN_SLIDERS.map(([key, icon]) => this._sliderRow(key, icon)).join("")}
          ${this._toggleRow("cover_sun_only", "mdi:weather-sunset-up")}
        </div>
        <details>
          <summary><ha-icon icon="mdi:chevron-right"></ha-icon>${t.more}</summary>
          <div class="sliders">
            ${MORE_SLIDERS.map(([key, icon]) => this._sliderRow(key, icon)).join("")}
            ${this._toggleRow("skip_next", "mdi:debug-step-over")}
          </div>
        </details>
        <div class="actions">
          <button class="btn stop" data-button="stop"><ha-icon icon="mdi:alarm-off"></ha-icon><span>${t.stop}</span></button>
          <button class="btn snooze" data-button="snooze"><ha-icon icon="mdi:alarm-snooze"></ha-icon><span>${t.snooze}</span></button>
          <button class="btn test" data-button="test"><ha-icon icon="mdi:play-circle-outline"></ha-icon><span>${t.test}</span></button>
        </div>
      </div>`;

    card.querySelectorAll("[data-row]").forEach((row) => {
      if (!this._ids[row.dataset.row]) row.hidden = true;
    });
    card.querySelectorAll("[data-switch]").forEach((el) =>
      el.addEventListener("click", () => this._toggle(el.dataset.switch)),
    );
    card.querySelectorAll("[data-button]").forEach((el) =>
      el.addEventListener("click", () => this._press(el.dataset.button)),
    );
    card.querySelectorAll("input[type=range]").forEach((el) => {
      const key = el.dataset.number;
      el.addEventListener("input", () => {
        this._dragging = key;
        this._setValueText(key, Number(el.value));
      });
      el.addEventListener("change", () => {
        this._dragging = null;
        this._setNumber(key, Number(el.value));
      });
    });
    const time = card.querySelector(".time");
    time.addEventListener("change", () => {
      if (this.shadowRoot.activeElement !== time) this._commitTime();
    });
    time.addEventListener("blur", () => this._commitTime());
    time.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") time.blur();
    });

    this._built = true;
    this._update();
  }

  _toggleRow(key, icon) {
    return `
      <div class="row toggle-row" data-row="${key}">
        <ha-icon icon="${icon}"></ha-icon>
        <span class="label">${this._t[key]}</span>
        <button class="switch" role="switch" data-switch="${key}" aria-label="${this._t[key]}"></button>
      </div>`;
  }

  _sliderRow(key, icon) {
    return `
      <div class="row" data-row="${key}">
        <ha-icon icon="${icon}"></ha-icon>
        <span class="label">${this._t[key]}</span>
        <input type="range" data-number="${key}" aria-label="${this._t[key]}">
        <span class="value"></span>
      </div>`;
  }

  // ---------------------------------------------------------------- update

  _state(key) {
    const id = this._ids[key];
    return id ? this._hass.states[id] : undefined;
  }

  _available(key) {
    const st = this._state(key);
    // Buttons stay "unknown" until first pressed, so only "unavailable" counts.
    return !!st && st.state !== "unavailable";
  }

  _isOn(key) {
    const pending = this._pending[key];
    if (pending) {
      const st = this._state(key);
      const actual = st && st.state === "on";
      if (actual === pending.value || Date.now() > pending.until) delete this._pending[key];
      else return pending.value;
    }
    const st = this._state(key);
    return !!st && st.state === "on";
  }

  _update() {
    if (!this._ids.enabled) return;
    const t = this._t;
    const card = this._card;
    const hass = this._hass;
    const enabled = this._isOn("enabled");
    const status = (this._state("status") || {}).state || (enabled ? "scheduled" : "off");

    card.className = ACTIVE.includes(status) ? `mode-${status}` : "";
    card.querySelector(".wrap").classList.toggle("off", !enabled);

    const device = hass.devices && hass.devices[this._config.device_id];
    card.querySelector(".name").textContent =
      this._config.title || (device && (device.name_by_user || device.name)) || t.card_name;
    card.querySelector(".header").classList.toggle("on", enabled);

    card.querySelectorAll("[data-switch]").forEach((el) => {
      const key = el.dataset.switch;
      const on = this._isOn(key);
      el.disabled = !this._available(key);
      if (el.classList.contains("chip")) el.classList.toggle("on", on);
      else el.setAttribute("aria-checked", String(on));
    });

    const time = card.querySelector(".time");
    const wake = this._state("wake_time");
    time.disabled = !this._available("wake_time");
    if (wake && this.shadowRoot.activeElement !== time) time.value = String(wake.state).slice(0, 5);

    this._updateStatus(status, enabled);

    for (const [key] of [...MAIN_SLIDERS, ...MORE_SLIDERS]) {
      const row = card.querySelector(`[data-row="${key}"]`);
      if (row.hidden) continue;
      const input = row.querySelector("input");
      const st = this._state(key);
      const available = this._available(key);
      row.classList.toggle("disabled", !available);
      input.disabled = !available;
      if (!st) continue;
      const attrs = st.attributes || {};
      input.min = attrs.min != null ? attrs.min : 0;
      input.max = attrs.max != null ? attrs.max : 100;
      input.step = attrs.step != null ? attrs.step : 1;
      if (this._dragging !== key && available && !Number.isNaN(Number(st.state))) {
        input.value = Number(st.state);
        this._setValueText(key, Number(st.state));
      }
    }

    const alert = ACTIVE.includes(status);
    card.querySelector(".actions").classList.toggle("alert", alert);
    card.querySelector('[data-button="stop"]').disabled = !alert || !this._available("stop");
    card.querySelector('[data-button="snooze"]').disabled = status !== "ringing" || !this._available("snooze");
    card.querySelector('[data-button="test"]').disabled = !this._available("test");
  }

  _setValueText(key, value) {
    const row = this._card.querySelector(`[data-row="${key}"]`);
    if (!row) return;
    const st = this._state(key);
    const unit = st && st.attributes ? st.attributes.unit_of_measurement : "";
    let text;
    if (key === "auto_stop" && value === 0) text = this._t.never;
    else if (unit === "%") text = `${value}%`;
    else if (unit === "min") text = `${value} ${this._t.min}`;
    else text = unit ? `${value} ${unit}` : String(value);
    row.querySelector(".value").textContent = text;
  }

  _updateStatus(status, enabled) {
    const t = this._t;
    const badge = this._card.querySelector(".badge");
    const next = this._card.querySelector(".next");
    badge.className = `badge ${status}`;
    badge.textContent = t.states[status] || status;

    if (status === "sunrise") {
      const wake = this._state("wake_time");
      next.textContent = wake ? fill(t.sunrise_until, { time: this._formatClock(String(wake.state)) }) : "";
      return;
    }
    if (!enabled || status === "ringing" || status === "snoozed") {
      next.textContent = "";
      return;
    }
    const nextWake = this._state("next_wake");
    const when = nextWake && nextWake.state && !["unknown", "unavailable"].includes(nextWake.state)
      ? this._formatWhen(new Date(nextWake.state))
      : "";
    if (this._isOn("skip_next") && when) {
      next.textContent = `${t.skipping} · ${fill(t.then, { when })}`;
    } else {
      next.textContent = capitalize(when);
    }
  }

  // ------------------------------------------------------------ formatting

  _timeZone() {
    // The wake time is server-local, so the next wake is shown in the server time zone too,
    // regardless of the user's "local time" profile setting.
    return (this._hass.config && this._hass.config.time_zone) || undefined;
  }

  _hourCycle() {
    const format = this._hass.locale && this._hass.locale.time_format;
    if (format === "12") return "h12";
    if (format === "24") return "h23";
    return undefined;
  }

  _locale() {
    return (this._hass.locale && this._hass.locale.language) || this._hass.language || "en";
  }

  _formatClock(hhmmss) {
    const [h, m] = hhmmss.split(":").map(Number);
    const date = new Date(Date.UTC(2000, 0, 1, h, m));
    return new Intl.DateTimeFormat(this._locale(), {
      hour: "2-digit", minute: "2-digit", hourCycle: this._hourCycle(), timeZone: "UTC",
    }).format(date);
  }

  _formatWhen(date) {
    if (Number.isNaN(date.getTime())) return "";
    const timeZone = this._timeZone();
    const dayKey = (d) => new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
    const time = new Intl.DateTimeFormat(this._locale(), {
      hour: "2-digit", minute: "2-digit", hourCycle: this._hourCycle(), timeZone,
    }).format(date);
    const now = new Date();
    const tomorrow = new Date(now.getTime() + 24 * 3600 * 1000);
    if (dayKey(date) === dayKey(now)) return fill(this._t.today, { time });
    if (dayKey(date) === dayKey(tomorrow)) return fill(this._t.tomorrow, { time });
    const day = new Intl.DateTimeFormat(this._locale(), { weekday: "short", day: "numeric", month: "short", timeZone }).format(date);
    return fill(this._t.on_date, { date: day, time });
  }

  // --------------------------------------------------------------- actions

  async _call(domain, service, data) {
    try {
      await this._hass.callService(domain, service, data);
    } catch (err) {
      this.dispatchEvent(new CustomEvent("hass-notification", {
        detail: { message: (err && err.message) || String(err) },
        bubbles: true,
        composed: true,
      }));
      this._pending = {};
      this._update();
    }
  }

  _toggle(key) {
    const id = this._ids[key];
    if (!id) return;
    const value = !this._isOn(key);
    this._pending[key] = { value, until: Date.now() + PENDING_TIMEOUT };
    setTimeout(() => this._built && this._update(), PENDING_TIMEOUT + 50);
    this._update();
    this._call("switch", value ? "turn_on" : "turn_off", { entity_id: id });
  }

  _press(key) {
    const id = this._ids[key];
    if (id) this._call("button", "press", { entity_id: id });
  }

  _setNumber(key, value) {
    const id = this._ids[key];
    const st = this._state(key);
    if (!id || (st && Number(st.state) === value)) return;
    this._call("number", "set_value", { entity_id: id, value });
  }

  _commitTime() {
    const input = this._card && this._card.querySelector(".time");
    const wake = this._state("wake_time");
    if (!input || !input.value || !wake) return;
    const value = `${input.value.slice(0, 5)}:00`;
    if (value !== String(wake.state)) this._call("time", "set_value", { entity_id: this._ids.wake_time, time: value });
  }
}

class WakeupAlarmCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    const t = strings(this._hass);
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) => (schema.name === "device_id" ? t.editor_device : t.editor_title);
      this._form.addEventListener("value-changed", (ev) => {
        const config = { ...this._config, ...ev.detail.value };
        if (!config.title) delete config.title;
        this._config = config;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = [
      { name: "device_id", required: true, selector: { device: { integration: DOMAIN } } },
      { name: "title", selector: { text: {} } },
    ];
  }
}

if (!customElements.get(CARD_TYPE)) customElements.define(CARD_TYPE, WakeupAlarmCard);
if (!customElements.get(EDITOR_TYPE)) customElements.define(EDITOR_TYPE, WakeupAlarmCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TYPE)) {
  const t = STRINGS[language()];
  window.customCards.push({
    type: CARD_TYPE,
    // Both names, so the card picker search finds it whatever the UI language is.
    name: t === STRINGS.ru ? "Будильник (Wake-up Alarm)" : "Wake-up Alarm (Будильник)",
    description: t.card_description,
    preview: true,
    documentationURL: "https://github.com/seredavin/ha-alarm#карточка",
  });
}
