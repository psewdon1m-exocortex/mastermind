# Кастомизация Obsidian через CSS и интеграция плагинов с темами

> Historical source / non-normative. Preserved during the 2026-10-06 documentation
> consolidation. Statements about current behavior, deployment, versions and
> policy below apply only to their original checkpoint. For the active contract,
> use the [documentation index](../../README.md).

## 1. Как кастомизация Obsidian устроена на самом деле

Тема Obsidian — прежде всего **CSS**, а не JS.

У community theme основными файлами являются:

```text
theme/
├── manifest.json
└── theme.css
```

У плагина:

```text
plugin/
├── manifest.json
├── main.js
└── styles.css     # необязателен
```

У пользователя дополнительно есть:

```text
<vault>/
└── .obsidian/
    └── snippets/
        ├── my-style.css
        └── ...
```

CSS snippets можно включать и отключать через `Settings → Appearance`, а Obsidian автоматически подхватывает изменения файла.

Главная архитектурная идея Obsidian — не просто возможность написать произвольный CSS, а использование **CSS variables как дизайн-токенов**.

Например:

```css
--background-primary
--background-secondary

--text-normal
--text-muted
--text-accent

--interactive-normal
--interactive-hover
--interactive-accent

--background-modifier-border

--color-red
--color-green

--radius-s
--font-interface
```

Obsidian предоставляет большое количество таких переменных. Тема в основном изменяет их значения, а интерфейс использует переменные вместо конкретных цветов.

Упрощённо:

```text
                 Obsidian UI
                     │
                     ▼
              semantic tokens
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
 --text-normal   --background-*  --interactive-*
        ▲            ▲            ▲
        └────────────┼────────────┘
                     │
                  THEME
```

Например тема может написать:

```css
.theme-dark {
    --background-primary: #121212;
    --text-normal: #eeeeee;
    --interactive-accent: #7c5cff;
}

.theme-light {
    --background-primary: #ffffff;
    --text-normal: #222222;
    --interactive-accent: #6750a4;
}
```

И весь интерфейс, использующий эти переменные, автоматически меняется.

---

## 2. Как плагин вписывается в тему

Допустим Mastermind выводит карточку.

Плохой вариант:

```css
.mastermind-card {
    background: #202020;
    color: #eeeeee;
    border: 1px solid #444444;
    border-radius: 8px;
}
```

В тёмной теме она ещё может выглядеть нормально.

Переключаем Obsidian на светлую тему:

```text
Obsidian         белый
Mastermind       чёрный
```

и плагин визуально превращается в чужеродное приложение внутри Obsidian.

Правильный вариант:

```css
.mastermind-card {
    background: var(--background-secondary);
    color: var(--text-normal);
    border: 1px solid var(--background-modifier-border);
    border-radius: var(--radius-s);
}
```

Теперь:

```text
             Default theme     Minimal      AnuPpuccin
                   │              │              │
                   ▼              ▼              ▼
--background-secondary =       разные значения
                   │
                   ▼
            Mastermind card
```

**Mastermind вообще не знает, какая тема установлена.**

---

## 3. Стандартные элементы лучше не рисовать самостоятельно

У Obsidian есть собственные UI abstractions/components.

Например настройки плагина можно делать через:

```ts
new Setting(containerEl)
    .setName("Enable feature")
    .addToggle(...)
```

а не:

```html
<div class="my-settings-row">
    <span>Enable feature</span>
    <input type="checkbox">
</div>
```

В первом случае Obsidian создаёт DOM нужной структуры, и его уже стилизует активная тема.

Правило можно сформулировать так:

```text
Можно использовать Obsidian component
        │
        ├── да → использовать его
        │
        └── нет
             │
             ▼
        custom DOM
             │
             ▼
        Obsidian CSS variables
```

Для Mastermind:

```text
toggle        → Obsidian Toggle
dropdown      → Obsidian Dropdown
setting row   → Setting
modal         → Modal
workspace UI  → ItemView
icons         → Obsidian/Lucide icons

сложная карточка графа
или кастомный inspector
              ↓
       собственный DOM
              ↓
       Obsidian variables
```

---

## 4. Где собственный `styles.css` всё-таки нужен

Нативная тема не может знать, что такое:

