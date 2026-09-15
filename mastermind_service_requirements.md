# Mastermind — техническое задание на разработку сервиса

**Статус:** implementation-ready  
**Версия:** 1.0  
**Назначение документа:** обязательные требования к реализации сервиса Mastermind в составе Exocortex.  
**Правило интерпретации:** все формулировки «должен», «не должен», «требуется», «запрещено» являются обязательными. Решения, зафиксированные в документе, не являются предметом выбора исполнителя. Любое отступление оформляется как отдельное изменение требований до начала реализации соответствующего блока.

---

# 1. Контекст Exocortex

На момент начала разработки Mastermind в составе Exocortex уже существуют и задеплоены:

- Kernel;
- Saturn;
- Volt;
- Gryphon;
- Updater;
- Neptune.

Следующими сервисами являются:

- Chronos;
- Laboratory.

Mastermind разрабатывается как новый основной сервис персональной базы знаний.

Mastermind рассчитан на одного владельца Exocortex. Проектировать multi-tenant SaaS, организации, команды, биллинг, tenant isolation и сложную ролевую модель не требуется.

---

# 2. Назначение Mastermind

Mastermind — центральный knowledge layer Exocortex.

Он должен:

1. хранить единственную авторитетную копию Obsidian Vault;
2. предоставлять владельцу web-доступ к настоящему Obsidian, запущенному на сервере;
3. сохранять полную совместимость Vault со стандартным Obsidian;
4. добавить вторую форму внутренних ссылок `@note` наряду с нативной `[[note]]`;
5. добавить межсервисные ссылки вида `@service: target`;
6. интегрировать заметки с Chronos;
7. интегрировать заметки с Saturn только через Neptune;
8. отображать удалённые файлы Saturn как нативоподобные вложения заметки;
9. строить граф связей и показатель связанности;
10. вести Activity Heatmap;
11. публиковать отдельные заметки по постоянным shared-ссылкам;
12. предоставлять Crusher — конвейер автоматической переработки внешних материалов в заметки;
13. реплицировать и резервировать данные через предусмотренные пайплайны Neptune;
14. не превращать производные индексы и кэши в источник истины.

---

# 3. Термины

## 3.1. Canonical Vault

**Canonical Vault** — единственная авторитетная и актуальная копия Vault.

Canonical Vault находится на сервере Mastermind.

Любые другие копии считаются вторичными.

## 3.2. Note

**Note** — Markdown-файл с расширением `.md`, находящийся внутри Canonical Vault.

Имя файла без `.md` является именем заметки.

Пример:

```text
Example note.md
```

Имя заметки:

```text
Example note
```

## 3.3. Native Internal Reference

Нативная внутренняя ссылка Obsidian:

```md
[[Example note]]
```

## 3.4. Mastermind Internal Reference

Дополнительная внутренняя ссылка Mastermind:

```md
@Example note
```

## 3.5. External Reference

Ссылка на сущность другого сервиса Exocortex:

```text
@service: target
```

Примеры:

```md
@chronos: t-28572589
@saturn: root/media/example.png
```

## 3.6. Mastermind Bridge

Obsidian plugin, реализующий дополнительную семантику Mastermind внутри настоящего Obsidian.

## 3.7. Obsidian Runtime

Настоящий официальный Obsidian, запущенный на сервере Mastermind в отдельной графической сессии и доступный владельцу через браузер.

## 3.8. Derived State

Данные, которые можно полностью восстановить из Canonical Vault и обязательного служебного состояния:

- поисковый индекс;
- backlinks index;
- graph index;
- semantic index;
- кэш Chronos;
- кэш Saturn metadata;
- вычисленный процент связанности.

Derived State не является источником истины.

## 3.9. Crusher

Асинхронный pipeline, принимающий внешний материал, анализирующий его и создающий структурированную заметку в Canonical Vault.

## 3.10. Share

Постоянная внешняя ссылка на актуальное состояние одной конкретной заметки.

---

# 4. Фундаментальные инварианты

Следующие правила обязательны для всей реализации.

## 4.1. Единственный источник истины

Источник истины:

```text
Mastermind server
└── Canonical Vault
```

Saturn не является источником истины Mastermind.

Локальная экспортная копия не является источником истины.

Индекс не является источником истины.

SQLite не является источником истины текста заметок.

## 4.2. Mastermind не синхронизирует равноправные master-копии

Запрещена архитектура:

```text
PC ↔ Laptop ↔ Phone ↔ Server
```

Архитектура должна быть:

```text
                   Mastermind
                 Canonical Vault
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       Obsidian     Neptune      Web services
       Runtime         │
                       ▼
                     Saturn
```

## 4.3. `.md` остаётся основной единицей данных

Текст заметки хранится в обычном Markdown-файле.

Запрещено переносить основной текст заметок в SQL, proprietary document store или другой формат.

## 4.4. Отдельный `note_id` не вводится

Identity заметки определяется её именем и текущим расположением в файловой системе.

Служебный UUID для заметок не должен добавляться в YAML/frontmatter и не должен быть необходим для работы ссылок.

## 4.5. Глобальная уникальность имени заметки

В пределах одного Vault не может существовать две `.md`-заметки с одинаковым basename.

Для проверки уникальности:

1. расширение `.md` игнорируется;
2. Unicode приводится к NFC;
3. сравнение выполняется case-insensitive через Unicode casefold.

Следовательно, одновременно запрещены:

```text
Example.md
example.md
```

и:

```text
Folder A/Example.md
Folder B/Example.md
```

Если операция CREATE, RENAME, MOVE, Crusher или Share-edit приводит к нарушению правила, операция отклоняется до записи.

При startup Mastermind обязан просканировать Vault. Если уже присутствует конфликт имён, Mastermind переходит в `NOT_READY`, показывает список конфликтов и не разрешает программные write-операции до исправления.

## 4.6. Версионность заметок не реализуется

Не требуется:

- Git history заметок;
- revision tree;
- per-edit snapshots;
- rollback отдельной заметки;
- live/snapshot режим Share.

Backup всей системы и version history заметки считаются разными механизмами.

## 4.7. Локальные клиенты вне scope

Не реализуются:

- двусторонняя синхронизация с локальным Obsidian;
- offline-first режим;
- CRDT;
- peer-to-peer sync;
- mobile sync.

Экспорт Vault для открытия в стандартном Obsidian является compatibility requirement, но не механизмом синхронизации.

---

# 5. Общая архитектура

Обязательная архитектура:

```text
                                Browser
                                   │
                                   ▼
                         Mastermind Web Shell
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
       /vault                  /crusher                /analytics
          │
          ▼
  Obsidian Runtime Gateway
          │
          ▼
     KasmVNC session
          │
          ▼
    Official Obsidian
          │
    Mastermind Bridge
          │
          ▼
     Canonical Vault
          │
      ┌───┴───────────────────────────────┐
      │                                   │
      ▼                                   ▼
Mastermind Core                        Neptune
      │                                   │
 ┌────┼─────┬────────┐                     ▼
 ▼    ▼     ▼        ▼                   Saturn
Index Share Activity Crusher
 │
 └──────────────► Chronos
```

---

# 6. Deployable units

Mastermind должен состоять минимум из двух runtime-компонентов.

## 6.1. `mastermind-core`

Отвечает за:

- HTTP API;
- Mastermind Web Shell;
- Vault watcher;
- Index;
- Graph;
- Activity;
- Shares;
- Crusher;
- Chronos resolver;
- Neptune/Saturn resolver;
- backup/replication orchestration;
- health/readiness.

## 6.2. `mastermind-obsidian-runtime`

Отвечает за:

- официальный Obsidian;
- виртуальную Linux graphical session;
- KasmVNC;
- запуск Mastermind Bridge;
- открытие Canonical Vault;
- восстановление графической сессии после restart.

Оба компонента могут находиться в одном `docker compose` stack, но должны иметь разные процессы и разные container boundaries.

---

# 7. Сетевые границы

## 7.1. Публично доступные маршруты

