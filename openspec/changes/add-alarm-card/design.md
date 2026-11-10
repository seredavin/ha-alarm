## Context

Бэкенд будильника готов (change `add-wakeup-alarm`). У каждого будильника одно устройство и 21 сущность с `translation_key`:
- `enabled`, `skip_next`, `weekday_mon` … `weekday_sun`;
- `wake_time`;
- `fade_duration`, `media_lead`, `max_volume`, `cover_lead`, `snooze_duration`, `auto_stop`;
- `stop`, `snooze`, `test`;
- `next_wake`, `status`.

На проде (HA 2026.10) Lovelace в storage-режиме. Mushroom и card-mod не установлены. Другие интеграции (`dreame_vacuum`) уже отдают свой фронтенд сами. Сборочного тулчейна для JS в репозитории нет, и заводить его ради одной карточки не хочется.

## Goals / Non-Goals

**Goals:**
- Один JS-файл без сборки и внешних зависимостей, который отдаёт сама интеграция.
- Карточка устойчива к изменениям фронтенда HA: опирается только на публичный контракт custom cards (`setConfig`, `hass`, `getCardSize`, `getConfigElement`, `getStubConfig`, `getGridOptions`, `window.customCards`) и широко используемые элементы (`ha-card`, `ha-icon`, `ha-form`).

**Non-Goals:**
- Изменение устройств будильника (источники, колонка, шторы) из карточки. Это остаётся в options flow.
- Отдельный HACS-репозиторий для карточки (категория Dashboard).
- Карточка «все будильники сразу». Ставится по одной карточке на будильник.
- Автоматические JS-тесты в CI. Карточка проверяется вручную на HA, см. tasks.

## Decisions

### 1. Доставка: статический путь + extra module + ресурс Lovelace
В `async_setup` интеграции один раз на процесс (флаг в `hass.data`):
- `hass.http.async_register_static_paths([StaticPathConfig("/wakeup_alarm/wakeup-alarm-card.js", <path>, cache_headers=False)])`;
- `frontend.add_extra_js_url(hass, url)`, если загружен `frontend`;
- если ресурсы Lovelace в storage-режиме — запись `module` с тем же `url` в коллекции ресурсов: создаётся, при смене версии обновляется, удаляется вместе с последним будильником.

`url` = `/wakeup_alarm/wakeup-alarm-card.js?v=<версия>`. Браузер импортирует модуль по одному URL один раз, поэтому двойной загрузки нет.
- *Почему не только `add_extra_js_url`.* Проверено на проде: фронтенд HA подключает extra modules только из `index.html` и не подписывается на их изменения. Service worker и приложение могут отдать `index.html` из кэша, сохранённый до установки карточки, либо страница может загрузиться во время рестарта HA до загрузки интеграции. Тогда карточка не определяется, и вместо неё «Ошибка конфигурации» до полной перезагрузки. Ресурсы Lovelace дашборд запрашивает по websocket при каждом открытии.
- *Почему не только ресурс.* В YAML-режиме ресурсов коллекция недоступна для записи, там остаётся extra module.
- В `manifest.json`: `dependencies: ["http"]`, `after_dependencies: ["frontend", "lovelace", "sun"]`.

### 2. Ванильный Web Component, без Lit
Внутренние ссылки фронтенда HA на Lit не являются публичным API, а трюк `customElements.get("hui-masonry-view")` ненадёжен. Карточка — `class WakeupAlarmCard extends HTMLElement` с Shadow DOM:
- **Рендер.** Один раз строится DOM-скелет. Затем `update()` при каждом `set hass` точечно меняет текст, классы и значения. Полной перерисовки нет, поэтому не сбиваются фокус и перетаскиваемый ползунок.
- **Сравнение.** Перед обновлением сравниваются `last_updated` только «своих» 21 сущностей. Обновления остальных сущностей HA карточку не трогают.
- **Стили.** CSS-переменные темы HA: `--primary-color`, `--secondary-text-color`, `--card-background-color`, `--state-active-color`, `--warning-color`, `--error-color`, `--ha-card-border-radius`. Тёмная и светлая тема получаются автоматически.
- **Элементы:**
  - `ha-card` — оболочка;
  - `ha-icon` — иконки;
  - нативный `<input type="range">`, стилизованный под тему (`accent-color` плюс трек);
  - нативный `<input type="time">`, открывается по клику на крупное время;
  - выключатель и «Пропустить следующий» — собственный CSS-переключатель на `<button role="switch">`, а не `ha-switch`, чей API менялся между версиями.

