# Mastermind — открытые вопросы и решения для обсуждения

**Статус:** все перечисленные вопросы открыты; варианты не утверждены.  
**Версия:** 1.0-draft.  
**Дата:** 2026-09-14.  
**Связанный документ:** [адаптированная концепция](mastermind_service_requirements_adapted.md).  
**Исходник:** [ТЗ 1.0](mastermind_service_requirements.md).  
**Правило решений:** [Part 00](../.docs/PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md).

Здесь собраны неопределённости исходного ТЗ и вопросы, возникшие при его сопоставлении с общими требованиями. Это предложения для обсуждения, а не список разрешений на отступление от безопасности, источника истины или восстановления.

Рекомендация выражает предпочтительный вариант для оценки. Она становится требованием только после явной записи принятого решения, изменения связанных разделов концепции и, если требуется, центральной документации.

Открытый вопрос блокирует утверждение зависящего от него контракта. Inventory, исследования, воспроизводимые прототипы и независимая работа могут продолжаться. Наличие описанного здесь риска не утверждает, что он уже обнаружен в работающем сервисе: Mastermind пока рассматривается на уровне концепции.

## Реестр

| ID | Вопрос | Тип | Статус |
| --- | --- | --- | --- |
| [MM-Q01](#mm-q01) | Граница Web Shell / Obsidian и поддерживаемый UX | Продуктовое решение + применимость Part 01 | OPEN |
| [MM-Q02](#mm-q02) | Один координатор операций Core и непосредственных writes Obsidian | Архитектурная реализуемость / data integrity | OPEN |
| [MM-Q03](#mm-q03) | Полная грамматика @references и восстановление broken links | Продуктовый синтаксис + parser contract | OPEN |
| [MM-Q04](#mm-q04) | Регистрация профиля Mastermind: recovery ZIP + Vault mirror | Общий межсервисный контракт | OPEN |
| [MM-Q05](#mm-q05) | Neptune как scoped reader и Range gateway | API gap / capability contract | OPEN |
| [MM-Q06](#mm-q06) | Continuous mirror, Saturn policy и сроки репликации | Продуктовый SLA + межсервисная policy | OPEN |
| [MM-Q07](#mm-q07) | Согласованный snapshot Vault + SQLite и restore transaction | Recovery architecture | OPEN |
| [MM-Q08](#mm-q08) | Состав .obsidian, plugin trust, export и запрещённые backup данные | Compatibility + security/recovery policy | OPEN |
| [MM-Q09](#mm-q09) | Большой backup: лимиты, spool и передача в Updater | Расширение transport/recovery contract | OPEN |
| [MM-Q10](#mm-q10) | Один release для двух контейнеров, Bridge и schema | Типизированный update profile | OPEN |
| [MM-Q11](#mm-q11) | Owner grants для внешних ресурсов в Share | Авторизация / продуктовые права | OPEN |
| [MM-Q12](#mm-q12) | Share — обмен по ссылке или индексируемая публикация | Продуктовый scope / exposure | OPEN |
| [MM-Q13](#mm-q13) | Повторное копирование постоянного Share URL | Token storage / UX | OPEN |
| [MM-Q14](#mm-q14) | Identity после delete/recreate и безопасность восстановленных Shares | Identity lifecycle / recovery | OPEN |
| [MM-Q15](#mm-q15) | Полномочия public Crusher session, результат и expiry | Capability / privacy / UX | OPEN |
| [MM-Q16](#mm-q16) | Восстановление незавершённых Crusher jobs и exactly-once результат | Durability / backup semantics | OPEN |
| [MM-Q17](#mm-q17) | Размеры, concurrency, sandbox и эксплуатационные budgets | Измерение / platform feasibility | OPEN |
| [MM-Q18](#mm-q18) | Три attempts и три backoff интервала | Уточнение исходного численного требования | OPEN |
| [MM-Q19](#mm-q19) | Baseline зависимостей, supported versions и bootstrap secret flow | Интеграционная проверка | OPEN |
| [MM-Q20](#mm-q20) | Embeddings и смысл semantic search при privacy invariant | AI/privacy implementation choice | OPEN |

## Что уже составляет обязательную основу

- Canonical Vault расположен на сервере; .md остаются источником текста, caches перестраиваются.
- Основной редактор — официальный Obsidian; собственный клон, sync peers и note revision history в scope не добавлены.
- Saturn используется через Neptune; host mutations — через scoped Updater; Core не получает Docker socket/sudo.
- Plaintext secrets не включаются в Vault, frontend, logs, artifacts и logical backup.
- Public editor/submitter не расширяет себе доступ изменением Markdown или input path.
- Backup обязан восстанавливать обещанное состояние, а partial operations не выдают success.
- Общие требования Part 00–07/09–10/12 применяются в своих границах; нерелевантная модель графа/редактора не навязывается заметкам.

## Последовательность обсуждения

Сначала определить data integrity и полномочия: MM-Q02, MM-Q03, MM-Q07, MM-Q08, MM-Q11, MM-Q14–MM-Q16. Параллельно уточнить межсервисные контракты: MM-Q04–MM-Q06, MM-Q09, MM-Q10, MM-Q19. UX, exposure и измеряемые параметры MM-Q01, MM-Q12, MM-Q13, MM-Q17, MM-Q18, MM-Q20 должны быть закрыты до реализации соответствующих функций.

Все вопросы важны для итоговой готовности; этот порядок отражает зависимости, а не разрешение откладывать обязательные решения до production.

---

<a id="mm-q01"></a>

## MM-Q01. Граница Web Shell / Obsidian и поддерживаемый UX

**Статус:** OPEN.  
**Тип:** Продуктовое решение + применимость Part 01.  
**Разделы концепции:** §§12–16, 38, 117–118, 135.

**Что не определено.** Part 01 задаёт единую palette/typography/accessibility, а исходная концепция сохраняет любые темы/snippets Obsidian. Нельзя заявить выполнение обоих требований ко всему UI без явной границы. Также не определены fullscreen layout, место operational Dashboard, mobile/screen-reader acceptance и завершение уже открытого WS после logout/revoke.

**Варианты для обсуждения:**

- A. Унифицированный Shell; Obsidian/Bridge сохраняют native theme как явно согласованная embedded область.
- B. Согласованная специальная тема Obsidian и более узкая поддержка пользовательских themes.
- C. Изменить продуктовую модель редактора — противоречит текущему инварианту official Obsidian и потребует отдельного пересмотра scope.

**Рекомендация, ещё не решение.** Предпочтителен A. Shell и public forms полностью следуют Part 01; Runtime имеет собственную честно описанную совместимость. Выделение Dashboard и fullscreen behavior подтвердить отдельно в этом же UX decision.

**Что нужно для закрытия.** Запись области применения, макет Shell/Vault, тест поддерживаемых браузеров/размеров, keyboard/clipboard/reconnect и а11y-проверка. Проверить, что revoked browser не сохраняет доступ благодаря открытой graphical session.

**Общая документация и затронутые системы.** При необходимости общий профиль встраиваемого внешнего приложения в Part 01; scope decision по Part 00. Имена Mastermind не добавлять в общие UI tokens.

---

<a id="mm-q02"></a>

## MM-Q02. Один координатор операций Core и непосредственных writes Obsidian

**Статус:** OPEN.  
**Тип:** Архитектурная реализуемость / data integrity.  
**Разделы концепции:** §§4.5, 8, 22–23, 51, 57, 79–82, 100, 104.

**Что не определено.** Core и Obsidian пишут один filesystem. Watcher замечает изменения после факта; check SHA + rename не защищает от save между ними. Не определены pre-write uniqueness, dirty buffers, multi-file rename, native [[...]] propagation при API rename и idempotent Activity delivery при потере Core.

**Варианты для обсуждения:**

- A. Bridge и Core используют общий протокол операции/quiesce; все поддерживаемые entry points реально участвуют.
- B. Для конфликтующих операций Runtime временно переводится в контролируемый maintenance/останавливается.
- C. Ослабить гарантии при сторонних writes/plugins — возможно только как явно пересмотренный продуктовый контракт.

**Рекомендация, ещё не решение.** Сначала feasibility spike A, с B для операций, которые нельзя надёжно согласовать. Не объявлять advisory lock достаточным, если официальный Obsidian или plugin его не соблюдает.

**Что нужно для закрытия.** Concurrency/fault tests: CREATE collision, two-way save, API/Obsidian rename/move/delete, dirty buffer, Runtime unavailable, crash между каждым filesystem/DB шагом, отсутствие lost updates/duplicate Activity.

**Общая документация и затронутые системы.** Part 03/07 нельзя ослабить локальным предположением; для ограниченного scope writers нужна явная запись решения.

---

<a id="mm-q03"></a>

## MM-Q03. Полная грамматика @references и восстановление broken links

**Статус:** OPEN.  
**Тип:** Продуктовый синтаксис + parser contract.  
**Разделы концепции:** §§18–24, 25, 30–31, 77, 79, 103, 114, 122.

**Что не определено.** Longest match по существующим именам не задаёт правую границу токена. После удаления цели и очистки cache parser больше не знает её имя, хотя должен показать broken state. Не определены escaping, reserved external namespaces, коллизии note names с ними, Unicode offsets и Saturn path с пробелами при outage. Добавление более длинного имени может поменять старый текст.

**Варианты для обсуждения:**

- A. Уточнить детерминированную грамматику границ/escaping, сохранив обычный @Name с пробелами там, где это возможно.
- B. Хранить долговечное reference state для неоднозначных/удалённых целей и включать его в backup/export contract.
- C. Ослабить broken-link гарантии после удаления/rebuild — это изменение продукта, не parser optimization.

**Рекомендация, ещё не решение.** Провести набор неоднозначных примеров до выбора. Предпочесть восстанавливаемую из текста семантику; если нужен B, не называть его cache и отдельно решить portable export. Не выбирать регулярное выражение как замену спецификации.

**Что нужно для закрытия.** Общие fixtures Core/TypeScript Bridge: prefixes, punctuation, email, code/frontmatter/comments, Unicode casefold, CREATE/DELETE/RENAME, offline Saturn и полный rebuild. Результаты до/после очистки cache совпадают в обещанной области.

**Общая документация и затронутые системы.** Локальные требования Mastermind; центральное изменение требуется только при выборе варианта, меняющего общую норму.

---

<a id="mm-q04"></a>

## MM-Q04. Регистрация профиля Mastermind: recovery ZIP + Vault mirror

**Статус:** OPEN.  
**Тип:** Общий межсервисный контракт.  
**Разделы концепции:** §§1, 7, 83–87, 120, 139.

**Что не определено.** Parts 09–10 перечисляют существующие profiles и подробно задают два pipeline Volt, но не утверждают аналогичный Mastermind profile. Нужны identity, namespace/deployment rules, archive/mirror credentials, setup-code scope и состояния частичной настройки.

**Варианты для обсуждения:**

- A. Один typed Mastermind enrollment создаёт две независимые pipelines.
- B. Две отдельные согласованные enrollment операции с явным composed status.

**Рекомендация, ещё не решение.** Предпочтителен A по модели двойного профиля, с раздельными workers/credentials/status и Repair partial configuration. Рекомендация не означает, что такой профиль уже поддержан Updater/Neptune/Saturn.

**Что нужно для закрытия.** Добавлены согласованные таблицы profile и UI, schemas и tested minimum versions; clean host install/reuse, wrong-profile rejection и проверка обеих pipelines после terminal enrollment.

**Общая документация и затронутые системы.** Изменения Parts 09–10 и соответствующих contracts/docs Updater, Neptune, Saturn. Root README обновляется при изменении общего списка/топологии.

---

<a id="mm-q05"></a>

## MM-Q05. Neptune как scoped reader и Range gateway

**Статус:** OPEN.  
**Тип:** API gap / capability contract.  
**Разделы концепции:** §§7.3, 29–34, 55–56, 64.3, 84, 139.

**Что не определено.** Archive/mirror transport не задаёт автоматически интерактивный listing/metadata/read/Range API. Не определены local routes/schemas, mapping logical root, credentials, errors, pagination, MIME/length, cancellation и безопасный folder traversal.

**Варианты для обсуждения:**

- A. Расширить существующий host Neptune typed read API с отдельными scopes.
- B. Выделить заранее развёрнутый read-компонент внутри ответственности Neptune с тем же trust contract.
- Прямой Saturn API из Mastermind не является допустимым вариантом текущей модели.

**Рекомендация, ещё не решение.** Предпочтителен узкий Neptune adapter без переноса permanent Saturn credentials в Core. Browser-facing grants проверяются отдельно от transport credential.

**Что нужно для закрытия.** Consumer-driven contract tests и real Neptune/Saturn tests: partial content/invalid Range, большие видео, cancellation, pagination, missing/stale file, traversal/symlink escape, folder scope, unauthorized object и outage.

**Общая документация и затронутые системы.** Согласованный service-agent integration record и Neptune/Saturn API docs; Parts 09–10 уточняются в части новой ответственности, если это расширяет общий agent contract.

---

<a id="mm-q06"></a>

## MM-Q06. Continuous mirror, Saturn policy и сроки репликации

**Статус:** OPEN.  
**Тип:** Продуктовый SLA + межсервисная policy.  
**Разделы концепции:** §§83–87, 120, 139, 141.

**Что не определено.** Исходник требует intent за 1 s, старт за 5 s и reconcile каждые 15 min. Центральные правила закрепляют schedule authority за Saturn, а архивы имеют отдельную cadence. Не определены enabled/disabled continuous mode, revoke, backlog, queue capacity, outbox receipt/coalescing и cold recovery.

**Варианты для обсуждения:**

- A. Отдельный continuous mirror mode с политикой в Saturn, event-driven исполнением Neptune и периодической проверкой.
- B. Scheduled mirror; latency обещание меняется явно.
- C. Отдельная гибридная policy с ограниченными окнами и честным отображением backlog.

**Рекомендация, ещё не решение.** Предпочтителен A, сохранив продуктовую оперативность. Архивное расписание не менять автоматически. Сроки считать только при healthy/enabled pipeline, а RPO подтверждать отдельно.

**Что нужно для закрытия.** Approved policy/schema и tests disable/revoke/outage/restart/backpressure. UI показывает receipt/lag, desired/applied state, а не выдаёт queue acceptance за доставку.

**Общая документация и затронутые системы.** Parts 09–10 и Saturn Synchronization profile. Численные изменения после измерения, без второго schedule editor в Mastermind.

---

<a id="mm-q07"></a>

## MM-Q07. Согласованный snapshot Vault + SQLite и restore transaction

**Статус:** OPEN.  
**Тип:** Recovery architecture.  
**Разделы концепции:** §§8, 80–88, 112, 119, 137.

**Что не определено.** Consistent SQLite copy и отдельно mirror Vault могут относиться к разным моментам. Не определены snapshot boundary, остановка dirty buffers, journal, rollback set и переключение bind mounts. Нельзя атомарным rename одного каталога доказать транзакцию всей системы.

**Варианты для обсуждения:**

- A. Короткий общий write barrier, snapshot/staging и согласованная activation/recovery procedure.
- B. Поддерживаемый filesystem snapshot с координацией DB/Runtime и проверяемым fallback.
- C. Иная generation-based схема с доказанной согласованностью всех mounts и state.

**Рекомендация, ещё не решение.** Предпочесть наиболее простой проверяемый A, если измеренная пауза приемлема. B/C выбирать по фактическому host/storage contract, а не предполагать наличие snapshot-capable filesystem.

**Что нужно для закрытия.** Алгоритм states/journal, реальные RPO/RTO и pause budgets; clean restore и interruption tests на каждой границе; Core и Runtime читают одинаковую восстановленную generation; старые файлы удаляются только после verification.

**Общая документация и затронутые системы.** Локальные требования Mastermind; центральное изменение требуется только при выборе варианта, меняющего общую норму.

---

<a id="mm-q08"></a>

## MM-Q08. Состав .obsidian, plugin trust, export и запрещённые backup данные

**Статус:** OPEN.  
**Тип:** Compatibility + security/recovery policy.  
**Разделы концепции:** §§11–16, 85–86, 107, 123, 137.

**Что не определено.** Исходник обещает полную совместимость .obsidian и plugin artifacts. Part 03 запрещает secrets и reproducible build output в logical backup. Существующие plugins могут хранить credentials или отправлять данные наружу, а их наличие не доказывает восстановимость trusted artifact.

**Варианты для обсуждения:**

- A. Разделить compatibility export, mirror и logical ZIP; для каждого задать inventory, artifact reconstruction и секретную boundary.
- B. Поддерживать ограниченный список plugins, документировать migration/unsupported state.
- C. Сохранять отдельные неустранимые artifacts только через явно согласованный exception/защищённый recovery profile.

**Рекомендация, ещё не решение.** Начать с A и inventory реального Vault, затем решить необходимость B/C. Bridge восстанавливать из проверенного релиза. Не удалять пользовательские файлы/ключи молча и не отправлять непроверенный .obsidian целиком в безопасно названный backup.

**Что нужно для закрытия.** File-classification table, import report без secret values, trusted artifact manifest, export в обычный Obsidian, restore themes/snippets/plugin data и forbidden-content scan. Проверить declared privacy при реально поддерживаемых plugins.

**Общая документация и затронутые системы.** Если требуются исключения для binaries/protected material — Part 03 decision; embedded trust/visual scope — Part 01/07. Обычные секреты не включаются plaintext.

---

<a id="mm-q09"></a>

## MM-Q09. Большой backup: лимиты, spool и передача в Updater

**Статус:** OPEN.  
**Тип:** Расширение transport/recovery contract.  
**Разделы концепции:** §§86, 88, 105, 137, 140–141.

**Что не определено.** Описанный Updater принимает backup до 128 MiB; полный Vault может быть больше. Размер реального архива ещё не измерен. Увеличение HTTP body limit не решает RAM, temp disk, timeout, integrity и rollback.

**Варианты для обсуждения:**

- A. Защищённый scoped spool/stream handoff, поддержанный Updater, с negotiated bounded size.
- B. Проверяемый multipart recovery set с общей manifest/transaction — только после расширения и тестирования.
- C. Явно ограничить supported full backup size, если измерение и владелец подтверждают приемлемость.

**Рекомендация, ещё не решение.** Сначала измерить Vault и worst-case growth; предпочтителен A. Core не передаёт произвольный host path, helper независимо проверяет ownership, size, digest и job binding. Исключать attachments ради 128 MiB нельзя молча.

**Что нужно для закрытия.** Согласованные budgets/interface/minimum helper version; большой backup, quota exhaustion, cancellation/restart, forged spool reference, digest mismatch и полное восстановление в пределах RAM/disk budgets.

**Общая документация и затронутые системы.** Parts 03/05 и Updater contract, если меняется общий предел/способ передачи. Одной локальной настройки Mastermind недостаточно.

---

<a id="mm-q10"></a>

## MM-Q10. Один release для двух контейнеров, Bridge и schema

**Статус:** OPEN.  
**Тип:** Типизированный update profile.  
**Разделы концепции:** §§6, 104–106, 112, 134, 140.

**Что не определено.** Generic image-only update не доказывает замену Core+Runtime и совместимого Bridge или применение новой Compose topology. В Part 11 есть многокомпонентный Saturn profile, но его порядок миграции/rollback нельзя автоматически перенести на Mastermind.

**Варианты для обсуждения:**

- A. Один signed Mastermind release и typed group apply/rollback.
- B. Отдельные typed component updates с compatibility matrix и общим recovery coordinator.
- C. Только explicit installer/package repair для topology changes; UI показывает этот механизм вместо притворного Apply.

**Рекомендация, ещё не решение.** Предпочтителен A; C допустим для отдельно описанных структурных изменений. Независимое обновление Obsidian self-updater не выбирать как обход.

**Что нужно для закрытия.** Manifest schema, allow-listed service group, tested minimum Updater, pre-pull/backup/write barrier, old/new compatibility; сбой Core/Runtime/Bridge/migration даёт доказанный rollback всего обещанного состояния.

**Общая документация и затронутые системы.** Part 05 profile extension и отдельный согласованный deployment record; пример Part 11 не означает включение Mastermind в исходный первоначальный профиль.

---

<a id="mm-q11"></a>

## MM-Q11. Owner grants для внешних ресурсов в Share

**Статус:** OPEN.  
**Тип:** Авторизация / продуктовые права.  
**Разделы концепции:** §§48, 54–57, 93–94, 135, 138.

**Что не определено.** Public editor может дописать @saturn или @chronos. Если право читать выводится только из текущего Markdown, он сможет расширить доступ. Независимость grants обязательна, но lifecycle ещё не выбран: initial scope, owner edits, удаление reference, subtree contents и ongoing streams.

**Варианты для обсуждения:**

- A. Grants фиксирует owner при создании Share; новые resources требуют отдельного owner action.
- B. Grants меняются только по authenticated owner-origin edits с audit/explicit policy.
- C. Запретить public edits внешних references, дополнительно сохранив независимую server-side authorization.

**Рекомендация, ещё не решение.** Предпочтителен A как простой начальный контракт; B — если удобство live sharing оправдывает сложность. C само по себе не заменяет grant checks.

**Что нужно для закрытия.** Grant schema/backup class, owner UI и tests: public insertion/replacement path/event, traversal, removed/revoked grants, password/expiry, active stream и запрет раскрытия private notes/context. Policy изменения не должны зависеть от доверия к Markdown.

**Общая документация и затронутые системы.** Локальные требования Mastermind; центральное изменение требуется только при выборе варианта, меняющего общую норму.

---

<a id="mm-q12"></a>

## MM-Q12. Share — обмен по ссылке или индексируемая публикация

**Статус:** OPEN.  
**Тип:** Продуктовый scope / exposure.  
**Разделы концепции:** §§47–57, 138, 143.

**Что не определено.** Слово «публиковать» в исходнике не определяет поисковую видимость. Доступ по bearer URL не равен согласию размещать note в sitemap, feeds и поисковых системах. Нужна явная classification и поведение metadata/cache/referrer.

**Варианты для обсуждения:**

- A. Только capability sharing, public/non-indexable, без discovery.
- B. Отдельный явно включаемый режим public/indexable с полным Part 08 contract.

**Рекомендация, ещё не решение.** Для первой версии предпочтителен A. Пока решение не принято, разрешения на public discovery нет. Возможный B не должен автоматически включаться для всех существующих Shares.

**Что нужно для закрытия.** Route registry, bot/cache/robots policy, tests отсутствия token URLs/private metadata в discovery. Для B дополнительно publication lifecycle, first-response HTML, canonical, sitemap/feeds и SEO acceptance.

**Общая документация и затронутые системы.** Part 08 применимость определяется выбранным scope; переход classification проходит Part 00/07 policy review.

---

<a id="mm-q13"></a>

## MM-Q13. Повторное копирование постоянного Share URL

**Статус:** OPEN.  
**Тип:** Token storage / UX.  
**Разделы концепции:** §§13.4, 47–48.

**Что не определено.** ТЗ требует token_hash и Copy URL в списке. Hash не позволяет восстановить raw token после создания и нового login. Нельзя обещать эту кнопку без решения о хранении или изменении UX.

**Варианты для обсуждения:**

- A. Показать полный URL только при создании; далее owner может revoke/create новый Share.
- B. Хранить recoverable encrypted token в approved secret boundary с отдельным key/recovery contract.
- C. Иной доказанный token design, сохраняющий entropy, revoke, permanence и отсутствие plaintext в обычном state.

**Рекомендация, ещё не решение.** Предпочтителен A, если повторное получение той же ссылки не обязательно. Если обязательно, выбрать B после security/recovery design. Не вводить reversible encoding под видом hash и не сохранять token в localStorage.

**Что нужно для закрытия.** Утверждённый UX, persistence/inventory, re-login и restore tests; проверка logs/backups/frontend state и явного изменения URL только при создании новой ссылки.

**Общая документация и затронутые системы.** Локальные требования Mastermind; центральное изменение требуется только при выборе варианта, меняющего общую норму.

---

<a id="mm-q14"></a>

## MM-Q14. Identity после delete/recreate и безопасность восстановленных Shares

**Статус:** OPEN.  
**Тип:** Identity lifecycle / recovery.  
**Разделы концепции:** §§4.4, 24, 48, 51–52, 86–88.

**Что не определено.** Нет note UUID, Share адресует текущий path. После удаления и создания другого файла с тем же path старый Share может ожить для другой заметки. Restore старой БД также может вернуть ранее отозванные Shares/credentials или старую grant policy.

**Варианты для обсуждения:**

- A. Durable target tombstone; path reuse не привязывает старый Share, owner явно rebind/reissue. Для restore определить дополнительное подтверждение/ревалидацию sensitive grants.
- B. Иной служебный lifecycle без note UUID в Markdown, доказывающий ту же identity/security boundary.
- C. Path-based rebinding как намеренная функция — только при явном изменении понятия «одна конкретная note».

**Рекомендация, ещё не решение.** Предпочтителен A. Session invalidation обязательна; политику уже выданных permanent Share URLs и revocation continuity согласовать отдельно, не обещать одновременно невозможные continuity гарантии.

**Что нужно для закрытия.** Delete → recreate same path, case/Unicode rename, move, cache rebuild, restore до/после revoke и Grant change. Продемонстрировать отсутствие случайного доступа к новому объекту и документировать судьбу старых URLs.

**Общая документация и затронутые системы.** Локальные требования Mastermind; центральное изменение требуется только при выборе варианта, меняющего общую норму.

---

<a id="mm-q15"></a>

## MM-Q15. Полномочия public Crusher session, результат и expiry

**Статус:** OPEN.  
**Тип:** Capability / privacy / UX.  
**Разделы концепции:** §§59–64, 70–74, 123.

**Что не определено.** Submission capability не должна давать owner access. Не определены permitted Saturn sources, объём private Vault context, видимость generated result/paths/metadata, GET после expiry и момент принятия долгой загрузки. Session заканчивается через 30 минут, accepted jobs продолжаются.

**Варианты для обсуждения:**

- A. Public session принимает только собственные inputs; Saturn/private-context sensitive flows доступны owner; результаты public flow минимизированы.
- B. Owner при выдаче access явно задаёт source/result/context scopes.
- Для GET после expiry: отдельная ограниченная result capability либо доступ только owner после завершения session.

**Рекомендация, ещё не решение.** Предпочесть минимальный scope A либо явно настроенный B. Не передавать весь Vault provider и не возвращать соседние private notes в public job output. Acceptance upload должно быть точным state transition.

**Что нужно для закрытия.** Actor/scope table и tests cross-session jobs, guessed IDs, arbitrary Saturn path, expiry до/во время upload/job/result, private-context leakage и unlimited repeated submissions. Согласовать quotas и revocation.

**Общая документация и затронутые системы.** Локальные требования Mastermind; центральное изменение требуется только при выборе варианта, меняющего общую норму.

---

<a id="mm-q16"></a>

## MM-Q16. Восстановление незавершённых Crusher jobs и exactly-once результат

**Статус:** OPEN.  
**Тип:** Durability / backup semantics.  
**Разделы концепции:** §§61–63, 74–76, 86, 104, 119, 126.

**Что не определено.** Lease не гарантирует exactly-once side effects. Worker может умереть после записи note, но до COMPLETED. В disaster backup есть job record, но временный upload/work по Part 03 исключён. Не определены stage replay, billing/idempotency и поведение без source.

**Варианты для обсуждения:**

- A. Durable commit identity/reconciliation; после restart продолжение возможно при наличии source, после restore missing source даёт явный terminal failure/resubmit workflow.
- B. Для выбранных источников хранить durable исходник отдельно по согласованной user-data policy, не маскируя temporary work под backup.
- C. Уточнить recovery scope jobs и явно ограничить обещание автоматического продолжения.

**Рекомендация, ещё не решение.** Предпочтителен A как начальный recovery contract. При необходимости B отдельно определить источник истины, privacy, retention и удаление. Не включать temp directories в ZIP незаметно.

**Что нужно для закрытия.** Crash до/после provider call и commit, expired lease, retry same job, restore без payload; не возникает второй .md, бесконечный ambiguous job или фиктивный COMPLETED. Не добавлять новые status enum без обновления API.

**Общая документация и затронутые системы.** Локальные требования Mastermind; центральное изменение требуется только при выборе варианта, меняющего общую норму.

---

<a id="mm-q17"></a>

## MM-Q17. Размеры, concurrency, sandbox и эксплуатационные budgets

**Статус:** OPEN.  
**Тип:** Измерение / platform feasibility.  
**Разделы концепции:** §§32–34, 64–76, 95, 102, 135, 141.

**Что не определено.** Известен одиночный upload limit 2 GiB, но не совокупный disk/RAM/CPU budget, queue length, число workers, archive expansion и duration. Схема extractor isolation также не выбрана. Сам job directory не изолирует parser от Vault и host credentials.

**Варианты для обсуждения:**

- A. Заранее развёрнутый ограниченный extractor worker без Vault/agent mounts; commit делает Core.
- B. Иная OS/process sandbox с доказанными границами и supervision.
- Для каждого пути выбрать численные hard limits по измерению representative workload.

**Рекомендация, ещё не решение.** Предпочесть простую заранее управляемую boundary и bounded spool. Не выдавать Core Docker socket для запуска произвольных containers и не поднимать глобальный auth/API лимит до размера upload.

**Что нужно для закрытия.** Limits matrix config/runtime/UI/tests, large upload + ordinary UI, archive bomb, SSRF через browser subrequests, quota exhaustion, cancel, worker death, graph render cap и 8-hour Runtime resource measurement.

**Общая документация и затронутые системы.** Локальные требования Mastermind; центральное изменение требуется только при выборе варианта, меняющего общую норму.

---

<a id="mm-q18"></a>

## MM-Q18. Три attempts и три backoff интервала

**Статус:** OPEN.  
**Тип:** Уточнение исходного численного требования.  
**Разделы концепции:** §§75, 126.

**Что не определено.** Исходник одновременно задаёт максимум 3 attempts и backoff 5s/30s/120s. Три total attempts обычно дают два интервала перед retries; три интервала могут означать четыре total attempts. Не определены stage/job accounting и Retry-After.

**Варианты для обсуждения:**

- A. Три total attempts, два явно выбранных интервала.
- B. Три retries после первой попытки — четыре total attempts и изменение исходного лимита.
- C. Иной явно описанный bounded retry schedule.

**Рекомендация, ещё не решение.** Предпочтителен A с сохранением исходного total budget; конкретные интервалы подтвердить. Пока вопрос открыт, не интерпретировать 120s как разрешение четвёртой попытки.

**Что нужно для закрытия.** Таблица attempt → delay → terminal outcome, Retry-After/cap policy, persisted budget и tests 429/5xx/timeout/restart/non-transient failure.

**Общая документация и затронутые системы.** Локальные требования Mastermind; центральное изменение требуется только при выборе варианта, меняющего общую норму.

---

<a id="mm-q19"></a>

## MM-Q19. Baseline зависимостей, supported versions и bootstrap secret flow

**Статус:** OPEN.  
**Тип:** Интеграционная проверка.  
**Разделы концепции:** §§1, 10, 12.1, 15, 28–34, 104–106, 134, 136, 140.

**Что не определено.** Не зафиксированы реальный deployment baseline, точные API/version compatibility Kernel/Volt/Chronos/Neptune/Updater, approved Obsidian/KasmVNC versions и Bridge auth outside Vault. Не определён полный cold-start путь при недоступном Kernel/Volt и policy истечения cached configuration.

**Варианты для обсуждения:**

- A. Поддержать один узкий проверенный dependency profile и pinned Runtime tuple.
- B. Поддерживать несколько профилей с отдельной compatibility matrix и тестами.

**Рекомендация, ещё не решение.** Предпочтителен A на первом release. Использовать Kernel/Register references и approved secret delivery, не брать токены из соседних env. Точные значения получать из baseline; не копировать номера версии Part 11 как автоматический минимум Mastermind.

**Что нужно для закрытия.** Version/endpoint/schema matrix, signed source/digest Runtime artifacts, Bridge channel without Vault secret, live credential rotation, cold start/outage/recovery tests и отсутствие dependency readiness cycle. Зафиксировать immutable central documentation SHA.

**Общая документация и затронутые системы.** Локальные требования Mastermind; центральное изменение требуется только при выборе варианта, меняющего общую норму.

---

<a id="mm-q20"></a>

## MM-Q20. Embeddings и смысл semantic search при privacy invariant

**Статус:** OPEN.  
**Тип:** AI/privacy implementation choice.  
**Разделы концепции:** §§71, 78, 103, 123, 141.

**Что не определено.** Semantic index нужен для placement/search, но обычная индексация не имеет права отправлять note content внешним AI services. Конкретная local model/runtime, quality, ресурсный бюджет и повторная загрузка artifacts пока не выбраны.

**Варианты для обсуждения:**

- A. Локальные embeddings с pinned model/artifact и bounded background compute.
- B. Внешний embedding provider только после явного изменения privacy contract и user-facing scope.
- C. Изменить semantic functionality/качество первой версии — только как отдельное изменение требований.

**Рекомендация, ещё не решение.** Предпочтителен A. Не считать remote embeddings незаметным техническим кэшем и не разрешать отправку всего Vault под видом Crusher preparation.

**Что нужно для закрытия.** Quality fixtures placement, peak memory/CPU и reindex time, cold/offline behavior, model digest/version, rebuild after cache deletion и network test: обычные edit/search/index не отправляют notes provider.

**Общая документация и затронутые системы.** Локальные требования Mastermind; центральное изменение требуется только при выборе варианта, меняющего общую норму.

---

## Где могут потребоваться центральные изменения

| Вопрос | Возможное изменение |
| --- | --- |
| MM-Q01 | Область embedded third-party UI в Part 01 и её acceptance |
| MM-Q04 | Профиль Mastermind в Parts 09–10 и schemas Updater/Neptune/Saturn |
| MM-Q05 | Scoped read/Range responsibility Neptune и integration contract |
| MM-Q06 | Continuous mirror policy и управление в Saturn Synchronization |
| MM-Q08 | Только при необходимости — явное recovery/artifact exception по Parts 03/07 |
| MM-Q09 | Large-backup handoff и budgets в Parts 03/05/Updater |
| MM-Q10 | Typed multi-component update/rollback profile и compatibility |
| MM-Q12 | Применимость Part 08 при выборе searchable publication |
| MM-Q19 | Новые dependency profiles/coordinates; не изменять initial Part 11 автоматически |

Остальные решения обычно уточняют локальный продуктовый контракт, но всё равно требуют обновления tests, inventory и docs, если меняют наблюдаемое поведение.

## Шаблон принятого решения

~~~text
ID: MM-Qxx
Status: OPEN / DECIDED / DEFERRED_WITH_EXPLICIT_SCOPE_CHANGE
Decision date:
Decision owner:
Chosen option:
Rationale and rejected alternatives:
Preserved invariants:
Changed product/central requirements:
Affected concept sections:
Affected services and minimum compatible versions:
Data migration / compatibility:
Rollback or safe fallback:
Acceptance tests and evidence:
Remaining limitations:
~~~

Status DECIDED означает, что вариант принят и внесён в требования, а не что runtime уже реализован и протестирован. Implementation/evidence readiness отмечается отдельно.

DEFERRED_WITH_EXPLICIT_SCOPE_CHANGE допускается только при явном изменении scope и соответствующего DoD; он не превращает невыполненное обязательное требование в PASS или N/A. Закрытые IDs сохраняются, чтобы ссылки и rationale оставались понятными.