Через общий reverse proxy Exocortex разрешены только маршруты Mastermind под его configured public base URL.

## 7.2. KasmVNC

KasmVNC не должен публиковать собственный порт напрямую в Internet.

Доступ к нему разрешён только:

```text
Mastermind Web Shell
    ↓ authenticated reverse proxy
KasmVNC
```

KasmVNC и Obsidian Runtime находятся во внутренней Docker network.

## 7.3. Saturn

Mastermind не обращается к Saturn напрямую.

Любые:

- listing;
- metadata;
- read;
- ranged read;
- folder traversal;
- replication;
- restore

выполняются через Neptune.

## 7.4. Chronos

Chronos вызывается через его внутренний API в сети Exocortex.

Mastermind не копирует Chronos event в собственное постоянное хранилище.

---

# 8. Файловая структура Mastermind

Использовать следующий layout:

```text
/var/lib/mastermind/
├── vault/                  # Canonical Vault
├── state/
│   └── mastermind.db       # non-note state
├── cache/
│   ├── search/
│   ├── semantic/
│   ├── chronos/
│   └── saturn/
├── crusher/
│   ├── incoming/
│   ├── work/
│   └── failed/
└── runtime/
    └── ...
```

Canonical Vault:

```text
/var/lib/mastermind/vault/
```

должен монтироваться read-write одновременно в:

- `mastermind-core`;
- `mastermind-obsidian-runtime`.

`cache/` разрешено удалять полностью без потери пользовательских данных.

`state/mastermind.db` удалять без восстановления backup нельзя.

---

# 9. SQLite state

SQLite используется в WAL mode.

Файл:

```text
/var/lib/mastermind/state/mastermind.db
```

Хранит:

- Activity events;
- Share records;
- Crusher sessions;
- Crusher jobs;
- write-operation audit;
- sync/replication state;
- служебные job locks;
- non-secret operational settings;
- derived index metadata.

Текст `.md` заметок в SQLite не является authoritative copy.

---

# 10. Secrets и конфигурация

Секреты должны храниться в Register согласно общей архитектуре Exocortex.

Запрещено хранить API keys:

- в Vault;
- в `.obsidian`;
- в Git;
- в `mastermind.db`;
- в Docker image.

Минимальные обязательные настройки:

```text
mastermind.public_base_url
mastermind.timezone
mastermind.vault_path
mastermind.crusher.provider
mastermind.crusher.text_model
mastermind.crusher.video_model
mastermind.crusher.max_upload_bytes
mastermind.obsidian.version
mastermind.activity.edit_idle_timeout_seconds
```

Обязательные secrets:

```text
mastermind.crusher.provider_api_key
```

а также service credentials Neptune/Chronos по принятому в Exocortex механизму.

Default:

```text
mastermind.vault_path = /var/lib/mastermind/vault
mastermind.crusher.provider = gemini
mastermind.crusher.max_upload_bytes = 2147483648
mastermind.activity.edit_idle_timeout_seconds = 300
```

Если обязательная конфигурация отсутствует, `/readyz` возвращает failure.

---

# 11. Импорт существующего Vault

Импорт выполняется один раз перед переводом Mastermind в рабочее состояние.

## 11.1. Импорт обязан быть non-destructive

Исходный Vault не изменяется.

Алгоритм:

1. создать immutable исходный snapshot;
2. посчитать количество `.md`;
3. посчитать количество всех файлов;
4. посчитать SHA-256 каждого файла;
5. проверить глобальную уникальность `.md` basenames;
6. скопировать Vault в `/var/lib/mastermind/vault`;
7. повторно посчитать SHA-256;
8. сравнить с исходником;
9. только после полного совпадения добавить Mastermind Bridge и необходимые Mastermind-specific файлы в `.obsidian`;
10. построить индексы;
11. создать первую Saturn replica через Neptune.

## 11.2. Конвертация ссылок запрещена

Во время импорта:

```md
[[Example]]
```

не заменяется на:

```md
@Example
```

Обе формы существуют параллельно.

---

# 12. Obsidian Runtime

## 12.1. Использовать настоящий Obsidian

Запрещено реализовывать собственный клон редактора в качестве основного Vault UI.

На сервере должен запускаться официальный unmodified Obsidian.

Obsidian binary:

- не модифицируется;
- не patchится;
- не декомпилируется;
- не хранится в репозитории Mastermind.

Версия Obsidian pinится в deployment configuration.

Обновление версии выполняется только через контролируемое обновление после compatibility test Mastermind Bridge.

## 12.2. Графическая среда

Использовать:

- Linux virtual display;
- lightweight window manager;
- KasmVNC как browser-accessible remote display.

После запуска graphical session автоматически стартует Obsidian и открывает:

```text
/var/lib/mastermind/vault
```

Пользователь не должен видеть обычный Linux desktop, terminal или file manager без отдельной административной необходимости.

Obsidian должен занимать рабочее окно session.

## 12.3. Browser integration

Mastermind Web Shell содержит вкладку:

```text
Vault
```

Она открывает proxied KasmVNC client.

Требуется поддержка:

- keyboard input;
- Ctrl/Cmd combinations;
- clipboard text;
- mouse;
- wheel/trackpad scrolling;
- resize;
- browser reconnect;
- WebSocket reconnect;
- persistent graphical session при временном закрытии browser tab.

## 12.4. Один owner session

Одновременно допускается одна активная writable Obsidian owner session.

Повторное открытие `/vault` тем же владельцем подключается к той же session, а не запускает второй Obsidian с отдельным Vault lock.

---

# 13. Mastermind Web Shell

Обязательные top-level sections:

```text
Vault
Crusher
Analytics
Shares
Settings
```

## 13.1. Vault

Настоящий server-side Obsidian.

## 13.2. Crusher

Создание access code, список jobs, статус pipeline, ошибки, результат и путь созданной заметки.

## 13.3. Analytics

Минимум:

- Activity Heatmap;
- Connectedness;
- количество notes;
- количество internal edges;
- broken internal references.

## 13.4. Shares

Список активных и истёкших shares:

- note;
- permission;
- password enabled;
- created_at;
- expires_at;
- revoke action;
- copy URL.

## 13.5. Settings

Только non-secret user-facing settings.

Secrets редактируются через принятую систему Register, а не выводятся в интерфейсе Mastermind.

---

# 14. `.obsidian` и совместимость Vault

Canonical Vault должен сохранять нормальную структуру Obsidian:

```text
.obsidian/
├── themes/
├── snippets/
├── plugins/
│   └── mastermind-bridge/
├── appearance.json
├── community-plugins.json
└── ...
```

Mastermind не должен переводить theme/plugin settings в собственный закрытый формат.

Если Vault скопировать на обычный компьютер и открыть стандартным Obsidian:

- Markdown открывается;
- папки открываются;
- `[[...]]` работают;
- установленная тема загружается;
- CSS snippets загружаются;
- Mastermind Bridge доступен как обычный plugin;
- `@...` остаются читаемым текстом даже при отключённом plugin.

Двусторонняя синхронизация такой экспортной копии с сервером в scope не входит.

---

# 15. Mastermind Bridge

Mastermind Bridge разрабатывается как обычный Obsidian plugin на TypeScript.

Структура runtime plugin:

```text
.obsidian/plugins/mastermind-bridge/
├── manifest.json
├── main.js
└── styles.css
```

Исходный TypeScript хранится в репозитории Mastermind, а в Vault помещается build artifact.

## 15.1. Обязанности plugin

Plugin реализует:

- internal `@note`;
- external `@chronos: ...`;
- external `@saturn: ...`;
- autocomplete;
- editor decorations;
- Reading View rendering;
- hover preview;
- merged outgoing links;
- merged backlinks;
- Mastermind Graph View;
- Activity owner events;
- rename propagation для `@note`;
- theme compatibility.

---

# 16. Theme compatibility

Mastermind-specific UI внутри Obsidian должен использовать:

- Obsidian CSS variables;
- native typography;
- native spacing;
- native border variables;
- native link classes/patterns;
- текущий accent color.