### 3. Поиск сущностей по `translation_key`
`hass.entities` (реестр отображения) содержит `device_id`, `platform` и `translation_key`. Карточка фильтрует `platform === "wakeup_alarm" && device_id === config.device_id` и строит словарь `translation_key → entity_id`. Если `enabled` или `wake_time` не нашлись, показывается ошибка «Будильник не найден». Привязка к `device_id`, а не к `entity_id` — один параметр вместо 21 и устойчивость к переименованиям.

### 4. Сервисные вызовы
- **Выключатели и чипы:** `hass.callService("switch", on ? "turn_off" : "turn_on", {entity_id})`. Чип переключается оптимистично и откатывается при ошибке или если состояние не подтвердилось за 5 с.
- **Время:** событие `change` у `<input type="time">` (а не `input`) → `time.set_value`, `{time: "HH:MM:00"}`.
- **Слайдеры:** на `input` меняется только подпись, на `change` (отпускание) вызывается `number.set_value`. Пока пользователь держит ползунок, входящие `hass`-обновления не меняют его значение (флаг `dragging`).
- **Кнопки:** `button.press`.
- **Ошибки сервисов:** показываются через событие `hass-notification` (стандартный тост HA).

### 5. Строка состояния и форматирование
- `next_wake` — ISO-время. Сравнивается с «сегодня» и «завтра» в часовом поясе сервера (`hass.config.time_zone`). Форматируется через `Intl.DateTimeFormat(hass.locale.language, {timeZone, hour, minute, hourCycle})`; формат 12/24 ч берётся из `hass.locale.time_format`.
- В состоянии `sunrise` подпись «Рассвет до HH:MM» берёт время подъёма из `time.*`.
- Названия состояний — из встроенного словаря карточки (ru/en), чтобы не зависеть от загрузки переводов сущности.

### 6. Визуальный редактор
`getConfigElement()` возвращает `wakeup-alarm-card-editor` — `HTMLElement` с `ha-form` внутри. Схема:
- `{name: "device_id", required: true, selector: {device: {integration: "wakeup_alarm"}}}`;
- `{name: "title", selector: {text: {}}}`.

Изменения уходят наружу событием `config-changed`. `getStubConfig(hass)` берёт первое устройство, у которого есть сущность платформы `wakeup_alarm`. Регистрация в `window.customCards` с `preview: true` и описанием.

### 7. Раскладка
Сверху вниз:
1. шапка: иконка, имя, выключатель;
2. блок времени: крупно, 48 px;
3. чипы дней;
4. строка состояния;
5. четыре слайдера;
6. `<details>` «Ещё»;
7. ряд кнопок.

В режиме срабатывания у карточки акцентная рамка и фон из `--warning-color` (рассвет) или `--error-color` (звонит), а «Стоп»/«Отложить» становятся крупными. Для sections: `getGridOptions()` → `{columns: 12, min_columns: 6, rows: "auto"}`. `getCardSize()` → 7.

## Risks / Trade-offs

- [`add_extra_js_url` загружает модуль на всех страницах фронтенда] → файл небольшой (~20 KB), кэшируется. Регистрация элементов защищена через `customElements.get(...)`, чтобы не упасть при повторной загрузке.
- [Нет `translation_key` в `hass.entities` у старых фронтендов] → минимальная версия HA 2025.1, где поле есть. Иначе карточка показывает ошибку с подсказкой обновить HA.
- [`ha-form` и селектор устройства — внутренние элементы] → используются почти всеми custom cards и стабильны годами. Если сломаются, редактор деградирует до YAML-режима, а сама карточка продолжит работать.
- [Нативный `input type=time` на iOS выглядит по-системному] → это приемлемо и даже удобно на телефоне.
- [Нет автотестов JS] → ручная проверка на проде через браузер (Playwright) по сценариям из спеки. Плюс Python-тест, что статический путь и extra JS URL регистрируются.

## Migration Plan

1. Релиз 0.2.0 → обновление через HACS → перезапуск HA → обновление страницы браузера.
2. Добавить карточку «Будильник» на дашборд для каждого будильника.
3. Откат: вернуться на 0.1.x в HACS. Карточки на дашборде покажут «Custom element doesn't exist», бэкенд не затронут.