```text
mastermind-entity-card
mastermind-relation-chip
mastermind-context-panel
mastermind-inference-indicator
```

Поэтому Mastermind должен определять **геометрию и семантику своего UI**, но не должен определять собственную независимую визуальную тему.

Например:

```css
.mastermind-entity-card {
    display: flex;
    flex-direction: column;
    gap: var(--size-4-2);

    padding: var(--size-4-3);

    background: var(--background-primary-alt);
    color: var(--text-normal);

    border: 1px solid var(--background-modifier-border);
    border-radius: var(--radius-m);
}

.mastermind-entity-card:hover {
    background: var(--background-modifier-hover);
}
```

Здесь Mastermind отвечает за:

```text
display
layout
структуру
иерархию
поведение
```

Obsidian/theme отвечает за:

```text
цвета
типографику
border
accent
hover
dark/light
визуальный язык
```

---

## 5. Внутренний слой токенов Mastermind

Для Mastermind имеет смысл ввести промежуточный слой токенов.

Вместо того чтобы по всему CSS обращаться непосредственно к:

```css
var(--background-secondary)
```

можно сделать:

```css
.mastermind {
    --mm-surface: var(--background-primary);
    --mm-surface-raised: var(--background-secondary);
    --mm-border: var(--background-modifier-border);

    --mm-text: var(--text-normal);
    --mm-text-muted: var(--text-muted);

    --mm-accent: var(--interactive-accent);
    --mm-hover: var(--background-modifier-hover);

    --mm-radius: var(--radius-s);
}
```

А компоненты уже используют:

```css
.mastermind-card {
    background: var(--mm-surface-raised);
    color: var(--mm-text);
    border-color: var(--mm-border);
    border-radius: var(--mm-radius);
}
```

Получается:

```text
Obsidian token
      │
      ▼
Mastermind semantic token
      │
      ▼
Mastermind component
```

Например:

```text
--interactive-accent
        ↓
--mm-accent
        ↓
entity selected state
relation selected state
primary action
active filter
```

Это даёт Mastermind собственный **контракт темизации**, не создавая отдельную тему.

---

## 6. Сторонняя тема сможет специально кастомизировать Mastermind

Например автор темы хочет, чтобы Mastermind выглядел немного иначе.

Он может написать:

```css
body {
    --mm-surface-raised: var(--background-primary-alt);
    --mm-radius: 12px;
}
```

И не трогать внутреннюю структуру Mastermind вообще.

Можно документировать публичные переменные:

```text
Mastermind theme API

--mm-surface
--mm-surface-raised
--mm-border

--mm-text
--mm-text-muted

--mm-accent

--mm-node-background
--mm-node-border

--mm-edge-color
--mm-edge-active-color
```

Это повторяет архитектурный принцип самого Obsidian.

---

## 7. Тема может напрямую стилизовать классы плагина

Крупные темы Obsidian часто содержат специальные интеграции с конкретными plugins.

Например Minimal отдельно поддерживает ряд популярных плагинов, включая Calendar, Dataview, Kanban, Excalidraw и другие.

То есть тема может сделать:

```css
.mastermind-entity-card {
    ...
}
```

или:

```css
.mastermind-graph-node {
    ...
}
```

и специально адаптировать Mastermind.

Из этого следует важное правило:

> Стабильные CSS class names фактически являются частью UI API плагина.

---

## 8. Namespace для CSS-классов обязателен

Писать:

```css
.card {}
.title {}
.button {}
.panel {}
```

плохо, потому что стили плагина могут конфликтовать с Obsidian или другими плагинами.

Нужно:

```css
.mastermind-card {}
.mastermind-card-title {}
.mastermind-panel {}
.mastermind-graph-node {}
```

или:

```css
.mm-card {}
.mm-card__title {}
```

Корневой контейнер:

```html
<div class="mastermind-view">

    <div class="mastermind-toolbar">
        ...
    </div>

    <div class="mastermind-content">

        <div class="mastermind-card">
            ...
        </div>

    </div>

</div>
```

CSS:

```css
.mastermind-view .mastermind-card {
    ...
}
```

Не следует глобально переопределять:

```css
button {}
input {}
.workspace-leaf {}
.view-content {}
```

---

## 9. Hardcoded styles — плохая архитектура

Такое:

```ts
element.style.backgroundColor = "#171717";
element.style.borderRadius = "8px";
```

делает плагин зависимым от собственного визуального стиля.

Лучше:

```ts
element.addClass("mastermind-card");
```

и:

```css
.mastermind-card {
    background: var(--background-secondary);
}
```

---

## 10. Light/Dark вручную обрабатывать почти никогда не требуется

У `body` есть:

```css
.theme-light
.theme-dark
```

Технически можно написать:

```css
.theme-dark .mastermind-card {
    ...
}

.theme-light .mastermind-card {
    ...
}
```

Но в большинстве случаев это лишнее.

Если использовать:

```css
background: var(--background-secondary);
color: var(--text-normal);
```

тема сама предоставит подходящие значения.

`.theme-dark` и `.theme-light` стоит использовать только там, где действительно требуется различная логика отображения.

---

## 11. Accent color тоже наследуется

Obsidian позволяет пользователю менять Accent color.

Для этого существуют переменные вроде:

```css
--color-accent
--color-accent-1
--color-accent-2

--interactive-accent
--interactive-accent-hover

--text-accent
--text-accent-hover
```

Поэтому:

```css
.mastermind-node.is-selected {
    border-color: var(--interactive-accent);
}
```

автоматически совпадёт с выбранным пользователем accent color.

---

## 12. Style Settings

В экосистеме Obsidian широко используется plugin **Style Settings**.

Он умеет читать специальные комментарии из CSS тем, snippets и plugins:

```css
/* @settings

name: Mastermind
id: mastermind
settings:
    -
        id: mastermind-card-radius
        title: Card radius
        type: variable-number-slider
        default: 8
        min: 0
        max: 24
        format: px

*/
```

После этого пользователь получает UI-настройку.

Plugin CSS может использовать:

```css
.mastermind-card {
    border-radius: var(--mastermind-card-radius);
}
```

Style Settings умеет менять CSS variables, цвета, строки, числовые значения и переключать классы на `body`.

Для Mastermind можно добавить:

```text
Style Settings
      │
      ├── Mastermind: compact mode
      ├── Mastermind: graph node radius
      ├── Mastermind: relation opacity
      └── Mastermind: panel density
```

без написания отдельной системы тем внутри Mastermind.

---

## 13. Общая модель темизации

```text
                    Obsidian
                       │
             ┌─────────┴─────────┐
             │                   │
           Theme              Plugins
             │                   │
             └──── CSS tokens ───┘
                       │
                 Style Settings
                       │
                  user overrides
```

---

## 14. Реальные плагины используют Obsidian tokens

Популярные плагины используют переменные вроде:

```css
font-family: var(--font-interface);
color: var(--text-accent);

border-radius: var(--radius-s);

color: var(--text-normal);
background-color: var(--background-secondary);
```

То есть они не пытаются строить отдельную независимую дизайн-систему, а подключаются к дизайн-системе Obsidian.

Именно поэтому такие плагины нормально переживают смену темы.

---

## 15. Уровни совместимости с темами

Можно выделить три уровня:

```text
LEVEL 1
Native Obsidian components
        ↓
почти автоматическая совместимость


LEVEL 2
Custom components
+ Obsidian variables
        ↓
очень хорошая совместимость


LEVEL 3
Theme contains explicit
Mastermind integration
        ↓
идеальная интеграция
```

Антипаттерны:

```text
hardcoded colors
hardcoded fonts
inline styles
глобальные selectors
собственная component library
с собственной palette
        ↓
плагин выглядит чужеродно
```

---

## 16. React не мешает темизации

Если сложный интерфейс Mastermind будет написан на React, это само по себе не создаёт проблем.

Например:

```tsx
<div className="mastermind-card">
    <span className="mastermind-card__title">
        Person
    </span>
</div>
```

и:

```css
.mastermind-card {
    background: var(--background-secondary);
}
```

нормально работают вместе с Obsidian themes.

Проблема возникает, если поверх Obsidian принести вторую независимую систему оформления, например:

```text
Material UI theme
Bootstrap theme
собственную Tailwind color palette
```

и строить поверх Obsidian отдельный visual language.

---

## 17. Особый случай — Canvas/WebGL

Если граф Mastermind будет рисоваться через:

```text
<canvas>
WebGL
PixiJS
Three.js
```