Запрещено жёстко задавать основную theme palette через literal hex/rgb цвета.

Допускаются минимальные fallback values только если соответствующая CSS variable отсутствует.

Mastermind-specific elements должны корректно работать с:

- default light;
- default dark;
- установленными community themes;
- custom CSS snippets.

---

# 17. Внутренние ссылки

Mastermind поддерживает одновременно две формы.

## 17.1. Native

```md
[[Example note]]
```

## 17.2. Mastermind

```md
@Example note
```

Обе формы указывают на одну и ту же note.

---

# 18. Разрешение `@note`

## 18.1. Поиск

Resolver ищет note по basename во всём Vault.

Текущая папка исходной заметки значения не имеет.

Пример:

```text
vault/
├── Current/
│   └── A.md
└── Archive/
    └── Example.md
```

В `A.md`:

```md
@Example
```

разрешается в:

```text
Archive/Example.md
```

## 18.2. Path syntax запрещён

Не вводить:

```text
@Folder/Example
@"Folder/Example"
```

Для внутренних ссылок пользователь пишет только:

```text
@ + note name
```

## 18.3. Case handling

Resolver:

1. сначала ищет exact basename;
2. затем casefold-equivalent basename.

Поскольку глобальная uniqueness проверяется также casefold, второй шаг всегда может вернуть максимум один результат.

---

# 19. Grammar `@note`

Задача parser — поддерживать имена заметок с пробелами без дополнительных кавычек.

Алгоритм:

1. символ `@` считается началом internal reference, если перед ним:
   - начало файла; или
   - whitespace; или
   - punctuation;
2. `@` не считается reference внутри email-like token, если перед ним alphanumeric, `_`, `-` или `.` без разделителя;
3. после `@` parser ищет **самое длинное имя существующей note**, совпадающее с последующим текстом;
4. note index используется как словарь допустимых имён;
5. если одновременно существуют `Example` и `Example note`, строка `@Example note` разрешается как `Example note`;
6. если совпадения нет, текст остаётся обычным текстом;
7. parser не обрабатывает:
   - fenced code blocks;
   - inline code;
   - HTML comments;
   - YAML frontmatter.

Autocomplete обязан быть основным способом вставки `@note`.

---

# 20. Autocomplete внутренних ссылок

После ввода `@` plugin показывает поиск по всему Vault.

Ranking:

1. prefix match;
2. word-prefix match;
3. substring match;
4. fuzzy match.

В UI показывается:

```text
Note name
relative/folder/path
```

После выбора вставляется только:

```md
@Note name
```

Путь не записывается в Markdown.

---

# 21. Внешний вид `[[note]]` и `@note`

В Live Preview и Reading View обе формы должны выглядеть одинаково.

Обязательное поведение:

- одинаковый цвет;
- одинаковая typography;
- одинаковое underline behavior;
- одинаковый cursor;
- одинаковый hover state;
- одинаковый broken-link state;
- одинаковый click behavior;
- одинаковый hover preview.

Для `@note` plugin должен использовать native-like CSS classes Obsidian internal link, а не отдельный визуальный стиль.

В Source Mode остаётся виден исходный синтаксис.

---

# 22. Rename и `@note`

При rename:

```text
Old name.md
    ↓
New name.md
```

все существующие Mastermind references:

```md
@Old name
```

должны быть автоматически заменены на:

```md
@New name
```

во всём Vault.

Требования:

1. используется Markdown-aware parser;
2. не изменяются code blocks;
3. не изменяется inline code;
4. не изменяются HTML comments;
5. не изменяются unrelated strings;
6. write выполняется atomic;
7. автоматические изменения ссылок не считаются Activity EDIT;
8. при ошибке операции не допускается частичное логическое состояние без rollback/recovery marker.

Native `[[...]]` links остаются под управлением стандартного механизма Obsidian.

---

# 23. MOVE

Перемещение note между папками без изменения basename:

```text
A/Example.md
    ↓
B/Example.md
```

не меняет:

```md
@Example
```

так как resolver ищет basename во всём Vault.

---

# 24. DELETE

После удаления target note:

```md
@Example
```

остаётся в тексте исходной note и получает broken-link styling.

Автоматически удалять reference запрещено.

---

# 25. External Reference Grammar

Общая форма:

```text
@service: target
```

`service`:

- lowercase ASCII;
- без пробелов;
- после имени обязательна `:`.

В первой версии обязательны два namespace:

```text
chronos
saturn
```

Неизвестный namespace остаётся текстом и не должен вызывать exception renderer.

---

# 26. Chronos reference

Форма:

```md
@chronos: t-28572589
```

`target` — opaque Chronos event ID.

Mastermind не должен извлекать семантику из структуры ID.

---

# 27. Chronos card

Chronos event сейчас не обязан иметь аннотацию.

Renderer показывает только фактические поля.

Минимальный вид:

```text
┌──────────────────────────────────────┐
│ Chronos                              │
│                                      │
│ Начало       14.09.2026 19:00        │
│ Окончание    14.09.2026 21:13        │
└──────────────────────────────────────┘
```

Если event active и end отсутствует:

```text
Окончание    —
```

Если Chronos недоступен:

```text
Chronos unavailable
t-28572589
```

Raw reference в `.md` не изменяется.

При восстановлении Chronos карточка автоматически начинает работать снова.

---

# 28. Chronos data ownership

Mastermind не хранит постоянную копию события.

Разрешён краткосрочный cache только для UI.

TTL cache:

```text
30 seconds
```

Chronos остаётся owner event data.

---

# 29. Saturn reference

Файл:

```md
@saturn: root/example_folder/example.file
```

Папка:

```md
@saturn: root/example_folder
```

В Markdown сохраняется полный Saturn path от `root`.

Имя само по себе без пути не используется.

---

# 30. Saturn path rules

Path:

- обязан начинаться с `root`;
- использует `/`;
- запрещает `..`;
- запрещает NUL;
- нормализуется перед отправкой в Neptune;
- не может выйти выше Saturn root;
- symlink traversal не должен позволять выйти за разрешённый root/subtree.

Autocomplete получает listing через Neptune.

---

# 31. Saturn autocomplete

После `@saturn:` plugin показывает дерево Saturn.

Пользователь выбирает folder или file.

После выбора записывается конкретный path:

```md
@saturn: root/projects/example/video.mp4
```

Если имя/path содержит пробелы, plugin записывает обычный path с пробелами.

Parser определяет target как самый длинный существующий Saturn path, совпадающий после `@saturn:`. Для вновь недоступного пути raw string сохраняется.

---

# 32. Saturn media rendering

`@saturn:` является embed, а не обычным текстовым hyperlink.

## 32.1. Image

Поддержать минимум:

```text
image/png
image/jpeg
image/webp
image/gif
image/svg+xml
```

Renderer:

- отображает preview;
- `max-width: 100%`;
- сохраняет aspect ratio;
- click открывает full preview.

## 32.2. Video

Поддерживаемые browser-native video types отображаются через HTML5 player.

Обязательно:

- controls;
- seek;
- pause/play;
- volume;
- fullscreen;
- HTTP Range.

Видео не скачивается целиком перед началом playback.

## 32.3. Audio

HTML5 audio player с seek.

## 32.4. PDF

Inline PDF preview/viewer.

## 32.5. Other file

Attachment card:

```text
example.file
2.7 GB
Open
Download
```

Размер и MIME берутся через Neptune.

---

# 33. Saturn folder embed

Folder reference отображается как embedded mini file browser.

Пример:

```text
┌ example_folder ─────────────────────────────┐
│                                            │
│  source/                                   │
│  cover.png                                 │
│  demo.mp4                                  │
│  specification.pdf                        │
│                                            │
│  4 objects · 8.3 GB                       │
└────────────────────────────────────────────┘
```

Разрешена навигация только внутри выбранного subtree.

Для:

```md
@saturn: root/projects/mastermind/assets
```

разрешено:

```text
root/projects/mastermind/assets/**
```

Запрещено подняться выше imported root через embedded folder UI.

---

# 34. Saturn streaming

