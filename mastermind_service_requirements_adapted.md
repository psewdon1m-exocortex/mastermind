# Mastermind — концепция и требования, адаптированные к Exocortex

**Статус:** адаптированный проект; открытые решения вынесены отдельно.  
**Версия документа:** 1.1-draft (не версия релиза сервиса).  
**Дата:** 2026-09-14.  
**Основа:** [исходное ТЗ 1.0](mastermind_service_requirements.md).  
**Нормативная база:** [центральная документация Exocortex](../.docs/PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md).  
**Открытые вопросы:** [mastermind_open_questions.md](mastermind_open_questions.md).

Документ содержит полную целевую концепцию, сохраняет нумерацию исходных §§1–133 и добавляет общесистемные контракты §§134–145. Исходный файл остаётся самостоятельным историческим основанием этой редакции; настоящий draft не является утверждением о готовой реализации или о согласовании всех вариантов.

Обязательные инварианты и общие требования изложены непосредственно здесь. Неопределённые решения имеют ссылки MM-Qxx; их варианты и рекомендации находятся в отдельном реестре и не считаются принятыми решениями.

---

<a id="section-0"></a>

# 0. Статус документа, нормативная база и границы решений

Эта редакция адаптирует продуктовую модель Mastermind к общим требованиям Exocortex. Нумерация §§1–133 сохранена для сопоставления с исходным ТЗ; новые общесистемные контракты приведены в §§134–145.

Приоритет требований:

1. Прямые решения владельца, явно принятые для проекта.
2. [Part 00](../.docs/PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md) и применимые центральные Parts.
3. Настоящий документ и согласованные решения Mastermind.
4. Примеры, рекомендации и предполагаемые реализации.

Реальное состояние кода и deployment является проверяемым baseline, а не подтверждением соответствия. Наличие README или исходников не означает успешный production rollout.

Формулировки «должен», «запрещено» и «обязательно» задают целевой контракт. Однако ссылка на открытый вопрос MM-Qxx означает, что перечисленные варианты реализации НЕ утверждены. Рекомендация из реестра вопросов не становится требованием автоматически. До закрытия вопроса нельзя объявлять затронутый контракт согласованным или соответствующий блок production-ready; независимая работа может продолжаться.

Все открытые решения находятся в [отдельном реестре](mastermind_open_questions.md). Изменение центрального правила нельзя легализовать только записью в локальном ТЗ: применимость, исключение или изменение общей нормы оформляется по Part 00.

## 0.1. Матрица применимости

