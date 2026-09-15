# Mastermind — финальная концепция и требования для разработки

**Статус:** нормативная база разработки; продуктовые решения приняты, runtime acceptance ещё не выполнена.  
**Версия документа:** 2.0 (не версия релиза сервиса).  
**Дата:** 2026-09-14.  
**Основа:** [адаптированная концепция](mastermind_service_requirements_adapted.md) и ответы владельца по MM-Q01–MM-Q20.  
**Общие требования:** [.docs / Part 00](docs/policy/PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md).

Навигация: [область и правила](#section-0), [архитектура](#section-5), [UI/Vault](#section-13), [Shares](#section-47), [Crusher](#section-58), [placement](#section-71), [writes](#section-80), [recovery](#section-86), [Neptune](#section-139), [Updater](#section-140), [limits](#section-141), [принятые решения](#section-146), [точные версии](#section-147), [изменения соседних систем](#section-148).

Документ содержит полный целевой контракт. Прежние файлы сохранены как история подготовки; все обязательные решения и компромиссы внесены непосредственно в затронутые разделы.

---

<a id="section-0"></a>

# 0. Статус документа, нормативная база и принятые решения

Это финальная нормативная база разработки Mastermind, версия документа 2.0. Решения MM-Q01–MM-Q20 приняты на основании ответов владельца от 2026-09-14; для остальных деталей выбран конкретный вариант. Их итоговый реестр находится в §146. Подтверждение работоспособности реализации выполняется отдельно по §§142–144: принятое решение не означает пройденный тест или готовый production.

Приоритет: прямые решения владельца → применимые общие требования Exocortex → настоящий документ → примеры. Предыдущие ТЗ 1.0, адаптированная редакция 1.1 и реестр открытых вопросов являются историей подготовки; их противоречащие формулировки не действуют. Исполняемые требования содержатся здесь, без необходимости собирать их из нескольких черновиков.

## 0.1. Применимость центральных требований

| Part | Применимость |
| --- | --- |
| [00 — Authority](docs/policy/PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md) | Области ответственности, applicability, evidence и изменение контрактов |
| [01 — Interface](docs/policy/PART_01_INTERFACE_AND_INTERACTION_UNIFICATION.md) | Весь собственный UI; содержимое вкладки Vault является утверждённым исключением и наследует Obsidian UI/UX |
| 01 — Node canvas / correlation graph | Node project/revision model не применяется к Markdown; общие требования взаимодействия применяются к собственному графу, его формула остаётся из §37 |
| [02 — Observability](docs/policy/PART_02_OBSERVABILITY_AUDIT_AND_LOG_EXPORT.md) | Logs/audit/export; Activity хранится отдельно как пользовательские данные |
| [03 — Recovery](docs/policy/PART_03_BACKUP_AND_RECOVERY.md) | Полный согласованный logical ZIP; пользовательский Vault сохраняется как непрозрачный зашифрованный payload, включая .obsidian (§§14, 86, 137) |
| [04 — Deployment](docs/policy/PART_04_BOOTSTRAP_AND_DEPLOYMENT.md) | Самостоятельный bootstrap, environment, mounts и host ingress |
| [05 — Releases/Updater](docs/policy/PART_05_CI_RELEASES_AND_LOCAL_UPDATES.md) | Подписанный комплект компонентов; typed Mastermind profile и большой streaming backup (§140) |
| [06 — Acceptance](docs/policy/PART_06_UNIFIED_ACCEPTANCE_CHECKLIST.md) | Семь областей pre-push и полный DoD |
| [07 — Security](docs/policy/PART_07_SECURITY_AND_EXPOSURE_CONTROL.md) | Все собственные principals, routes, credentials и untrusted inputs; существующие secrets/plugins внутри Vault не мигрируются и не переписываются |
| [08 — SEO/GEO](docs/policy/PART_08_SEO_AND_GEO.md) | Индексируемых страниц нет; правила обнаружения/продвижения N/A, запрет индексации и exposure checks обязательны |
| [09 — Agents lifecycle](docs/policy/PART_09_SERVICE_AGENTS_DEPLOYMENT_AND_LIFECYCLE.md) | Один host Neptune, Updater, typed enrollment с двумя pipelines |
| [10 — Agents UI](docs/policy/PART_10_SERVICE_AGENTS_UI_AND_OPERATOR_WORKFLOWS.md) | Settings Backup/Updates; расписания принадлежат Saturn |
| [11 — Initial profile](docs/policy/PART_11_INITIAL_MULTI_SERVICE_DEPLOYMENT.md) | Общие совместимые механизмы; продуктовые версии и recovery другого сервиса не копируются |
| [12 — Known problems](docs/policy/PART_12_KNOWN_DEPLOYMENT_AND_OPERATIONS_PROBLEMS.md) | Каждый active ID получает evidence на точной ревизии кандидата |

Исключения для Vault UI и сохранения пользовательского .obsidian приняты владельцем. Их необходимо отразить в applicability/decision records общей документации при реализации; повторное продуктовое согласование этих решений не требуется. Изменения API соседних сервисов выполняются и выпускаются в соответствующих репозиториях до зависимого релиза Mastermind.

## 0.2. Воспроизводимая основа

Использованы локальные Parts 00–12 и последние опубликованные стабильные service-qualified релизы на момент проверки. Точные теги, source SHA, SHA-256 артефактов и digest центральных документов приведены в §147. Workspace не является единым Git-репозиторием; вымышленный общий commit ему не назначается.

Нумерация §§1–145 сохранена для сопоставления с адаптированной концепцией; §§146–148 добавляют решения, проверенный baseline и конкретные изменения соседних систем. При выделении самостоятельного репозитория ссылки ../.docs заменяются ссылками на закреплённую центральную revision либо на включённый policy snapshot.

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

Если поддерживаемая managed операция CREATE, RENAME, MOVE, Crusher или Share-edit приводит к нарушению правила, она отклоняется до записи. Native команды включаются в managed протокол через Bridge. Неизвестные plugin/external writes, обходящие протокол, проверяются после факта; их исключение из pre-write guarantee и реакция NOT_READY явно установлены в §80.2.

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

Neptune и Updater — общие host agents, не sidecars Mastermind. Browser не получает agent tokens. Локальные adapters, два pipelines и typed update profile определены в §§139–140.

Отдельный заранее развёрнутый worker обязателен (§6): extraction/local embeddings, без Vault mount/agent sockets/прямого commit.

---

<a id="section-6"></a>

# 6. Deployable units и области полномочий

## 6.1. mastermind-core

HTTP API, Web Shell, Runtime Gateway, watcher, индексы, Graph, Activity, Shares, Crusher orchestration, Chronos/Neptune adapters, backup/restore, audit и readiness. Только Core выполняет программный commit от Shares/Crusher/maintenance. Нативные owner edits остаются в Obsidian и согласуются с Core по §§80–81.

Core не имеет Docker socket, sudo, произвольного shell API или доступа к чужим agent profiles. Host mutations выполняет Updater.

## 6.2. mastermind-obsidian-runtime

Официальный Obsidian, virtual display, lightweight window manager, KasmVNC, Bridge и узкий supervisor процесса Obsidian. Supervisor поддерживает только status/quiesce/stop/start закреплённого приложения для собственного Vault; произвольные executable/args/paths не принимает.

Runtime получает Vault и собственный runtime state. Он не получает mastermind.db, provider/Kernel/Updater/Neptune credentials. Пользовательские .obsidian/plugins и их настройки сохраняются согласно §14.

## 6.3. mastermind-crusher-worker

Один заранее развёрнутый контейнер для извлечения текста, медиаобработки и локальных embeddings. Core передаёт bounded job payload, worker возвращает bounded результат. У worker нет Vault mount, БД, owner session, provider/agent tokens и прямого commit API. Общий staging доступен только в границах конкретных заданий; в первой версии одновременно исполняется один job.

Worker не запускает загруженные scripts/hooks и не устанавливает пакеты из источника. Внешний AI вызывается отдельным adapter Core после проверки payload, а не произвольным extractor.

## 6.4. Единица выпуска

Один релиз описывает три image digest — Core, Runtime, worker — и совместимые Bridge, Obsidian, DB schema, local model artifacts. Третий контейнер является принятым способом изоляции Crusher; отдельного продукта или self-updater он не создаёт. Apply/rollback всей группы выполняется typed профилем (§140).

---

<a id="section-7"></a>

# 7. Сетевые границы и ingress

## 7.1. Публичный ingress

Один server-managed Nginx владеет публичными HTTP(S), WebSocket routing и TLS. Mastermind предоставляет versioned namespaced include либо декларативный upstream contract; installer не устанавливает, не запускает и не reload-ит Nginx.

Core публикует только согласованный host-loopback upstream. Unknown Host/SNI и неизвестные routes отклоняются; SPA fallback не превращает probe path в HTTP 200.

Browser operator Login доступен с любого клиентского IP через canonical HTTPS. Обязательный VPN или OPERATOR_CIDR не вводятся. IP используется для abuse controls, а не вместо аутентификации.

## 7.2. KasmVNC

Runtime не публикует KasmVNC port в Internet. HTTP client и WebSocket Upgrade проходят проверку owner session в Runtime Gateway. Reconnect заново проверяет авторизацию; сохранение graphical session не означает сохранение отозванного browser access.

Trusted proxy headers принимаются только от собственного Nginx. WS revoke/reconnect и ограничения определены §§12–13/135/141.

coturn отсутствует: WebRTC NAT traversal не является требованием этого проекта.

## 7.3. Saturn и Neptune

Listing, metadata, read, ranged read, traversal, replication и remote restore выполняются только через Neptune. Прямые Saturn, WebDAV, Storage Box или SFTP credentials в Core/Bridge не добавляются.

Host Neptune API находится за authenticated Unix socket; typed profile и required read capabilities определены §139. Наличие archive uploader не доказывает поддержку Range reader.

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

Атомарная замена vault directory не считается достаточным доказательством переключения bind-mounted Runtime. Mount topology, recreation/reconnect и rollback проверяются как единая операция; см. §§80/88.

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

Reference history — обязательное non-note state (§24). Share records используют HMAC с pepper_key_id, не raw capabilities; external grants не хранятся. Active sessions, codes, status tickets и leases не восстанавливаются из backup.

---

<a id="section-10"></a>

# 10. Конфигурация, Register и secrets

## 10.1. Владение настройками

Register хранит service discovery и ссылки на защищённые значения Volt. Core разрешает секреты оболочки через Kernel, кэширует их только в памяти на срок credential contract и повторно получает после холодного старта. Существующие secrets Obsidian и community plugins в этот каталог не переносятся.

Собственный .env mode 0600 содержит четыре группы: Operator input, Generated secrets, Release lock, Runtime defaults. После initial seed изменяемые non-secret Settings принадлежат server-side state; .env не перезаписывает их при каждом запуске. Release digests принадлежат installer.

## 10.2. Каталог настроек

| Настройка | Владелец / начальное значение |
| --- | --- |
| public_base_url, Kernel endpoint | Проверенные deployment coordinates; затем server-side Settings |
| timezone | IANA timezone владельца, initial seed deployment |
| vault_path | /var/lib/mastermind/vault, installer-owned |
| crusher.provider | gemini |
| crusher.text_model, crusher.video_model | Явно закреплённые доступные модели в release/runtime profile; startup не подставляет случайный latest |
| crusher.max_upload_bytes | 2147483648 |
| crusher.hierarchy_root | root.md; при импорте разрешается по уникальному basename root |
| activity.edit_idle_timeout_seconds | 300 |
| semantic.model | intfloat/multilingual-e5-small, локально (§78) |
| resource budgets | Численные defaults §141 |
| Obsidian/Bridge/worker versions | Только release lock |
| archive/mirror schedules | Saturn policy, не локальные Settings |

Точное Wire API каждого adapter фиксируется OpenAPI/contract fixtures на source SHA §147. Логические названия Mastermind не выдаются за уже существующие Register keys.

## 10.3. Секреты оболочки

| Значение | Получение и восстановление |
| --- | --- |
| AI provider API key, Chronos service credential | Volt → Kernel → память Core; отдельные scoped records |
| Share pepper и backup recovery identity | Volt → Kernel; отдельные immutable key IDs/versions, сохраняемые во внешнем recovery escrow |
| Owner Access Key | Exact operator input → Argon2id verifier; plaintext не сохраняется |
| Kernel bootstrap credential | Защищённый initial seed/host secret file вне Vault; восстановление до старта Core |
| Neptune/Updater local control и export credentials | Typed enrollment/installer, локальные защищённые файлы; не копируются из чужого сервиса |
| Bridge/supervisor channel | Локальная узкая identity, короткий lifecycle; без секретов соседних сервисов |

Новые ключи Mastermind не записываются в Vault/.obsidian, Git, mastermind.db, images, browser persistence, logs или открытый backup. Запрет касается данных, которыми управляет оболочка; он не является требованием искать или изменять уже существующие plugin credentials внутри Vault.

При недоступном Kernel уже открытый Vault работает, настроенные внешние функции получают DEGRADED/явную ошибку. Для новой операции без необходимого ключа нет fallback на plaintext. После cold start обязательный локальный state должен быть READY; отсутствие настроенного внешнего ключа отключает соответствующую функцию, а отсутствие обязательной core/auth конфигурации даёт NOT_READY.

## 10.4. Runtime Settings

Узкие потоки: смена Access Key с текущим proof и двумя совпадающими новыми значениями; validated Kernel URL; write-only Kernel token rotation. Новое значение проверяется реальным consumer request до activation, ошибка сохраняет прежнее. Rotation отзывает затронутые sessions. Общего редактора provider/host/plugin secrets нет.

---

<a id="section-11"></a>

# 11. Импорт существующего Vault

Импорт не изменяет исходную папку. Из исходника создаётся snapshot, inventory paths/sizes/SHA-256 и отдельная staging copy. Проверяются безопасные пути, отсутствие symlink/hardlink escape, читаемость и глобальная NFC/casefold уникальность .md basenames; проверка не сканирует содержимое .obsidian на секреты и не запускает найденный код.

Каждый исходный файл, включая plugins/configuration, сравнивается byte-for-byte. После этой проверки добавляется только release-verified Mastermind Bridge и его запись в community-plugins.json; diff этих собственных изменений фиксируется отдельным post-install manifest. Другие plugins, их настройки, темы, snippets, ключи и enabled state не очищаются и не мигрируются. Если каталог mastermind-bridge уже занят неизвестными файлами, activation завершается диагностикой без перезаписи.

Проверяется нативная настройка Obsidian автоматического обновления внутренних ссылок при rename. Для поддерживаемого режима она должна быть включена; Bridge показывает явную настройку её включения, не переписывая прочую конфигурацию.

Далее activate Canonical Vault, открыть Runtime, построить индексы и hierarchy (§71). Отсутствующая root или неоднозначная иерархия отключает только автоматическое placement, направляя Crusher в Inbox/Crusher.

Typed enrollment §139 выполняется до initial remote mirror. Archive и mirror проверяются отдельно, initial acceptance не закрывается без обоих подтверждений. Ссылки [[...]] не конвертируются в @...; новые note IDs не добавляются.

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

Primary destinations: Dashboard, Vault, Crusher, Analytics, Shares, Settings. Documentation и Logout — отдельная ненумерованная группа. Порядок primary navigation и Appearance сохраняются server-side.

## 13.1. Dashboard и Analytics

Dashboard начинается CPU, RAM, Disk, Uptime в порядке Part 01. Disk использует f_bavail filesystem Canonical Vault, Uptime — monotonic lifetime Core. Unknown/stale не показываются нулём. Далее — состояние Runtime, backup/mirror и jobs.

Analytics содержит Activity Heatmap, Connectedness, counts notes/internal edges, broken references. Метрики знаний не заменяют operational Dashboard.

## 13.2. Vault

Вкладка открывает authenticated KasmVNC client с настоящим Obsidian. Внешние sidebar/header/status/fullscreen controls принадлежат Shell и следуют Part 01. Внутри viewport действуют native Obsidian UI/UX, темы, dialogs, typography и shortcuts. Shell Appearance не изменяет Obsidian appearance.json.

Fullscreen разворачивает только Vault viewport; сохраняет явный выход обратно в Shell. Не заявляется web screen-reader доступность содержимого graphical stream: поддерживаются keyboard/clipboard/zoom/reconnect, а доступность самого Shell проверяется отдельно.

## 13.3. Crusher

Только ввод/загрузка источника, создание access code для владельца, список своих submissions, progress bar, текущий этап и sanitized terminal status/error. Результат, текст, generated title, путь, preview, download и кнопка открытия созданной заметки на Crusher не показываются. Владелец найдёт заметку в Vault.

Процент относится к подтверждённым этапам (§62), а не к выдуманному времени модели. UI не выводит сырые responses provider/extractor.

## 13.4. Shares

Список note, permission, password flag, created/expires/state. Создание выдаёт URL; повторное копирование доступно только пока capability находится в памяти текущей owner browser session, как в Saturn. После reload/login список не восстанавливает token из hash: Copy disabled с объяснением. Потерянный URL заменяется явным созданием нового Share; старый можно отозвать отдельно.

Revoke и destructive restore используют custom confirmation; приватные настройки открываются только владельцу.

## 13.5. Settings и Documentation

Обязательные секции: Appearance, Security, Backup, Updates, Logs. Appearance: preview/Apply/Reset; остальные ordinary settings применяются после подтверждённого server commit без общего Save. Backup: create/download, inspect/restore, Neptune status/Initialize/Repair. Updates: installed/available verified version, compatibility и explicit Apply. Logs: bounded stream и архив.

Расписания/remote runs управляются в Saturn Synchronization. Documentation — authenticated view с поиском, navigation и актуальными инструкциями.

Собственный UI использует Part 01 palette/typography, toolbar, cards, keyboard, overlays, clipboard fallback и responsive rules. Исключение для native Vault не распространяется на Shared Note или Crusher.

---

<a id="section-14"></a>

# 14. .obsidian и совместимость Vault

Пользовательский Vault — непрозрачный набор пользовательских файлов. .obsidian/themes, snippets, plugins, их binaries, конфигурация, credentials и enabled state сохраняются. Mastermind не ищет, не удаляет, не переносит в Volt и не заменяет секреты внутри Obsidian. В Volt через Kernel помещаются только новые секреты оболочки.

Разрешены только изменения собственного mastermind-bridge и минимальная запись его включения. Для Bridge проверяется release digest; пользовательские plugin settings в том же каталоге отделяются от release-owned files. Обновление не переписывает чужие plugins/themes/config.

Три продукта имеют разные оболочки, но сохраняют полный пользовательский Vault:

- Compatibility export для владельца — обычная переносимая копия Vault с plugins/themes; может содержать исходные plugin secrets, поэтому выдаётся только owner и не называется очищенной от секретов.
- Dedicated mirror — точная приватная копия дерева через Neptune; .obsidian и служебное пользовательское содержимое не доступны через public Shares Mastermind.
- Full logical backup — зашифрованный payload всего Vault и authoritative state внутри ZIP (§86); существующие plugin binaries сохранены как пользовательские данные, а не воспроизводимые сервисные dependencies.

Это утверждённая владельцем граница совместимости и исключение из blanket-исключения binaries для пользовательского Vault. Нельзя обещать, что произвольный community plugin безопасен, соблюдает lock или не обращается в сеть. Privacy гарантия Mastermind распространяется на его собственные компоненты; чужой код остаётся в runtime boundary.

Экспорт открывается обычным Obsidian. Native ссылки и темы работают; Bridge обеспечивает @references, без него они остаются текстом. Обратная синхронизация в Canonical Vault не поддерживается.

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

Вкладка Vault, включая встроенный Obsidian и Bridge, наследует native UI/UX Obsidian. Это принятое исключение Part 01. Bridge использует Obsidian CSS variables, native typography/spacing/borders/internal-link classes и текущий accent; literal hex/rgb допустим только как минимальный fallback отсутствующей переменной.

Проверяются default light/dark, используемая владельцем community theme и snippets. @note и [[note]] выглядят эквивалентно. Shell, Shared Note, Crusher, Settings и Documentation используют общие tokens проекта; исключение Vault на них не распространяется.

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

Для имён с пробелами сохраняется обычная запись @Name без обязательных кавычек и folder-qualified syntax. Одинаковые fixtures обязательны для Core и TypeScript Bridge.

1. Сначала Markdown parser исключает YAML frontmatter, fenced/inline code, HTML comments и raw HTML attributes. Escape `\@` (нечётное число обратных слешей непосредственно перед @) оставляет литерал.
2. Левая граница — начало строки/файла, whitespace либо Unicode punctuation, кроме точки, дефиса и underscore. Перед @ не допускается letter/number/mark; email user@example.org не считается ссылкой.
3. Форма @ + lowercase ASCII namespace + двоеточие обрабатывается раньше internal grammar. chronos/saturn — внешние ссылки; неизвестный namespace остаётся текстом и не запускает fetch. Заметки с таким префиксом доступны через native [[...]].
4. Internal matcher сравнивает NFC + Unicode casefold с именами из словаря текущих и ранее распознанных targets (§24). Выбирается наиболее длинный match, после которого конец строки/файла, whitespace либо punctuation. Продолжение letter/number/mark/_ запрещает завершение token.
5. Пробелы внутри basename значимы, не схлопываются. Точка или дефис внутри известного длинного имени поглощаются до проверки правой границы. Например, при Example и Example note текст @Example note. выбирает Example note, а @Examplemore не выбирает Example.
6. Исходные spans считаются по Unicode code points; Bridge явно переводит их в UTF-16 offsets редактора. Нормализация сравнения не меняет пользовательские bytes.
7. Если ни текущего, ни исторического совпадения нет, последовательность остаётся обычным текстом. Autocomplete вставляет существующее полное имя; unknown free text не считается обещанной broken reference.
8. Создание более длинного совпадающего имени может изменить трактовку прежнего текста: это принятая семантика longest match. CREATE/RENAME/DELETE инвалидирует зависимые parse results; полный и инкрементальный rebuild дают одинаковый результат.

Reference state §24 долговечен и входит в recovery/export; disposable cache не подменяет его.

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

Все owner/API rename проходят одну managed operation с operation_id, preflight уникальности, ожидаемыми hashes и recovery journal (§80). Для нативных [[...]] используется механизм Obsidian через FileManager.renameFile при включённом автоматическом обновлении ссылок. Bridge не реализует второй независимый native link rewriter.

При Old name.md → New name.md Bridge/Core обновляют только действительно распознанные @Old name во всём Vault. Не затрагиваются code, comments, frontmatter, emails и unrelated text. Rename plan включает native и @ affected files; одновременно изменённый файл не перезаписывается.

После native rename/propagation и flush Runtime quiesce, supervisor останавливает процесс перед завершающими Core writes. Core повторно сверяет состояние, атомарно фиксирует @ substitutions, Share paths, reference history и outbox. Только полное завершение даёт success/один owner RENAME. Автоматическая propagation не даёт owner EDIT.

При crash journal позволяет finish/rollback всей операции. Если неизвестный writer изменил уже затронутый файл, автоматический rollback не стирает его: RECOVERY_REQUIRED, сохранение обеих версий для ручного разрешения. Эти временные recovery preimages не являются историей заметок и удаляются после проверки.

API rename при недоступном Runtime не делает filesystem-only rename: возвращает RUNTIME_UNAVAILABLE без изменения файла. Внешний rename, обошедший managed path, диагностируется отдельно и не считается успешно выполненной API-операцией.

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

Удаление target оставляет исходный Markdown references без изменения. Known missing target отображается broken и не создаёт graph edge. После recreation того же basename ссылка снова разрешается.

Для неограниченной формы @Name принят долговечный reference history: source of truth — отдельные reference_history records в SQLite с normalized/display basename и историческими распознанными Saturn paths. Это не note UUID, не revision history и не cache. Запись добавляется при первом успешном распознавании и сохраняется после удаления target.

Полный backup включает history. Compatibility export создаёт в экспортной копии дополнительный credential-free snapshot history для собственного Bridge; исходные пользовательские файлы не изменяются. Без этого snapshot native Markdown читается, но распознавание давно удалённых @targets не обещается. Cache deletion/reindex сохраняют history и broken styling.

History не содержит grants и не запрещает Share path revival. Share lifecycle определяется отдельно §52.

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

Owner autocomplete получает через Neptune paginated listing (100 entries/page) только текущей папки и отменяет устаревшие запросы. Выбор вставляет полный path от root с обычными пробелами; public Shared/Crusher submitter tree не получает.

Для @saturn: после одного или более пробелов выбирается самый длинный известный resource path из текущего metadata index и долговечного reference history (§24), с правой границей по §19. Пути с пробелами поддерживаются без кавычек. Внешний outage не удаляет history и не меняет исходный текст.

Если path ещё неизвестен, безопасный fallback распознаёт только root или root/... до первого whitespace/конца строки и показывает unresolved literal без автоматического расширения поиска. Неоднозначный path с пробелами вставляется через autocomplete; весь Saturn ради разбора одной строки не обходится. Structured path проверяется по §30 перед любым Neptune request.

Chronos target ограничен opaque token до whitespace, angle bracket или конца строки; explicit UI selection обеспечивает корректный ID. Нераспознанные формы остаются текстом, не вызывая network fetch.

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

Owner browser → authenticated Core stream endpoint → scoped Neptune reader → Saturn. Public Share/Crusher tokens этот путь не открывают.

Поддерживаются single Range/206/416, ETag/If-Range, length/MIME, streaming backpressure и cancellation по §139. Большой объект не буферизуется целиком. Credentials Neptune/Saturn не выдаются browser; HTML/SVG не исполняется как активный same-origin content.

Limits §141 и Nginx buffering/timeouts проверяются на реальном media path. Остановка consumer отменяет upstream; новая revision ресурса не смешивается со старым stream.

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

Он учитывает [[...]] и @..., открывает note по click, поддерживает pan/zoom и internal/external filters, соответствует текущей Obsidian theme во вкладке Vault согласно утверждённому исключению §16. Native Graph остаётся доступен. Authoritative projection для analytics — Mastermind Graph; отношения восстанавливаются из Canonical Vault и явно классифицированного обязательного state.

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

В Web Analytics heatmap использует Shell accent; внутри Obsidian — текущие variables темы во вкладке Vault (§16). Формула и уровни §§45–46 сохраняются.

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

Share предоставляет capability-доступ к одной текущей заметке Canonical Vault в режиме view или edit. Доступ к её соседям, attachments, external resources, Vault tree, поиску, graph и autocomplete отсутствует.

URL имеет форму /s/{token}. Token — random 32 bytes, base64url без padding (43 символа). Сервер хранит HMAC-SHA256 с отдельным Share pepper из Volt через Kernel, как в Saturn. Raw token/URL выдаётся только create response и остаётся в памяти owner browser session; list/get не возвращают его.

URL действует до revoke/expiry и сохраняется при managed rename/move. Без expires_at ссылка бессрочная. Потеря локальной копии URL не отзывает уже выданный доступ и не делает token восстанавливаемым. Создание замены выдаёт новую capability; revoke старой — явное действие.

Режим не индексируется поисковыми системами (§138). Live/snapshot переключателя, note version history и публичного каталога нет.

---

<a id="section-48"></a>

# 48. Share fields и state

Обязательные поля: share_id, token_hmac, pepper_key_id, canonical_relative_path, permission (view/edit), password_hash nullable, created_at, updated_at, expires_at nullable, revoked_at nullable, policy_version.

share_id — идентификатор capability record, не note UUID. Target identity — текущий path. target_missing вычисляется отдельно от active/revoked/expired. External grants/resources/subtrees в schema отсутствуют.

Доступ повторно проверяется на каждом request и перед write commit: token, state, expiry, password session, policy_version, target path и expected SHA. Public caller не задаёт path самостоятельно. Owner list допускает отсутствующую target note и сохраняет возможность revoke.

Saturn служит образцом issuance/hash/session/expiry/revoke/Copy URL поведения. Его file download quotas, folder browse, CIDR controls и resource UUID identity не переносятся на Markdown Share; здесь действуют view/edit и path identity по прямым решениям владельца.

---

<a id="section-49"></a>

# 49. Share password

Password optional, Argon2id verifier с солью. Совместимый baseline Saturn: m=19456 KiB, t=2, p=1, hash 32 bytes, salt 16 bytes; пароль 12–128 символов и не более 256 UTF-8 bytes, без CR/LF.

Unlock ограничен пятью неуспешными попытками за 15 минут на source IP по всем Share, с bounded failure delay и 429 при превышении. IP/UA сохраняются как HMAC, не как открытые значения. Password errors не раскрывают дополнительные данные заметки.

Успешный unlock создаёт scoped HttpOnly Secure SameSite session на 30 минут, ограниченную share_id, policy_version и token. Для edit обязательны CSRF/Origin checks. Public requests без password также имеют узкую Share session, которая не становится owner session. Изменение password/permission, revoke или restore инвалидирует прежние sessions.

---

<a id="section-50"></a>

# 50. Share expiration

Отсутствующий expires_at означает бессрочный Share, как в Saturn. Явная будущая дата ограничена 365 днями от момента установки; изменение policy доступно только owner.

После expiry новые read/write requests отклоняются, уже открытая страница теряет право save. Server проверяет expiry повторно внутри commit boundary. Revoke/expired/неизвестный token возвращают одинаковый 404; пароль проверяется только для активного Share.

Продление owner policy допускается явным изменением expires_at; revoke необратим для данного token. Время — UTC; browser не является источником решения об истечении.

---

<a id="section-51"></a>

# 51. Share при rename/move

Managed rename/move атомарно в смысле recovery protocol обновляет canonical_relative_path всех Share target records, сохраняя share_id, token_hmac, policy и URL. Во время незавершённой операции read/write не выдаёт частичное состояние.

Программный filesystem rename без native Obsidian link propagation запрещён (§22). Переименование не является созданием нового Share и не сбрасывает revoke/expiry.

---

<a id="section-52"></a>

# 52. Share при delete/recreate и restore

Отсутствующая target note даёт 410 для ещё действующего и авторизованного Share. Запись и URL сохраняются. Если по сохранённому path появляется новая заметка, старый активный Share открывает её с прежними permission/password/expiry. Это явно принятое владельцем поведение; tombstone/incarnation guard не вводится.

Revoked/expired Share от появления нового файла не оживает. Managed rename до удаления меняет отслеживаемый path (§51). Другая заметка с тем же basename в другом path не заменяет target автоматически.

Full restore возвращает Share records и policies в состояние snapshot. Все owner/Share/Crusher sessions, access codes и status tickets инвалидируются. Старые URL из snapshot продолжают работать после повторного unlock при доступном прежнем pepper_key_id. Revoke, выполненный после snapshot, может быть утрачен при disaster restore; owner restore confirmation прямо сообщает эту семантику. При наличии живого более нового локального revocation set restore объединяет revocations монотонно, чтобы не отменить известный revoke.

Ключи pepper старых backup хранятся во внешнем escrow, не в ZIP. Без нужного ключа Shares остаются недоступны, Vault восстанавливается с явным DEGRADED; подмена новым pepper не выдаётся за continuity.

---

<a id="section-53"></a>

# 53. Shared Note rendering

Отдельный server renderer использует allowlist безопасных Markdown text/block elements. Он получает только целевую note и никогда не получает владельческие resolvers, plugins, Vault filesystem traversal или Neptune/Chronos client.

Все references, Markdown links/images, wiki links/embeds, transclusions, HTML, iframes, SVG, URL autolinks и Obsidian URI остаются инертными текстовыми/служебными placeholders либо удаляются из rendered projection. Existing note source не переписывается ради публичного показа. Frontmatter, HTML comments и Crusher service footer не публикуются.

Ни internal, ни external ресурсы не загружаются и не открываются. В public content нет кликабельных ссылок, hover previews, attachment downloads или элементов, проверяющих существование другой заметки. Bare URL не превращается в anchor. Renderer не исполняет Obsidian/community plugins.

CSP: default-src 'none'; скрипты/стили только собственные с nonce/hash; connect-src ограничен Share API того же origin; frame/object/base запрещены. Не используются сторонние fonts/analytics/media, URL previews, service workers или owner cookies. Referrer-Policy: no-referrer, Cache-Control: no-store, X-Robots-Tag: noindex, nofollow, noarchive.

---

<a id="section-54"></a>

# 54. Internal links внутри Share

[[note]], ![[note]], @note и Markdown relative links не разрешаются. Посетитель видит только инертный исходный label/placeholder без проверки target existence, hover, backlinks или перехода. Нельзя открывать другие заметки или локальные attachments по target ID/path/URL через Share API.

Owner и visitor получают одинаково ограниченный Share renderer; owner открывает полноценную заметку во вкладке Vault.

---

<a id="section-55"></a>

# 55. Chronos внутри Share

@chronos: не создаёт card, fetch, link или event lookup. Share не содержит Chronos grant. Ввод нового reference запрещён сервером по §57; существующий остаётся inert placeholder.

---

<a id="section-56"></a>

# 56. Saturn внутри Share

@saturn:, файлы, папки и media embeds не разрешаются. Нет listing, subtree traversal, Range endpoint, download или owner proxy в Share scope. Любой запрос Share token к owner Neptune/Saturn API отклоняется, даже если path присутствует в note.

---

<a id="section-57"></a>

# 57. Share edit

Редактор позволяет менять только текст целевой заметки, без создания/rename/move/delete файлов и без добавления references.

Чтобы существующие ссылки владельца не исчезали после публичного save, API возвращает versioned projection: редактируемые Markdown text segments и защищённые opaque fragments для references, links, HTML/frontmatter/comments. Защищённые fragments отображаются как read-only placeholders; их bytes хранятся на сервере и не принимаются обратно от visitor. PUT передаёт projection_id, ordered editable segment values и If-Match; клиент не управляет fragment bytes/порядком/идентичностью.

Сервер реконструирует Markdown из сохранённой projection, проверяет SHA исходной note и заново разбирает полный результат. Новые/изменённые references или изменение контекста защищённых fragments отклоняются с 422 REFERENCE_NOT_ALLOWED. Все уже существующие запрещаемые последовательности (включая literal @, URL и wiki delimiters) также представлены protected fragments, чтобы неизменённый source всегда проходил round-trip. Для новых editable segments запрещены @, [[, ]], Markdown links/images/reference definitions/autolinks, raw HTML и URL-схемы/http(s)/www. Проверка выполняется после нормализации кодировок и на полном reconstructed AST, включая конструкции, собранные через границы segments. Клиентская блокировка символов служит подсказкой; server validation обязательна.

При stale If-Match — 409 и свежая безопасная projection для ручного merge; raw owner source с hidden metadata не возвращается. Без If-Match — 428. Secret/resource substitution и молчаливое вычищение частей исходной note запрещены.

Commit проходит §§80–81; permission/expiry/revoke проверяются снова после quiesce. Dirty owner edit даёт conflict либо 423 VAULT_BUSY без потери данных. Успешный public edit попадает в audit и outbox, но не в owner Activity.

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

~~~text
POST /api/v1/crusher/access
POST /api/v1/crusher/sessions
POST /api/v1/crusher/uploads
POST /api/v1/crusher/uploads/:id/complete
POST /api/v1/crusher/jobs
GET  /api/v1/crusher/jobs/:id
GET  /api/v1/crusher/jobs
~~~

/access — только owner; /sessions активирует code. Submit/upload требуют active Crusher Session либо owner login. Public session видит только собственные job IDs, owner — свои owner-managed jobs. Public list перечисляет только jobs данного session.

Job status возвращает только job_id, accepted source label (без credentials), state, stage, progress_percent, timestamps и безопасный error_code/message. Нет result endpoint, generated Markdown/title/path, related notes, destination candidates, model responses или download. На странице Crusher результат не показывается и для owner.

Public input: raw text, public http(s) sources и собственные uploads. Saturn input допускается только при owner login с owner-authorized selection через Neptune. Public session не получает никакого private source scope.

Acceptance — транзакционная регистрация job после полностью принятого и проверенного source. Upload reservation не является accepted job: upload должен закончиться и job быть зарегистрирован до 30-minute session expiry; незавершённый upload после expiry закрывается и очищается. Accepted job продолжает processing после expiry.

При acceptance выдаётся отдельный random status-only ticket на 24 часа, hash в DB, binding к одному job. Он позволяет смотреть только sanitized progress после submit session expiry, не создавать jobs и не читать note/source content. Ticket хранится в памяти клиента, не в URL/persistence. Expiry ticket не останавливает job; owner сохраняет доступ к status через login.

Idempotency-Key обязателен для POST job, scoped по principal и canonical source digest. Повтор того же ключа/тела возвращает прежний job, иной payload с тем же ключом — 409. Потеря response не создаёт вторую заметку.

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

Progress_percent означает завершённую часть фиксированного pipeline, не оценку оставшегося времени: QUEUED=0, ACQUIRING=5, NORMALIZING=15, EXTRACTING=20, UNDERSTANDING=40, PLACING=55, GENERATING=65, VALIDATING=85, COMMITTING=95, COMPLETED=100. Внутри stage допускается известный byte-progress; неизвестная длительность отображается spinner вместе с stage. Retry не уменьшает уже показанный progress, FAILED сохраняет последний процент и error. 100 выдаётся только после durable commit.

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

Только http/https public destinations. Запрещены loopback/private/link-local/metadata ranges, file/ftp/Unix sockets и credentials в URL. SSRF guard проверяет реально используемый DNS address, каждый redirect (максимум 3), IPv6, alternative representations, DNS rebinding и все browser/extractor subrequests. Fetch выполняется через ограниченный egress worker, не из owner network context.

## 64.2. Upload

Максимум 2147483648 bytes (2 GiB), streaming, reserve-before-write, серверная проверка размера/MIME/SHA. Одновременно два uploads и один processing job; budgets §141 действуют также на Nginx. Incoming файл до complete/job acceptance не обещает дальнейшую обработку. Expiry handling — §61.

## 64.3. Saturn input

Только owner-origin job. Core проверяет выбранный resource и выдаёт worker собственный bounded source stream через Neptune. Worker/public submitter не получает Saturn credentials, listing или произвольное право менять path. Чтение source не делает его доступным в Crusher status.

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

Provider получает normalized source и минимальный явно построенный context packet (§71). Обычная обработка не выгружает Vault. Structured result включает title, summary, topics, entities, suggested_links, destination_candidates, placement_confidence и выбранный candidate handle.

Paths, references и confidence — предложения данных, не полномочия модели. Core проверяет schema, допустимые handles, существующие paths, unique filename, source limits и разрешённый private context. Модель не может запросить произвольную заметку или расширить следующий context packet.

Untrusted source отделён от system writing rules; инструкции в PDF/web/note не запускают команды, не читают secrets и не меняют существующие notes. Invalid schema после bounded retry завершается FAILED.

Результат и использованный private context доступны только внутри backend processing и итоговой owner note. Ни status API, ни Crusher UI их не возвращают.

---

<a id="section-71"></a>

# 71. Иерархическое размещение Crusher note

## 71.1. Смысловая структура

Иерархия имеет вид root → #main → #key → вложенные #key. Это структура связанных заметок, а не обязательная копия дерева папок. Default entry — уникальная root.md; owner может выбрать другую root note в обычных non-secret Settings.

Теги #main/#key читаются из Markdown tags и YAML tags по семантике Obsidian, исключая code/comments. Локальный индекс получает outgoing internal links: root → notes с #main, #main → notes с #key, #key → другие #key. Только эти edges формируют skeleton; обычные ссылки между рядовыми заметками не превращаются в разделы.

Один child может иметь несколько parent links. Для placement нужен один однозначный путь от root; cycle, конфликт #main/#key, несколько путей к выбранной ветви, missing root или отсутствие нужного child направляют неоднозначный результат в Inbox/Crusher с owner diagnostic. Индекс не перестраивает Vault и не удаляет «лишние» cross-links.

## 71.2. Bounded context selection

1. Understand source без Vault context даёт topics/summary.
2. Локальные FTS и embeddings ранжируют #main детей root по source topics. Provider получает максимум 12 candidate карточек текущего уровня: request-local handle, title, tags и excerpt до 512 символов, без полного файла.
3. Выбирается один #main, затем аналогично один #key на уровне и при необходимости вложенный #key. На каждом уровне доступны stop и Inbox. Максимум 8 уровней; попытка уйти глубже — Inbox с diagnostic.
4. Provider получает только текущих детей и короткий breadcrumb выбранной ветви, а не полную карту Vault. На всех запросах одного job суммарный уникальный Vault context ≤12000 model tokens; повторно отправленные breadcrumbs учитываются также в суммарном transmitted budget ≤24000 tokens.
5. Для GENERATING разрешены максимум 3 релевантных notes выбранной ветви, excerpt каждой ≤1500 tokens; они входят в указанные общие budgets. .obsidian, attachments, служебные данные и нерелевантные ветви не включаются. Source budget отдельный (§141).
6. Точные paths остаются в Core mapping request-local handles. Модель возвращает handle, а Core проверяет его относительно выданных candidates. Смена иерархии до commit требует локальной revalidation, не full Vault upload.

Truncation выполняется локально до отправки. Exhausted budget, unavailable local index и сомнительный выбор ведут в Inbox, не к расширению доступа. Public submission авторизует только этот заранее ограниченный pipeline; возможности запрашивать private context submitter не получает.

## 71.3. Destination и confidence

Итоговая уверенность — минимум проверенных confidence по выбранным уровням. Если local constraints не выполнены, confidence не повышается по словам модели.

- confidence ≥0.90: создать note в директории выбранного #key, либо #main при осмысленном stop без #key. Если несколько смысловых ветвей используют одну папку, ветвь определяется link на anchor note, а не одной directory.
- 0.65 ≤ confidence <0.90: Inbox/Crusher, suggested branch хранится в private job metadata.
- confidence <0.65 или неоднозначность: Inbox/Crusher, сохранить private top candidates/diagnostic.

В итоговой note указывается native [[selected anchor]] при уверенном выборе; root/#main/#key notes автоматически не переписываются. Новые branch notes/теги, папки и изменение иерархии модель не создаёт. Inbox/Crusher создаётся управляемой операцией при отсутствии. Job не ждёт ручного approval бесконечно.

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

Footer не заменяет durable job/commit record; он может участвовать в проверке отсутствия дубликатов после interruption согласно §126.

---

<a id="section-75"></a>

# 75. Crusher retries

На каждый retryable внешний stage допускается максимум три total attempts: initial, retry после 5 секунд, retry после 30 секунд. Четвёртой попытки/отдельной задержки 120 секунд нет. Общий wall-clock deadline job и budgets §141 сохраняются.

Retry только transient network failure, HTTP 429/5xx и provider timeout. Валидный Retry-After может увеличить соответствующее ожидание до 120 секунд, но не выйти за deadline. Invalid/слишком длинный Retry-After приводит к bounded failure, не бесконечному sleep. В state сохраняются attempt и next_attempt_at; restart не сбрасывает счётчик.

Validation/policy/unsupported errors не retry. Provider idempotency используется при наличии; timeout с неизвестным upstream outcome не объявляется exactly-once billing. Exactly-once гарантируется для локального note commit (§126), а повторный платный вызов учитывается в audit/budget.

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

Temporary payloads не включаются в logical backup по умолчанию. Поведение восстановленных non-terminal jobs с отсутствующим source определяется §126; backup не может обещать восстановление данных, которых в нём нет.

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

Локальные embeddings являются derived state и дополняют FTS/graph при выборе ветви и owner semantic search. Default model — [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small), source revision 614241f622f53c4eeff9890bdc4f31cfecc418b3, CPU inference в worker, ONNX artifact с закреплёнными revision/SHA-256 и offline load. Модель/лицензия/точные tokenizer и preprocessing входят в release inventory; runtime ничего не скачивает автоматически.

Notes разбиваются на chunks не более 512 model tokens; query/passages используют preprocessing model card. Вектор хранит source SHA, chunk span, model digest; cosine search локален. Worker получает только нужные plaintext chunks, не Vault mount; batch ограничен §141.

Background edits/index/search не отправляются remote embedding API. Если локальная модель недоступна, owner semantic search явно unavailable, Crusher использует hierarchy + FTS и консервативный Inbox fallback. Cold FTS/graph target <30s не включает отдельный full embedding rebuild; embedding readiness показывается отдельно.

Удаление индекса безопасно; deterministic rebuild использует текущие .md. Model change требует explicit reindex и не меняет текст заметок.

---

<a id="section-79"></a>

# 79. File watcher

Core отслеживает create/modify/rename/move/delete, debounce 500 ms. Watcher запускает validation, incremental indexes/graph, durable replication intents и cache invalidation. Пропуски events компенсируются inventory reconciliation.

Watcher не блокирует запись до факта, не гарантирует atomic filesystem+DB и не определяет owner Activity. У поддерживаемых managed commands preflight выполняется координатором; неизвестный внешний/plugin write диагностируется отдельно. Нарушение basename uniqueness — NOT_READY, блокировка дальнейших программных mutations и список конфликтов без auto repair.

Изменение словаря текущих/исторических имён инвалидирует references в других notes. Rename event вне managed operation не даёт права автоматически переписать Share path: неизвестный rename может быть delete/create. Doctor показывает такой drift; repair выполняет owner через managed workflow.

---

<a id="section-80"></a>

# 80. Координатор и программные writes

Принят единый durable Core coordinator с Bridge quiesce и обязательным supervisor fallback. Advisory mutex без участия Runtime недостаточен.

## 80.1. Managed boundary

Все Core writes, поддерживаемые owner rename/move/delete/create commands Bridge, Share saves, Crusher commit, backup snapshot и restore получают operation_id и сериализуются глобальным mutation gate. Native owner typing/save остаётся в Obsidian; он останавливается на время внешнего commit.

1. Записать PREPARING operation, ожидаемые paths/hashes и уникальные reserved names.
2. Bridge блокирует новые managed mutations, завершает сохранение dirty native buffers и подтверждает quiesce. Незавершённые edits не отбрасываются.
3. Supervisor корректно останавливает процесс Obsidian и подтверждает отсутствие writer process/open handles. Запущенные им worker processes завершаются в том же runtime process group. Если quiesce не подтверждён, операция ждёт в пределах deadline или возвращает 423 VAULT_BUSY; принудительное закрытие с потерей dirty edits запрещено.
4. Уже после остановки перечитать SHA/inventory, проверить permissions/expiry/unique names. Изменившееся ожидаемое содержимое — 409, без overwrite.
5. Core пишет temp на том же filesystem → fsync → validate → atomic replacement либо no-clobber CREATE → fsync parent.
6. Recovery-aware transaction фиксирует operation/outbox/audit и authoritative metadata. Для batch journal содержит preimages и expected post hashes каждого affected file; startup завершает либо откатывает незавершённое.
7. Перезапустить Obsidian на той же generation, дождаться Bridge/Vault health, снять gate. Shell показывает короткую «Сохранение/обслуживание Vault» паузу и возвращает layout/cursor, когда это поддерживается native workspace state.

Для rename native FileManager propagation выполняется внутри managed gate до завершающего stop/Core phase (§22). Backup snapshot использует ту же boundary, но сжатие/шифрование выполняется уже после копирования и возобновления Runtime.

## 80.2. Граница гарантий

По умолчанию принимается более простой проверяемый вариант с паузой Runtime для внешних commits. Убирать остановку можно только после доказательства эквивалентной координации всех writers в отдельном изменении; первая версия не полагается на monkey-patch binary или несоблюдаемые locks.

Неизвестные community plugins и внешние filesystem tools могут обходить managed commands. Они сохраняются по §14, но не получают обещания transactional API/предварительного запрета коллизий. Это принятый компромисс: controlled operations отклоняют конфликт до записи, неконтролируемые writes обнаруживаются и блокируют программную работу при нарушении invariants. Silent исправление/удаление plugin data запрещено.

При отсутствии Bridge и работающем Obsidian программные commits не обходят quiesce. Если Runtime уже штатно остановлен и supervisor подтверждает это, Core-only create/edit/snapshot допустимы; native rename требует доступного Obsidian.

---

<a id="section-81"></a>

# 81. Content concurrency

Программные edits требуют expected_sha256, public Share — If-Match и projection_id. Нет note revision history. Stale SHA даёт 409; отсутствующий required precondition — 428.

Проверка SHA выполняется после flush/stop Runtime внутри mutation gate непосредственно перед commit. Save, случившийся между первичным read и quiesce, не затирается. Dirty buffer reload после commit производится запуском Runtime на подтверждённой generation, без replay старого несохранённого текста.

Batch operation проверяет каждый affected SHA и использует durable journal. После неизвестного изменения автоматический rollback не перезаписывает посторонний новый content; RECOVERY_REQUIRED сохраняет preimage/current для явного разрешения. Во время recovery не допускается публичный read частично изменённой target note.

---

<a id="section-82"></a>

# 82. Activity attribution

Watcher не считает каждое modification событием Activity.

Bridge передаёт owner events отдельным authenticated channel:

- owner Obsidian edit → Activity;
- Crusher write → no Activity;
- public Share edit → no Activity;
- automatic link rewrite → no Activity.

Channel требует event ID/deduplication, bounded retry и проверки principal; public clients не могут подделывать owner Activity. При недоступном Core Bridge сохраняет минимальный durable outbox собственных event IDs/UTC/type/path без note bodies в своём runtime state (10 MiB cap). После reconnect replay дедуплицируется SQLite UNIQUE(event_id). Незавершённая edit session имеет stable session_id и last_activity_at, после restart закрывается один раз при превышении idle deadline. Если event spool исчерпан, дальнейшие owner edits блокируются с явным status до drain; уже сохранённый note content не откатывается.

Programmatic/audit events сохраняются отдельно по retention Part 02. Автоматическая операция может требовать audit, оставаясь исключённой из heatmap.

---

<a id="section-83"></a>

# 83. Replication в Saturn

Core создаёт durable dirty intent не позднее 1 секунды после подтверждённого изменения. Neptune владеет транспортом, credential и remote destination. Mirror остаётся вторичной копией.

Для первой версии принят scheduled zip-tree mirror существующего профиля: default interval 5 минут, minimum 1 минута, расписание/enable/revoke только в Saturn. Архивный pipeline независим, default cadence 24 часа. Manual remote run выполняется тем же Neptune worker, без второго локального scheduler.

Это явный компромисс относительно исходного требования «начать передачу за 5 секунд»: оно не входит в первый релиз. Фактический lag равен ожиданию расписания, очереди и длительности snapshot/transfer. Ни 5 минут, ни 350 MiB не выдаются за измеренный RPO. При outage SLA доставки отсутствует; UI показывает last verified success, oldest dirty generation и lag.

Dirty intents coalesce по path/generation, limit 100000 records. При overflow durable full_reconcile_required заменяет подробную очередь без потери знания о несинхронизированном state. Snapshot receipt закрывает только included generation; изменения после его boundary остаются dirty.

Disable/revoke прекращает новые передачи, но не owner editing. Нет прямого Saturn fallback. Initial и периодические full inventories проверяют remote hashes; success определяется завершением pipeline/receipt, не acceptance запроса. Continuous mode оставлен вне первого релиза и не требуется для его приёмки.

---

<a id="section-84"></a>

# 84. Saturn namespaces

Логические destinations: root/mastermind/ для private Vault mirror; root/backups/mastermind/ для recovery archives. Конкретный deployment segment/producer slug назначает typed Saturn enrollment; Core не придумывает произвольные paths.

Один project/deployment identity связывает archive и mirror, но credentials и scopes различны. Mirror credential ограничен собственным mastermind root; archive credential — собственным producer archive namespace. Интерактивный owner read имеет отдельный scope §139 и не наследует write/archive privileges.

Вторая установка не может направить destructive tree reconciliation в уже занятый чужой root. Wrong deployment/root/profile отвергается до запуска worker. Общая host Neptune установка переиспользуется.

---

<a id="section-85"></a>

# 85. Состав dedicated replica

Mirror содержит полное дерево Vault byte-for-byte: .md, attachments, .obsidian, themes/snippets/plugins/config и существующие plugin credentials. Содержимое не очищается и не перекодируется; реплика не называется secret-free. External Saturn resources из @saturn повторно не копируются.

Для zip-tree Core отдаёт отдельный приватный Vault ZIP, не full recovery ZIP. Neptune распаковывает только этот tree export и сверяет/обновляет destination в пределах своего root. Full logical archive §86, напротив, переносится как opaque bytes.

Remote .obsidian и другие непубличные пользовательские файлы получают закрытую classification/policy Saturn и не допускаются в его public folder shares; Mastermind Shared вообще не имеет доступа к mirror. Backup transport scopes не дают browsing сторонним submitters.

Mirror обеспечивает восстановление дерева, но без подходящего authoritative state backup не обещает восстановить Activity/Shares/jobs.

---

<a id="section-86"></a>

# 86. Полный logical backup Mastermind

Один builder обслуживает manual download, local Neptune archive export и Updater handoff. Размер текущего пользовательского архива около 350 MiB — исходная оценка владельца, не выполненное в этой задаче измерение.

## 86.1. Состав и шифрование

Внешний артефакт — .zip с application/zip:
~~~text
manifest.json
payload.age
~~~

payload.age содержит зашифрованный внутренний logical ZIP:
~~~text
inventory.json
vault/**
state/*.json
~~~

Внутренний payload включает полный Vault, Activity, reference history, Share records/policies/revocations/pepper key IDs, Crusher jobs/commit records, settings, Access Key verifier, schema и необходимое recovery state. SQLite snapshot получают WAL-aware API, из него экспортируют только классифицированные restorable records.

Применяется стандартный [age v1](https://age-encryption.org/v1) с X25519 recipient, готовой проверенной библиотекой/utility; собственная криптография и legacy ZIP passwords запрещены. Encryption identity и recovery escrow находятся вне Vault/ZIP, в Volt через Kernel и независимой защищённой disaster-recovery копии. Для создания достаточно public recipient; restore/automatic rollback требует соответствующего защищённого identity. Ключ передаётся через protected descriptor/file, не argv/log/browser read API.

Внешний manifest: format mastermind-backup/v1, UTC boundary, service/schema versions, payload size/SHA-256, encryption/key ID, protected inventory digest, limits. Имена заметок и user paths остаются внутри ciphertext. Inner inventory содержит каждый member path, SHA-256, byte size и record count.

Целостность ciphertext проверяется age; происхождение внешнего manifest подтверждает service backup signing key (Ed25519, отдельный от release key). Detached signature хранится в manifest envelope над canonical unsigned manifest. Trust public key привязан к service recovery profile и сохраняется вне backup; нельзя доверять ключу, пришедшему только из того же архива.

## 86.2. Исключения и boundary

Из service state исключаются raw credentials, .env, cookies, active sessions/codes/tickets, caches, FTS/embeddings, temporary uploads/work, release images и host agent state. Существующие secrets/binaries внутри vault/** сохраняются как непрозрачные пользовательские данные исключительно в зашифрованном payload. Это не разрешение класть новые shell secrets в Vault.

## 86.3. Согласованный snapshot

Mutation gate → Bridge flush → подтверждённый stop Runtime → pause Core writers/queue claims → consistent SQLite snapshot и копия всего Vault в private staging → inventory/hashes → release gate/Runtime restart → serialize/compress/encrypt из immutable staging. Сжатие и network transfer не удерживают editor pause. Reflink допускается только при доказанном copy-on-write; hardlink на изменяемые live files не является snapshot.

Snapshot маркируется одной generation; partial snapshot удаляется и не предлагается для download. Neptune архивный pipeline передаёт точные внешние ZIP bytes без recompression/распаковки/re-encryption и получает receipt. Local temporary plaintext staging mode 0700/0600 очищается после ciphertext verification по §141.

Clean restore обязан восстановить весь заявленный state. DB-only архив и независимо свежий mirror не являются согласованным full backup.

---

<a id="section-87"></a>

# 87. Periodic reconciliation

Каждый scheduled mirror run сопоставляет полный source inventory своего snapshot с remote tree через Neptune, проверяет hashes, удаляет отсутствующие entries только в собственном root. Неполный listing, authorization error или incomplete export запрещает remote deletions и завершает run ошибкой.

Core каждые 15 минут сверяет локальный inventory, outbox и last confirmed generation для восстановления после пропущенных watcher events. Это проверка состояния, а не отдельный authority расписания передачи. Rename/delete/move и новые изменения после snapshot учитываются следующей generation.

Outage, disabled/revoked policy и backpressure видны в status. При восстановлении связи очередь coalesce/full-reconcile догоняет текущее дерево; промежуточные версии не сохраняются как history.

---

<a id="section-88"></a>

# 88. Restore

Restore — explicit owner/admin operation с inspect, reviewable summary и custom confirmation. Startup не восстанавливает автоматически из Saturn. При restore сообщается, что текущее дерево/state заменяется snapshot, sessions прекращаются, Share URLs следуют snapshot policy (§52).

1. Принять ZIP streaming в private bounded spool; проверить signature/trusted key, ciphertext digest, format и size.
2. Получить external recovery identity, decrypt в private staging. Проверить оба уровня ZIP, allowlist, counts, SHA, safe paths, отсутствие links/duplicates/Unicode collisions и schema compatibility. До конца проверки live state не меняется.
3. Создать verified pre-restore backup. Получить mutation gate, flush/stop Runtime, остановить writers/leases.
4. Подготовить новую полную DB и Vault generation; записать durable PREPARED journal со old/new locations и checksums.
5. Переключить DB/Vault как одну логическую transaction; отдельные filesystem renames могут быть неатомарны вместе, поэтому durable COMMITTING marker определяет recovery. Core не стартует в normal mode между половинами.
6. Updater/supervisor переоткрывает mounts/Runtime на новой generation; старые bind mounts не считаются обновлёнными по одному directory rename.
7. Поднять совместимый Core/schema/verified Bridge, перестроить FTS/graph, проверить counts, source hashes, Vault open и bridge handshake.
8. Инвалидировать sessions/codes/tickets, восстановить settings/Activity/reference history/Share semantics/jobs (§126). Без external keys затронутые функции DEGRADED, не silently regenerated.
9. После functional verification — COMMITTED, снять gate. Old generation и pre-restore backup хранить 24 часа, затем cleanup с path validation.

Failure до завершения проверки откатывает весь комплект DB/Vault/Runtime. Startup читает journal до обычной readiness и завершает либо откатывает операцию детерминированно. Если обнаружено непредусмотренное изменение old/new state, RECOVERY_REQUIRED без стирания данных.

При update rollback сначала остановить новый код, восстановить pre-update data generation/schema и старые components/Bridge, затем открыть старый Runtime. Старый код не запускается на несовместимой новой schema.

Mirror-only restore разрешён только как явно обозначенное восстановление Vault без обещания Shares/Activity/jobs. Дубли basenames и неверные keys не исправляются автоматически.

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

Audit фиксирует programmatic CREATE/EDIT/RENAME/MOVE/DELETE, share creation/revoke/policy changes, Crusher transitions/commit outcome без result content, restore, replication failures, auth/credential changes, settings/order persistence и accepted agent/update operations.

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

Public Share renderer использует allowlist §§53–57: raw HTML не исполняется и не превращается в активные элементы. Запрещены все resource links/embeds/transclusions/autolinks, не только javascript или unsafe URLs; любые browser/server fetch к содержимому ссылки отсутствуют.

Owner Obsidian Runtime может использовать стандартные возможности Obsidian отдельно; Share renderer всегда работает в stricter mode.

---

<a id="section-95"></a>

# 95. Crusher sandbox

Обрабатываются недоверенные источники в заранее развёрнутом worker (§6). No root/privileged mode, Docker socket, sudo, host network или Vault/DB mounts. Read-only root filesystem, bounded per-job writable work directory, noexec для загруженных binaries. Worker исполняет только встроенные allowlisted extractors, без Git hooks/scripts/package install и без shell интерполяции source input.

Fetch egress проверяет SSRF для каждого address/redirect/browser subrequest; extraction phase не имеет сети. Provider credentials остаются в Core adapter. Локальные embeddings получают только переданный Core bounded chunk batch.

Archives: reject traversal, symlink/hardlink/device entries, duplicate/casefold-colliding paths, encrypted unknown formats и excess expansion; depth/count/bytes/CPU/RAM/deadlines заданы §141. Sandbox failure и отсутствие source дают explicit FAILED.

Worker output и AI JSON считаются данными. Только Core назначает safe destination, проверяет schema/limits и делает commit.

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
GET  /api/v1/crusher/jobs

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

Набор выше не означает, что POST /crusher/sessions и capability-protected job routes требуют owner session: их собственные правила §§59–61 имеют приоритет. Схемы интеграционных families должны выполнять §§10/139/140/147. Crusher upload/complete и status-only ticket semantics обязательны по §61; result endpoint отсутствует.

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

Endpoint не должен работать по принципу «rename сейчас, Obsidian когда-нибудь перепишет native links». Native propagation, dirty editor buffers и доступность Runtime определены §§22/80–81.

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

Cache rebuild должен воспроизводить те же refs, broken states и counters. Семантика §§19/24/31 задаёт общие Core/Bridge acceptance fixtures. Admin full reindex остаётся доступен.

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

При незавершённом restore/rename нельзя запустить writers поверх partial state. Core и Runtime не должны образовать циклический readiness wait. Core сначала поднимает local control/recovery phase без Runtime readiness dependency, проверяет state/mounts и выдаёт supervisor разрешение старта; normal Ready появляется после локальных проверок, Runtime status остаётся отдельным компонентом. Недоступный Kernel/Volt не блокирует чтение существующего Vault при наличии local auth state, но функции без нужных ключей не запускаются (§10). Mandatory schema migration без verified pre-migration backup не выполняется.

---

<a id="section-105"></a>

# 105. Mastermind, Obsidian и Updater

Updater применяет один verified Mastermind release: Core, Runtime, worker, pinned Obsidian, Bridge, local model digest и DB schema.

Discovery не начинает install. UI показывает точную версию, change summary, compatibility и backup readiness. Apply сначала pre-pull/verify всех artifacts и проверяет space/keys, затем устанавливает mutation barrier, делает fresh consistent pre-update snapshot и передаёт его streaming handoff §140. Между snapshot и runtime mutation новые writes не допускаются.

Typed profile проверяет manifest/signature/digests независимо от Core, применяет group и migration, проверяет Core health, Vault open, Runtime/Bridge и worker. Только functional acceptance даёт COMPLETED. Любой failure после mutation запускает rollback всех components и pre-update state; непроверенный rollback не называется success.

Obsidian self-update в production отключён поддерживаемой настройкой/packaging; binary не patchится. Версия меняется только в общем release после compatibility suite. Непроверенный Bridge нельзя оставить под новой версией Core.

Baseline §147 — последние выпуски на дату составления, но Updater v0.4.7 ещё имеет 128 MiB inline-backup limit. Необходимое расширение §140 должно выйти отдельным новым релизом Updater до зависимого Mastermind; номера будущих релизов не выдумываются.

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

На filesystem copy полного Vault проверить byte equality исходных files, темы/snippets/plugins/config, затем открыть standard Obsidian закреплённой версии вне host Mastermind. Native [[...]], @... с Bridge и broken history snapshot должны работать; без Bridge Markdown остаётся читаемым.

External references при отсутствии Mastermind API дают безопасный unavailable placeholder. Export не требует host-only credentials/absolute paths. Plugin secrets остаются исходными bytes; тест не сканирует или мигрирует их. Проверяется, что оболочка не добавила собственные provider/agent secrets.

Экспортная history snapshot добавляется только в собственной области Bridge экспортной копии и явно отражается в export manifest. Sync обратно в сервер не поддерживается.

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

Core read API, Shared rendering, Crusher processing и analytics продолжают работать. `/vault` показывает Runtime unavailable. Write commit доступен только при подтверждённой остановке Obsidian либо рабочем quiesce channel (§80); отказ KasmVNC сам по себе не доказывает отсутствие writer.

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

Совместимость old/new Core, Bridge, Runtime и schema описывается в release manifest. Rollback не обязан быть down-migration: он может восстановить verified pre-update logical state по процедуре §§88/140.

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

Дополнительно покрыть exact Access Key preservation, recursive secret redaction, полный запрет Share resource resolution, server projection reconstruction и reference rejection при public edit, filename no-clobber, idempotency/lease budget, dictionary invalidation и правила parser/history §§19/24/31.

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

18. Share edit пытается добавить internal/external reference → 422; существующие protected fragments сохраняются, resource fetch отсутствует.
19. Public Crusher caller не читает чужие jobs/private sources/context; ни owner, ни public Crusher response не содержит результата/пути.
20. Конкурентные Obsidian save и API write не теряют изменения.
21. API rename корректно координирует native [[...]] и @ references.
22. CREATE более длинного имени инвалидирует зависимые parsed references.
23. Worker crash после commit не создаёт вторую Crusher note.
24. Agent accepted job остаётся pending до terminal result и refreshed observed state.
25. Restore переключает Core/Runtime views на правильную generation, worker остаётся без Vault mount.
26. Обновление key/token действительно применяется в consumer после atomic secret replacement.

27. root → #main → #key → nested #key placement соблюдает контекстные budgets; cycles/multiple parents/missing anchors дают Inbox.
28. Scheduled mirror policy/lag не выдаёт promise 5 секунд; archive и mirror независимы.
29. Delete/recreate по прежнему path оживляет только active Share, не revoked/expired.
30. Plugin-secret fixture сохраняется byte-for-byte в encrypted backup и не сканируется мигратором.

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

Для embedded Obsidian не выдавать наличие VNC-картинки за доказанную screen-reader/mobile accessibility. Поддерживаемая область и критерии определены §§12–16/135. Невыполненный обязательный сценарий отражается в evidence явно.

---

<a id="section-119"></a>

# 119. Backup/restore acceptance test

1. Fixture полного Vault с .md, attachments, themes/snippets/plugins; тестовый plugin secret сохраняется неизменным внутри Vault.
2. Создать Activity, settings, reference history, Share policies/revocations и jobs до/после commit.
3. Проверить два независимых Neptune pipelines, mirror inventory и archive receipt.
4. Построить full logical ZIP тем же builder для manual/agent/update; проверить подпись, шифрование, inventory и limits.
5. Внешний ZIP не содержит plaintext note/plugin secret/shell token. После decrypt Vault plugin secret должен round-trip byte-for-byte; новые shell credentials отсутствуют даже во внутреннем service state.
6. Clean restore в отдельную среду с external recovery keys; сравнить все mandatory records, paths/bytes, открыть Obsidian и перестроить derived state.
7. Проверить Share delete/recreate, restore policy, отсутствие public resources, invalidated sessions и lost-source jobs.
8. Повторить поверх живого state, с corrupted/unknown/oversized/traversal архивами и на каждой interruption boundary DB/Vault/mount.
9. Проверить >350 MiB и 8 GiB boundary transfer с bounded RAM/disk, cancellation, forged handoff, wrong hash/key; измерить snapshot pause и RTO.
10. Проверить oldest supported backup schema и полный update rollback. Runtime checkboxes закрываются только фактическими результатами.

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

Выделенный operational Dashboard начинает с CPU/RAM/Disk/Uptime по Part 01; источник и scope метрик явные. Скрывать backlog/unknown через нулевое значение запрещено.

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

Из этого не следует разрешение удалить SQLite domain state. Reference history, Share policies, settings или recovery markers нельзя назвать cache, если без них изменяется поведение.

Проверка включает FTS, graph, semantic cache, Chronos/Saturn UI cache и broken-link semantics §§19/24/31. Embeddings восстанавливаются без несогласованной отправки notes внешнему provider.

---

<a id="section-123"></a>

# 123. Privacy

Owner edit/graph/search/Activity, Share rendering и background indexing не отправляют note content внешним AI. Локальная модель §78 выполняется без remote inference.

Crusher передаёт source и ограниченный selected hierarchy context по §§70–71, никогда всю базу. Нехватка контекста, индекса или confidence ведёт в Inbox, а не к full dump. Context assembly происходит в Core, источники и модель не могут расширить его.

Crusher status/UI не возвращает результат, title/path, соседние notes или provider output даже после completion. Shared не разрешает никаких resource links. Logs и audit не содержат note bodies, private prompts, raw tokens или plugin settings.

Эта гарантия относится к компонентам Mastermind. Существующие community plugins сохраняют собственные настройки и network behavior; Mastermind не переносит их секреты и не выдаёт их работу за проверенную privacy гарантию оболочки.

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

Также вне первой версии: continuous 5-second mirror, Shared attachments/external resources, индексируемая публикация, выдача Crusher результата на его странице/API, автоматическая миграция plugin secrets и принудительное приведение Obsidian UI к Shell tokens.

---

<a id="section-125"></a>

# 125. Технологические ограничения

Core следует применимому backend standard самостоятельного проекта. При отсутствии обязательного другого стандарта сохраняется Python 3.12+ / FastAPI. Наличие polyglot соседних сервисов не требует переписывать этот выбор. Bridge — TypeScript.

SQLite в WAL mode обязателен для local state на текущем масштабе. FTS5 — для search; derived embeddings — без отдельного обязательного graph DB/Elasticsearch.

Внешний broker не вводится. Crusher, Core outbox и background jobs используют persistent SQLite-backed queues с transactional claim и leases. Это не заменяет собственный transport journal Neptune и не создаёт второй agent.

Toolchains/dependencies/images фиксируются воспроизводимо. Cross-repository dependencies потребляются из verified immutable release assets, не из sibling source directories.

Отдельный заранее развёрнутый worker обязателен по §§6/95; это не основание добавить Kafka, Kubernetes либо новую платформу orchestration.

---

<a id="section-126"></a>

# 126. Persistent job semantics

SQLite queue хранит status, stage, leased_by, lease_expires_at, attempt, next_attempt_at, source digest, idempotency binding и timestamps. Lease 60 секунд, heartbeat каждые 15 секунд. Claim транзакционный; restart не сбрасывает retry budget.

Exactly-once относится к созданию итоговой note. До filesystem write Core сохраняет COMMIT_INTENT с job_id, reserved path, content SHA и generation; безопасный footer содержит job_id. Затем no-clobber atomic write + fsync, после чего COMMITTED record, audit и outbox фиксируются recovery-aware transaction.

После crash reconciler проверяет reserved path/SHA/footer: совпавший commit завершает DB transition без второго файла; отсутствующий write повторяет прежний intent; посторонний файл никогда не перезаписывает и даёт conflict/recovery. Lease сама по себе этой гарантии не даёт.

После process restart job продолжается с последнего подтверждённого stage при наличии verified source. После disaster restore:
- COMMITTED note и record согласованы — сохранить COMPLETED;
- note существует с правильным commit marker, DB не успела — завершить reconciliation;
- незавершённый job и исключённый temporary source отсутствует — FAILED / SOURCE_UNAVAILABLE, требуется новая submission;
- active sessions/codes/status tickets/leases инвалидируются.

Старый record не создаёт выдуманный результат и не вызывает повторный commit. Temporary preimages/commit recovery state после подтверждённой операции удаляются согласно retention. Provider billing exactly-once не обещается.

Neptune transport и Updater имеют собственные durable jobs/receipts; их enum не смешивается с Crusher stages.

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
- [ ] Managed operations предварительно запрещают duplicate basenames, неконтролируемый drift переводит сервис в NOT_READY.

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
- [ ] В Shared полностью отсутствует internal/external resource resolution, server edit projection сохраняет protected fragments.
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

- [ ] Матрица применимости, принятые решения §146 и baseline §147 отражены в implementation artifacts.
- [ ] Для embedded Obsidian зафиксирована граница Part 01, без фиктивной visual/a11y совместимости.
- [ ] Shell/Login/Settings/Documentation реализуют общие UI requirements.
- [ ] Access Key parity, session/CSRF и write-only credential rotation проверены.
- [ ] Shared agents имеют точный Mastermind profile; archive и mirror подтверждены отдельно.
- [ ] Neptune read/Range/subtree contract реализован и проверен против реального совместимого сервиса.
- [ ] Public edits/submissions не расширяют external permissions и не раскрывают private context.
- [ ] Full logical ZIP согласован по Vault/DB; user Vault сохранён encrypted, shell secrets отсутствуют; clean restore и interrupted rollback проверены.
- [ ] Large backup handoff и multi-component update проходят functional health/rollback.
- [ ] Production mounts/UID, Nginx ingress, route limits и external-negative checks проверены.
- [ ] Logs bounded/redacted, Activity не обрезается retention operational audit.
- [ ] Exact candidate artifacts signed, digest-pinned и проверены installer.
- [ ] Семь областей pre-push gate имеют корректные PASS/N/A; security всегда PASS.
- [ ] Каждый active Part 12 ID имеет revision-bound evidence, known-problems-report.json полон.
- [ ] Production-only NOT_RUN не выдан за PASS.
- [ ] Все MM-Q01–MM-Q20 реализованы согласно §146; обязательные integration/benchmark checks не выданы за выполненные по одному ТЗ.

Эти пункты добавляются к продуктовым acceptance criteria выше. Сам факт создания этого документа не закрывает ни один runtime checkbox.

Дополнительно обязательны: Saturn-style URL lifecycle, Share path revival; Crusher progress-only UI/API и expiry tickets; hierarchy root/#main/nested #key без полного Vault upload; local embeddings; independent scheduled mirror/archive; streaming backup >350 MiB; полный rollback трёх компонентов. Все checkboxes выше — задания на приёмку, не результаты этой редакции.

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

Эта сводка описывает целевую модель. Принятые решения сведены в §146; конкретные integration gaps и порядок разработки заданы §§144/148, соответствие общим требованиям — §§134–143. Исходные ограничения не оправдывают обход agent, secret, backup или ingress contracts.

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

Release lock перечисляет точные Core/Runtime/worker digests, Bridge и model artifact digests. Изменение Compose topology имеет собственный installation/repair/update contract по §140.

---

<a id="section-135"></a>

# 135. Ingress, Runtime Gateway и browser boundaries

Server Nginx — единственный public ingress. Core реализует authenticated Runtime Gateway; embedded Nginx/Caddy, public raw VNC/Runtime и host control APIs отсутствуют.

Версионируемый include задаёт Host/SNI, trusted forwarded headers, route-specific size/time limits, WebSocket Upgrade/Origin, streaming/backpressure, private export/control routes, CSP/cache/robots и token redaction. /s/{token} redacted также в Nginx access/error logs. Никаких third-party requests из Shared.

Gateway принимает только owner login. Logout/revoke/Access Key rotation немедленно закрывает все WS затронутой browser session и запрещает reconnect; supervisor сохраняет локальную graphical session, но другой revoked browser к ней не подключается. Внутренняя VNC credential не передаётся публичному клиенту как обход Gateway.

Public Share/Crusher capabilities не проходят в owner routes. Share resources полностью запрещены (§53), а Saturn Range существует только в owner API. CORS/frame policy explicit, без wildcard credentials.

Acceptance проходит через реальный host proxy: Host/Origin/cookies/CSRF, auth-negative probes, unknown routes, 413, долгий upload, streamed backup, Range, revoke активного WS и reconnect. Health внутри Docker network недостаточно.

---

<a id="section-136"></a>

# 136. Матрица данных, principals и secret ownership

| Principal | Разрешённые данные и действия |
| --- | --- |
| Owner browser | Собственные authenticated UI/API; Vault Runtime, settings, raw notes |
| Core | Canonical files, authoritative state, bounded provider context; shell keys через Kernel/Volt |
| Obsidian/Bridge | Vault и собственный runtime state; нет provider/agent/DB доступа |
| Community plugin | Унаследованные возможности внутри Obsidian; его secrets/config не мигрируются и не сканируются |
| Crusher worker | Переданный source/chunks, private job work; нет Vault mount/credentials/commit |
| Crusher public submitter | Свой source upload и sanitized job progress; private Saturn/result/context запрещены |
| Share visitor | Одна безопасная note projection и разрешённые text edits; никаких resource grants |
| AI provider | Только bounded source и selected branch context явного job |
| Neptune | Archive, mirror и отдельный read scope своего project; host credentials не раскрываются Core |
| Updater | Typed own head group/lifecycle/backup handoff; произвольные команды/paths запрещены |
| Kernel/Volt | Discovery и secrets оболочки; user plugin secrets остаются внутри Vault |
| Release CI | Protected signing identity; подпись именно проверенных artifacts |

Для каждого межсервисного credential: issuer/audience/holder/scope/key ID/version/rotation/revoke/expiry, consumer verification и recovery dependency. Rotation проверяется реальным запросом из consumer перед activation. Service-generated secrets не включаются в обычные files/artifacts/logs; Vault payload исключение §14 не расширяет права оболочки.

---

<a id="section-137"></a>

# 137. Backup inventory и compatibility contract

| Данные | Класс / восстановление |
| --- | --- |
| Полный Vault, включая .obsidian/plugins/config | Mandatory opaque user data, byte-for-byte внутри encrypted payload |
| Существующие plugin secrets/binaries | Не сканируются/не мигрируются; сохраняются вместе с Vault и защищаются шифрованием |
| Собственные release-owned Bridge files | В Vault snapshot сохраняются; при update/restore сверяются с trusted совместимым release, user Bridge settings сохраняются отдельно |
| Images/OS/model binaries вне Vault | Reconstructible, digest/verified artifact retrieval; не включаются в payload |
| Activity/reference history | Mandatory; не disposable cache |
| Share records/policies/revocations/key IDs | Mandatory, path revival и restore semantics §52 |
| Crusher jobs/transitions/commit records | Mandatory; отсутствующий temporary source → явный FAILED |
| Settings/order/Access Key verifier | Mandatory, восстановить поведение, не только строки manifest |
| Active sessions/codes/status tickets/leases | Ephemeral, инвалидировать |
| FTS/graph/embeddings/cache | Derived, rebuild |
| Service .env/raw keys/cookies/credentials | Запрещены даже во внутреннем service state; отдельный escrow |
| Upload/work/update staging/log spool | Не входят в обычный recovery payload |
| Host-wide Neptune/Updater state | Вне Mastermind ZIP, восстановление соответствующим host profile |

External ZIP ограничен §141, содержит encrypted payload и подписанный manifest; inner ZIP имеет allowlisted vault/** и typed state sections. Проверяются actual streamed sizes, member counts/digests, duplicate/casefold paths, symlinks/hardlinks/device entries, traversal, depth и schema. Encryption не заменяет structural validation; compressed checksum не заменяет signature/trust.

Для initial format mastermind-backup/v1 поддерживается restore этого же формата. Каждый следующий релиз сохраняет чтение всех ранее production-published форматов либо поставляет явный tested converter до удаления reader. DB migration не делает старый ZIP автоматически совместимым.

Recovery prerequisites: compatible release artifacts, backup trust public key, age identity, нужные pepper versions и deployment bootstrap secrets. Ключи нельзя восстанавливать только из данных, зашифрованных ими же. RPO измеряется по последнему подтверждённому полному архиву; mirror имеет отдельный lag и не подменяет его.

---

<a id="section-138"></a>

# 138. Exposure registry: без индексации

| Surface | Категория |
| --- | --- |
| Login/owner origin | Public authenticated, non-indexable, вход с любого IP |
| Owner APIs/Settings/Analytics/Documentation | Owner auth, no-store/non-indexable |
| Raw KasmVNC/supervisor/worker | Internal private, no public ingress |
| Neptune/Updater/export controls | Private local scoped identity |
| /s/{token} и Share API | Capability-protected, одна note projection, non-indexable |
| Crusher activation/submission/status | Public capability, без результатов/Vault доступа |
| Health | Минимальный bounded public response; detailed status protected |
| Debug/OpenAPI/source maps/manifests | Не опубликованы либо явно защищены |

Все доступные browser страницы имеют X-Robots-Tag: noindex, nofollow, noarchive; HTML также meta robots. Нет sitemap, feeds, llms.txt с контентом/ссылками, public search, каталога notes или searchable-public режима. Robots policy disallow не перечисляет tokens/приватные paths. Noindex не заменяет auth и не обещает удаление уже сохранённых третьей стороной копий.

Bot/User-Agent/verification headers не дают privilege. Part 08 продвижение N/A для текущего scope. Изменение на indexable publication требует отдельного будущего продуктового решения.

---

<a id="section-139"></a>

# 139. Контракт интеграции Neptune

## 139.1. Typed enrollment

Одна операция mastermind enrollment создаёт project/deployment registration с двумя независимыми pipelines: recovery archive и mirror mode zip-tree/root mastermind. Используется существующий host daemon, не второй процесс. Исходники baseline уже содержат эту модель (§147); до Mastermind acceptance нужны реальные integrated tests.

Workflow: owner получает typed setup code в Saturn Synchronization → Settings Backup Initialize → Core передаёт code/own identity в Updater → durable REQUESTED/INSTALLING/ENROLLING/COMPLETED или FAILED → UI перечитывает фактический Neptune state. COMPLETED требует наличия обеих правильных scopes/roots. Partial configuration показывает Repair; retry idempotent и не создаёт чужую/дублирующую registration.

Setup code 32 characters, 15 minutes, не сохраняется Shell и не смешивается с 6-digit Crusher code. Archive/mirror credentials разные. Saturn владеет расписаниями, enabled/revoked desired state, quotas и remote commands. Local UI: status, Initialize/Repair, Open Synchronization.

## 139.2. Export/transport

Core exposes private local POST archive export (full encrypted ZIP) и POST mirror export (plain protected Vault tree ZIP) с отдельной проверкой export identity/purpose. Одновременные snapshots coalesce по generation; incomplete artifact не выдается как complete.

Archive получает size/SHA-256 receipt, exact bytes и stable idempotency run key. Mirror zip-tree получает snapshot generation и inventory; после upload/delete reconcile возвращает result/verified generation. Readiness различает agent running, registered, configured и successful pipeline.

## 139.3. Scoped interactive reader — обязательное расширение

Для owner @saturn и owner-origin Crusher Neptune предоставляет versioned local contract:
~~~text
GET /api/v1/projects/{project_id}/resources?path={logical_path}&cursor={opaque}&limit=100
GET /api/v1/projects/{project_id}/resource-metadata?path={logical_path}
GET /api/v1/projects/{project_id}/resource-content?path={logical_path}
~~~

Эти routes — требуемый новый consumer contract, не заявление об их наличии в baseline. Core передаёт own scoped local identity, purpose и canonical logical path. Neptune сам получает Saturn read credential; permanent Saturn keys не передаются Core.

Listing возвращает только direct children: canonical path, type, display name, MIME, size, ETag, opaque next_cursor. Limit ≤100, один page per request, timeout/cancellation и maximum response 1 MiB. Scope Root задаётся typed service policy; '..', double decoding, absolute host paths и escape через symlink отвергаются.

Content streaming возвращает Content-Type/Length/ETag/Accept-Ranges; single valid Range →206, invalid/unsatisfiable→416, missing→404, forbidden→403, dependency unavailable→503. Multi-range отклоняется. If-Range/ETag mismatch возвращает новое полное representation по HTTP semantics либо явный conflict до stream; нельзя смешивать bytes разных revisions.

Отмена browser request отменяет upstream; RAM bounded, нет whole-file buffer. MIME не разрешает active HTML/SVG execution. Token не попадает в URLs/logs. Share/Crusher-public principal не может вызвать эти routes через Core независимо от написанного path.

Контракт реализуется в Neptune и при необходимости Saturn, затем выпускается и квалифицируется до Mastermind. Прямой Saturn fallback запрещён.

---

<a id="section-140"></a>

# 140. Совместимый release и Updater profile

## 140.1. Manifest и group apply

Signed Mastermind manifest включает service-qualified version/source SHA, platform, три image digests, pinned Obsidian/Bridge/model artifacts, DB schema/source compatibility, tested dependency tuple и health profile. Release notes/bundle URL/checksums привязаны к проверенным bytes.

Updater получает own head_id/request_id/verified version, а repository/trust/profile разрешает независимо. Allowlisted group содержит только Core, Runtime, worker и собственные data generations. Поддерживаются typed quiesce, snapshot handoff, group apply, migration, functional health и rollback; arbitrary Compose/shell/URL/image/path входы запрещены.

## 140.2. Streaming backup handoff

Расширение Updater заменяет inline dataBase64 для Mastermind на bounded stream:
~~~text
POST /v1/heads/{head_id}/backup-spools
PUT  /v1/heads/{head_id}/backup-spools/{spool_id}/content
POST /v1/heads/{head_id}/backup-spools/{spool_id}/seal
~~~

Authenticated local create принимает request_id, fixed .zip filename, size и SHA-256. Updater резервирует квоту и выдаёт opaque spool_id, bound к head/request. PUT передаёт bytes без base64 в file mode 0600 под root-owned parent; seal сверяет actual size/hash, fsync и marks immutable. Apply принимает только sealed spool_id того же head/request; произвольный host path не передаётся.

Disconnect до seal оставляет incomplete state с TTL; повторная загрузка начинает тот же bounded объект заново, не создаёт неограниченные copies. Expired/wrong-head/used-for-other-request/symlink/hash mismatch отклоняются. Retry Apply с тем же request_id возвращает существующий job. Срок unclaimed spool 1 час; backup completed update сохраняется 24 часа, rollback failure удерживает его до explicit repair в пределах reserved quota.

Точный prefix может быть приведён к существующему Updater router при реализации с сохранением этих wire semantics; versioned OpenAPI фиксируется producer/consumer contract tests. Legacy inline endpoint остаётся для старых consumers; Mastermind не обходит 128 MiB omission/chunk-by-base64.

## 140.3. Gate

Baseline Updater v0.4.7 не удовлетворяет handoff для архива около 350 MiB. До UI Apply нужен новый released Updater с этими capability flags и group tests. До этого discovery показывает incompatible, Apply disabled с точной причиной, обычный Vault работает.

Pre-update backup делается под retained write barrier; все artifacts pre-pulled до него. Failure любой части возвращает старый components+data комплект по §88, health проверяет функциональность, не только process alive. Обновления Mastermind, Updater и Neptune имеют отдельные jobs/labels.

---

<a id="section-141"></a>

# 141. Численные resource budgets

Default supported host для qualification: Linux x86-64, 4 vCPU, 8 GiB RAM, локальное постоянное filesystem; arm64 объявляется поддержанным только после собственного release/test. Space preflight использует f_bavail, а не общий размер диска. Это начальные нормативные limits, не результаты измерения.

| Путь | Default limit |
| --- | --- |
| JSON ordinary API / headers / URI | 1 MiB / 16 KiB / 8 KiB |
| Owner .md read/write / public Share projection | 8 MiB / 1 MiB; oversized share недоступен с ясной ошибкой |
| Raw text Crusher | 1 MiB |
| Crusher upload/download source | 2 GiB на source; два concurrent uploads |
| Crusher jobs | Один active, очередь 100 globally / 20 на public session |
| Worker resource | 2 vCPU, 2 GiB RAM; один source job |
| Core / Runtime | 2 GiB RAM / 3 GiB RAM, отдельные cgroup limits |
| Incoming/work quota | 16 GiB общая; reserve при acceptance |
| Source archive expansion | 8 GiB, 10000 members, depth 16, 1000:1 maximum ratio |
| Source processing | Fetch/clone 15 min, extract 20 min, один provider attempt 5 min, весь accepted job 60 min |
| Full backup / Vault mirror ZIP | 8 GiB compressed, 32 GiB expanded, 100000 members, depth 64, per-member 8 GiB |
| Backup recovery expansion ratio | 1000:1; encrypted/store outer wrapper также ограничен absolute bytes |
| Backup/recovery spool | 96 GiB reserved cap, одна snapshot/restore/update operation одновременно |
| Snapshot editor pause | Qualification target ≤30 s для representative Vault; hard deadline 120 s до отказа |
| Full local restore | Qualification target ≤15 min для representative Vault, hard deadline 60 min |
| Backup stream | 1 MiB working buffer, extra streaming RSS ≤128 MiB; deadline 60 min, no-progress timeout 60 s |
| Neptune media stream | 256 KiB buffer, 4 streams owner-wide, no-progress timeout 60 s |
| Extraction diagnostic output | 64 KiB/job, sanitized/truncated с явной отметкой |
| Локальные embeddings | Batch ≤16 chunks, 512 tokens/chunk; rebuild deadline 30 min |
| AI source input / output | ≤32000 input model tokens/job after local extraction/chunking; output ≤8000 tokens |
| AI Vault context | §71: ≤12000 unique / ≤24000 transmitted tokens/job, max 8 hierarchy levels |
| In-memory graph display | До 5000 visible nodes / 20000 edges; выше — viewport/filter и LOD |
| Derived API lists | Default page 100, max 500; public Shares не перечисляют Vault |
| Temporary TTL | accepted source пока job active; success cleanup immediate, failed ≤24 h |
| Restore old generation | 24 h после functional success, с reserved space |

До snapshot/restore/acceptance резервируется worst-case space для source, expanded payload, staged new state, необходимого old state и ZIP. Учитываются текущие reservations других операций. Если бюджет/f_bavail не покрывает расчёт, операция отклоняется до изменения live state; advertised max не обещает выполнение при недостатке диска.

Дедлайны не прерывают атомарный commit посередине: при переходе в commit/recovery сохраняется journal и завершается безопасный outcome. Выросший Vault сверх limit требует явного validated изменения configured bounds и повторного round-trip, не обрезания данных.

Все bounds enforced в backend/worker и согласованы с host Nginx. Full note/backup/result buffers не удерживаются целиком в RAM; проверка на представительном архиве около 350 MiB и на границах обязательна.

---

<a id="section-142"></a>

# 142. Verification matrix и обязательные failure paths

| Контракт | Минимальное доказательство |
| --- | --- |
| Canonical Vault/uniqueness | Concurrent Core/Obsidian operations, startup conflicts, no-clobber create |
| References | Longest-match/Unicode/exclusions, rename/native propagation, deleted target после cache rebuild |
| Shared data consistency | Crash на каждом filesystem/SQLite boundary и recoverable outcome |
| Activity | Autosave dedup, owner attribution, restart session handling, no public/automated increments |
| Shares | Hash/password/expiry/revoke, ETag race, никаких resource resolvers, protected projection, path revival |
| Crusher capability | One-time activation race, scoped jobs/sources/status-only tickets, отсутствие result output, expiry during accepted work |
| Crusher processing | SSRF redirects/DNS/browser subrequests, archive/Git isolation, schema/privacy checks |
| Persistent jobs | Worker death до/после side effect, lease recovery, no duplicate commit |
| Neptune | Exact profile, archive+mirror separately, receipt, outage/recovery, scope/Range |
| Backup | Full clean restore, shell-secret exclusion, opaque plugin-secret encrypted round-trip, mismatched/corrupt/oversized ZIP, interrupted rollback |
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

# 144. Порядок реализации и проверки

1. Зафиксировать policy digests и baseline §147; перенести принятые исключения и integration contracts в применимые project records (§148).
2. Реализовать coordinator/Bridge/supervisor с no-lost-update и interrupted rename fixtures; затем file state/journals, grammar/history и incremental indexes.
3. Квалифицировать существующий двухканальный Mastermind enrollment и scheduled mirror; реализовать scoped Neptune reader.
4. Реализовать и выпустить Updater large spool/group profile; зависимости зафиксировать точными новыми released versions.
5. Проверить complete backup/restore/rollback до подключения опасных mutations, затем Shell/auth/Vault runtime, Shared projection и capability tests.
6. Добавить worker/extractors/Crusher и bounded hierarchy placement, локальные embeddings; проверить source/privacy/expiry/exactly-once.
7. Импортировать representative Vault, прогнать browser/themes/8-hour session, resource и real-agent acceptance.
8. Собрать signed Mastermind release, выполнить bootstrap/update/recovery и все §§130/142/143 gates; production qualification оформить отдельно.

Продуктовые решения закрыты этим документом. Feasibility/contract/benchmark проверки являются обязательными задачами разработки, а не новыми вопросами владельцу. Если реализация не выполняет выбранный контракт, исправляется реализация либо оформляется явное изменение требований; неизвестный результат теста не считается разрешённым исключением.

---

<a id="section-145"></a>

# 145. Что изменено относительно адаптированной концепции

| Область | Финальное решение / компромисс |
| --- | --- |
| UI | Собственный Dashboard/Shell унифицирован; native Vault — принятое исключение |
| Writes | Общий coordinator, flush/stop Runtime перед внешним commit; короткая пауза ради отсутствия lost updates |
| Native links | Используется Obsidian rename propagation; Bridge отвечает за @ и согласование state |
| @ grammar | Longest match + явно долговечный reference history для broken targets |
| Plugins/secrets | Пользовательские .obsidian files сохраняются; только shell secrets переходят в Volt через Kernel |
| Shares | Saturn token/session UX; никакого resource resolution; защищённая text projection для edit |
| Share identity | Path-based revival после delete/recreate принят; no note UUID |
| Индексация | Shared и остальные страницы non-indexable |
| Crusher UI | Только source, stages/progress/status; result API исключён |
| Placement | root/#main/вложенные #key, bounded selected context, Inbox fallback |
| Neptune | Один enrollment, два существующих profiles; initial mirror по расписанию вместо 5-second promise |
| Recovery | Полный encrypted payload внутри ZIP, включая opaque Vault; keys вне archive |
| Updates | Typed group трёх компонентов и streamed spool вместо 128 MiB inline |
| Versions | Проверенные последние релизы как baseline; новые contract gaps требуют отдельных последующих релизов |
| Budgets/retries | Численные defaults, три total attempts, crash-safe local commit |

Предыдущие черновики сохранены для истории. Для разработки применяется этот полный документ и приведённые в нём общие требования; отдельного списка неутверждённых продуктовых решений нет.

---

<a id="section-146"></a>

# 146. Реестр принятых решений MM-Q01–MM-Q20

Все записи имеют статус **DECIDED**. Основание — ответы владельца и поручение выбрать рекомендуемые решения для остальных деталей. Слово «оптимальный» означает конкретный выбранный вариант ниже; оно не оставляет обязательную развилку реализации.

| ID | Тема | Основание | Решение | Разделы |
| --- | --- | --- | --- | --- |
| <a id="mm-q01"></a>MM-Q01 | Граница UI | Решение владельца | Общие правила для Shell/public UI; native Vault наследует Obsidian UI/UX. | [§13](#section-13), [§16](#section-16) |
| <a id="mm-q02"></a>MM-Q02 | Write coordination | Делегирован оптимальный выбор | Core coordinator + Bridge quiesce + supervisor stop для внешних commits; неизвестные plugin writes диагностируются. | [§4](#section-4), [§80](#section-80), [§81](#section-81) |
| <a id="mm-q03"></a>MM-Q03 | Rename/grammar | Ответ владельца + уточнение | Native rename обновляет [[...]] через Obsidian; Bridge обновляет @; полная grammar и durable history для broken targets. | [§19](#section-19), [§22](#section-22), [§24](#section-24) |
| <a id="mm-q04"></a>MM-Q04 | Mastermind enrollment | Ответ владельца + проверка кода | Один typed enrollment, независимые archive и zip-tree mirror; существующую основу квалифицировать. | [§139](#section-139), [§147](#section-147) |
| <a id="mm-q05"></a>MM-Q05 | Neptune reader | Принята рекомендация | Scoped local reader/Range API в Neptune, отдельные scopes; без прямого Saturn fallback. | [§34](#section-34), [§139](#section-139) |
| <a id="mm-q06"></a>MM-Q06 | Mirror policy | Оптимальный выбор по проверенному baseline | Первый релиз: scheduled mirror default 5 min, policy в Saturn. Принятый компромисс вместо исходного 5-second SLA. | [§83](#section-83), [§87](#section-87) |
| <a id="mm-q07"></a>MM-Q07 | Snapshot/restore | Принята рекомендация | Общий write barrier, immutable staging, consistent DB/Vault, generation journal и полный rollback. | [§86](#section-86), [§88](#section-88) |
| <a id="mm-q08"></a>MM-Q08 | Plugin secrets | Решение владельца | Не сканировать/менять/переносить существующие secrets .obsidian; shell secrets — Volt через Kernel; Vault сохраняется целиком. | [§10](#section-10), [§14](#section-14), [§137](#section-137) |
| <a id="mm-q09"></a>MM-Q09 | Размер backup | Оценка владельца + выбранное решение | Около 350 MiB; full encrypted ZIP, streaming spool; baseline limit 8 GiB compressed/32 GiB expanded. | [§86](#section-86), [§140](#section-140), [§141](#section-141) |
| <a id="mm-q10"></a>MM-Q10 | Release unit | Принята рекомендация | Один подписанный комплект Core/Runtime/worker/Obsidian/Bridge/schema, typed apply/rollback. | [§6](#section-6), [§105](#section-105), [§140](#section-140) |
| <a id="mm-q11"></a>MM-Q11 | Shared resources | Решение владельца | Запрещены все internal/external links/embeds/resolvers; server text projection и rejection новых reference constructs. | [§53](#section-53), [§54](#section-54), [§55](#section-55), [§56](#section-56), [§57](#section-57) |
| <a id="mm-q12"></a>MM-Q12 | Индексация | Решение владельца | Без индексации, discovery и public catalog. | [§138](#section-138) |
| <a id="mm-q13"></a>MM-Q13 | Share URL | Решение владельца + проверка Saturn | Saturn issuance/HMAC/session UX: URL доступен при создании и в памяти текущей owner session, не восстанавливается из списка. | [§47](#section-47), [§48](#section-48), [§49](#section-49) |
| <a id="mm-q14"></a>MM-Q14 | Share identity | Решение владельца | Delete/recreate того же path может открыть новую note по старому active Share; revoked/expired не оживают. | [§52](#section-52) |
| <a id="mm-q15"></a>MM-Q15 | Crusher UI | Решение владельца | Только source, progress/stage/status; результат/путь/preview/download отсутствуют. | [§13](#section-13), [§61](#section-61), [§62](#section-62) |
| <a id="mm-q16"></a>MM-Q16 | Job recovery | Принята рекомендация | Durable commit intent + reconciliation, один локальный commit; source потерян после restore — FAILED, resubmit. | [§126](#section-126) |
| <a id="mm-q17"></a>MM-Q17 | Isolation/budgets | Принята рекомендация | Заранее развёрнутый worker без Vault/secret mounts, численные quotas/deadlines. | [§6](#section-6), [§95](#section-95), [§141](#section-141) |
| <a id="mm-q18"></a>MM-Q18 | Retries | Принята рекомендация | Три total attempts, delays 5/30 s, bounded Retry-After; durable budget. | [§75](#section-75) |
| <a id="mm-q19"></a>MM-Q19 | Dependencies/secrets | Решение владельца | Последние стабильные published releases на время проверки; exact pins, новые gaps выпускаются перед Mastermind. | [§10](#section-10), [§147](#section-147), [§148](#section-148) |
| <a id="mm-q20"></a>MM-Q20 | Placement/privacy | Решение владельца + рекомендация | root → #main → #key → nested #key; bounded selected context; local embeddings, Inbox fallback, без full Vault upload. | [§70](#section-70), [§71](#section-71), [§78](#section-78), [§123](#section-123) |

Для MM-Q02 принята пауза Runtime вместо недоказанного бесшовного multi-writer режима. Для MM-Q06 принят scheduled mirror на существующем profile вместо добавления continuous mode в первый релиз. Для MM-Q09 нельзя сохранить legacy 128 MiB handoff: он меньше текущего пользовательского архива, поэтому расширение Updater обязательно. Это зафиксированные компромиссы, не скрытые ослабления требований.

Открытых продуктовых вопросов из прежнего реестра не осталось. Интеграционные проверки, измерение реального архива/паузы и испытания provider quality остаются работой разработки; для них ниже заданы критерии, а не вымышленные PASS.

---

<a id="section-147"></a>

# 147. Проверенный baseline и источники

## 147.1. Последние релизы соседних сервисов

Проверка GitHub Releases API и tag commits выполнена 2026-09-14, 19:36–19:38 UTC. Выбраны опубликованные stable service-qualified releases, без draft/prerelease/plain-v CI tags. Реестры содержали менее 100 releases каждый и прочитаны полностью одной страницей. Состояние production серверов в этой задаче не проверялось.

| Сервис | Последний опубликованный релиз | Published at UTC | Source commit SHA |
| --- | --- | --- | --- |
| kernel | [kernel-v0.2.10](https://github.com/psewdon1m-exocortex/kernel/releases/tag/kernel-v0.2.10) | 2026-09-13T23:05:16Z | ddacbf517bf20b53f8d152043bc0eb7d56bf240d |
| volt | [volt-v0.1.5](https://github.com/psewdon1m-exocortex/volt/releases/tag/volt-v0.1.5) | 2026-09-13T22:58:24Z | cdf3eeba2976fcddcd8b3917a979523905f86301 |
| saturn | [saturn-v0.1.14](https://github.com/psewdon1m-exocortex/saturn/releases/tag/saturn-v0.1.14) | 2026-09-13T23:07:26Z | c58838ad5813aac84a61b61e2e50829fb1c2022d |
| neptune | [neptune-v0.1.7](https://github.com/psewdon1m-exocortex/neptune/releases/tag/neptune-v0.1.7) | 2026-09-14T18:46:53Z | 34222db49ca9e3b18ba9ee99100e9b035010570e |
| updater | [updater-v0.4.7](https://github.com/psewdon1m-exocortex/updater/releases/tag/updater-v0.4.7) | 2026-09-14T18:44:49Z | 6a9046434c2a60f9c3528afd55f70b6b0227cbf7 |
| chronos | [chronos-v0.1.1](https://github.com/psewdon1m-exocortex/chronos/releases/tag/chronos-v0.1.1) | 2026-09-14T19:30:40Z | 0fb6b21d59cfa26a8ae94ca7b0b1f266e3717f82 |

Gryphon/Laboratory не являются runtime dependencies Mastermind и в compatibility tuple не включаются. Chronos указан как optional feature dependency, но его baseline также взят из последнего релиза.

Это стартовый baseline разработки и contract tests, а не список доказанно совместимых minimum versions. Если требуется новый API, producer сначала выпускает новый stable release; Mastermind pin обновляется до этого конкретного релиза после integration test. Runtime floating latest не используется. Перед первым implementation release discovery повторяется, чтобы новые stable versions не потерялись.

## 147.2. Опубликованные asset digests

Ниже digest metadata из GitHub release assets, не утверждение о выполненном скачивании/исполнении всех binaries. Bootstrap/CI обязаны проверить реальные downloaded bytes и подпись manifest отдельно. Для таблицы выбраны deployment bundle либо Linux x64 agent bundle.

| Сервис | Artifact | Bytes | Published SHA-256 |
| --- | --- | --- | --- |
| kernel | [kernel-0.2.10-compose.tar.gz](https://github.com/psewdon1m-exocortex/kernel/releases/download/kernel-v0.2.10/kernel-0.2.10-compose.tar.gz) | 3130161 | d04e6fb58fffd3c62780d9ed70e6a41d854f1f3f7db02f644c57cda945e7d640 |
| volt | [volt-0.1.5-compose.tar.gz](https://github.com/psewdon1m-exocortex/volt/releases/download/volt-v0.1.5/volt-0.1.5-compose.tar.gz) | 3136286 | 7d007708dc301d625b7c95d4ac462c518dbec3ff2c4108a45883e402ab48ab2b |
| saturn | [saturn-0.1.14.zip](https://github.com/psewdon1m-exocortex/saturn/releases/download/saturn-v0.1.14/saturn-0.1.14.zip) | 3170915 | 60624f3977055c24e099a7a07c1169d5e68cb9ac84bf5bdb8683372026b6ab79 |
| neptune | [neptune-linux-0.1.7-linux-x64.tar.gz](https://github.com/psewdon1m-exocortex/neptune/releases/download/neptune-v0.1.7/neptune-linux-0.1.7-linux-x64.tar.gz) | 45211897 | 0876b16110fa81cb2b654682475702260f2f0719aff624caa79df59f46e06a23 |
| updater | [updater-0.4.7-install.tar.gz](https://github.com/psewdon1m-exocortex/updater/releases/download/updater-v0.4.7/updater-0.4.7-install.tar.gz) | 3132808 | 22b8350c5026dd6130c1266b922c568dd803906ffbf5bdda6a18e6bce8d1c847 |
| chronos | [chronos-0.1.1-compose.tar.gz](https://github.com/psewdon1m-exocortex/chronos/releases/download/chronos-v0.1.1/chronos-0.1.1-compose.tar.gz) | 3141835 | 94366c633f9d2ac030faa1a3abe0694732301e80250d86839da9fa3816a270a8 |

## 147.3. Что установлено чтением кода

- [Saturn Share service на release tag](https://github.com/psewdon1m-exocortex/saturn/blob/saturn-v0.1.14/packages/shares/src/share.service.ts): random token, HMAC с pepper, create-only URL response; list не содержит capability.
- [Saturn owner UI на release tag](https://github.com/psewdon1m-exocortex/saturn/blob/saturn-v0.1.14/apps/web/src/app.tsx): capability доступна в текущей owner session; historical Copy отключён без неё.
- [Saturn backup enrollment](https://github.com/psewdon1m-exocortex/saturn/blob/saturn-v0.1.14/apps/api/src/backup.controller.ts): mirrorRoot mastermind, отдельный mirror device token, mode zip-tree.
- [Neptune registration model](https://github.com/psewdon1m-exocortex/neptune/blob/neptune-v0.1.7/src/Neptune.Core/Models.cs) и [MirrorWorker](https://github.com/psewdon1m-exocortex/neptune/blob/neptune-v0.1.7/src/Neptune.Linux/MirrorWorker.cs): archive registration с отдельным mirror, interval-based scheduling, tree export/download/extract/hash upload; bounds 8 GiB archive/32 GiB expanded/100000 entries. Continuous delivery за 5 секунд из этого не следует.
- [Updater enrollment](https://github.com/psewdon1m-exocortex/updater/blob/updater-v0.4.7/internal/component/neptune_enrollment.go): принимает mastermind root и zip-tree mode.
- [Updater engine](https://github.com/psewdon1m-exocortex/updater/blob/updater-v0.4.7/internal/engine/engine.go): decodeBackup принимает inline base64 и отклоняет decoded bytes свыше 128 MiB. Для оценочных 350 MiB нужна доработка §140.

Neptune/Updater local HEAD совпали с соответствующими release SHA. Local Saturn HEAD был другим, поэтому Share/enrollment behavior проверено дополнительно именно по release tag, а не выдано за release по одному checkout.

Наличие этих source paths не означает успешный enrollment/restore/Range под Mastermind. Required read API, encrypted archive contract, refresh обоих pipelines и group rollback требуют acceptance §§139–142/148.

## 147.4. Центральная документация

Источник — локальные файлы .docs на 2026-09-14. Репозиторий general: HEAD bb381b3ac03dcdb60d570aaef226348b343b9446. На момент чтения Part 12 имеет уже существующие локальные изменения, поэтому эффективная нормативная база закрепляется также полными content SHA-256 ниже; одним HEAD она не описывается. В этой задаче центральные файлы не изменяются.

| Part | SHA-256 |
| --- | --- |
| [PART_00](docs/policy/PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md) | de5c3e3a30efb5c96efd129b6e80fae796c0b51f38230a499237dd3f2aa8a8fe |
| [PART_01](docs/policy/PART_01_INTERFACE_AND_INTERACTION_UNIFICATION.md) | e312ba36d63a55389b9c2172f06207b2da2b65d0f7f2f66e2591598ffd8a125e |
| [PART_02](docs/policy/PART_02_OBSERVABILITY_AUDIT_AND_LOG_EXPORT.md) | 29aca751349f7f0c5e632c1f943f183c716ee6e969bd7eaa7ff6f50f8570d32a |
| [PART_03](docs/policy/PART_03_BACKUP_AND_RECOVERY.md) | 17ffe419f75a227ec827951d6f3d39eb281f0d0060ae8d0ae5a3647b1a537f36 |
| [PART_04](docs/policy/PART_04_BOOTSTRAP_AND_DEPLOYMENT.md) | 768f5f4ff3473f5906fea90ef0fe6db74d4d6b3b017dc00ea5556d0c9e310696 |
| [PART_05](docs/policy/PART_05_CI_RELEASES_AND_LOCAL_UPDATES.md) | 294301cf61b44788f10f7025756861e66d81f6c0d0b3d6747804c1f0c016d0d0 |
| [PART_06](docs/policy/PART_06_UNIFIED_ACCEPTANCE_CHECKLIST.md) | 76ca402d572a47d6bf74685e4da0129c790005895ed6b2e558658bd7730946f3 |
| [PART_07](docs/policy/PART_07_SECURITY_AND_EXPOSURE_CONTROL.md) | 0eeb1b476ad45ea2d0ef48f0d0881e51006db66560684406c58f0d1dec495d5c |
| [PART_08](docs/policy/PART_08_SEO_AND_GEO.md) | f89429750d951d3f8d7d2052c5d267b58ff9fe4f60f65bd374101f6083ee6416 |
| [PART_09](docs/policy/PART_09_SERVICE_AGENTS_DEPLOYMENT_AND_LIFECYCLE.md) | 92a1e91cfd72eb86e70e0c4e81739be52edb98367ac43423da01275eacd90def |
| [PART_10](docs/policy/PART_10_SERVICE_AGENTS_UI_AND_OPERATOR_WORKFLOWS.md) | 02bca5ce723e9504f27351f931ab45f4f32c28a3bd80757d687310233694fdd5 |
| [PART_11](docs/policy/PART_11_INITIAL_MULTI_SERVICE_DEPLOYMENT.md) | 240998e8bb2c4655aaa42e393f7052d9d21e53a1e4bfab53f30ab0840dc9fdb9 |
| [PART_12](docs/policy/PART_12_KNOWN_DEPLOYMENT_AND_OPERATIONS_PROBLEMS.md) | 50c76318747867575935e77fff0520c9517fe513912fef4c8c08944de9562ac5 |

Основа адаптации: mastermind_service_requirements_adapted.md SHA-256 bd9402636ae6674662cce0e815eb4fc697e67319577217ccb40a6ed451d3a209. Исходное ТЗ: f7b16e08594e4554eb027a741fe8f66dfc28fb384edb422e33f2677aaf14bee4. Эти файлы не изменяются данной редакцией.

## 147.5. Внешние component references

Native rename API: [Obsidian FileManager.renameFile](https://docs.obsidian.md/Reference/TypeScript+API/FileManager/renameFile). Сама поддержка всех UI/plugin entry points подтверждается compatibility tests pinned Obsidian, а не одним наличием метода.

Локальная модель: [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small), source revision 614241f622f53c4eeff9890bdc4f31cfecc418b3, MIT по model card. ONNX conversion/tokenizer/weights digest фиксируются при сборке release artifact; непроверенный скомпилированный digest здесь не выдумывается.

Формат backup encryption: [age v1](https://age-encryption.org/v1), реализация [age](https://github.com/FiloSottile/age). Tool versions, Obsidian/KasmVNC и transitive packages закрепляются в первом Mastermind component lock по последнему доступному stable выпуску на момент сборки, затем проходят совместимость; automatic runtime update отсутствует.

---

<a id="section-148"></a>

# 148. Обязательные изменения и проверки соседних систем

Это backlog интеграции с принятыми контрактами. Статус всех execution проверок на дату документа — NOT_RUN; приведённое чтение кода не закрывает их.

| Область / где | Конкретное действие | Критерий завершения |
| --- | --- | --- |
| Mastermind Core/Bridge/runtime supervisor | Implement coordinator §80, native rename + @, recoverable batch/dirty buffers | Race/crash fixtures без lost update; unsupported plugin drift виден, pre-write guarantee не выдуман |
| Mastermind Share API/renderer/editor | Удалить resource grants/resolvers, реализовать protected projection, Saturn capability UX | Нельзя получить internal/external resource любым public payload/API; stale edit 409 |
| Mastermind Crusher UI/API/worker | Source/progress-only, status ticket, hierarchy packet builder/local embeddings | Ни result/path/context в responses; token/source budgets enforced; commit один |
| Saturn apps/api/src/backup.controller.ts и backup-ingest | Квалифицировать существующий mastermind enrollment, two credentials, revoke/repair/idempotency | Clean enrollment, partial failure/retry без второго чужого device; оба pipelines observed |
| Saturn Synchronization policy/UI | Archive и mirror раздельные status/schedules, bounds/private mirror classification | Schedule/disable/revoke применяются Neptune; .obsidian не попадает в public folder shares |
| Neptune Models/ProjectRegistry/MirrorWorker/BackupWorker | Reuse typed zip-tree; add generation/receipt reconciliation по потребности, проверить bounds | Byte/hash mirror + opaque encrypted archive; outage/restart/delete protection |
| Neptune Program/Core read adapter — новый контракт | Добавить scoped listing/metadata/content/Range §139, отдельный Saturn read scope | Real Saturn 206/416/cancellation/scope/large-media contract suite |
| Updater model/engine/store/API | Добавить streaming spool §140 вместо inline base64 для Mastermind | >350 MiB и верхняя граница, bounded RSS/disk, wrong-head/hash/path rejection |
| Updater deployment/group profile | Allowlisted Core/Runtime/worker/Bridge/schema apply+rollback | Failure каждого компонента возвращает old data/components; no stale bind mounts |
| Kernel Register / Volt | Создать typed shell secret refs, recovery/signing/pepper keys и escrow metadata | Cold start/rotation/restore consumer probes; plugin data не трогается |
| Chronos adapter / contract fixtures | Привязать discovery/auth/event schema к последнему released baseline | Owner card start/end/TTL/outage без public Share access |
| .docs Part 01 | Applicability embedded Obsidian UI/UX exception | Общая документация соответствует решению MM-Q01 |
| .docs Parts 03/07 | Opaque user Vault, protected encrypted payload, separate shell/plugin ownership | Нет обещания secret-free plaintext Vault; round-trip сохраняет plugin files |
| .docs Parts 05/09/10 | Mastermind group/spool/read profile и существующий two-pipeline workflow | Producer/consumer contracts и UI tables согласованы |
| Root/service README, docs/api, recovery/runbook, release manifest | Exact tested dependency tuple и operator workflows | Ссылки/версии/пределы соответствуют реализации; artifacts не зависят от sibling checkouts |
| Acceptance / Part 12 reports | Оценить каждый applicable/active ID на exact candidate SHA | PASS/FAIL/N/A/NOT_RUN с фактическим evidence, без фиктивной production готовности |

Новая функциональность соседнего сервиса поставляется самостоятельным подписанным релизом до зависимого Mastermind. В документе не назначаются несуществующие номера будущих версий. Зафиксированные здесь новые endpoints/fields реализуются producer-first, затем consumer pins и contracts обновляются вместе.

Приёмка Mastermind не требует возвращаться к старому реестру вопросов. Она требует выполнить эти работы, полный DoD и реальные проверки.

---