Mastermind не должен полностью буферизовать большие Saturn objects.

Схема:

```text
Browser
  ↓ Range request
Mastermind
  ↓ ranged request
Neptune
  ↓
Saturn
```

Требуется pass-through streaming с backpressure.

Для public shares выдаётся только resource-specific capability на время HTTP request; постоянные Neptune/Saturn credentials клиенту не передаются.

---

# 35. Graph model

Внутренняя note graph:

```text
note = vertex
internal reference = edge
```

Учитываются обе формы:

```md
[[Example]]
@Example
```

Они эквивалентны.

---

# 36. Graph edge rules

Для Connectedness:

- graph undirected;
- self-link игнорируется;
- несколько ссылок A → B считаются одним edge;
- A → B и B → A считаются одним edge;
- broken references не являются edge;
- Chronos не входит;
- Saturn не входит.

---

# 37. Connectedness

Для `N` notes:

```text
max_edges = N × (N - 1) / 2
```

Для `E` существующих unique internal edges:

```text
connectedness = E / max_edges × 100%
```

Если `N < 2`, значение равно `0%`.

Интерпретация:

- `0%` — ни одна note не связана с другой;
- `100%` — каждая note непосредственно связана с каждой другой note.

В UI выводить значение с двумя decimal places.

---

# 38. Mastermind Graph View

Поскольку native Obsidian Graph не обязан понимать `@note`, Mastermind Bridge должен предоставить собственный Graph View.

Он обязан:

- учитывать `[[...]]`;
- учитывать `@...`;
- визуально соответствовать текущей Obsidian theme;
- открывать note по click;
- поддерживать zoom/pan;
- фильтровать internal/external nodes;
- использовать internal-only graph для Connectedness.

Native Obsidian Graph не удаляется.

Authoritative граф для Mastermind analytics — Mastermind Graph, а не native Graph.

---

# 39. Merged backlinks/outgoing links

Mastermind Bridge добавляет panes:

```text
Mastermind Backlinks
Mastermind Outgoing Links
```

Они объединяют:

- native `[[...]]`;
- `@note`.

External references показываются в Outgoing Links отдельной секцией:

```text
External
├── Chronos
└── Saturn
```

---

# 40. Activity Heatmap

Activity Heatmap учитывает только действия владельца над заметками.

Типы событий:

```text
CREATE
EDIT
RENAME
MOVE
```

Никаких других типов в heatmap нет.

---

# 41. Что не считается Activity

Не учитывать:

- open;
- read;
- scroll;
- search;
- hover;
- follow internal reference;
- follow external reference;
- playback;
- download;
- render;
- autosave как отдельное событие;
- background indexing;
- Neptune sync;
- Saturn replication;
- Chronos refresh;
- Crusher automated writes;
- automatic rename propagation;
- edits через public Shared Note;
- health checks.

Attachment insertion проходит как изменение Markdown и входит в `EDIT`.

---

# 42. EDIT session

Физические autosave не должны искусственно увеличивать activity.

Правило:

1. первая content modification note открывает edit session;
2. последующие content modifications той же note входят в эту же session;
3. session закрывается:
   - при переключении focus на другую note; или
   - через 300 секунд после последнего изменения; или
   - при закрытии note;
4. закрытая session создаёт ровно один `EDIT`;
5. новый edit после закрытия session создаёт новую session.

Если note была создана и затем редактировалась:

```text
CREATE = +1
EDIT   = +1
```

---

# 43. RENAME и MOVE Activity

Если изменился basename:

```text
RENAME +1
```

Если изменился parent folder:

```text
MOVE +1
```

Если одна операция одновременно меняет basename и folder:

```text
RENAME +1
MOVE   +1
```

Автоматическая перепись ссылок после rename не создаёт дополнительных EDIT events.

---

# 44. Activity timestamps

В database все timestamps сохраняются в UTC.

Для группировки по дням используется:

```text
mastermind.timezone
```

Смена timezone не переписывает исторические timestamps, а только меняет day grouping при query/render.

---

# 45. Heatmap normalization

Для каждого календарного дня:

```text
activity(day) = CREATE + EDIT + RENAME + MOVE
```

Для отображаемого периода:

```text
max_activity = max(activity(day))
```

Если `max_activity = 0`, все клетки пустые.

Иначе:

```text
intensity(day) = activity(day) / max_activity
```

Если единственный активный день имеет `1`, он получает `1.00`, то есть максимальную яркость.

---

# 46. Heatmap visual levels

Использовать четыре ненулевых уровня плюс empty:

```text
0 events            → empty
0 < I <= 0.25       → level 1
0.25 < I <= 0.50    → level 2
0.50 < I <= 0.75    → level 3
0.75 < I <= 1.00    → level 4
```

Цвет должен строиться от theme accent через opacity/derived variables, а не фиксироваться жёстким зелёным.

Hover показывает дату и количество actions.

---

# 47. Share model

Share создаётся для одной конкретной note.

URL:

```text
<public_base_url>/s/<token>
```

Token:

- cryptographically random;
- минимум 256 bits entropy;
- URL-safe;
- не содержит path/title note.

---

# 48. Share fields

Обязательные поля:

```text
share_id
token_hash
target_path
permission
password_hash nullable
created_at
expires_at nullable
revoked_at nullable
```

`permission`:

```text
view
edit
```

Режима snapshot нет.

Любой Share всегда показывает актуальное состояние note.

---

# 49. Share password

Если установлен password:

- использовать Argon2id;
- raw password нигде не сохраняется;
- не логировать password;
- не помещать password в URL;
- session после успешного password challenge хранить в Secure, HttpOnly cookie.

Rate limiting:

```text
5 failed attempts / 10 minutes / IP / share
```

После лимита возвращать `HTTP 429`.

---

# 50. Share expiration

Если `expires_at` отсутствует — ссылка бессрочная.

После expiration или revoke возвращать `HTTP 404`, не раскрывая существование ранее доступного Share.

---

# 51. Share при rename/move

Share не меняет URL.

При изменении пути Mastermind обновляет `target_path` в Share record.

Token остаётся тем же.

---

# 52. Share при delete

Если target note удалена, существующий не revoked Share возвращает:

```text
HTTP 410 Gone
```

В Shares UI record помечается `target_missing`.

---

# 53. Shared Note rendering

Public Share не использует Obsidian Runtime.

Схема:

```text
Share URL
   ↓
Mastermind Share Renderer
   ↓
Canonical Markdown
```

Public visitor не получает:

- remote desktop;
- Obsidian;
- Vault filesystem;
- Neptune token;
- Saturn credentials;
- Chronos credentials.

---

# 54. Internal links внутри Share

`[[Other note]]` и `@Other note`:

- отображаются тем же визуальным стилем;
- не открывают private note;
- не transclude private note;
- не создают автоматический public access к target.

По click показывается нейтральный state `Linked private note` без раскрытия path или content.

---

# 55. Chronos внутри Share

Если note явно содержит `@chronos: t-...`, Share Renderer может показать только:

- start;
- end.

Другие Chronos details через Share не раскрываются.

---

# 56. Saturn внутри Share

Если note явно содержит `@saturn: root/path/file`, Share может читать только этот объект.

Если note содержит folder, Share может читать только соответствующий subtree.

Нельзя использовать Share как gateway к любому другому Saturn path.

---

# 57. Share edit

При `permission=edit` public editor редактирует Markdown target note.

Использовать optimistic concurrency.

GET возвращает:

```text
ETag: <content_sha256>
```

Write требует:

```text
If-Match: <content_sha256>
```

Если current SHA изменился, возвращать `HTTP 409 Conflict` и:

- current content;
- submitted content;
- current ETag.

UI показывает обе версии и требует ручного merge. Silent overwrite запрещён.

Public edit не считается owner Activity.

---

# 58. Crusher purpose

Crusher должен преобразовывать внешние материалы в структурированные заметки Canonical Vault.

Поддерживаемые input classes:

- raw text;
- webpage URL;
- YouTube URL;
- uploaded file;
- audio;
- video;
- PDF;
- document;
- source archive;
- public Git repository URL;
- Saturn file reference.