| Part | Применимость | Граница |
| --- | --- | --- |
| [00 — Authority](../.docs/PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md) | Применяется | Приоритет, applicability/baseline/decision records, порядок работ |
| [01 — Interface](../.docs/PART_01_INTERFACE_AND_INTERACTION_UNIFICATION.md) | Применяется к собственному UI | Shell, Login, Settings, Documentation, публичные формы; граница Obsidian требует [MM-Q01](mastermind_open_questions.md#mm-q01) |
| 01 §7 — Embedded node canvas | Не применяется к Markdown и derived graph | Mastermind не создаёт собственный редактор исполняемых/node-canvas проектов; это не основание вводить note revisions или note IDs |
| 01 §8 — Correlation graph | Частично | Навигация, доступность, ресурсы и lifecycle применяются; модель entity/property и её формула не описывают note graph Mastermind |
| [02 — Observability](../.docs/PART_02_OBSERVABILITY_AUDIT_AND_LOG_EXPORT.md) | Применяется | Operational logs, security/write audit, exports; Activity — отдельные domain data |
| [03 — Recovery](../.docs/PART_03_BACKUP_AND_RECOVERY.md) | Применяется | Полный logical ZIP, классификация данных, согласованный restore |
| [04 — Deployment](../.docs/PART_04_BOOTSTRAP_AND_DEPLOYMENT.md) | Применяется | Собственные bootstrap/env, подписанные артефакты, host ingress |
| [05 — Releases/Updater](../.docs/PART_05_CI_RELEASES_AND_LOCAL_UPDATES.md) | Применяется | Один релиз сервиса, совместимый комплект компонентов; расширения профиля требуют [MM-Q09](mastermind_open_questions.md#mm-q09)/[MM-Q10](mastermind_open_questions.md#mm-q10) |
| [06 — Acceptance](../.docs/PART_06_UNIFIED_ACCEPTANCE_CHECKLIST.md) | Применяется | Семь областей pre-push review и интегрированный DoD |
| [07 — Security](../.docs/PART_07_SECURITY_AND_EXPOSURE_CONTROL.md) | Применяется | Все principals, secrets, capabilities, listeners, CI и untrusted inputs |
| [08 — SEO/GEO](../.docs/PART_08_SEO_AND_GEO.md) | Условно | На текущем scope нет подтверждённой цели поискового продвижения; режим Share вынесен в [MM-Q12](mastermind_open_questions.md#mm-q12). До решения нельзя добавлять discovery публичных заметок |
| [09 — Agents lifecycle](../.docs/PART_09_SERVICE_AGENTS_DEPLOYMENT_AND_LIFECYCLE.md) | Применяется к Updater/Neptune | Требуется согласованный профиль Mastermind; Gryphon не нужен при отсутствии Telegram-функций |
| [10 — Agents UI](../.docs/PART_10_SERVICE_AGENTS_UI_AND_OPERATOR_WORKFLOWS.md) | Применяется к Backup/Updates | Таблицы нового профиля дополняются; Bot connection вне scope |
| [11 — Initial profile](../.docs/PART_11_INITIAL_MULTI_SERVICE_DEPLOYMENT.md) | Справочная и совместимая часть | Не переносить автоматически продуктовые идентификаторы, точные версии и Volt/Saturn recovery semantics на новый сервис |
| [12 — Known problems](../.docs/PART_12_KNOWN_DEPLOYMENT_AND_OPERATIONS_PROBLEMS.md) | Применяется | Каждый active ID оценивается по точной ревизии кандидата |

Эта матрица — начальная классификация. Перед кодом она детализируется по реальным routes, компонентам и проверяемым enforcement points. Нерелевантный пункт получает конкретный N/A с объяснением; открытый применимый контракт не получает N/A.

## 0.2. Версии центральной документации

Документ подготовлен по локальному набору Parts 00–12 на 2026-09-14. Это дата чтения, а не immutable policy revision. До implementation/release gate необходимо закрепить полный commit SHA центрального репозитория и digest Part 12. Неизвестные SHA и production coordinates не подставляются вымышленными значениями.

Ссылки ../.docs/ предназначены для текущего integration workspace. При выделении самостоятельного репозитория они заменяются на ссылки к закреплённой центральной revision либо сопровождаются включённой документацией; release не должен зависеть от соседнего checkout.

---

<a id="section-1"></a>

# 1. Контекст Exocortex

Mastermind — новый персональный knowledge service в Exocortex, рассчитанный на одного владельца.

В integration workspace существуют самостоятельные сервисы Kernel, Volt, Saturn, Neptune, Updater, Gryphon, Chronos и Laboratory. Их фактические production versions, доступность и готовность интеграционных API должны быть зафиксированы в baseline перед реализацией. Этот документ не утверждает факт их успешного deployment.

Роли зависимостей:

- Kernel — discovery, Register и разрешение согласованных ссылок конфигурации.
- Volt — защищённые значения, доступные по принятой модели Kernel/Volt.
- Neptune — единственный транспорт Mastermind к Saturn.
- Saturn — удалённые ресурсы, backup/mirror storage и control plane расписаний.
- Chronos — события и время.
- Updater — разрешённые операции установки, регистрации, обновления и восстановления локального сервиса.

Gryphon не подключается только потому, что существует в Exocortex. Telegram-функции Mastermind в scope не входят.

Mastermind выпускается как самостоятельный сервис: собственный repository/release contract, bootstrap, environment и документация. Core, Runtime и Bridge являются компонентами этого сервиса; наличие нескольких контейнеров не создаёт несколько независимых продуктов.

Multi-tenant SaaS, организации, команды, биллинг и сложная ролевая модель не требуются.

---

<a id="section-2"></a>

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

<a id="section-3"></a>

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

<a id="section-4"></a>

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

<a id="section-5"></a>

# 5. Общая архитектура

~~~text
Browser
  ↓ canonical HTTPS
Server-managed Nginx
  ↓ loopback upstream
Mastermind Core / Web Shell
  ├── owner session → Runtime Gateway → internal KasmVNC → Official Obsidian
  │                                                        ↓ Bridge
  │                                                   Canonical Vault
  ├── Shares / Activity / Search / Graph / Crusher
  ├── internal authenticated API → Chronos
  ├── local authenticated Neptune adapter → neptuned → Saturn
  ├── local typed Updater adapter → host Updater
  └── Kernel / Register → approved secret resolution through Volt
~~~

Core и Obsidian Runtime имеют отдельные process/container boundaries. KasmVNC доступен только через authenticated Runtime Gateway; собственного публичного listener нет.

Core владеет domain semantics и программными записями Canonical Vault. Obsidian непосредственно редактирует тот же Vault. Координация обоих writers обязательна; watcher не считается pre-write lock.

Neptune и Updater — общие host agents, не sidecars Mastermind. Browser не получает agent tokens. Фактические локальные adapters и согласованный профиль фиксируются по [MM-Q04](mastermind_open_questions.md#mm-q04)/[MM-Q05](mastermind_open_questions.md#mm-q05)/[MM-Q10](mastermind_open_questions.md#mm-q10).

Дополнительный изолированный extractor worker допускается как компонент deployment, если этого требует sandbox, но его права не должны включать произвольную запись Vault или доступ к agent sockets. Конкретная изоляция определяется в [MM-Q17](mastermind_open_questions.md#mm-q17).

---

<a id="section-6"></a>

# 6. Deployable units и области полномочий

## 6.1. mastermind-core

Отвечает за HTTP API, Web Shell, Runtime Gateway, watcher, индексы, Graph, Activity, Shares, Crusher orchestration, Chronos/Neptune adapters, backup builder, restore semantics, audit и readiness.

Только Core выполняет программный commit заметок от Shares, Crusher и maintenance. Это не отменяет непосредственные owner edits в Obsidian.

Core не получает Docker socket, sudo, произвольный shell API либо доступ к чужим agent profiles. Host mutations выполняет Updater по allow-listed операциям.

## 6.2. mastermind-obsidian-runtime

Отвечает за официальный Obsidian, Linux graphical session, lightweight window manager, KasmVNC, загрузку Bridge и открытие Canonical Vault.

Runtime получает только необходимые Vault/runtime mounts. Доступ к mastermind.db, provider keys, host agents и чужим данным не предоставляется по факту общей Docker network. Существующие plugins требуют отдельной границы доверия по [MM-Q08](mastermind_open_questions.md#mm-q08).

## 6.3. Единица выпуска

Один Mastermind release описывает Core image, Runtime image, Bridge build, pinned Obsidian version и DB schema compatibility. Оба контейнера могут находиться в одном Compose stack.

Согласованный apply/rollback этого комплекта задаётся отдельным typed Updater profile, а не arbitrary Compose command из web API; см. [MM-Q10](mastermind_open_questions.md#mm-q10).

---

<a id="section-7"></a>

# 7. Сетевые границы и ingress

## 7.1. Публичный ingress

Один server-managed Nginx владеет публичными HTTP(S), WebSocket routing и TLS. Mastermind предоставляет versioned namespaced include либо декларативный upstream contract; installer не устанавливает, не запускает и не reload-ит Nginx.

Core публикует только согласованный host-loopback upstream. Unknown Host/SNI и неизвестные routes отклоняются; SPA fallback не превращает probe path в HTTP 200.

Browser operator Login доступен с любого клиентского IP через canonical HTTPS. Обязательный VPN или OPERATOR_CIDR не вводятся. IP используется для abuse controls, а не вместо аутентификации.

## 7.2. KasmVNC

Runtime не публикует KasmVNC port в Internet. HTTP client и WebSocket Upgrade проходят проверку owner session в Runtime Gateway. Reconnect заново проверяет авторизацию; сохранение graphical session не означает сохранение отозванного browser access.

Trusted proxy headers принимаются только от собственного Nginx. Подробные политики WS lifetime, revocation и clipboard фиксируются по [MM-Q01](mastermind_open_questions.md#mm-q01)/[MM-Q17](mastermind_open_questions.md#mm-q17).

coturn отсутствует: WebRTC NAT traversal не является требованием этого проекта.

## 7.3. Saturn и Neptune

Listing, metadata, read, ranged read, traversal, replication и remote restore выполняются только через Neptune. Прямые Saturn, WebDAV, Storage Box или SFTP credentials в Core/Bridge не добавляются.

Host Neptune API находится за authenticated Unix socket; shared profile и read capabilities должны быть определены до реализации, см. [MM-Q04](mastermind_open_questions.md#mm-q04)/[MM-Q05](mastermind_open_questions.md#mm-q05). Наличие archive uploader не доказывает поддержку Range reader.

## 7.4. Chronos

Chronos вызывается через согласованный authenticated внутренний API. Mastermind не владеет постоянной копией событий. Endpoint, identity, audience, минимальная версия и cache/error schema входят в connection contract.

## 7.5. Route policies

Каждый route/listener получает явную exposure classification по §138. Auth/API, Crusher upload, backup upload/download, media Range и KasmVNC имеют отдельные body, timeout, concurrency и buffering budgets. Лимит 2 GiB для Crusher не становится глобальным лимитом auth/API.

---

<a id="section-8"></a>

# 8. Файловая структура и mounts

Основной layout:
~~~text
/var/lib/mastermind/
├── vault/                  # Canonical Vault
├── state/
│   └── mastermind.db       # authoritative non-note state + derived metadata
├── cache/
│   ├── search/
│   ├── semantic/
│   ├── chronos/
│   └── saturn/
├── crusher/
│   ├── incoming/
│   ├── work/
│   └── failed/
├── backup/
│   └── spool/              # protected, bounded, temporary
├── recovery/
│   └── ...                 # protected staging/transaction recovery
└── runtime/
    └── ...
~~~

Canonical Vault находится по /var/lib/mastermind/vault и доступен read-write Core и Obsidian Runtime. Другие mounts выдаются отдельно по необходимости; Runtime не получает весь родительский каталог только ради удобства restore.

Чтение и запись проверяются от production UID:GID, с реальными mounts, umask и ограничениями. Запрещены обходы через world-writable permissions. Политика общей группы/setgid либо согласованных UID должна предотвращать появление недоступных второму writer файлов.

Удаление cache/ не теряет user data. state/mastermind.db удалять без восстановления нельзя. Backup spool, Crusher staging и recovery snapshots имеют собственные квоты и cleanup lifecycle.

Атомарная замена vault directory не считается достаточным доказательством переключения bind-mounted Runtime. Mount topology, recreation/reconnect и rollback проверяются как единая операция; см. [MM-Q02](mastermind_open_questions.md#mm-q02)/[MM-Q07](mastermind_open_questions.md#mm-q07).

Deployment .env, runtime secrets и release trust находятся за пределами Vault и logical backup. Точный secret-file layout задаётся installer contract.

---

<a id="section-9"></a>

# 9. SQLite state

Используется SQLite в WAL mode, файл /var/lib/mastermind/state/mastermind.db.

Обязательное служебное состояние:

- Activity domain events и незавершённые owner edit sessions, если нужны для crash recovery.
- Share records, access policy, revocation и target lifecycle.
- Crusher sessions и jobs, stage transitions и idempotency/commit records.
- Programmatic write audit с отдельной retention policy.
- Replication outbox, receipts и reconciliation state.
- Leases/job locks и recovery markers.
- Non-secret settings: timezone, Appearance, navigation/card order, validated control-plane endpoint.
- Access Key verifier с KDF parameters; активные browser sessions — только по отдельному session contract.
- Derived index metadata.

Текст .md в SQLite не становится authoritative copy. Derived tables должны быть отличимы от обязательного state при backup и rebuild.

Provider/service keys, raw Bearer tokens и plaintext Access Key в БД не хранятся. Для ephemeral credentials используются hashes/ограниченный lifecycle по соответствующему контракту.

Физический SQLite backup используется для получения согласованного snapshot, но прямой download всей БД не заменяет logical ZIP. Export включает только классифицированные restorable данные и исключает запрещённые/производные поля.

---

<a id="section-10"></a>

# 10. Конфигурация, Register и secrets

## 10.1. Источники и владение

Register хранит согласованные references и metadata, а не открытые provider keys. Значения разрешаются через действующую модель Kernel/Volt. Защищённые bootstrap coordinates и локальные agent credentials передаются установленными механизмами deployment/enrollment.

Должна существовать таблица для каждого поля: owner, authoritative source, initial seed, consumer, classification, rotation, backup class. .env, Register и Settings не конкурируют за одно значение.

Собственный mode-0600 .env содержит отдельные группы:

1. Operator input.
2. Generated secrets.
3. Release lock.
4. Runtime defaults.

Operator Access Key задаётся владельцем; machine secrets генерируются безопасно без вывода. Initial Kernel URL после успешной инициализации становится authenticated server-side setting. Release digests остаются machine-owned.

## 10.2. Обязательные логические настройки

~~~text
mastermind.public_base_url
mastermind.timezone
mastermind.vault_path
mastermind.crusher.provider
mastermind.crusher.text_model
mastermind.crusher.video_model
mastermind.crusher.max_upload_bytes
mastermind.obsidian.version
mastermind.activity.edit_idle_timeout_seconds
~~~

Названия задают логический каталог Mastermind. Их точное размещение и references в Register фиксируются вместе с dependency/secret contract по [MM-Q19](mastermind_open_questions.md#mm-q19); API/endpoint values не угадываются.

Default:
~~~text
mastermind.vault_path = /var/lib/mastermind/vault
mastermind.crusher.provider = gemini
mastermind.crusher.max_upload_bytes = 2147483648
mastermind.activity.edit_idle_timeout_seconds = 300
~~~

Дополнительно требуются typed настройки embedding model, resource budgets, verified release registry и agent profile. Обязательные численные budgets выбираются и проверяются по [MM-Q17](mastermind_open_questions.md#mm-q17); unresolved markers не являются допустимыми runtime defaults.

## 10.3. Secrets

Требуются provider API key и service-scoped credentials для Kernel, Neptune, Chronos и Updater по фактическому connection contract. Bridge получает отдельный узкий authenticated channel, а не provider/agent credentials.

Запрещено сохранять API keys в Vault, .obsidian, Git, mastermind.db, Docker image, browser persistence, logs или logical backup. Источник, получение, обновление и поведение после холодного старта фиксируются в [MM-Q19](mastermind_open_questions.md#mm-q19).

Отсутствие обязательной активной конфигурации даёт NOT_READY. Недоступность уже настроенного внешнего сервиса отражается как DEGRADED по §§89–90/108. Нельзя требовать фиктивные credentials для функций вне выбранного scope.

## 10.4. Runtime Settings

Поддерживаются узкие потоки:

- смена Access Key с текущим proof, двумя новыми exact-match значениями и отзывом остальных сессий;
- validated изменение Kernel URL с сохранением предыдущего при ошибке;
- write-only rotation Kernel token с проверкой до activation.

Это не общий secrets editor. Provider и host secrets управляются своим approved boundary. Current secret никогда не возвращается read API и не prefill-ится в форме.

---

<a id="section-11"></a>

# 11. Импорт существующего Vault

Импорт выполняется перед вводом Canonical Vault в рабочее состояние.

## 11.1. Non-destructive импорт

1. Создать immutable snapshot исходного Vault без изменения оригинала.
2. Составить inventory всех файлов, .md count, total count и SHA-256 manifest.
3. Проверить Unicode NFC/casefold uniqueness basenames, path/symlink policy, readability и потенциально секретное/исполняемое содержимое .obsidian.
4. Скопировать Vault в staging; не смешивать его с уже активным Vault.
5. Повторно проверить SHA-256 каждого файла и counts.
6. Только после byte-identical проверки добавить verified Mastermind Bridge artifact и минимальные явно описанные изменения .obsidian.
7. Зафиксировать отдельный post-install manifest, чтобы изменения Bridge не выдавались за совпадение с оригиналом.
8. В рамках согласованного activation переключить Canonical Vault, открыть его в Runtime и построить индексы.
9. Создать initial Neptune mirror и проверить receipt/remote integrity по утверждённому профилю.

Порядок initial enrollment и первого mirror определяется [MM-Q04](mastermind_open_questions.md#mm-q04)/[MM-Q19](mastermind_open_questions.md#mm-q19). Неуспешная первая replica не должна выдаваться за завершённую acceptance проверку.

Политика найденных plugin secrets, links и несовместимых plugins требует [MM-Q08](mastermind_open_questions.md#mm-q08). Запрещено молча удалить их из исходника, расширить права или назвать секретный byte-identical export безопасным logical backup.

## 11.2. Ссылки не конвертируются

Импорт не заменяет [[Example]] на @Example. Обе формы продолжают существовать параллельно.

---

<a id="section-12"></a>

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

<a id="section-13"></a>

# 13. Mastermind Web Shell

Обязательные основные destinations:
~~~text
Vault
Crusher
Analytics
Shares
Settings
~~~

Documentation и Logout располагаются отдельной ненумерованной группой sidebar. Primary navigation, порядок и Appearance сохраняются server-side и восстанавливаются после нового login.

## 13.1. Vault

Authenticated KasmVNC client открывает настоящий server-side Obsidian. Shell управляет подключением, доступностью и возвратом в сервис. Содержимое Obsidian не переделывается в собственный редактор. Визуальная/a11y граница и fullscreen layout требуют [MM-Q01](mastermind_open_questions.md#mm-q01).

## 13.2. Crusher

Создание access code, jobs, stages, expiry, sanitized ошибки, результат и путь созданной заметки. Принятый job показывается как pending до подтверждённого результата.

## 13.3. Analytics и operational metrics

Knowledge analytics содержит Activity Heatmap, Connectedness, counts notes/internal edges и broken references.

Если view выполняет роль operational Dashboard, он начинается карточками CPU, RAM, Disk, Uptime в порядке Part 01. Выделение отдельного Dashboard либо расположение operational overview согласуется в [MM-Q01](mastermind_open_questions.md#mm-q01); оно не меняет формулу knowledge metrics.

Метрики должны иметь explicit scope. Disk относится к filesystem Canonical Vault и считает доступность через f_bavail; Uptime — monotonic lifetime текущего Core instance, а не хоста. Runtime uptime может отображаться отдельно. Unknown/stale значения не показываются как ноль.

## 13.4. Shares

Список содержит note, permission, password enabled, created_at, expires_at, revoked/target_missing и действия по актуальной policy. Revoke требует custom confirmation.

Выдача/повторное копирование URL определяется [MM-Q13](mastermind_open_questions.md#mm-q13): token_hash не позволяет восстановить исходный token, поэтому UI не должен обещать неподдерживаемое повторное копирование.

## 13.5. Settings

Обязательные полные секции Part 01:

- Appearance: accent preview/Apply/Reset и sidebar mode.
- Security: Access Key, Kernel URL/reachability и write-only token rotation.
- Backup: Create and download snapshot, Restore snapshot, Neptune status/Initialize/Repair.
- Updates: installed release, Updater/Register reachability, verified discovery и explicit Apply.
- Logs: bounded realtime stream и Download archived logs.

Mastermind-specific groups добавляются после обязательных секций. Ordinary settings сохраняются после committed change; общего Save нет, accent имеет отдельный Apply. Ошибка возвращает предыдущее confirmed value.

Automatic archive/mirror schedules и remote commands редактируются в Saturn Synchronization, не в Settings Mastermind.

## 13.6. Documentation

Обычный authenticated view с navigation, full-text search, articles и responsive layout по Part 01 §5.7. Изменённые workflows, limits и recovery instructions обновляются в той же ревизии, что и реализация.

## 13.7. Общий UI

Собственный UI следует palette, typography, cards, command bars, keyboard, overlays, clipboard fallback и responsive правилам Part 01. Search, count и primary action располагаются в одном sticky collection toolbar. Native confirm/alert не используются как готовые product dialogs.

Web UI не предлагает общего редактора provider/host secrets и не возвращает сохранённые секретные значения.

---

<a id="section-14"></a>

# 14. .obsidian и совместимость Vault

Canonical Vault сохраняет стандартную структуру Obsidian: themes/, snippets/, plugins/, appearance.json, community-plugins.json и прочие пользовательские файлы.

Theme/plugin settings не переводятся в закрытый формат Mastermind. Экспортированная копия должна открываться стандартным Obsidian: Markdown, папки, [[...]], темы и snippets работают, Bridge доступен как обычный plugin, @... остаётся читаемым текстом при его отключении.

Нужно различать:

1. Compatibility export Vault для владельца.
2. Dedicated remote mirror по согласованному профилю.
3. Секретно-безопасный logical backup всего Mastermind.

Состав и обработка .obsidian в этих продуктах не считаются автоматически одинаковыми. Credentials и воспроизводимые binaries исключаются из logical backup по Part 03; plugin settings/user data и restoration artifacts классифицируются по [MM-Q08](mastermind_open_questions.md#mm-q08).

Runtime не загружает непроверенный Bridge вместо релизного artifact. Существующие community plugins сохраняются согласно согласованной trust/compatibility policy; нельзя обещать безопасность произвольного plugin только из-за его работы внутри Obsidian.

Экспорт не поддерживает sync обратно в Canonical Vault.

---

<a id="section-15"></a>

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

<a id="section-16"></a>

# 16. Theme compatibility и граница унификации

Внутри Obsidian Mastermind Bridge должен использовать Obsidian CSS variables, native typography/spacing/borders, internal-link classes и текущий accent. Основная theme palette не задаётся literal hex/rgb; допустимы только минимальные fallbacks для отсутствующих переменных.

Требуется совместимость с default light/dark, установленной production community theme и custom snippets. @note и [[note]] должны выглядеть эквивалентно.

Собственный Web Shell, Settings, Documentation и public forms следуют токенам Part 01; настройки Shell не переписывают Obsidian appearance.json без отдельного user action.

Сохранение произвольной темы Obsidian расходится с буквальным применением единой palette ко всем пикселям сервиса. Граница embedded third-party application должна быть согласована в [MM-Q01](mastermind_open_questions.md#mm-q01) и при необходимости отражена в Part 01. До решения этот раздел фиксирует продуктовую потребность, но не заявляет уже одобренное исключение центральной нормы.

---

<a id="section-17"></a>

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

<a id="section-18"></a>

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

<a id="section-19"></a>

# 19. Grammar @note

Требуется поддержка имён с пробелами без обязательных кавычек и без folder-qualified syntax.

Сохранённая базовая семантика:

1. @ может начинать reference после начала файла, whitespace или разделяющей punctuation.
2. Email-like token с непосредственно предшествующим alphanumeric, _, - или . не считается ссылкой.
3. Для существующих заметок выбирается самое длинное совпадающее имя из note dictionary.
4. Example и Example note разрешаются в пользу Example note для соответствующего текста.
5. Fenced/inline code, HTML comments и YAML frontmatter исключаются.
6. Autocomplete — основной путь вставки.

Полная грамматика пока не определена: нужны правила правой границы, escaping, приоритета внешних namespace, Unicode offset mapping и поведения неизвестных/удалённых имён.

Особенно важно: правило «нет существующего совпадения — обычный текст» само по себе не выполняет требование §24 о broken reference после удаления и rebuild. Выбранное решение не должно молча превращать disposable cache в обязательный источник истины.

Эти вопросы рассматриваются совместно в [MM-Q03](mastermind_open_questions.md#mm-q03). До закрытия вопроса нельзя считать parser final или утверждать, что удаление cache сохраняет распознавание deleted references.

---

<a id="section-20"></a>

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

<a id="section-21"></a>

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

<a id="section-22"></a>

# 22. Rename и @note

При rename Old name.md → New name.md все ссылки, которые действительно указывают на переименованную заметку, должны измениться с @Old name на @New name во всём Vault.

Требования:

- Markdown-aware parser, единый контракт с renderer/indexer.
- Не изменять code blocks, inline code, comments, frontmatter и unrelated strings.
- Проверять global basename uniqueness до записи.
- Зафиксировать полный plan и ожидаемые SHA-256 затрагиваемых файлов.
- Координировать writes Core и Obsidian; изменения между plan и commit не перезаписывать.
- Обновить Shares, индекс и replication outbox согласованно с filesystem.
- Каждую программную запись выполнять atomic.
- При сбое иметь проверяемый rollback или durable recovery marker и не сообщать success в partial state.
- Не считать автоматическую propagation за owner EDIT.

Native [[...]] остаются под управлением стандартного механизма Obsidian. Однако rename, начатый API, также должен корректно задействовать этот механизм: нельзя предполагать, что внешний filesystem rename автоматически обновит native links.

Координатор rename/move/delete, Bridge interception и работа при недоступном Runtime определяются [MM-Q02](mastermind_open_questions.md#mm-q02); grammar/affected references — [MM-Q03](mastermind_open_questions.md#mm-q03).

---

<a id="section-23"></a>

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

<a id="section-24"></a>

# 24. DELETE и broken references

Удаление target note не удаляет ссылки из исходных .md. Распознанные ссылки на удалённую note должны иметь broken-link styling и не становиться связями графа.

Поведение должно сохраняться после restart, cache deletion и reindex. Возможность выполнить это без изменения синтаксиса либо без дополнительного обязательного reference state пока не доказана; решение требует [MM-Q03](mastermind_open_questions.md#mm-q03).

Повторное создание заметки с тем же именем/путём не должно неявно решать вопрос identity прежних Shares. Поведение links и Share lifecycle рассматриваются отдельно; см. [MM-Q14](mastermind_open_questions.md#mm-q14).

---

<a id="section-25"></a>

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

<a id="section-26"></a>

# 26. Chronos reference

Форма:

```md
@chronos: t-28572589
```

`target` — opaque Chronos event ID.

Mastermind не должен извлекать семантику из структуры ID.

---

<a id="section-27"></a>

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

<a id="section-28"></a>

# 28. Chronos data ownership

Mastermind не хранит постоянную копию события.

Разрешён краткосрочный cache только для UI.

TTL cache:

```text
30 seconds
```

Chronos остаётся owner event data.

---

<a id="section-29"></a>

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

<a id="section-30"></a>

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

<a id="section-31"></a>

# 31. Saturn autocomplete и parsing

После @saturn: plugin показывает дерево ресурсов через Neptune и scoped owner authorization. Выбор file/folder вставляет полный path от root с /, в том числе обычные пробелы.

Предполагается longest existing path match. Raw reference не переписывается при временной недоступности ресурса.

Правая граница path, неоднозначность с последующим текстом, недоступный metadata cache и восстановление offline placeholder должны быть определены вместе с grammar [MM-Q03](mastermind_open_questions.md#mm-q03) и API [MM-Q05](mastermind_open_questions.md#mm-q05).

Autocomplete не выполняет неограниченный обход всего Saturn при каждом keystroke. Listing имеет pagination, отмену устаревшего запроса, budgets и проверку subtree.

Public Share editor и Crusher submitter не наследуют owner tree autocomplete.

---

<a id="section-32"></a>

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

<a id="section-33"></a>

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

<a id="section-34"></a>

# 34. Saturn streaming

~~~text
Browser Range request
  ↓ scope check
Mastermind stream endpoint
  ↓ bounded ranged request
Neptune
  ↓
Saturn
~~~

Большие объекты не загружаются полностью перед playback и не буферизуются целиком Core. Нужны pass-through streaming, backpressure, cancellation и согласованная обработка Range, MIME, length, upstream errors и partial content.

Browser получает только право на конкретный запрос/объект или разрешённый subtree. Постоянные Neptune/Saturn credentials не передаются.

Share scope проверяется на сервере независимо от переданного path и текущего Markdown, с учётом password session, expiration и revoke. Добавленная public editor ссылка не выдаёт новый grant.

Neptune read API, capability checks, limits и коды ответов определяются [MM-Q05](mastermind_open_questions.md#mm-q05)/[MM-Q11](mastermind_open_questions.md#mm-q11)/[MM-Q17](mastermind_open_questions.md#mm-q17). Nginx buffering/timeouts проверяются на фактическом streaming path.

---

<a id="section-35"></a>

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

<a id="section-36"></a>

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

<a id="section-37"></a>

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

<a id="section-38"></a>

# 38. Mastermind Graph View

Bridge предоставляет собственный Graph View, поскольку native Obsidian Graph не обязан понимать @note.

Он учитывает [[...]] и @..., открывает note по click, поддерживает pan/zoom и internal/external filters, соответствует текущей Obsidian theme в согласованной области [MM-Q01](mastermind_open_questions.md#mm-q01). Native Graph остаётся доступен. Authoritative projection для analytics — Mastermind Graph; отношения восстанавливаются из Canonical Vault и явно классифицированного обязательного state.

Connectedness использует только внутренний undirected graph по §§35–37. Формула property-reuse correlation из Part 01 §8 не применяется к note graph.

Из Part 01 принимаются:

- доступный список/таблица связей и keyboard path к открытию заметки;
- collapsed presentation controls и сохранение validated user presentation settings;
- bounded labels, device-pixel ratio и стоимость hit testing;
- отдельно измеренный render/animation cap;
- worker/приближённый layout при превышении безопасного small-graph threshold;
- отсутствие animation/redraw loop у скрытого/выключенного view;
- cleanup observers/listeners и отсутствие повторной подписки после remount.

Перетаскивание графического узла меняет presentation, не Markdown relations. Derived node keys не превращаются в обязательный UUID/frontmatter заметки. Все user presentation settings, которые обещано восстановить, входят в logical backup.

---

<a id="section-39"></a>

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

<a id="section-40"></a>

# 40. Activity Heatmap

Activity учитывает только действия владельца над заметками:
~~~text
CREATE
EDIT
RENAME
MOVE
~~~

Это обязательные domain data, а не operational logs/security audit. Политика Part 02 для удаления старых diagnostic events не применяется к Activity автоматически.

UTC timestamps и типы действий сохраняются так, чтобы поддерживать смену timezone при query. Aggregation не должна терять обещанную детализацию. Quotas/масштабирование Activity не могут молча удалять пользовательскую историю.

В Web Analytics heatmap использует Shell accent; внутри Obsidian — текущие variables темы в согласованной области [MM-Q01](mastermind_open_questions.md#mm-q01). Формула и уровни §§45–46 сохраняются.

---

<a id="section-41"></a>

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

<a id="section-42"></a>

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

<a id="section-43"></a>

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

<a id="section-44"></a>

# 44. Activity timestamps

В database все timestamps сохраняются в UTC.

Для группировки по дням используется:

```text
mastermind.timezone
```

Смена timezone не переписывает исторические timestamps, а только меняет day grouping при query/render.

---

<a id="section-45"></a>

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

<a id="section-46"></a>

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

<a id="section-47"></a>

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

<a id="section-48"></a>

# 48. Share fields и state

Минимальные поля:
~~~text
share_id
token_hash
target_path
permission
password_hash nullable
created_at
expires_at nullable
revoked_at nullable
~~~

permission имеет значения view или edit. Snapshot mode отсутствует: доступный Share показывает текущее состояние своей note.

Дополнительно требуется durable state для owner-authorized external grants и lifecycle target_missing, если это необходимо выбранным контрактам [MM-Q11](mastermind_open_questions.md#mm-q11)/[MM-Q14](mastermind_open_questions.md#mm-q14). Эти records являются authoritative non-note state и включаются в backup с проверяемой restore policy.

Raw token не сохраняется как обычное поле БД. Требование повторно копировать постоянный URL рассматривается в [MM-Q13](mastermind_open_questions.md#mm-q13): hash не позволяет его восстановить. Хранение token ciphertext, если будет выбрано, потребует отдельного approved secret/key/recovery contract.

share_id не является note_id и не помещается в Markdown.

---

<a id="section-49"></a>

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

<a id="section-50"></a>

# 50. Share expiration

Если `expires_at` отсутствует — ссылка бессрочная.

После expiration или revoke возвращать `HTTP 404`, не раскрывая существование ранее доступного Share.

---

<a id="section-51"></a>

# 51. Share при rename/move

Share сохраняет URL/token при rename/move той же заметки. target_path обновляется в рамках согласованной операции, а не произвольного eventual watcher repair после сообщения success.

Нужно выдержать restart между filesystem rename, обновлением Share, native links, @links и index/outbox maintenance. Координатор и recovery marker определяются [MM-Q02](mastermind_open_questions.md#mm-q02).

Смена имени не выдаёт новые права на external resources. Identity после удаления и повторного создания пути определяется отдельно в [MM-Q14](mastermind_open_questions.md#mm-q14).

---

<a id="section-52"></a>

# 52. Share при delete

Для неистёкшего, неотозванного Share удалённая target note даёт HTTP 410 Gone и target_missing в owner UI.

Expiration/revoke имеют приоритет: такой Share возвращает HTTP 404 независимо от наличия target и не раскрывает прежнее состояние.

Повторное использование имени/пути не должно неявно переопределить, на какую «конкретную заметку» был выдан доступ. Правила tombstone/rebind и последствия restore старых Share records требуют [MM-Q14](mastermind_open_questions.md#mm-q14); до решения нельзя просто оживлять Share при появлении файла по target_path.

---

<a id="section-53"></a>

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

<a id="section-54"></a>

# 54. Internal links внутри Share

[[Other note]] и @Other note отображаются согласованно, но не открывают и не transclude private note. По click показывается нейтральное Linked private note без раскрытия пути или содержимого.

Public visitor не получает owner autocomplete, note listing, backlinks, graph, semantic neighbors или hidden frontmatter других заметок. Renderer не загружает private preview ради выполнения formatting.

Разбор ссылок не должен превращаться в endpoint перебора всего Vault. Доступность других заметок определяется отдельными grants, а не наличием текста ссылки; автоматическое public sharing target запрещено.

---

<a id="section-55"></a>

# 55. Chronos внутри Share

При owner-authorized доступе к конкретному Chronos event Share может показать только start и end. Другие event details и credentials не раскрываются.

Вставка @chronos: ... через public edit сама по себе не выдаёт право прочитать новое событие. Нужен независимый server-side scope, управляемый владельцем; lifecycle grants рассматривается в [MM-Q11](mastermind_open_questions.md#mm-q11).

Недоступность Chronos не ломает заметку и не изменяет raw reference.

---

<a id="section-56"></a>

# 56. Saturn внутри Share

Share может читать только конкретные разрешённые objects или явно разрешённые folder subtrees. Нельзя подняться выше granted root, выйти через path normalization/symlink либо использовать stream endpoint как arbitrary Saturn gateway.

Наличие @saturn: root/path в текущем Markdown НЕ является достаточным доказательством owner authorization: Markdown может быть изменён public editor.

Server проверяет одновременно:

1. Валидность Share, permission и password session.
2. Доступность target note.
3. Независимый owner-authorized resource grant.
4. Принадлежность запрошенного объекта разрешённому subtree.
5. Текущие expiration/revocation условия.

Добавление новой ссылки публичным редактором не расширяет grants. Формирование первоначального scope, изменение после owner edit и отзыв во время streaming определяются [MM-Q11](mastermind_open_questions.md#mm-q11)/[MM-Q05](mastermind_open_questions.md#mm-q05).

Permanent Neptune/Saturn credentials клиенту не выдаются.

---

<a id="section-57"></a>

# 57. Share edit

permission=edit позволяет менять Markdown только target note. Это не разрешение CREATE/RENAME/MOVE/DELETE других заметок, записи .obsidian, изменения Share policy или доступа к owner APIs.

GET возвращает ETag = content SHA-256. Write требует If-Match; при отличающемся current SHA возвращается HTTP 409 Conflict с current content, submitted content и current ETag только этой target note.

UI показывает обе версии и требует ручного merge. Silent overwrite запрещён. Hash check и commit должны быть защищены от одновременного save Obsidian, см. [MM-Q02](mastermind_open_questions.md#mm-q02).

Cookie-authenticated mutations имеют CSRF/Origin protection; authorization проверяется на каждом запросе. Share edit не создаёт owner Activity, но пишет bounded audit event.

Изменение текста не выдаёт новые external grants (§§55–56). Ограничения public editor и точный grant lifecycle согласуются в [MM-Q11](mastermind_open_questions.md#mm-q11).

---

<a id="section-58"></a>

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

<a id="section-59"></a>

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

<a id="section-60"></a>

# 60. Crusher code security

Activation endpoint ограничивает:
~~~text
10 attempts / 10 minutes / IP
30 attempts / 10 minutes globally
~~~

Успешная activation атомарно потребляет code ровно один раз. Concurrent/replayed activation не создаёт дополнительные sessions.

Session token:

- cryptographically random, не менее 256 bits entropy;
- передаётся Bearer;
- raw token не сохраняется в DB, используется hash;
- не попадает в URL, logs, provider context, artifacts или browser persistence.

Codes и tokens не логируются ни до, ни после activation. Редакция секретов централизована.

Эта 6-digit/30-minute модель не является Neptune enrollment: Neptune setup code имеет собственный 15-minute lifecycle и формат по Parts 09–10. В UI и API эти назначения не смешиваются.

---

<a id="section-61"></a>

# 61. Crusher job API и authorization

Минимальные routes:
~~~text
POST /api/v1/crusher/access
POST /api/v1/crusher/sessions
POST /api/v1/crusher/jobs
GET  /api/v1/crusher/jobs/:id
GET  /api/v1/crusher/jobs/:id/result
~~~

POST /access доступен только owner; POST /sessions принимает одноразовый code; POST /jobs требует active Crusher Session.

Каждый job связывается с выдавшим доступ principal/session. Owner видит свои jobs в private UI. Public caller не получает jobs другого session, даже зная ID.

Capability scope должен явно определять допустимые input classes, Saturn sources и видимость результата. Session не является owner login и не даёт доступ к Vault/Neptune autocomplete или произвольным private resources.

Доступ к status/result после session expiry, lifetime accepted upload, допустимость Saturn input и раскрываемый Vault context требуют [MM-Q15](mastermind_open_questions.md#mm-q15). До решения нельзя трактовать короткую submit capability как бессрочный read token.

Повторная отправка одного idempotency key не создаёт дубликат job/заметки. Accepted response сообщает pending/job ID, success — только после durable commit.

---

<a id="section-62"></a>

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

<a id="section-63"></a>

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

<a id="section-64"></a>

# 64. Crusher Acquire

## 64.1. URL

Разрешены только http/https. SSRF policy запрещает localhost, loopback, private/link-local ranges, metadata endpoints, Unix sockets, file://, ftp:// и переходы в запрещённые сети.

Проверяются фактически используемые DNS addresses и каждый redirect; должна быть защита от DNS rebinding, IPv6/alternative representations и переходов через extractor/browser subrequests. Браузерный renderer не получает произвольный доступ к внутренней сети.

Downloaded material — untrusted data. Инструкции из источника не расширяют capabilities extractor или AI pipeline.

## 64.2. Upload

Default max_upload_bytes = 2147483648 (2 GiB). Upload streamится в ограниченный incoming/spool, не удерживается целиком в RAM. Размер повторно проверяется сервером; MIME не принимается на веру.

Нужны total spool quota, concurrent uploads, timeout, reservation/release и очистка прерванных uploads. Limits согласуются на Nginx, API и worker и проверяются совместно с обычными UI запросами; см. [MM-Q17](mastermind_open_questions.md#mm-q17).

Session expiry не отменяет ранее принятый job, но точный момент acceptance для незавершённого upload требует [MM-Q15](mastermind_open_questions.md#mm-q15).

## 64.3. Saturn input

Получение идёт через Neptune и отдельный allowed source scope. Public Crusher Session не авторизует произвольный Saturn path. Правила выдачи scope — [MM-Q15](mastermind_open_questions.md#mm-q15).

---

<a id="section-65"></a>

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

<a id="section-66"></a>

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

<a id="section-67"></a>

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

<a id="section-68"></a>

# 68. PDF

Сначала выполнять deterministic extraction:

- text;
- headings;
- page boundaries;
- document metadata.

Если PDF scanned/image-only, использовать multimodal provider.

Не использовать OCR как первый путь для normal text PDF.

---

<a id="section-69"></a>

# 69. GitRepositoryExtractor

Для public Git repository:

1. Разрешённый http/https URL проходит SSRF policy до network access.
2. Shallow clone depth=1 выполняется в изолированном job directory.
3. Git hooks, произвольные helpers, scripts и исполнение скачанного кода отключены.
4. Submodules/LFS/redirects не обходят сетевую и resource policy; их поддержка явно задаётся extractor profile.
5. .git, бинарные и secret-like files (.env, private keys, credentials, token dumps) не передаются provider.
6. Сначала анализируются README/docs/manifests/top-level tree; source выбирается по релевантности в bounded context.
7. Clone size, file count, object expansion, disk и duration ограничены.
8. Clone удаляется после job по cleanup policy.

Source instructions считаются содержимым для анализа, а не командами для host/agent.

---

<a id="section-70"></a>

# 70. Crusher Understand

Configured provider получает только разрешённый объём normalized source, структуры Vault, релевантных notes, writing rules и ограниченного соседнего контекста.

Structured result:
~~~json
{
  "title": "...",
  "summary": "...",
  "topics": [],
  "entities": [],
  "suggested_links": [],
  "destination_candidates": [],
  "placement_confidence": 0.0
}
~~~

Raw LLM output не считается валидным до schema validation. Предложения модели не являются разрешениями: filesystem paths, links, filename, confidence и policy проверяет Core.

Prompt/source/result не могут заставить pipeline читать произвольный Vault, обращаться к внутреннему URL, выполнять код, раскрывать secrets или менять существующие notes. System writing rules и untrusted source разделяются.

Объём передаваемого private context и его возможное раскрытие public submitter через generated result определяется [MM-Q15](mastermind_open_questions.md#mm-q15). Fallback не должен отправлять весь Vault из-за отсутствия semantic matches.

---

<a id="section-71"></a>

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

<a id="section-72"></a>

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

<a id="section-73"></a>

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

<a id="section-74"></a>

# 74. Crusher metadata footer

В конец созданной note добавляется HTML comment:
~~~md
<!-- mastermind:crusher
job_id: <id>
source_type: <type>
source: <safe-url-or-name>
processed_at: <ISO-8601 UTC>
provider: <provider>
model: <model>
placement_confidence: <0..1>
suggested_destination: <path-or-empty>
-->
~~~

Footer является частью .md и перемещается вместе с note; renderer его не показывает как visible content.

Все значения сериализуются безопасно, без разрыва HTML comment или инъекции дополнительных metadata fields. Source не содержит credentials, Bearer query parameters и private local host paths. Job ID не является capability.

Footer не заменяет durable job/commit record; он может участвовать в проверке отсутствия дубликатов после interruption согласно [MM-Q16](mastermind_open_questions.md#mm-q16).

---

<a id="section-75"></a>

# 75. Crusher retries

Retry разрешён только для transient failures: HTTP 429/5xx, temporary network failure и provider timeout. Validation error, unsupported format и policy rejection не retry.

Сохраняется требование «максимум 3 attempts». Attempt и lease сохраняются durable; process restart не сбрасывает retry budget.

Исходный список backoff 5s / 30s / 120s неоднозначен при трёх total attempts. Точное число retries, интервалы, Retry-After и stage-level accounting требуют [MM-Q18](mastermind_open_questions.md#mm-q18). Пока вопрос открыт, список из трёх задержек не является утверждённым алгоритмом.

Повтор stage не должен дублировать billable/provider operation или filesystem commit без idempotency/reconciliation. Non-transient ошибки завершаются явным FAILED.

---

<a id="section-76"></a>

# 76. Crusher cleanup

После terminal COMPLETED/FAILED:

- temporary uploads удаляются не позднее 24 часов;
- work directory удаляется сразу после успешного commit;
- failed work допустимо хранить до 24 часов для диагностики с restricted access;
- исходник пользователя в Saturn не удаляется;
- committed note остаётся в Canonical Vault.

Active payload нельзя удалять только потому, что истекла submit session. Cleanup учитывает leases, accepted jobs и recovery markers.

После interruption upload reservations и незавершённые temp files освобождаются по bounded TTL. Cleanup не удаляет материал, необходимый незавершённой restore/rollback transaction.

Temporary payloads не включаются в logical backup по умолчанию. Поведение восстановленных non-terminal jobs с отсутствующим source определяется [MM-Q16](mastermind_open_questions.md#mm-q16); backup не может обещать восстановление данных, которых в нём нет.

---

<a id="section-77"></a>

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

<a id="section-78"></a>

# 78. Semantic index

Embeddings используются для Crusher placement и semantic search и являются Derived State. Model/version и индексная схема задаются конфигурацией; при смене модели разрешён explicit reindex.

Privacy invariant: обычное редактирование, поиск и фоновая индексация не отправляют note content внешнему AI provider.

Рекомендуемый путь — локальное вычисление embeddings. Конкретная модель, runtime, память, лицензирование artifacts и quality/performance acceptance требуют [MM-Q20](mastermind_open_questions.md#mm-q20). Внешний embedding API для общего фонового index нельзя включить без отдельного изменения §123.

Удаление semantic cache должно быть восстанавливаемым в согласованных resource/time budgets.

---

<a id="section-79"></a>

# 79. File watcher

Core отслеживает create, modify, rename, move и delete Canonical Vault. Debounce filesystem events — 500 ms.

Watcher инициирует validation, incremental indexes/graph, durable replication outbox, Share target maintenance и cache invalidation. Event replay/reconcile должен переживать пропуски watcher и process restart.

Watcher не является pre-write authorization или достаточной защитой от race:

- он не доказывает, что duplicate filename был отклонён до записи;
- он не делает атомарными filesystem + DB;
- он сам не определяет owner Activity.

При обнаружении конфликтов имён сервис показывает NOT_READY и прекращает программные mutations. Стратегия непосредственных Obsidian writes, атомарной coordination и восстановления определяется [MM-Q02](mastermind_open_questions.md#mm-q02).

Изменение словаря имён может менять parsing других notes при longest match. Indexer должен инвалидировать затронутые references при CREATE/RENAME/DELETE, даже если исходная заметка не была сохранена; см. [MM-Q03](mastermind_open_questions.md#mm-q03) и §103.

---

<a id="section-80"></a>

# 80. Programmatic writes

Crusher, Share и maintenance не используют truncate-in-place:
~~~text
acquire coordinated write boundary
→ verify expected state / reserve unique name
→ write temp in same filesystem
→ fsync temp
→ validate
→ atomic file replacement or no-clobber CREATE
→ fsync parent
→ finalize state/outbox/audit through recovery-aware transaction
~~~

CREATE не должен перезаписать появившийся конкурентно файл. Проверка свободного имени отдельно от rename-over-target этого не гарантирует.

Для batch rename/move и других составных операций требуется durable plan/marker и определённый rollback/recovery; atomically replaced отдельный файл ещё не означает atomic logical operation.

Общая граница с непосредственными writes Obsidian, включая dirty buffers, определяется [MM-Q02](mastermind_open_questions.md#mm-q02). Объявлять операцию безопасной только на основании наличия os.rename запрещено.

---

<a id="section-81"></a>

# 81. Content concurrency

Версионная история заметок не вводится. Программные edits используют expected_sha256; public Share — эквивалентный If-Match.

Current SHA, отличный от expected, даёт HTTP 409 Conflict. Silent overwrite запрещён.

Проверка SHA должна быть связана с commit через координатор, который учитывает все writers. Проверить hash и позже заменить файл без защиты от Obsidian save — недостаточно.

Для multi-file operation учитываются ожидаемые hashes каждого изменяемого файла, а при конфликте не допускается скрытый partial success. Dirty editor buffers после внешней записи также требуют явного поведения. Решение — [MM-Q02](mastermind_open_questions.md#mm-q02).

---

<a id="section-82"></a>

# 82. Activity attribution

Watcher не считает каждое modification событием Activity.

Bridge передаёт owner events отдельным authenticated channel:

- owner Obsidian edit → Activity;
- Crusher write → no Activity;
- public Share edit → no Activity;
- automatic link rewrite → no Activity.

Channel требует event ID/deduplication, bounded retry и проверки principal; public clients не могут подделывать owner Activity. При недоступном Core должно быть определено восстановление незавершённых edit sessions без потери или двойного счёта; часть coordination [MM-Q02](mastermind_open_questions.md#mm-q02).

Programmatic/audit events сохраняются отдельно по retention Part 02. Автоматическая операция может требовать audit, оставаясь исключённой из heatmap.

---

<a id="section-83"></a>

# 83. Replication в Saturn

Изменение Canonical Vault создаёт durable replication intent/outbox. Core определяет, что изменилось; Neptune владеет transport, destination credentials и исполнением согласованного mirror profile.

Продуктовые целевые сроки при включённом healthy continuous mirror:

- intent попадает в queue не позднее 1 секунды;
- нормальная передача стартует не позднее 5 секунд.

Эти сроки не равны подтверждённому RPO и не являются обещанием доставки при outage, disabled/revoked pipeline или превышении capacity.

Neptune outage не блокирует обычное редактирование; состояние DEGRADED, intents сохраняются, retry bounded и автоматический. Queue capacity, coalescing и overflow должны быть определены без молчаливой потери данных.

Continuous mirror, policy owner, disable/revoke semantics и взаимодействие с Saturn desired state требуют [MM-Q06](mastermind_open_questions.md#mm-q06). Core не создаёт вторую независимую schedule authority и не обходит Neptune при failure.

Success определяется receipt/проверенным remote состоянием, а не HTTP acceptance.

---

<a id="section-84"></a>

# 84. Saturn namespaces

Продуктовые логические назначения:
~~~text
root/mastermind/          # dedicated Vault mirror
root/backups/mastermind/  # logical recovery archives
~~~

Это не host paths и не автоматически готовые Neptune/WebDAV routes. Mapping к текущим Saturn logical roots, namespace/deployment identity и permissions фиксируется в профиле [MM-Q04](mastermind_open_questions.md#mm-q04)/[MM-Q05](mastermind_open_questions.md#mm-q05).

Другие deployments/pipelines не должны писать в тот же managed namespace случайно. Archive producer credentials и mirror/read capabilities разделяются.

Используются согласованные Neptune pipelines. Direct-to-Saturn protocol не создаётся.

---

<a id="section-85"></a>

# 85. Состав dedicated replica

Mirror должен позволять восстановить согласованное содержимое Canonical Vault с relative paths, .md, локальными attachments и необходимыми .obsidian settings/themes/snippets.

Saturn resources, на которые только ссылаются @saturn, повторно не копируются.

Mirror и recovery ZIP — разные продукты. Их inventory/exclusions и policy для .obsidian/plugins/credentials должны быть явно согласованы в [MM-Q08](mastermind_open_questions.md#mm-q08). Нельзя одновременно обещать безусловное vault/** и исключение секретов/воспроизводимых artifacts без определения правил.

Verified Bridge artifact и другие воспроизводимые dependencies имеют version/digest metadata и restoration path. Если обещана переносимость plugin artifacts в mirror, это отдельная классифицированная часть профиля.

Neptune не меняет смысл user files и не превращает secondary copy в master.

---

<a id="section-86"></a>

# 86. Полный logical backup Mastermind

Backup является ZIP полного сервиса, а не только резервной копией SQLite. Один logical builder используется manual download, authenticated local export для Neptune и update/rollback handoff.

Обязательные данные:

- Canonical .md, папки, локальные attachments.
- Классифицированное user state .obsidian, themes и snippets.
- Согласованные Share records/policies, Activity и Crusher job records.
- Необходимый operational state/настройки, authentication verifier и разрешённые recovery records.
- Manifest: format/schema/source version, UTC time, scope, replace semantics, component versions, dependency digests и inventory.
- Для каждого member: SHA-256, uncompressed size, record count где применим.

Derived indexes, caches, temporary files, update staging, .env, cookies, raw tokens, plaintext secrets и воспроизводимые binaries исключаются. Active sessions по умолчанию не восстанавливают доступ; session/grant continuity требует явной policy.

SQLite snapshot должен быть consistent (WAL-aware backup mechanism). Из него экспортируются restorable sections; пользователь не скачивает случайный live DB/WAL набор.

Vault и DB относятся к одной проверенной consistency boundary. Алгоритм quiesce/snapshot, состав ZIP, правила plugin artifacts и security continuity требуют [MM-Q07](mastermind_open_questions.md#mm-q07)/[MM-Q08](mastermind_open_questions.md#mm-q08)/[MM-Q14](mastermind_open_questions.md#mm-q14)/[MM-Q16](mastermind_open_questions.md#mm-q16).

Neptune передаёт точные ZIP bytes без распаковки, переименования members, re-encryption или recompression. Получение удалённой копии завершается receipt.

Каждый backup имеет проверяемую совместимость и восстановление в чистой среде. Запрещено называть полный recovery обеспеченным, если сохранён только state или только mirror.

---

<a id="section-87"></a>

# 87. Periodic reconciliation

Целевой интервал integrity reconciliation continuous Vault mirror — 15 минут.

Проверяются file count, size, изменившиеся content hashes/manifests, missing remote files и unexpected remote files в managed namespace. Каноническая локальная версия побеждает при обычном reconciliation.

Интервал и условия запуска должны быть частью согласованной mirror policy Saturn/Neptune, а не конфликтующим local schedule editor. Disable/revoke, outage и backlog semantics — [MM-Q06](mastermind_open_questions.md#mm-q06).

Изменения secondary storage не восстанавливаются в Canonical Vault автоматически. Удаление remote objects допустимо только в собственном namespace по явной mirror policy и с проверкой прав.

Reconciliation не заменяет history backups и не гарантирует независимый failure domain Saturn archive/mirror.

---

<a id="section-88"></a>

# 88. Restore

Restore — только explicit owner/admin operation с custom confirmation. Автоматический startup restore из Saturn запрещён.

Обязательная последовательность:

1. Выбрать source ZIP/согласованный recovery set и авторизовать доступ.
2. Spool с compressed-size limit в private staging.
3. Проверить manifest, source/schema compatibility, allow-listed members, sizes/count/ratio и все digests.
4. Проверить records, paths, unique basenames и readability без live mutation.
5. Получить verified pre-restore snapshot в согласованной consistency boundary.
6. Установить общий write barrier: Core, workers, Shares, Bridge/Obsidian и другие writers.
7. Подготовить DB и filesystem state в staging; записать durable recovery journal.
8. Переключить связанную DB/Vault generation по согласованной commit procedure.
9. Переподключить mounts/Runtime, восстановить verified Bridge/dependencies и перестроить derived indexes.
10. Проверить invariants, counts, local readiness и открытие Vault.
11. Применить session/capability invalidation policy и зафиксировать audit/outcome.
12. Только после успешной проверки освобождать старое state по bounded retention.

До завершения functional verification rollback должен восстановить прежние DB, файлы и runtime relationship. После restart незавершённая restore transaction должна быть распознана и завершена либо откатана, а не объявлена HEALTHY.

При update rollback порядок запуска старого кода и восстановления данных должен соответствовать именно согласованному Mastermind profile. Нельзя копировать product-specific порядок другого сервиса без compatibility test.

Remote mirror без подходящего state backup не считается полным восстановлением сервиса. Restored jobs с потерянными sources, Share revocations и external keys имеют отдельные правила.

Механизм consistency и mount switching — [MM-Q07](mastermind_open_questions.md#mm-q07); размеры/Updater transport — [MM-Q09](mastermind_open_questions.md#mm-q09); security lifecycle — [MM-Q14](mastermind_open_questions.md#mm-q14); jobs — [MM-Q16](mastermind_open_questions.md#mm-q16).

---

<a id="section-89"></a>

# 89. Health endpoints

Обязательны GET /healthz и GET /readyz.

Liveness сообщает, что процесс Core жив, и не возвращает secrets, версии, пути или topology неаутентифицированному caller.

Readiness проверяет SQLite/schema, доступность Canonical Vault, отсутствие duplicate basenames, обязательную конфигурацию, verified Bridge artifact, очередь/workers и отсутствие незавершённой опасной transaction.

Подробное состояние доступно authenticated owner/monitor principal. Public reachability check получает только минимальный status без private diagnostics.

Chronos, Neptune, AI provider и Runtime имеют отдельные component states. Их временная недоступность не должна превращать рабочий Core в restart loop. Core готовность и функциональная готовность всего Mastermind показываются отдельно.

Installer/update gates дополнительно проверяют host-loopback path, declared functional smoke и canonical public HTTPS после настройки ingress. Core liveness не доказывает открытие Vault в Obsidian.

Health schema, freshness и consumer expectations версионируются в integration contract.

---

<a id="section-90"></a>

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

<a id="section-91"></a>

# 91. Logging

Operational JSON logs содержат timestamp, level, service, module, event и request/correlation ID. Для jobs добавляется job_id, для Shares — share_id.

Operational logs, security/write audit, process-manager output и Activity имеют разные назначения и retention. Stdout не является единственным audit trail.

Central recursive redaction выполняется до любого sink. Запрещены passwords, Access Keys, codes, raw tokens, cookies, API keys, decrypted credentials, secret URLs, полное private note content и auth/provisioning request bodies. Токен в /s/<token> маскируется также в Nginx/access/error/trace logs.

Unknown cause/stack остаются null; diagnostics не выдумываются. Один event/context, очереди логов и output tails ограничены.

Базовые пределы Part 02:

- audit: 10000 events, 30 дней, 64 MiB estimated retained payload;
- один JSONL: 5 MiB, 30 дней;
- весь application log directory: 64 MiB, 30 дней;
- ordinary container stream: 3 × 10 MiB;
- chatty auxiliary stream: 2 × 5 MiB;
- web stream: 200 initially, response cap 1000.

Count, age и bytes действуют одновременно. Изменение defaults требует измерения; host journal также ограничивается. Activity автоматически по этим лимитам не удаляется.

Tail/query/export streamятся или spool-ятся; полный log set не загружается в RAM ради последних строк. Очередь имеет overflow policy с counter.

Settings Logs получает cursor-based, ordered, deduplicated realtime stream с bounded DOM и корректным reconnect/hidden-page behavior. Export ZIP содержит manifest.json, events.jsonl, errors.json, README.txt и optional sanitized raw logs, требует owner authorization, audit и private/no-store response.

---

<a id="section-92"></a>

# 92. Audit

Audit фиксирует programmatic CREATE/EDIT/RENAME/MOVE/DELETE, share creation/revoke/policy changes, Crusher jobs/results, restore, replication failures, auth/credential changes, settings/order persistence и accepted agent/update operations.

Рекомендуемые поля по Part 02: event ID, UTC time, severity/outcome, action, actor type/non-secret ID, target type/identifier, summary, correlation ID, transport и bounded error/context.

Audit не является version history и не хранит старые тексты заметок. Исторический note path фиксирует цель на момент действия и сам по себе не требует введения note UUID.

Audit имеет count/age/byte retention; Activity остаётся отдельным domain dataset. Search/read/hover не создают audit success events только ради посещения.

---

<a id="section-93"></a>

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

<a id="section-94"></a>

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

<a id="section-95"></a>

# 95. Crusher sandbox

Downloaded sources, archives, PDF/document parsers, Git repositories, rendered web pages и model output считаются untrusted.

Обязательны:

- private job directory и отдельная ограниченная identity/process boundary;
- no privileged container, Docker socket, sudo или arbitrary host filesystem;
- отсутствие provider/agent secrets у extractor, которому они не нужны;
- отсутствие прямых commit прав в Canonical Vault у untrusted processing;
- запрет исполнения downloaded binaries, scripts, Git hooks и package install steps;
- archive protection от traversal, links, duplicate members и decompression bombs;
- limits CPU/RAM/disk, expansion size/depth/count, duration и concurrency;
- bounded network egress с SSRF enforcement для всех fetch paths.

Job directory сам по себе не доказывает изоляцию. Конкретная container/process/worker topology и budgets требуют [MM-Q17](mastermind_open_questions.md#mm-q17). Если нужен дополнительный заранее развёрнутый worker, его lifecycle задаётся deployment, а не динамическим Docker API из Core.

AI outputs проверяются как данные. Они не задают host command, secret source, доступ к произвольному path или исключение из authorization.

---

<a id="section-96"></a>

# 96. Owner authentication

Сервис single-operator. Login содержит одно поле Access Key и не требует username/email.

Access Key — explicitly supplied opaque exact value. Запрещены специальные min/max length, composition/strength/entropy/ASCII/URL-safe/denylist правила, trimming, normalization, case folding и truncation. Отсутствующее значение означает unconfigured state. Это не отменяет KDF, constant-time verification, transport security, abuse limits и общий bounded request parsing.

После входа используется bounded server-side session и Secure, HttpOnly, SameSite cookie. Все owner routes и Runtime Gateway проверяют session/authorization. Cookie mutations требуют CSRF/Origin protection.

Key rotation требует recent current-key proof, двух точно совпадающих новых значений, atomic verifier change, rotation session state и отзыва остальных активных browser sessions. Secret fields пусты при первом open/reset, не prefill-ятся текущим значением.

Neptune/Updater/Chronos/Bridge используют отдельные service-scoped identities. Один owner не означает один универсальный токен для всех principals.

Public Share и Crusher endpoints работают по собственным capabilities; owner Access Key не передаётся этим посетителям или AI provider.

---

<a id="section-97"></a>

# 97. API versioning

Все программные API:

```text
/api/v1/...
```

Breaking changes требуют `/api/v2`.

---

<a id="section-98"></a>

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

## Дополнительные обязательные API families

Кроме перечисленного domain API должны быть versioned contracts для:

- owner login/logout/session и Access Key rotation;
- non-secret Settings и write-only control-plane token rotation;
- protected system/component status и telemetry;
- manual logical ZIP create/download;
- restore inspect/apply/job status;
- authenticated local archive export для Neptune/Updater;
- Neptune status/initialize/repair и durable operation status;
- verified release discovery/apply/job status;
- bounded logs stream/page и ZIP export.

Точные paths/schemas должны быть перечислены в docs/api.md и route registry. Agent/export endpoints не получают публичный ingress по факту общего префикса. Прокси к Updater не принимает arbitrary URL, image, command, чужой service/profile или неограниченный host path.

Набор выше не означает, что POST /crusher/sessions и capability-protected job routes требуют owner session: их собственные правила §§59–61 имеют приоритет. Схемы интеграционных families зависят от [MM-Q04](mastermind_open_questions.md#mm-q04)/[MM-Q05](mastermind_open_questions.md#mm-q05)/[MM-Q10](mastermind_open_questions.md#mm-q10)/[MM-Q19](mastermind_open_questions.md#mm-q19).

---

<a id="section-99"></a>

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

<a id="section-100"></a>

# 100. Rename API

Request:
~~~json
{
  "new_name": "New example"
}
~~~

Server проверяет uniqueness и input policy, получает snapshot/hash plan, координирует native и @ references, переименовывает файл, обновляет Shares, indexes и outbox и только после согласованного результата возвращает success.

При изменившемся expected state — conflict, при partial failure — durable recovery и явный error/recovery status, без silent success.

Endpoint не должен работать по принципу «rename сейчас, Obsidian когда-нибудь перепишет native links». Native propagation, dirty editor buffers и доступность Runtime определяются [MM-Q02](mastermind_open_questions.md#mm-q02).

---

<a id="section-101"></a>

# 101. Delete semantics

Delete через Mastermind UI/API должен требовать explicit confirmation.

Физическое поведение:

- note перемещается в Obsidian-configured trash behavior, если оно включено;
- иначе используется managed trash Mastermind.

Hard delete отдельной API operation в первой реализации не требуется.

---

<a id="section-102"></a>

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

<a id="section-103"></a>

# 103. Incremental indexing

На save одной note выполняются reparse, update outgoing/backlinks, FTS row, graph counters и semantic content fingerprint. Embedding пересчитывается только при meaningful change и в рамках privacy §123.

Полный reindex на каждый keystroke/save запрещён. UI не блокируется полным graph recompute.

Dictionary-based @ parser создаёт дополнительную зависимость: CREATE/RENAME/DELETE note name может изменить longest match в других неизменённых notes. Нужен индекс lexical dependencies или другой доказанный механизм invalidation; нельзя обновлять только файл, имя которого изменилось.

Cache rebuild должен воспроизводить те же refs, broken states и counters. Семантика [MM-Q03](mastermind_open_questions.md#mm-q03) задаёт acceptance fixtures. Admin full reindex остаётся доступен.

---

<a id="section-104"></a>

# 104. Startup sequence

Core:

1. Load validated config/secret references без вывода values.
2. Открыть SQLite и проверить незавершённые recovery/migration/write markers.
3. Создать consistent pre-migration snapshot и выполнить migrations безопасно.
4. Проверить Vault path, permissions от runtime UID и uniqueness.
5. Проверить Bridge artifact/version/digest по release manifest.
6. Запустить watcher и восстановить лёгкие indexes.
7. Reconcile leases/jobs/outbox без duplicate commit.
8. Запустить workers и объявить local readiness.
9. Отдельно сообщить Runtime, Neptune, Chronos и provider states.

Runtime:

1. Дождаться правильного Canonical Vault mount и согласованного разрешения старта.
2. Проверить Bridge artifact без запуска произвольного build из Vault.
3. Запустить graphical session и KasmVNC.
4. Запустить pinned official Obsidian, открыть Canonical Vault.
5. Подтвердить Bridge/channel и supervised process.
6. При reconnect сохранить ту же owner graphical session.

При незавершённом restore/rename нельзя запустить writers поверх partial state. Core и Runtime не должны образовать циклический readiness wait. Порядок cold start, dependencies и mode при недоступном Register/Volt фиксируются в [MM-Q19](mastermind_open_questions.md#mm-q19).

---

<a id="section-105"></a>

# 105. Mastermind, Obsidian и Updater

Updater устанавливает проверенный Mastermind release как согласованный комплект Core image, Runtime image, Obsidian version, Bridge artifact и DB schema.

Обновление:

1. Owner запускает verified discovery; оно не начинает install.
2. UI показывает compatibility, backup readiness и explicit Apply.
3. Core формирует fresh verified logical backup.
4. Typed Updater profile независимо разрешает approved release по версии.
5. Проверяются signature, digests, component roles и минимальные версии.
6. Все artifacts загружаются до runtime mutation.
7. Устанавливается write barrier и выполняется согласованный apply.
8. Проверяются Core, Runtime, Vault open и Bridge functionality.
9. Только после functional health update получает COMPLETED.
10. Failure запускает rollback комплекта и state по утверждённому профилю.

Прямая бесконтрольная self-update Obsidian не допускается в production workflow; техническая возможность отключения проверяется на pinned версии. Binary не patch-ится и не хранится в source repository.

Obsidian version меняется после staging compatibility suite. Core release не может silently оставить несовместимый Bridge в .obsidian.

Updater group profile/Compose evolution — [MM-Q10](mastermind_open_questions.md#mm-q10); large backup handoff — [MM-Q09](mastermind_open_questions.md#mm-q09); supported versions/source verification — [MM-Q19](mastermind_open_questions.md#mm-q19). Без их проверки pin версии сам по себе не доказывает безопасное обновление.

---

<a id="section-106"></a>

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

<a id="section-107"></a>

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

Compatibility export не является автоматически тем же ZIP, который используется для service restore. Состав artifacts и handling пользовательских plugins/secrets проверяются по [MM-Q08](mastermind_open_questions.md#mm-q08). Тест не допускает незаметной зависимости export copy от host-only credentials или абсолютных путей сервера.

---

<a id="section-108"></a>

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

<a id="section-109"></a>

# 109. No hidden destructive repair

Mastermind не должен автоматически:

- удалять broken links;
- переименовывать user notes из-за semantic guess;
- перемещать existing notes по AI;
- восстанавливать Canonical Vault из Saturn без команды;
- переписывать весь Vault при parser upgrade.

Любая bulk mutation выполняется через explicit admin operation с dry-run report.

---

<a id="section-110"></a>

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

<a id="section-111"></a>

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

Дополнительно doctor проверяет согласованность release/Bridge, scoped agent enrollment, recovery markers, spool capacity, фактические mount identities и доступ production UID. Отдельно выводятся live, ready, dependency и edge verification; unknown не заменяется нулём/HEALTHY. Raw secret values и полные note bodies в отчёт не попадают.

---

<a id="section-112"></a>

# 112. Database migrations

Миграции versioned и forward-only в обычном deploy. Перед migration создаётся проверенный consistent DB/state backup, необходимый для восстановления поддерживаемой предыдущей версии.

Failure не запускает сервис с partial schema. Незавершённая migration распознаётся после restart.

Совместимость old/new Core, Bridge, Runtime и schema описывается в release manifest. Rollback не обязан быть down-migration: он может восстановить verified pre-update logical state по согласованной процедуре [MM-Q10](mastermind_open_questions.md#mm-q10).

Изменение persisted field требует backup classification, schema/export/import updates и round-trip tests по Part 03. Derived cache migration не должна стать обязательной причиной потери пользовательского state.

---

<a id="section-113"></a>

# 113. Testing strategy

Обязательны:

- unit tests;
- integration tests;
- end-to-end tests;
- recovery tests;
- compatibility tests.

Дополнительно обязательны deployment/packaging tests, signed-artifact/trust checks, restore/update fault injection, owner/capability boundary tests, visual/accessibility checks и resource-bound tests. Test matrix связывает требование с config default, runtime enforcement, UI/docs и reproducible evidence.

Предположения о внешних production endpoints помечаются NOT_RUN/UNKNOWN до проверки, а не PASS. Цена проверки сама по себе не является N/A.

---

<a id="section-114"></a>

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

Дополнительно покрыть exact Access Key preservation, recursive secret redaction, independent Share resource grants, grant non-escalation при public edit, filename no-clobber, idempotency/lease budget, dictionary invalidation и правила parser, выбранные в [MM-Q03](mastermind_open_questions.md#mm-q03).

---

<a id="section-115"></a>

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

Дополнительные обязательные сценарии:

18. Share edit добавляет внешний path/event → дополнительных read permissions не возникает.
19. Public Crusher caller не читает чужие jobs, private sources или owner search context.
20. Конкурентные Obsidian save и API write не теряют изменения.
21. API rename корректно координирует native [[...]] и @ references.
22. CREATE более длинного имени инвалидирует зависимые parsed references.
23. Worker crash после commit не создаёт вторую Crusher note.
24. Agent accepted job остаётся pending до terminal result и refreshed observed state.
25. Restore переключает оба container views на правильный Vault и согласованную БД.
26. Обновление key/token действительно применяется в consumer после atomic secret replacement.

---

<a id="section-116"></a>

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

<a id="section-117"></a>

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

<a id="section-118"></a>

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

Для собственного Shell дополнительно проверяются reference desktop 1919x1034 и 1920x1080, sidebar open/hidden, narrow viewport, keyboard/focus/reduced-motion, clipboard rejection/manual fallback и reconnect.

Для embedded Obsidian не выдавать наличие VNC-картинки за доказанную screen-reader/mobile accessibility. Поддерживаемая область и критерии фиксируются в [MM-Q01](mastermind_open_questions.md#mm-q01). Невыполненный обязательный сценарий отражается в evidence явно.

---

<a id="section-119"></a>

# 119. Backup/restore acceptance test

1. Создать representative Vault с notes, локальными attachments, themes/snippets и согласованными plugins.
2. Создать owner settings, Activity, Shares/grants/revocations и Crusher job records.
3. Проверить оба Neptune pipelines и дождаться подтверждённого mirror.
4. Создать full logical ZIP через тот же builder, что обслуживает manual/agent/update export.
5. Проверить manifest, digests, limits и отсутствие тестовых plaintext secrets/tokens.
6. В изолированной чистой среде восстановить всё объявленное authoritative state.
7. Сравнить .md bytes, structure, .obsidian data, Settings, Activity, Shares и jobs.
8. Проверить session/grant lifecycle, external dependency preconditions и Bridge reconstruction.
9. Перестроить cache, открыть Vault официальным Obsidian, проверить references.
10. Повторить restore поверх существующего state.
11. Проверить corrupted/missing/unknown/oversized archive и отсутствие live mutation.
12. Прервать процедуру на DB/filesystem/mount boundaries, перезапустить и проверить rollback/recovery.
13. Измерить RAM/temp disk, actual archive size, pause duration и RPO/RTO.
14. Повторить для oldest supported backup format и update rollback profile.

Простой restore только файлов либо только БД не закрывает acceptance. Данные и jobs, исключённые из archive, должны иметь явно проверенное восстановление/terminal failure поведение по [MM-Q16](mastermind_open_questions.md#mm-q16).

---

<a id="section-120"></a>

# 120. Observability в UI

Settings/Status показывает:
~~~text
Core            HEALTHY / DEGRADED / NOT_READY
Obsidian        process / Vault / Bridge / session status
Chronos         configured / reachable / unavailable / stale
Neptune         absent / unlinked / initializing / linked / partial / offline / failed
Vault mirror    enabled state / last receipt / lag / backlog
Recovery ZIP    last successful artifact / next due / overdue
Index           status / generation / rebuild state
Crusher worker  status / queue / leases / capacity
Updater         reachability / installed release / active job
~~~

Словари component-specific state не заменяются произвольным общим «Connected». Accepted/queued не означает completed. Данные имеют freshness и время последнего успеха.

Operational Dashboard, если выделен, начинает с CPU/RAM/Disk/Uptime по Part 01; источник и scope метрик явные. Скрывать backlog/unknown через нулевое значение запрещено.

Secret values, raw tokens, host credentials и private topology не доступны public health/capability visitors.

---

<a id="section-121"></a>

# 121. Error presentation

Ошибки пользовательского UI должны содержать:

- понятное сообщение;
- short error code;
- retry, если операция retryable;
- request/job ID для логов.

Не показывать raw stack trace пользователю.

---

<a id="section-122"></a>

# 122. Deletion of derived data

Удаление cache/ и запуск mastermind reindex должны восстановить derived functionality без service backup.

Из этого не следует разрешение удалить SQLite domain state. Reference memory, grants, settings или recovery markers нельзя назвать cache, если без них изменяется поведение.

Проверка включает FTS, graph, semantic cache, Chronos/Saturn UI cache и выбранную broken-link semantics [MM-Q03](mastermind_open_questions.md#mm-q03). Embeddings восстанавливаются без несогласованной отправки notes внешнему provider.

---

<a id="section-123"></a>

# 123. Privacy

Обычные edit, graph, search, Share rendering, Activity и background indexing не отправляют note content внешним AI services.

Только явно авторизованные Crusher AI operations могут передавать normalized source и минимально необходимый Vault context configured provider. Context ограничивается policy; full Vault dump не является fallback.

Public Crusher capability не подразумевает разрешение раскрывать приватный соседний контекст в job output. Правила результата и permitted sources определяются [MM-Q15](mastermind_open_questions.md#mm-q15).

Semantic index по умолчанию должен соблюдать локальную privacy boundary; выбор реализации требует [MM-Q20](mastermind_open_questions.md#mm-q20). Подключение remote embeddings для обычной индексации потребует отдельного изменения этого контракта.

Logs, diagnostics, public metadata и AI footer не раскрывают secrets или private note bodies. Произвольные community plugins могут иметь собственный network behavior; поддерживаемая trust/privacy policy Vault определяется [MM-Q08](mastermind_open_questions.md#mm-q08) и не подменяется обещанием Core.

---

<a id="section-124"></a>

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

<a id="section-125"></a>

# 125. Технологические ограничения

Core следует применимому backend standard самостоятельного проекта. При отсутствии обязательного другого стандарта сохраняется Python 3.12+ / FastAPI. Наличие polyglot соседних сервисов не требует переписывать этот выбор. Bridge — TypeScript.

SQLite в WAL mode обязателен для local state на текущем масштабе. FTS5 — для search; derived embeddings — без отдельного обязательного graph DB/Elasticsearch.

Внешний broker не вводится. Crusher, Core outbox и background jobs используют persistent SQLite-backed queues с transactional claim и leases. Это не заменяет собственный transport journal Neptune и не создаёт второй agent.

Toolchains/dependencies/images фиксируются воспроизводимо. Cross-repository dependencies потребляются из verified immutable release assets, не из sibling source directories.

Дополнительная sandbox process/container boundary допускается по [MM-Q17](mastermind_open_questions.md#mm-q17); это не основание добавить Kafka, Kubernetes либо новую платформу orchestration.

---

<a id="section-126"></a>

# 126. Persistent job semantics

Job state включает:
~~~text
status
leased_by
lease_expires_at
attempt
~~~

Claim транзакционный; lease истекает после worker death. Повторный worker может продолжить согласованный stage после проверки уже выполненного side effect.

Обязательны stable job/idempotency key, bounded attempts, stage timestamps и reconciliation. Lease не гарантирует exactly-once commit сам по себе.

Применяется к Crusher, Core replication/outbox и background reindex. Neptune использует собственный transport receipt/journal по profile.

После restart незавершённый job не теряется и не остаётся бесконечно ambiguous. После disaster restore наличие job record не означает наличие исключённого temporary source; policy resume/fail/resubmit определяется [MM-Q16](mastermind_open_questions.md#mm-q16).

Обновление и host mutations используют отдельные durable jobs Updater с его state vocabulary. Они не смешиваются с Crusher pipeline enum.

---

<a id="section-127"></a>

# 127. Документация и review artifacts

В самостоятельном репозитории должны существовать:
~~~text
README.md
docs/architecture.md
docs/deployment.md
docs/operations.md
docs/backup-restore.md
docs/mastermind-bridge.md
docs/crusher.md
docs/sharing.md
docs/api.md
docs/security.md
docs/releases.md
docs/compatibility.md
~~~

Дополнительно:

- versioned source встроенного Documentation view и search/navigation metadata;
- applicability matrix и baseline evidence;
- resolved/open decision register;
- exposure/connection/secret ownership matrix;
- backup inventory/classification;
- requirement → enforcement → test verification matrix;
- pre-push impact record и known-problems release evidence.

Расположение вспомогательных records задаётся проектом, но содержание обязательно. README не заменяет подробные документы, а technical docs не заменяют operator Documentation.

Центральные ссылки в isolated checkout должны разрешаться без соседних directories. Перед push обновляются affected service docs и root README, если изменились workspace-wide facts.

---

<a id="section-128"></a>

# 128. README minimum

README должен содержать:

- что такое Mastermind;
- архитектурную схему;
- dependencies;
- quick deployment;
- health check;
- ссылки на подробные документы.

---

<a id="section-129"></a>

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

Дополнительно описать Access Key/control-plane token rotation, Initialize/Repair двух Neptune pipelines, capability revoke, full ZIP create/download/inspect/restore, interrupted transaction, mount/UID failures, spool exhaustion, verified update и rollback/rollback failure.

Runbook отделяет установку агента, enrollment и successful artifact. Diagnostic commands не раскрывают secrets и не требуют arbitrary root доступа Core.

---

<a id="section-130"></a>

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

## Общесистемная готовность

- [ ] Матрица применимости и baseline завершены; открытые решения затронутого scope закрыты с evidence.
- [ ] Для embedded Obsidian зафиксирована граница Part 01, без фиктивной visual/a11y совместимости.
- [ ] Shell/Login/Settings/Documentation реализуют общие UI requirements.
- [ ] Access Key parity, session/CSRF и write-only credential rotation проверены.
- [ ] Shared agents имеют точный Mastermind profile; archive и mirror подтверждены отдельно.
- [ ] Neptune read/Range/subtree contract реализован и проверен против реального совместимого сервиса.
- [ ] Public edits/submissions не расширяют external permissions и не раскрывают private context.
- [ ] Full logical ZIP согласован по Vault/DB, без forbidden content; clean restore и interrupted rollback проверены.
- [ ] Large backup handoff и multi-component update проходят functional health/rollback.
- [ ] Production mounts/UID, Nginx ingress, route limits и external-negative checks проверены.
- [ ] Logs bounded/redacted, Activity не обрезается retention operational audit.
- [ ] Exact candidate artifacts signed, digest-pinned и проверены installer.
- [ ] Семь областей pre-push gate имеют корректные PASS/N/A; security всегда PASS.
- [ ] Каждый active Part 12 ID имеет revision-bound evidence, known-problems-report.json полон.
- [ ] Production-only NOT_RUN не выдан за PASS.
- [ ] MM-Qxx рекомендации не представлены в документах как решения без записи принятого варианта.

Эти пункты добавляются к продуктовым acceptance criteria выше. Сам факт создания этого документа не закрывает ни один runtime checkbox.

---

<a id="section-131"></a>

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

<a id="section-132"></a>

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

<a id="section-133"></a>

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

Эта сводка описывает целевую модель. Готовность к реализации отдельных спорных блоков определяется реестром MM-Qxx, а соответствие общим требованиям — §§134–145. Исходные ограничения не оправдывают обход agent, secret, backup или ingress contracts.

---

<a id="section-134"></a>

# 134. Bootstrap и самостоятельный release contract

Mastermind имеет собственные bootstrap.sh, installer/wrapper, deployment directory, mode-0600 .env, signing key и release lifecycle.

Первый releasable version — 0.0.1. Plain v0.0.1 запускает только verification CI. Только точный mastermind-vMAJOR.MINOR.PATCH может запускать protected release publication. PR/default-branch CI не получает release secrets.

Bootstrap загружается из exact immutable qualified release, не из main/latest. Встроенный public signing key создаёт /etc/exocortex/release-trust/mastermind.pem; existing mismatching key не заменяется молча.

Порядок:

1. Operator готовит host/OS/network.
2. Bootstrap проверяет platform, embedded trust, signed manifest, role/version, allowed artifact source и digests до распаковки.
3. Подготавливает только Mastermind, собственный env и локальный installer в prepare mode.
4. Печатает точный путь operator inputs и команду продолжения без secret values.
5. После operator input installer проверяет env/release locks, pulls exact images и validate Compose.
6. Устанавливает либо переиспользует host Updater и регистрирует только Mastermind profile.
7. Запускает сервис с least privilege и bounded health timeout.
8. После успешного local status/loopback health operator настраивает host Nginx, выполняет nginx -t и проверяет canonical HTTPS извне.

Повторный bootstrap не перезаписывает существующую установку; update/refresh/repair — отдельные явные paths. Cross-project dependencies не читаются из соседнего .env/checkout.

Release lock перечисляет точные Core/Runtime digests и Bridge digest. Изменение Compose topology имеет собственный installation/repair/update contract по [MM-Q10](mastermind_open_questions.md#mm-q10).

---

<a id="section-135"></a>

# 135. Ingress, Runtime Gateway и browser boundaries

Server Nginx — единственный public ingress. Core реализует authenticated proxy logic для KasmVNC без embedded Nginx/Caddy. Runtime, DB и host control APIs не получают direct public ports.

Версионируемый include описывает:

- canonical Host/SNI и доверенные forwarded headers;
- route-specific body/header/URI/multipart limits;
- WebSocket Upgrade, reconnect/timeouts и origin validation;
- buffering/backpressure для upload, logs/backup downloads и media Range;
- protected/local-only export/control routes;
- security/cache/robots policy;
- token redaction в access/error logs.

Runtime Gateway проверяет owner identity и не принимает public Share/Crusher token за owner session. Logout/revoke прекращает возможность нового доступа; режим завершения уже открытого WS определяется [MM-Q01](mastermind_open_questions.md#mm-q01).

Same-origin UI применяется там, где требуется safe downloads/session handling. Cross-origin exceptions имеют конкретные CORS/frame rules, а не wildcard.

Public renderer не загружает unsafe HTML/SVG/iframes и не делает arbitrary URL fetch от лица владельца. Внешние URL, referrals, previews и third-party requests не должны раскрывать Share token; применяется подходящий Referrer-Policy и минимальный asset/network profile по [MM-Q11](mastermind_open_questions.md#mm-q11)/[MM-Q12](mastermind_open_questions.md#mm-q12).

Обязательны проверки через реальный proxy: Host, Origin, cookies, CSRF, auth rejection, unknown paths, 413, Range, long upload и WS reconnect. Health внутри Docker network не заменяет эти проверки.

---

<a id="section-136"></a>

# 136. Матрица данных, principals и secret ownership

| Principal/data | Полномочия/владение | Хранение и backup |
| --- | --- | --- |
| Owner | Управляет одним Mastermind | Salted Access Key verifier; hash/parameters — logical state |
| Owner browser session | Только разрешённые owner routes | Bounded session state, no plaintext credentials, revalidate/invalidate после restore |
| Bridge | Owner events и согласованные Vault operations | Узкий channel; credential не в .obsidian/export; mechanism [MM-Q19](mastermind_open_questions.md#mm-q19) |
| Core | Notes commit, domain state, grant checks | Vault + SQLite, classified logical ZIP |
| Runtime/community plugins | Непосредственная работа с Vault | Только нужные mounts; trust/privacy policy [MM-Q08](mastermind_open_questions.md#mm-q08) |
| Crusher submitter | Только выданный submission/result scope | Session hash/expiry и job ownership; policy [MM-Q15](mastermind_open_questions.md#mm-q15) |
| Share visitor | Одна note и отдельные external grants | Share hash/policy; нельзя расширить scope текстом |
| AI provider | Только разрешённый source/context явного Crusher job | Provider key через approved secret boundary; note context не логируется |
| Neptune | Transport archive/mirror/read по профилю | Host scoped credentials/journal; Core не экспортирует host-wide secrets |
| Updater | Typed privileged operations только своего head | Root-owned profile/control token; Core не получает Docker socket |
| Kernel/Register | References, discovery, validated policy | Resolved secret values не сохраняются как plain Register data |
| Volt | Защищённые значения в утверждённой модели | Отдельный lifecycle, не копируется в Mastermind backup открытым текстом |
| Release CI | Подписывает Mastermind manifest | Private signing key только protected GitHub Secrets |

Каждая связь документирует issuer, audience, holder, scope, rotation, revoke, endpoint/version и error behavior. Root-owned host-wide recovery не предоставляется Mastermind только потому, что аналогичный механизм существует у Saturn.

Configuration changes активируются atomic после validation; consumer должен реально перечитать credential. Проверка файла на host без authenticated request из consumer не доказывает успешную rotation.

---

<a id="section-137"></a>

# 137. Backup inventory и compatibility contract

| Данные | Класс | Обязательное поведение |
| --- | --- | --- |
| .md и локальные пользовательские attachments | Mandatory | Сохранить bytes, paths, manifests и восстановить согласованно с DB |
| .obsidian settings, themes, snippets, user plugin data | Mandatory/conditional по inventory | Нельзя молча потерять; secrets/artifacts требуют [MM-Q08](mastermind_open_questions.md#mm-q08) |
| Bridge/reproducible dependencies | Derived/reconstructible | Version/digest/trusted retrieval; не включать build output в logical ZIP без центрального решения |
| Activity | Mandatory domain state | Retention audit не применяется; round-trip UTC/type/timezone behavior |
| Shares, grants, lifecycle | Mandatory | Restore security/identity semantics [MM-Q11](mastermind_open_questions.md#mm-q11)/[MM-Q14](mastermind_open_questions.md#mm-q14) |
| Crusher jobs/transitions/commit records | Mandatory | Не обещать наличие исключённых payloads; recovery [MM-Q16](mastermind_open_questions.md#mm-q16) |
| Settings и presentation order | Mandatory | Применяются после restore, не только перечисляются в manifest |
| Access Key verifier | Mandatory для continuity | Hash/KDF parameters; raw key не экспортируется |
| Active sessions/codes/leases | Conditional/ephemeral | Invalidate, expire либо revalidate по явной policy; no raw token export |
| FTS/graph/embedding/UI caches | Derived | Документированный и протестированный rebuild |
| Operational audit/logs | Conditional diagnostics | Retention/redaction, явная optional restore semantics |
| .env, cookies, raw credentials/private keys | Forbidden | Отдельный secret recovery; отсутствуют в logical ZIP |
| Temporary uploads/work/update staging | Forbidden в обычном logical ZIP | Bounded lifecycle; job recovery не зависит от обещанного отсутствующего payload |
| Host agent state | Вне scope обычного Mastermind ZIP | Восстанавливается approved host-agent procedure, не чужим head |

Manifest member names allow-listed, paths безопасны, duplicates/links/traversal/unknown schema отклоняются. Bounds включают compressed/uncompressed/per-member size, count и compression ratio.

Backup через trust boundary требует authenticated signature/encryption contract; checksum не является подтверждением автора. Legacy ZIP password не применяется. Confidential archive доступен только авторизованным principals.

Нужно явно документировать restore replace semantics, поддерживаемые source formats, external key dependencies, missing dependency behavior и recovery order. RPO/RTO/size budgets — [MM-Q07](mastermind_open_questions.md#mm-q07)/[MM-Q09](mastermind_open_questions.md#mm-q09).

---

<a id="section-138"></a>

# 138. Exposure registry и применимость SEO/GEO

Каждый route/listener классифицируется в versioned registry до production publication.

| Surface | Целевая категория/граница |
| --- | --- |
| Login и owner browser origin | Public authenticated / non-indexable; доступность с любого IP, no owner data до auth |
| Owner APIs, Settings, Analytics, Documentation | Application-authenticated routes того же origin; no-store/non-indexable |
| KasmVNC raw listener | Internal private; только Gateway, без direct public ingress |
| Neptune/Updater controls и internal export | Private local identity/socket/approved network; не public capability |
| Public Share | Capability-protected surface; indexing policy [MM-Q12](mastermind_open_questions.md#mm-q12), content scope [MM-Q11](mastermind_open_questions.md#mm-q11) |
| Crusher activation/submission/results | Public capability endpoints по §61; no owner access |
| Health reachability | Минимальный bounded public ответ; detailed readiness/metrics protected |
| Debug/OpenAPI/source maps/internal manifests | Не публикуются либо явно protected согласно назначению |

До решения [MM-Q12](mastermind_open_questions.md#mm-q12) нет разрешения публиковать Shares в sitemap/feed/llms.txt или каталогах. Noindex/robots не являются access control, а possession token не означает согласие на searchable publication.

Bot decisions и headers/edge policy происходят из одного versioned registry. Spoofed User-Agent/verification headers не дают privilege. Нельзя использовать prompt injection/hostile content как crawler defense.

Если включается отдельный public/indexable mode, Part 08 применяется полностью к этому scope: first-response HTML, canonical, lifecycle, discovery, structured data, performance и SEO release diff. Скрытые note IDs/paths/capability URLs не включаются в публичные metadata.

Reclassification — явное изменение policy с central impact review, а не побочный эффект добавления меню.

---

<a id="section-139"></a>

# 139. Контракт интеграции Neptune

Для Mastermind требуется согласованный typed profile с раздельными recovery archive и dedicated mirror pipelines. Установка переиспользует один host daemon; доступ не выдаётся через ручное копирование чужих env tokens.

Initialize workflow:

1. Owner получает setup code нужного profile в Saturn Synchronization.
2. В Mastermind Settings → Backup вводит его в пустую форму.
3. Backend передаёт code и собственную service identity в typed Updater initialize.
4. Updater проверяет profile, устанавливает отсутствующий агент и выполняет enrollment.
5. UI следует durable job до terminal outcome, переживает reconnect.
6. После COMPLETED перечитывает Neptune state и проверяет обе pipelines.
7. Missing/wrong pipeline даёт Partial configuration и Repair, не success.

Neptune setup code по текущему общему UI имеет 32-character формат и 15-minute expiry. Он не является 6-digit Crusher code и не сохраняется web service.

Saturn остаётся authoritative control plane для schedules, identities, quotas, revoke, fleet state и remote runs. Mastermind показывает status, Initialize/Repair и Open Synchronization.

Нужно согласовать:

- registration identity/namespace и минимальные версии всех consumers;
- control/export/archive/mirror/read scopes;
- idempotency, receipts, resumed uploads и state revisions;
- continuous mirror semantics и finite outbox;
- listing/metadata/read/Range/subtree API, errors, quotas и cancellation.

Archive bytes не изменяются Neptune. Mirror не расширяется за свой root. Availability агента не означает валидный enrollment. Детали открыты в [MM-Q04](mastermind_open_questions.md#mm-q04)–[MM-Q06](mastermind_open_questions.md#mm-q06).

---

<a id="section-140"></a>

# 140. Совместимый release и Updater profile

Signed Mastermind manifest фиксирует:

- exact service-qualified version, source revision и component role;
- immutable Core и Runtime image digests;
- Bridge version/digest и поддерживаемый Obsidian version;
- DB schema generation и supported migration/restore sources;
- minimum tested Updater/Neptune/Chronos/API contracts;
- verified bundle URL/SHA-256, platform и release notes;
- required health/functional verification profile.

Это целевой смысловой контракт, а не утверждение, что текущий Updater уже принимает такую schema.

UI отправляет только own service identity, request ID, выбранную verified version и согласованный backup handoff. Updater независимо получает repository/artifacts и выполняет allow-listed profile. Arbitrary image/URL/path/command запрещены.

Apply должен иметь host mutation lock, durable state, idempotency, backup before mutation, pre-pull всех images, согласованное обновление файлов/Bridge, health и rollback. COMMITTED note/DB state не подменяется старой replica при restart.

Группа контейнеров и recovery sequence задаются [MM-Q10](mastermind_open_questions.md#mm-q10). Если текущий helper поддерживает только image-only path либо 128 MiB backup, это блокер профильной реализации, а не разрешение пропустить Runtime или Vault backup.

Жизненный цикл Mastermind release, Updater self-update и Neptune component update имеет разные UI labels/jobs и не объединяется в неоднозначный Apply.

---

<a id="section-141"></a>

# 141. Resource budgets и bounded operation

Численные defaults исходного продукта сохраняются там, где они однозначны: Crusher upload 2 GiB; watcher debounce 500 ms; Activity idle 300 s; Chronos UI cache TTL 30 s; access code/session по 30 минут; performance targets §102.

Для каждого дорогого пути дополнительно должны быть заданы и enforced:

- maximum body/header/URI/member bytes;
- total staging/spool disk и reservation;
- per-worker/process RAM/CPU;
- parallel requests/uploads/jobs и queue length;
- archive expansion count/depth/ratio;
- fetch/clone/extract/provider/stream/export duration;
- log/event/error context и diagnostic output;
- graph rendering/animation/labels cap.

Неизвестные значения фиксируются как нерешённые в [MM-Q17](mastermind_open_questions.md#mm-q17), измеряются на representative dataset и отражаются в config/runtime/UI/tests. Нельзя выпускать production профиль с неограниченным buffer/queue только потому, что численное значение ещё не согласовано.

Отдельно измеряются full backup size, pause duration и RPO/RTO по [MM-Q07](mastermind_open_questions.md#mm-q07)/[MM-Q09](mastermind_open_questions.md#mm-q09). Limit Updater не обходится base64 encoding, silent omission или разбиением без проверенного восстановления.

---

<a id="section-142"></a>

# 142. Verification matrix и обязательные failure paths

| Контракт | Минимальное доказательство |
| --- | --- |
| Canonical Vault/uniqueness | Concurrent Core/Obsidian operations, startup conflicts, no-clobber create |
| References | Longest-match/Unicode/exclusions, rename/native propagation, deleted target после cache rebuild |
| Shared data consistency | Crash на каждом filesystem/SQLite boundary и recoverable outcome |
| Activity | Autosave dedup, owner attribution, restart session handling, no public/automated increments |
| Shares | Hash/password/expiry/revoke, ETag race, no private transclusion, no grant escalation |
| Crusher capability | One-time activation race, scoped jobs/sources/results, expiry during accepted work |
| Crusher processing | SSRF redirects/DNS/browser subrequests, archive/Git isolation, schema/privacy checks |
| Persistent jobs | Worker death до/после side effect, lease recovery, no duplicate commit |
| Neptune | Exact profile, archive+mirror separately, receipt, outage/recovery, scope/Range |
| Backup | Full clean restore, forbidden-content scan, mismatched/corrupt/oversized ZIP, interrupted rollback |
| Updates | Oldest supported version → candidate; failed migration/health → verified rollback |
| Runtime | Official Obsidian/Bridge versions, export compatibility, keyboard/clipboard/reconnect, 8-hour test |
| Own UI | Part 01 reference views, Settings/Documentation, accessibility и pending/failure states |
| Secrets/ingress | Exact Access Key parity, rotation consumer check, external unauthorized probes |
| Resource budgets | Peak RAM/disk under concurrent large upload and ordinary UI; enforced limits |
| Documentation | Build/render, links, search/findability, no stale operator procedures |
| Supply chain | Tested bytes = published digests, signed manifest, clean bootstrap verification |

Mocked transport/unit tests дополняют, но не заменяют real service/host validation соответствующего контракта. В отчётах различаются PASS, FAIL, UNKNOWN и NOT_RUN; production-only checks не получают фиктивный PASS.

---

<a id="section-143"></a>

# 143. Pre-push и release gates

Каждый branch/tag push требует review полного outgoing diff по семи областям:

1. Backup/restore.
2. Updates/compatibility/rollback.
3. Встроенная Documentation.
4. Technical docs и affected root README.
5. Security — всегда PASS.
6. Public/indexable SEO/GEO — если профиль существует.
7. Private/concealed exposure — если профиль существует.

N/A указывает конкретные inspected paths и причину неприменимости. Если conditional profile активен, unrelated diff получает proportionate no-impact PASS, а не N/A.

Проект предоставляет одну reproducible pre-push command; CI повторяет machine-verifiable gates. Protected release запускается только по точному qualified tag после проверок того же revision.

Part 12:

- фиксируются immutable central documentation SHA и catalog digest;
- каждый active ID представлен ровно один раз;
- PASS имеет test/job/command evidence, N/A — проверяемую причину;
- FAIL, UNKNOWN, omission, duplicate или stale report блокируют следующий privileged этап;
- pre-signing checks выполняются до secret access;
- signed-artifact/trust checks завершаются до publication;
- known-problems-report.json сохраняется с release evidence.

Production DNS/credentials/external-vantage tests остаются NOT_RUN в deployment-readiness record, пока не выполнены. Это не выдаётся за full deployment qualification.

Final artifacts build once/test/promote same bytes; private signing key находится только в защищённом release job. Actions/toolchains/dependencies pinned, SBOM/provenance и secret/layer scans являются частью pipeline.

---

<a id="section-144"></a>

# 144. Порядок реализации и решения перед зависимой работой

Рекомендуемый dependency order:

1. Зафиксировать baseline, exposure/secret matrix и центральную policy revision.
2. Закрыть вопросы identity, write coordination, grammar и публичных capabilities.
3. Согласовать Neptune profile/read APIs и Mastermind Updater contract.
4. Реализовать bounded observability и persistent/recovery foundation.
5. Проверить full backup/restore и interruption до сложных mutations/update.
6. Реализовать Core/Bridge/Runtime интеграцию, UI и source extractors.
7. Выполнить import/compatibility, signed packaging, installation и update tests.
8. Закрыть release gates и отдельно production qualification.

Это порядок зависимостей, не разрешение выполнять всё одним небезопасным изменением. Open question блокирует только зависящий от него выбор; можно продолжать inventory, schemas/tests для неизменных инвариантов, документы и независимые прототипы.

Требующие central изменения оформляются по Part 00: rule/evidence/mismatch/impact/options/recommendation, решение владельца, acceptance и rollback. Прототип подтверждает feasibility, но не заменяет решение.

Статус implementation-ready возможен только после закрытия определяющих контракт вопросов. Release-ready дополнительно требует всех применимых runtime/evidence gates.

---

<a id="section-145"></a>

# 145. Карта адаптации исходного ТЗ

| Исходные разделы | Адаптация |
| --- | --- |
| §1, новый §0 | Уточнены scope/authority; deployment не объявляется проверенным по наличию кода |
| §§4–8, 22, 79–82 | Сохранён Canonical Vault; явно выделена проблема координации всех writers |
| §§9–10, 96 | Authoritative non-note state, secret sources, Access Key и narrow runtime rotation |
| §§11–16, 107 | Import/compatibility отделены от безопасного logical backup; embedded UI boundary открыта |
| §§19, 24, 31, 103 | Не скрыта неоднозначность grammar/broken links и dictionary invalidation |
| §§35–46 | Сохранены note graph density и Activity; переняты UI/resource/accessibility contracts |
| §§48–57 | Share grants независимы от public text; token/identity lifecycle требует решения |
| §§59–78, 95, 123, 126 | Capabilities, private context, isolation, privacy, retry и job recovery |
| §§83–88, 119 | Neptune ownership, отдельные archive/mirror policies, полный согласованный restore |
| §§89–92, 120 | Разделены health/component/audit/Activity; добавлены bounded logs и diagnostics |
| §§98, 104–106, 112 | API families, startup safety, совместимый update/rollback |
| §§113–118, 125–130 | Общие проверки, самостоятельный release и двусторонняя документация |
| §§134–144 | Развёрнуты deployment, principals, inventory, exposure, agent/update/resource/evidence contracts |

Неизменённые разделы исходника включены в эту редакцию непосредственно; исходный файл для исполнения требований читать дополнительно не требуется. При этом конкретные незакрытые решения перечислены отдельно и не являются утверждёнными defaults.

Реестр вопросов: [mastermind_open_questions.md](mastermind_open_questions.md). Вопрос закрывается обновлением затронутых требований и acceptance criteria, а не только сменой его статуса в таблице.

---