CSS не сможет непосредственно стилизовать отрисованные примитивы.

Тогда нужно получать значения CSS variables:

```ts
getComputedStyle(document.body)
    .getPropertyValue("--text-muted");
```

и передавать их renderer'у.

Получается bridge:

```text
Obsidian Theme
      ↓
CSS variables
      ↓
getComputedStyle()
      ↓
Mastermind Graph Renderer
      ↓
nodes / edges / labels
```

При смене темы граф необходимо перерисовывать.

---

## 18. Предлагаемый контракт Mastermind UI

```text
MASTERmind UI
│
├── Native UI Layer
│   ├── Modal
│   ├── Setting
│   ├── inputs
│   ├── buttons
│   └── menus
│
├── Custom UI Layer
│   ├── inspector
│   ├── entity cards
│   ├── relation widgets
│   └── special panels
│
├── Theme Adapter
│   │
│   ├── Obsidian semantic tokens
│   │       ↓
│   └── --mm-* tokens
│
├── Graph Theme Adapter
│       CSS tokens
│           ↓
│       JS computed values
│           ↓
│       Canvas/WebGL
│
└── Public styling contract
        ├── stable .mastermind-* classes
        └── stable --mm-* variables
```

Главное архитектурное правило:

> **Mastermind не имеет собственной темы.**

У него есть semantic UI layer, который наследует тему Obsidian.

Не:

```text
Obsidian Theme
+
Mastermind Theme
```

а:

```text
          Obsidian Theme
                │
                ▼
        Obsidian UI Tokens
                │
        ┌───────┴───────┐
        ▼               ▼
    Obsidian         Mastermind
      UI                UI
```

Именно это позволит Mastermind выглядеть как нативная часть Obsidian, а не как web-приложение, вставленное внутрь него.

---

# Требования к Mastermind

1. **Никаких hardcoded цветов интерфейса.**
2. **Никаких hardcoded font families**, кроме функционально необходимых случаев.
3. Стандартные controls реализуются через Obsidian API.
4. Custom controls используют Obsidian semantic CSS variables.
5. Все CSS selectors Mastermind находятся под namespace `.mastermind-*`.
6. Не переопределяются глобальные Obsidian selectors.
7. Вводится внутренний слой `--mm-*`.
8. `--mm-*` по умолчанию отображаются на Obsidian variables.
9. `--mm-*` считаются публичным стабильным theme API.
10. Light/dark не определяется вручную, пока это можно решить semantic variables.
11. Accent наследуется от Obsidian.
12. Canvas/WebGL получает цвета через отдельный `ThemeAdapter`.
13. Смена темы должна обновлять Canvas/WebGL без перезапуска.
14. Основной UI должен нормально выглядеть **без специальной поддержки конкретной темы**.
15. Тема при желании может получить более глубокую интеграцию через `.mastermind-*` и `--mm-*`.
16. `styles.css` Mastermind отвечает в основном за **layout и уникальную семантику**, а не за самостоятельный visual identity.

---

# Итог

Наши новые функции Obsidian должны «вписываться» в существующие пользовательские темы не через анализ конкретно установленной темы и ручную адаптацию под Minimal, Things, AnuPpuccin и другие.

Правильная архитектура:

```text
Theme
  ↓
Obsidian semantic tokens
  ↓
Mastermind theme adapter
  ↓
Mastermind UI
```

Если Mastermind встроится в систему дизайн-токенов Obsidian, активная тема автоматически будет определять его визуальное оформление.

Точечные integrations с популярными темами можно добавлять позднее как enhancement, но они не должны быть обязательным условием нормального отображения.

---

## Полезные источники

- Obsidian Developer Docs — CSS variables: https://docs.obsidian.md/Reference/CSS+variables/About+styling
- Obsidian Developer Docs — UI / HTML elements: https://docs.obsidian.md/Plugins/User+interface/HTML+elements
- Obsidian Developer Docs — Plugin guidelines/checklist: https://docs.obsidian.md/oo/plugin
- Obsidian Developer Docs — React in plugins: https://docs.obsidian.md/Plugins/Getting+started/Use+React+in+your+plugin
- Minimal theme: https://github.com/kepano/obsidian-minimal
- Style Settings plugin: https://github.com/mgmeyers/obsidian-style-settings