---

# 59. Crusher access model

Crusher public submission endpoint защищается тем же принципом, что Saturn Drop Point.

Алгоритм:

1. владелец в Mastermind UI нажимает `Create Crusher access`;
2. Mastermind генерирует одноразовый 6-digit numeric code;
3. code действителен 30 минут;
4. code можно успешно активировать ровно один раз;
5. successful activation создаёт Crusher Session;
6. Crusher Session действительна 30 минут с момента activation;
7. пока session active, разрешено создавать новые jobs;
8. после session expiration новые jobs отклоняются;
9. ранее принятые jobs продолжаются до завершения или failure.

---

# 60. Crusher code security

Code activation endpoint rate limit:

```text
10 attempts / 10 minutes / IP
30 attempts / 10 minutes globally
```

После successful activation code немедленно invalidated.

Session token:

- cryptographically random;
- минимум 256 bits;
- передаётся Bearer token;
- raw token не сохраняется в DB, сохраняется hash.

---

# 61. Crusher job API

Минимум:

```text
POST /api/v1/crusher/access
POST /api/v1/crusher/sessions
POST /api/v1/crusher/jobs
GET  /api/v1/crusher/jobs/:id
GET  /api/v1/crusher/jobs/:id/result
```

`POST /access` доступен только authenticated owner.

`POST /sessions` принимает one-time code.

`POST /jobs` требует active Crusher Session.

---

# 62. Crusher job states

Использовать конечный набор:

```text
QUEUED
ACQUIRING
NORMALIZING
EXTRACTING
UNDERSTANDING
PLACING
GENERATING
VALIDATING
COMMITTING
COMPLETED
FAILED
```

Каждый transition сохраняется с timestamp.

---

# 63. Crusher pipeline

Обязательная последовательность:

```text
INPUT
  ↓
Acquire
  ↓
Normalize
  ↓
Extract
  ↓
Understand
  ↓
Find destination
  ↓
Generate note
  ↓
Validate
  ↓
Commit
```

Stage нельзя пропускать логически, даже если конкретный extractor объединяет внутренние операции.

---

# 64. Crusher Acquire

## 64.1. URL

Разрешены только `http` и `https`.

Перед fetch требуется SSRF protection.

Запрещены:

- localhost;
- loopback;
- RFC1918 private ranges;
- link-local;
- metadata IP;
- unix sockets;
- `file://`;
- `ftp://`;
- redirects в запрещённые диапазоны.

Каждый redirect проверяется заново.

## 64.2. Upload

Default max:

```text
2 GiB
```

Значение задаётся `mastermind.crusher.max_upload_bytes`.

Файл streamится в `crusher/incoming`, а не удерживается в memory.

## 64.3. Saturn reference

Crusher принимает Saturn path и получает содержимое через Neptune.

---

# 65. Crusher extractors

Архитектура:

```text
CrusherExtractor
├── RawTextExtractor
├── WebPageExtractor
├── YouTubeExtractor
├── PDFExtractor
├── AudioExtractor
├── VideoExtractor
├── DocumentExtractor
├── GitRepositoryExtractor
└── GenericFileExtractor
```

Выбор extractor выполняется по explicit source type + MIME/content sniffing.

---

# 66. WebPageExtractor

Pipeline:

1. HTTP fetch;
2. MIME validation;
3. HTML parse;
4. удалить navigation, ads, scripts, styles;
5. извлечь main article content;
6. сохранить title, canonical URL, author/date при наличии и body;
7. если страница требует JS rendering, использовать Playwright sandbox;
8. максимум 3 redirects.

---

# 67. YouTube и video

Initial AI provider:

```text
Gemini
```

Model names не hardcode в source code. Они берутся из Register:

```text
mastermind.crusher.video_model
```

YouTube URL передаётся extractor/provider предусмотренным provider способом.

Если direct URL processing невозможно, job может скачать допустимую media representation во временный sandbox и передать её provider.

Временные media files удаляются после завершения job.

---

# 68. PDF

Сначала выполнять deterministic extraction:

- text;
- headings;
- page boundaries;
- document metadata.

Если PDF scanned/image-only, использовать multimodal provider.

Не использовать OCR как первый путь для normal text PDF.

---

# 69. GitRepositoryExtractor

Для public Git repository:

1. shallow clone с `depth=1`;
2. clone выполняется в isolated job directory;
3. `.git` не передаётся в LLM;
4. бинарные файлы не передаются;
5. сначала анализировать README, docs, manifest/package files и top-level tree;
6. source code выбирать по релевантности;
7. secret-like files (`.env`, private keys, credentials, token dumps) не отправлять provider;
8. после job clone удаляется.

---

# 70. Crusher Understand

Provider должен получить:

- normalized source;
- структуру существующего Vault;
- релевантные notes;
- правила написания заметок;
- ограниченный контекст соседних notes.

Результат structured:

```json
{
  "title": "...",
  "summary": "...",
  "topics": [],
  "entities": [],
  "suggested_links": [],
  "destination_candidates": [],
  "placement_confidence": 0.0
}
```

LLM raw response не считается валидным, пока не прошёл schema validation.

---

# 71. Поиск места для Crusher note

Учитывать:

- folder structure;
- existing note content;
- internal graph;
- semantic similarity;
- neighboring notes;
- existing topic clusters.

Правило placement:

```text
confidence >= 0.90
    → commit в выбранный destination

0.65 <= confidence < 0.90
    → commit в Inbox/Crusher/
      + сохранить suggested_destination

confidence < 0.65
    → commit в Inbox/Crusher/
      + сохранить top candidates
```

Crusher job не должен ждать ручного approval бесконечно.

---

# 72. Crusher filename

AI формирует title.

Filename:

```text
<title>.md
```

Перед create:

1. убрать path separators;
2. убрать NUL/control chars;
3. trim;
4. если title пустой — использовать `Crusher note <timestamp>`;
5. проверить global basename uniqueness.

При collision:

```text
Title.md
Title (2).md
Title (3).md
...
```

Выбирается первое свободное имя.

---

# 73. Crusher note content

Note должна быть самостоятельной читабельной заметкой, а не логом LLM.

Она должна:

- давать содержательную выжимку;
- сохранять существенные факты;
- не выдумывать отсутствующие факты;
- использовать внутренние links только если target реально существует;
- использовать `@note` или `[[note]]` согласно стилю соседнего Vault context;
- не вставлять secret/provider data.

---

# 74. Crusher metadata footer

В конец созданной note помещать HTML comment:

```md
<!-- mastermind:crusher
job_id: <id>
source_type: <type>
source: <url-or-name>
processed_at: <ISO-8601 UTC>
provider: <provider>
model: <model>
placement_confidence: <0..1>
suggested_destination: <path-or-empty>
-->
```

Renderer не показывает этот блок как visible content.

Metadata является частью `.md` и перемещается вместе с note.

---

# 75. Crusher retries

Автоматически retry только transient failures:

- HTTP 429;
- HTTP 5xx;
- temporary network failure;
- provider timeout.

Максимум `3 attempts`.

Backoff:

```text
5s
30s
120s
```

Validation error, unsupported format и policy rejection не retry.

---

# 76. Crusher cleanup

После COMPLETED/FAILED:

- temporary uploads удаляются после 24 часов;
- work directories удаляются немедленно после successful commit;
- failed work можно хранить 24 часа для диагностики;
- user source в Saturn не удаляется;
- созданная note при COMPLETED остаётся в Canonical Vault.

---

# 77. Search index

Mastermind Core строит собственный index для API, Crusher и analytics.

Для текущего масштаба использовать SQLite FTS5.

Индексировать:

- basename;
- relative path;
- Markdown plain text;
- headings;
- tags;
- frontmatter properties;
- `[[...]]`;
- `@note`;
- `@chronos`;
- `@saturn`.

FTS index является Derived State и должен перестраиваться.

---

# 78. Semantic index

Semantic embeddings нужны для Crusher placement и semantic search.

Embedding storage является Derived State.

При смене embedding model разрешён полный reindex.

Model/provider задаётся конфигурацией, не hardcode.

---

# 79. File watcher

Mastermind Core должен отслеживать Canonical Vault через filesystem watcher.

События:

- create;
- modify;
- rename;
- move;
- delete.

Watcher запускает:

- validation;
- index update;
- graph update;
- replication queue;
- share target maintenance;
- cache invalidation.

Debounce filesystem events:

```text
500 ms
```

---

# 80. Programmatic writes

Crusher, Share и Mastermind maintenance не должны писать файл напрямую через truncate-in-place.

Алгоритм:

```text
write temp file in same filesystem
↓
fsync temp
↓
validate
↓
atomic rename over target
↓
fsync parent directory
```

CREATE также выполняется через temp + atomic rename.

---

# 81. Content concurrency

Поскольку version history отсутствует, программные edits обязаны использовать content SHA-256.

Write API принимает `expected_sha256`.

Если current hash отличается, возвращать `409 Conflict`.

Silent overwrite запрещён.

---

# 82. Activity attribution

Watcher сам по себе не должен считать каждое filesystem modification Activity.

Activity owner events передаются Mastermind Bridge отдельным authenticated channel/API.

Таким образом:

- Obsidian owner edit → Activity;
- Crusher file write → no Activity;
- Share edit → no Activity;
- automatic link rewrite → no Activity.

---

# 83. Replication в Saturn

После изменения Canonical Vault Mastermind ставит replication task в очередь Neptune.

Требование:

- событие изменения должно попасть в queue не позднее 1 секунды;
- нормальный replication должен стартовать не позднее 5 секунд;
- временная недоступность Neptune не блокирует редактирование Canonical Vault;
- состояние отображается как `DEGRADED`;
- retry выполняется автоматически.

---

# 84. Путь Saturn для Mastermind

Основная replica:

```text
root/mastermind/
```

Backup:

```text
root/backups/mastermind/
```

Использовать уже предусмотренные Neptune pipelines для Mastermind.

Mastermind не создаёт альтернативный direct-to-Saturn protocol.

---

# 85. Что входит в replica

`root/mastermind/` должен содержать достаточные данные для восстановления Canonical Vault.

Минимум:

```text
vault/**
```

с сохранением:

- relative paths;
- `.obsidian`;
- themes;
- snippets;
- Mastermind Bridge build;
- attachments, которые физически находятся внутри Vault.

Saturn external resources, на которые ссылается `@saturn`, повторно в replica не копируются.

---

# 86. Что входит в backup Mastermind state

`root/backups/mastermind/` должен сохранять:

- consistent SQLite backup `mastermind.db`;
- non-secret configuration export;
- manifest с versions;
- checksum manifest.

Secrets не копируются из Register в backup в открытом виде.

---

# 87. Periodic reconciliation

Кроме event-driven replication выполнять reconciliation каждые 15 минут.

Проверять:

- file count;
- size;
- content hashes по изменившимся manifests;
- missing remote files;
- unexpected remote files в managed namespace.

Canonical Vault всегда побеждает автоматически при обычной reconciliation.

Saturn не должен молча перезаписывать Canonical Vault.

---

# 88. Restore

Restore — только explicit owner/admin operation.

Автоматический startup restore из Saturn запрещён.

Алгоритм:

1. выбрать backup/replica;
2. проверить manifest;
3. проверить checksums;
4. восстановить во временный directory;
5. проверить unique basenames;
6. проверить `.md` readability;
7. остановить writes;
8. atomically swap Canonical Vault;
9. rebuild indexes;
10. restart Obsidian Runtime;
11. verify;
12. только после success удалить старый active path либо переместить в recovery snapshot.

Rollback должен быть возможен до завершения шага 11.

---

# 89. Health endpoints

Обязательны:

```text
GET /healthz
GET /readyz
```

`/healthz` проверяет, что process жив.

`/readyz` проверяет минимум:

- SQLite open;
- Canonical Vault readable/writable;
- no duplicate note basenames;
- required config present;
- Mastermind Bridge artifact present;
- worker queue available.

Chronos/Neptune могут быть degraded без перевода Core в crash, но status должен отражаться в readiness detail.

---

# 90. Status model

Использовать:

```text
HEALTHY
DEGRADED
NOT_READY
```

Примеры `DEGRADED`:

- Chronos unavailable;
- Neptune unavailable;
- Saturn replication lagging;
- AI provider unavailable.

Примеры `NOT_READY`:

- Canonical Vault unavailable;
- duplicate note names;
- SQLite corruption;
- missing required config;
- schema migration failed.

---

# 91. Logging

Все services используют structured JSON logs.

Обязательные поля:

```text
timestamp
level
service
module
event
request_id
```

Для jobs добавлять `job_id`, для Share — `share_id`.

Нельзя логировать:

- passwords;
- access codes после activation;
- raw Bearer tokens;
- API keys;
- full private note content.

---

# 92. Audit

Non-version audit хранит события:

- programmatic CREATE;
- programmatic EDIT;
- programmatic RENAME;
- programmatic MOVE;
- DELETE;
- share create/revoke;
- Crusher job create/result;
- restore;
- replication failure.

Audit — не version history и не позволяет восстановить старый content.

---

# 93. Security: path traversal

Любой relative path, полученный через API, обязан проходить canonicalization.

Запрещены:

```text
..
NUL
absolute host path
symlink escape
```

Проверка выполняется после normalization, а не только на raw input.

---

# 94. Security: HTML/Markdown rendering

Public Share renderer обязан sanitize HTML.

Запрещать:

- script;
- inline event handlers;
- `javascript:` URLs;
- unsafe iframe;
- arbitrary local file URLs.

Owner Obsidian Runtime может использовать стандартные возможности Obsidian отдельно; Share renderer всегда работает в stricter mode.

---

# 95. Security: Crusher sandbox

Всё скачанное Crusher считается untrusted.

Обработка:

- отдельный job work directory;
- no privileged container;
- no Docker socket;
- no host filesystem;
- execution of downloaded binaries запрещено;
- Git hooks отключены;
- archive extraction с защитой от zip-slip;
- archive size/depth limits.

---

# 96. Authentication owner UI

Mastermind не создаёт multi-user database.

Используется один owner authentication context Exocortex.

Все private routes (`/vault`, Crusher UI, analytics, shares, settings, private API) требуют owner authentication.

Public Share и Crusher capability endpoints используют собственные rules этого ТЗ.

---

# 97. API versioning

Все программные API:

```text
/api/v1/...
```

Breaking changes требуют `/api/v2`.

---

# 98. Минимальный private API

Обязательный набор:

```text
GET  /api/v1/vault/notes
GET  /api/v1/vault/notes/:name
POST /api/v1/vault/notes
PATCH /api/v1/vault/notes/:name
POST /api/v1/vault/notes/:name/rename
POST /api/v1/vault/notes/:name/move
DELETE /api/v1/vault/notes/:name

GET  /api/v1/graph
GET  /api/v1/analytics/connectedness
GET  /api/v1/analytics/activity

GET  /api/v1/references/chronos/:id
GET  /api/v1/references/saturn
GET  /api/v1/references/saturn/stream

POST /api/v1/shares
GET  /api/v1/shares
PATCH /api/v1/shares/:id
DELETE /api/v1/shares/:id

POST /api/v1/crusher/access
POST /api/v1/crusher/sessions
POST /api/v1/crusher/jobs
GET  /api/v1/crusher/jobs/:id
GET  /api/v1/crusher/jobs/:id/result

POST /api/v1/activity/events
```

---

# 99. Note create API

Request:

```json
{
  "name": "Example",
  "folder": "Research",
  "content": "# Example\n"
}
```

Validation:

- `.md` extension добавляет server;
- basename globally unique;
- folder within Vault;
- no traversal.

Response `201 Created` с relative path и SHA-256.

---

# 100. Rename API

Request:

```json
{
  "new_name": "New example"
}
```

Server:

1. проверяет uniqueness;
2. находит `@old` references;
3. готовит update plan;
4. выполняет rename;
5. обновляет `@` references;
6. обновляет Shares;
7. обновляет indexes;
8. ставит replication;
9. возвращает success.

---

# 101. Delete semantics

Delete через Mastermind UI/API должен требовать explicit confirmation.

Физическое поведение:

- note перемещается в Obsidian-configured trash behavior, если оно включено;
- иначе используется managed trash Mastermind.

Hard delete отдельной API operation в первой реализации не требуется.

---

# 102. Performance targets

Для Vault порядка 1 650 notes требования:

- cold index build: `< 30 s` на целевом сервере;
- internal `@` autocomplete: `< 100 ms` после local index load;
- connectedness incremental calculation: `< 200 ms`;
- note list query: `< 100 ms`;
- Share Markdown first render server processing: `< 300 ms` без external embeds;
- UI не должен блокироваться на полном graph recompute при каждом keystroke.

Значения измеряются server-side без сетевой RTT.

---

# 103. Incremental indexing

Не выполнять полный reindex при каждом save.

При изменении одной note:

1. reparse note;
2. update its outgoing edges;
3. update affected backlinks;
4. update FTS row;
5. update graph counters;
6. update semantic embedding только если content meaningfully changed.

Полный reindex доступен как admin operation.

---

# 104. Startup sequence

`mastermind-core`:

1. load config;
2. open SQLite;
3. migrate schema;
4. validate Vault path;
5. scan global basename uniqueness;
6. validate Bridge artifact;
7. start watcher;
8. load/rebuild lightweight indexes;
9. start workers;
10. expose ready.

`mastermind-obsidian-runtime`:

1. wait for Canonical Vault mount;
2. ensure `.obsidian/plugins/mastermind-bridge`;
3. start graphical session;
4. start KasmVNC;
5. launch Obsidian;
6. open Canonical Vault;
7. keep process supervised.

---

# 105. Obsidian и Updater

Obsidian Runtime version pinится.

Обновление:

1. Updater получает новую approved version;
2. staging compatibility test;
3. Mastermind Bridge test suite;
4. restart runtime;
5. verify Vault open;
6. только затем rollout считается successful.

Автоматическое бесконтрольное self-update Obsidian на production server отключить, если это технически возможно.

---

# 106. Mastermind Bridge compatibility tests

Для каждой поддерживаемой Obsidian version обязательно проверять:

- plugin loads;
- `@note` decoration;
- autocomplete;
- click;
- hover;
- theme variables;
- rename propagation;
- Chronos card;
- Saturn image;
- Saturn video;
- Saturn folder;
- Activity event channel;
- Graph View.

---

# 107. Export compatibility test

Обязательный acceptance test:

1. сделать filesystem copy Canonical Vault;
2. открыть copy стандартным Obsidian соответствующей версии;
3. убедиться, что Vault открывается без Mastermind server-side filesystem assumptions;
4. проверить existing theme;
5. проверить snippets;
6. проверить `[[note]]`;
7. включить Mastermind Bridge;
8. проверить `@note`;
9. проверить, что без доступного Mastermind API external references деградируют в безопасный placeholder, а не ломают note;
10. убедиться, что обычный Markdown остаётся читаемым.

Этот тест не означает поддержку sync обратно в Canonical Vault.

---

# 108. Graceful degradation

## 108.1. Chronos down

Notes продолжают открываться. Карточка показывает unavailable state.

## 108.2. Neptune/Saturn down

Notes продолжают открываться и редактироваться. Saturn embed показывает unavailable state. Replication queue сохраняется и retry.

## 108.3. AI provider down

Обычная работа Mastermind продолжается. Новые Crusher jobs переходят FAILED после retry.

## 108.4. KasmVNC down

Core API, Shares, Crusher workers и analytics продолжают работать. `/vault` показывает Runtime unavailable.

---

# 109. No hidden destructive repair

Mastermind не должен автоматически:

- удалять broken links;
- переименовывать user notes из-за semantic guess;
- перемещать existing notes по AI;
- восстанавливать Canonical Vault из Saturn без команды;
- переписывать весь Vault при parser upgrade.

Любая bulk mutation выполняется через explicit admin operation с dry-run report.

---

# 110. CLI / administrative commands

Предоставить административный CLI внутри `mastermind-core`.

Обязательные команды:

```text
mastermind doctor
mastermind reindex
mastermind graph rebuild
mastermind replication status
mastermind replication reconcile
mastermind backup create
mastermind restore verify <source>
mastermind restore apply <source>
mastermind vault validate
```

`doctor` не изменяет данные без отдельного флага.

---

# 111. `mastermind doctor`

Проверяет:

- config;
- Register reachability;
- Vault permissions;
- duplicate basenames;
- SQLite integrity;
- watcher;
- Bridge files;
- Neptune;
- Chronos;
- replication lag;
- stale Crusher jobs;
- KasmVNC reachability;
- Obsidian process status.

Выход non-zero при `NOT_READY`.

---

# 112. Database migrations

SQLite migrations:

- versioned;
- forward-only в обычном deploy;
- перед migration создаётся consistent DB backup;
- migration failure не должна запускать сервис в partial schema state.

---

# 113. Testing strategy

Обязательны:

- unit tests;
- integration tests;
- end-to-end tests;
- recovery tests;
- compatibility tests.

---

# 114. Unit tests

Минимально покрыть:

- basename normalization;
- duplicate detection;
- `@note` parser;
- longest-match parsing;
- email false-positive;
- code block exclusion;
- external reference parsing;
- Saturn path normalization;
- graph edge deduplication;
- connectedness formula;
- Activity normalization;
- Share token/password;
- Crusher session expiry;
- placement thresholds.

---

# 115. Integration tests

Обязательны сценарии:

1. create note → Obsidian sees file;
2. Obsidian edit → index updates;
3. rename → `@` references update;
4. move → `@` unchanged;
5. duplicate create rejected;
6. Chronos card resolved;
7. Saturn image streamed through Neptune;
8. Saturn video Range;
9. folder subtree cannot escape;
10. Share reflects current note after edit;
11. Share URL survives rename;
12. Share edit 409 on stale ETag;
13. Crusher code expires;
14. Crusher session expires while job continues;
15. Crusher creates unique filename;
16. Neptune outage queues replication;
17. Neptune recovery drains queue.

---

# 116. Data-integrity tests

Перед release на реальном Vault:

- исходный `.md` count;
- SHA-256 manifest;
- import;
- post-import manifest;
- no accidental content changes;
- graph parse count;
- broken references report;
- no duplicate basenames;
- successful Saturn replica.

---

# 117. Theme tests

Минимум:

- Obsidian default light;
- Obsidian default dark;
- одна установленная user community theme из production Vault.

Проверить:

- `@note`;
- broken `@note`;
- Chronos card;
- Saturn attachment;
- Saturn folder;
- Mastermind Graph;
- heatmap if rendered in Obsidian;
- hover states.

---

# 118. Browser tests для Obsidian Runtime

Проверить:

- Chromium;
- Firefox;
- Safari/WebKit-compatible browser, если доступен в CI/manual QA.

Обязательные сценарии:

- keyboard;
- clipboard;
- mouse;
- resize;
- reconnect;
- fullscreen;
- hotkeys;
- 8-hour session stability.

---

# 119. Backup/restore acceptance test

1. создать representative Vault;
2. создать Shares;
3. создать Activity;
4. выполнить Crusher job;
5. дождаться replication;
6. создать backup;
7. уничтожить test Mastermind state;
8. выполнить restore;
9. проверить notes, `.obsidian`, theme, shares, activity, crusher job records, graph rebuild, Obsidian Runtime, Saturn refs и Chronos refs.

---

# 120. Observability

Mastermind Web Settings/Status должен показывать:

```text
Core            HEALTHY/DEGRADED/NOT_READY
Obsidian        status
Chronos         status
Neptune         status
Saturn replica  last successful sync + lag
Index           status
Crusher worker  status
```

Не показывать secret values.

---

# 121. Error presentation

Ошибки пользовательского UI должны содержать:

- понятное сообщение;
- short error code;
- retry, если операция retryable;
- request/job ID для логов.

Не показывать raw stack trace пользователю.

---

# 122. Deletion of derived data

Администратор должен иметь возможность удалить `cache/` и выполнить `mastermind reindex`, после чего функциональность восстанавливается без обращения к backup.

---

# 123. Privacy

Mastermind не отправляет note content во внешние сервисы кроме явных AI operations Crusher.

Обычное редактирование, graph, search, Share rendering и Activity не должны вызывать AI provider.

Crusher source и только необходимый Vault context могут отправляться configured provider.

---

# 124. Scope exclusions

В первую реализацию явно не входят:

- local sync;
- mobile application;
- CRDT;
- note revision history;
- collaborative simultaneous editing;
- multi-user accounts;
- organization/team model;
- Kafka;
- отдельный graph database;
- Elasticsearch;
- direct Saturn API;
- автоматическая замена всех `[[...]]` на `@...`;
- собственный клон Obsidian UI.

---

# 125. Технологические ограничения

## 125.1. Core

Core должен использовать основной backend stack, уже принятый в Exocortex. Если в репозитории нет обязательного стандарта для нового сервиса, default implementation — Python 3.12+ / FastAPI.

Mastermind Bridge — TypeScript.

Смена backend языка допустима только для приведения к существующему стандарту репозитория и не может изменять архитектуру, API semantics или требования этого документа.

## 125.2. DB

SQLite обязателен для local Mastermind state на текущем масштабе.

## 125.3. Queue

Внешний broker в первой реализации не вводится.

Crusher и replication используют persistent SQLite-backed job queue.

Job claim выполняется транзакционно.

После process restart незавершённые jobs восстанавливаются.

---

# 126. Persistent job semantics

Job worker должен использовать lease.

Поля:

```text
status
leased_by
lease_expires_at
attempt
```

Если worker умер, после expiry lease job становится доступен другому worker.

Это касается:

- Crusher;
- replication;
- background reindex operations.

---

# 127. Необходимая документация в репозитории

После реализации должны существовать:

```text
README.md
docs/architecture.md
docs/deployment.md
docs/operations.md
docs/backup-restore.md
docs/mastermind-bridge.md
docs/crusher.md
docs/sharing.md
docs/api.md
```

`README.md` не заменяет остальные документы.

---

# 128. README minimum

README должен содержать:

- что такое Mastermind;
- архитектурную схему;
- dependencies;
- quick deployment;
- health check;
- ссылки на подробные документы.

---

# 129. Operational runbook

`docs/operations.md` должен описывать:

- startup;
- shutdown;
- update;
- Obsidian Runtime restart;
- reindex;
- Neptune outage;
- Chronos outage;
- Crusher provider outage;
- duplicate basename failure;
- DB integrity failure;
- stuck job recovery.

---

# 130. Definition of Done

Mastermind считается готовым только если выполнены все пункты ниже.

## Storage

- [ ] Canonical Vault находится на Mastermind server.
- [ ] Saturn не является source of truth.
- [ ] Neptune replication работает.
- [ ] Restore протестирован.
- [ ] `.md` content не хранится authoritative в DB.
- [ ] Duplicate basenames запрещены глобально.

## Obsidian

- [ ] Запускается настоящий официальный Obsidian.
- [ ] Vault открывается напрямую из Canonical path.
- [ ] Browser remote UI стабилен.
- [ ] Theme Vault применяется.
- [ ] Mastermind Bridge загружается.
- [ ] Export copy открывается standard Obsidian.

## References

- [ ] `[[note]]` работает нативно.
- [ ] `@note` работает по всему Vault.
- [ ] Обе формы выглядят одинаково.
- [ ] Rename обновляет `@note`.
- [ ] `@chronos:` отображает start/end.
- [ ] `@saturn:` отображает file/folder embeds.
- [ ] Large media streamится Range requests.

## Graph

- [ ] Учитываются `[[...]]` и `@...`.
- [ ] Duplicate edges collapse.
- [ ] External nodes не входят в connectedness.
- [ ] Connectedness соответствует формуле.

## Activity

- [ ] Только CREATE/EDIT/RENAME/MOVE.
- [ ] Autosave не создаёт множество EDIT.
- [ ] Automated writes не считаются.
- [ ] Heatmap normalizes relative to max day.

## Shares

- [ ] Permanent token URL.
- [ ] View/Edit.
- [ ] Optional password.
- [ ] Optional expiration.
- [ ] Always current note.
- [ ] Rename не меняет URL.
- [ ] Private linked notes не раскрываются.
- [ ] Saturn subtree ограничен.
- [ ] Stale edit получает 409.

## Crusher

- [ ] One-time code 30 minutes.
- [ ] Session 30 minutes.
- [ ] New jobs rejected after expiry.
- [ ] Existing jobs continue.
- [ ] Pipeline stages реализованы.
- [ ] Web/YouTube/PDF/audio/video/file/repository/Saturn source поддержаны.
- [ ] SSRF protection есть.
- [ ] Placement thresholds соблюдаются.
- [ ] Metadata footer записывается.
- [ ] Filename globally unique.
- [ ] Temporary data очищается.

## Reliability

- [ ] SQLite WAL.
- [ ] Persistent job queue.
- [ ] Atomic file writes.
- [ ] Health/readiness.
- [ ] Structured logs.
- [ ] Doctor CLI.
- [ ] Unit/integration/E2E tests.
- [ ] Backup/restore test.
- [ ] 8-hour Obsidian Runtime test.

---

# 131. Финальная модель ответственности

```text
Chronos
└── владеет временем и событиями

Saturn
└── владеет удалёнными файлами

Neptune
└── владеет транспортом Mastermind ↔ Saturn

Mastermind
├── владеет Canonical Vault
├── владеет knowledge graph
├── владеет Activity
├── владеет Shares
├── владеет Crusher
└── предоставляет Obsidian Runtime

Obsidian
└── является основным интерактивным редактором Canonical Vault

Mastermind Bridge
└── расширяет Obsidian семантикой Exocortex
```

---

# 132. Финальная синтаксическая модель

```md
[[Example note]]
```

Нативная внутренняя ссылка Obsidian.

```md
@Example note
```

Равноправная внутренняя ссылка Mastermind на ту же note.

```md
@chronos: t-28572589
```

Ссылка на Chronos event.

```md
@saturn: root/example_folder/example.file
```

Embed файла Saturn.

```md
@saturn: root/example_folder
```

Embed папки Saturn.

Никаких обязательных path-qualified internal references, note IDs или миграции `[[...]] → @...` не существует.

---

# 133. Итог

Mastermind должен быть реализован как персональный knowledge service, в котором:

1. Canonical Obsidian Vault физически находится на сервере Mastermind.
2. Настоящий Obsidian работает непосредственно с этим Vault.
3. В браузере пользователь получает тот же Obsidian через server-side graphical session.
4. Существующие themes, snippets и plugins сохраняются.
5. Mastermind Bridge добавляет `@note`, `@chronos:` и `@saturn:`.
6. `[[note]]` и `@note` сосуществуют и визуально эквивалентны.
7. Имя note глобально уникально в пределах Vault.
8. Saturn resources ведут себя как тяжёлые внешние attachments.
9. Knowledge graph учитывает обе формы внутренних ссылок.
10. Activity Heatmap измеряет только CREATE/EDIT/RENAME/MOVE владельца.
11. Share всегда показывает актуальную note.
12. Crusher защищён 30-минутной одноразовой access-моделью и пишет результат непосредственно в Canonical Vault.
13. Saturn используется только через Neptune.
14. Любой derived state перестраивается.
15. Любая операция, способная повредить пользовательские данные, должна быть либо atomic, либо иметь проверяемый rollback.
16. Ни один автоматический процесс не имеет права молча заменить Canonical Vault данными из secondary storage.

Реализация считается соответствующей ТЗ только при выполнении всех требований и acceptance tests из данного документа.
