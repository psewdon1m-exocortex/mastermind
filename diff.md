Новый механизм **архитектурно заметно сильнее**, но я бы не выбрасывал старый. В старом Crusher уже есть несколько очень хороших свойств, которые стоит сохранить как жёсткий каркас. Оптимальный вариант — **оставить старые ограничения допустимости и safety-checks, но заменить сам механизм поиска места новым Retriever/Reranker pipeline**.

Главное: пока нельзя утверждать, что новый механизм *фактически точнее* — это проверяется только на размеченном наборе реальных нот. Но у него существенно **выше потолок точности**, потому что он устраняет несколько фундаментальных слабостей текущего алгоритма.

## 1. Ключевое различие

Сейчас Crusher решает задачу как **greedy descent**:

```text
root
 ↓
выбрать лучший #main
 ↓
выбрать лучший #key
 ↓
выбрать следующий #key
 ↓
...
```

На каждом шаге:

```text
локальный FTS
→ E5
→ top-12
→ Gemini
→ выбрать ОДНУ ветку
```

После выбора назад дороги практически нет.

Новый механизм решает задачу иначе:

```text
Нота
 ↓
Query / Placement Query
 ↓
несколько retrieval strategies
 ↓
глобальный Candidate Set
 ↓
fusion
 ↓
Reranker
 ↓
relation/path analysis
 ↓
несколько конкурирующих placement hypotheses
 ↓
confidence
 ↓
при необходимости Curator
 ↓
повторная проверка гипотезы
```

То есть старый задаёт вопрос:

> «В какую из этих 12 дочерних веток идти дальше?»

Новый задаёт вопрос:

> «Какие места во всей допустимой структуре лучше всего объясняются содержимым этой ноты и существующим графом?»

Это принципиально более сильная постановка.

---

# 2. Самая большая проблема старого механизма — ранняя необратимая ошибка

Представим:

```text
root
├── Infrastructure
│   └── Storage
│
└── Projects
    └── Saturn
        └── Uploads
```

Нота:

> Для загрузки файлов по 100 GB в Saturn можно сделать промежуточный буфер на сервере, а затем постепенно переносить данные на диск.

На первом шаге очень легко получить:

```text
Infrastructure = 0.91
Projects       = 0.89
```

Gemini выбирает:

```text
Infrastructure
```

И всё.

Дальше:

```text
root
└── Infrastructure
    ↓
```

`Saturn → Uploads` алгоритм **больше вообще не увидит**.

Даже если истинная релевантность была бы:

```text
Projects/Saturn/Uploads = 0.98
```

она уже недостижима.

Это классическая проблема greedy search.

### Новый механизм

Он может одновременно сохранить:

```text
Infrastructure/Storage      0.84
Projects/Saturn             0.91
Projects/Saturn/Uploads     0.96
```

и сравнить их **до окончательного решения**.

Это, пожалуй, самое серьёзное преимущество новой архитектуры.

---

# 3. Старый механизм имеет информационное бутылочное горлышко

Сейчас:

```text
Source
 ↓
Gemini understanding
 ↓
summary + topics
 ↓
placement
```

То есть placement работает уже не с исходной информацией, а с **интерпретацией первой модели**.

Получается:

```text
исходная нота
    ↓
compression
    ↓
summary
    ↓
placement
```

Если при compression потерялся один ключевой аспект:

```text
Saturn
upload buffering
large files
```

то Retriever его уже никак не восстановит.

Это error propagation:

```text
ошибка Understanding
        ↓
ошибка Placement
```

---

## Новый механизм лучше разделить

Placement Query должен строиться из нескольких независимых сигналов:

```text
                 FULL NOTE
                    │
        ┌───────────┼─────────────┐
        │           │             │
        ▼           ▼             ▼
      text       entities       metadata
        │           │             │
        ▼           ▼             ▼
      FTS        graph/entity    filters
        │
        ▼
    embedding

+
summary
+
topics
```

То есть `summary/topics` остаются полезным сигналом, но **перестают быть единственным representation ноты**.

Это сильно повышает устойчивость.

---

# 4. Текущий E5 — хороший компонент, но используется слишком локально

Сейчас E5 делает примерно:

```text
current siblings
   ↓
48 FTS candidates
   ↓
embedding rerank
   ↓
12
```

Это разумный локальный reranker.

Проблема не в E5.

Проблема в том, что E5 видит только то, что:

1. находится среди детей уже выбранного узла;
2. прошло FTS;
3. попало в top-48.

Если правильный кандидат:

```text
не содержит нужного слова
```

или:

```text
находится в другой ветке
```

E5 его никогда не увидит.

---

## В новом Retriever vector search становится самостоятельным каналом

```text
                  Query
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
      BM25        Vector      Entity
        │           │           │
        ├───────────┼───────────┤
        ▼           ▼           ▼
      Graph      Metadata    Temporal
        │           │           │
        └───────────┼───────────┘
                    ▼
              Candidate Set
```

Это очень важное отличие:

```text
old:
BM25 → E5 rerank
```

против:

```text
new:
BM25 ─────┐
Vector ───┤
Graph ────┤
Entity ───┼→ fusion → rerank
Metadata ─┤
Temporal ─┘
```

Теперь один слабый retrieval-канал не может полностью уничтожить кандидата.

---

# 5. Entity information сейчас фактически выбрасывается

Это особенно заметная упущенная возможность.

Crusher уже получает:

```text
title
summary
topics
entities
relations
```

но placement использует в основном:

```text
summary
topics
```

Предположим нота содержит:

```text
Saturn
Neptune
Wyvern
upload gateway
```

Это очень сильные structural signals.

Если существует граф:

```text
Saturn
 ├── Upload
 └── Storage
```

то сущность `Saturn` должна очень сильно повышать вероятность этой ветки.

В новом механизме:

```text
Entity Search
+
Graph Traversal
+
Relation Expansion
```

становятся полноценными retrieval signals.

Например:

```text
note
mentions → Saturn

Saturn
has_topic → Upload

Upload
belongs_to → Storage
```

Это намного сильнее чистого semantic similarity.

---

# 6. Новый механизм лучше использует сам Knowledge Graph

Старый алгоритм использует граф преимущественно как:

```text
структуру навигации
```

то есть:

```text
parent → child
```

Новый Retriever использует граф ещё и как **evidence**.

Это большая разница.

Например:

```text
candidate A
semantic similarity = 0.88
graph connection = none
```

против:

```text
candidate B
semantic similarity = 0.82

note entities
   ↓
Saturn
   ↓
Uploads
   ↓
candidate B
```

Для placement кандидат B вполне может быть сильнее.

---

# 7. Но иерархию `root → main → key` я бы НЕ убирал

Это одна из сильнейших частей текущего механизма.

Она определяет:

> **куда вообще разрешено помещать знания.**

Это нужно оставить как **hard constraint**.

То есть не:

```text
Retriever ищет абсолютно любую note
```

а:

```text
Knowledge Base
     ↓
Structural Index
     ↓
valid placement nodes
     ↓
Retriever
```

Например:

```text
eligible_targets = {
    все reachable #main / #key
}
```

А уже среди них новый Retriever ищет лучший вариант.

Получается хорошее разделение:

```text
Hierarchy
= что ЯВЛЯЕТСЯ допустимым местом

Retriever
= какое допустимое место релевантно

Reranker
= какое из релевантных мест лучше

Confidence
= достаточно ли доказательств для auto-placement
```

---

# 8. Я бы вообще убрал обязательный последовательный descent

Иерархию сохранить, но использовать иначе.

Сейчас:

```text
root
 ↓
choose 1
 ↓
choose 1
 ↓
choose 1
```

Лучше сначала построить индекс всех reachable structural nodes:

```text
root
├── A
│   ├── A1
│   └── A2
├── B
│   ├── B1
│   └── B2
└── C
```

И Retriever может одновременно оценивать:

```text
A
A1
A2
B
B1
B2
C
```

А потом проверять path consistency.

Например:

```text
B2 = 0.94
B  = 0.87
```

Это совершенно нормальный результат:

```text
root → B → B2
```

Нет необходимости сначала заставлять модель выбрать `B`, не показывая ей доказательства в пользу `B2`.

---

# 9. Компромиссный вариант — Beam Search

Если глобальный поиск по всей структуре окажется слишком дорогим, есть промежуточный вариант.

Вместо:

```text
beam width = 1
```

как сейчас:

```text
root
 ↓
ONE branch
```

держать, например:

```text
beam width = 3
```

```text
             root
        ┌─────┼─────┐
        A     B     C
       / \   / \   / \
```

После следующего уровня сохранять лучшие несколько маршрутов.

Например:

```text
1. B → B2     0.94
2. A → A1     0.88
3. B → B1     0.86
```

Это уже радикально уменьшит вероятность фатальной ошибки на верхнем уровне.

Но при наличии нормального глобального Retriever я бы скорее использовал глобальный поиск + path validation.

---

# 10. Самая слабая часть старого confidence — Gemini оценивает сам себя

Сейчас:

```text
Gemini:
choose A
confidence: 0.95
```

Но:

```text
0.95 ≠ 95% вероятность правильности
```

Это просто число, которое генеративная модель решила вывести.

Текущий подход:

```text
min(confidence_per_step)
```

сам по себе консервативный и разумный, но исходные значения плохо калиброваны.

---

## Новый Confidence Evaluator гораздо сильнее

Он может учитывать:

```text
reranker score
+
top1 / top2 margin
+
agreement BM25 ↔ Vector
+
entity evidence
+
graph evidence
+
metadata compatibility
+
path consistency
+
number of independent signals
```

Например:

```text
Candidate: Saturn / Uploads

BM25               ✓
Vector              ✓
Entity Saturn       ✓
Graph relation      ✓
Metadata            ✓
Reranker #1         ✓
Top1-top2 gap       large
```

Это действительно веские основания.

А другой кандидат:

```text
Candidate: Infrastructure

BM25                ✓
Vector              ✓
Entity              ✗
Graph               ✗
Reranker #2
```

Тогда confidence можно выводить из **наблюдаемых доказательств**, а не спрашивать модель:

> «Ты насколько уверена от 0 до 1?»

---

# 11. Curator здесь тоже сильнее Gemini chooser

Старый Gemini принимает решение:

```text
выбери A/B/C
```

То есть фактически является судьёй.

Curator в новой схеме имеет более безопасную роль:

```text
не знаю между A и B
        ↓
Curator
        ↓
"проверь ещё такие признаки,
такую entity и такую graph relation"
        ↓
Retriever
        ↓
фактическая проверка
```

То есть:

```text
OLD

LLM opinion
   ↓
decision
```

против:

```text
NEW

LLM hypothesis
   ↓
retrieval verification
   ↓
decision
```

Вторая схема архитектурно значительно надёжнее.

---

# 12. Ещё одно крупное улучшение — Branch Profile

На мой взгляд, это стоит добавить обязательно.

Сейчас структурная нота описывается Gemini примерно так:

```text
title
tags
first 512 chars
```

Но структурная нота по смыслу представляет не только себя.

Например:

```text
Saturn.md
```

может содержать две строки, а под ней лежат 500 нот.

Первые 512 символов `Saturn.md` совершенно не описывают содержимое ветки.

Нужен производный объект:

```text
PlacementProfile
```

например:

```yaml
node: "[[Saturn]]"

title:
  Saturn

path:
  root / Projects / Saturn

description:
  File storage and synchronization subsystem.

topics:
  - storage
  - uploads
  - synchronization
  - SFTP
  - large files

entities:
  - Saturn
  - storage server

child_topics:
  - upload buffering
  - permissions
  - sharing
  - backups

representative_notes:
  - ...
  - ...

embedding:
  ...

updated_at:
  ...
```

Этот профиль автоматически пересчитывается при изменениях поддерева.

И Retriever ищет уже не по:

```text
первые 512 символов Saturn.md
```

а по:

```text
semantic representation of Saturn branch
```

Это может дать очень большой прирост точности даже без Curator.

---

# 13. Сравнение по компонентам

| Свойство                       | Старый Crusher              | Новый pipeline                    |
| ------------------------------ | --------------------------- | --------------------------------- |
| Допустимые места               | **Очень хорошо ограничены** | Нужно сохранить это ограничение   |
| Full-text                      | Есть                        | Есть                              |
| Vector                         | Есть как локальный reranker | Полноценный независимый retrieval |
| Entity Search                  | Практически нет в placement | Есть                              |
| Graph semantics                | В основном hierarchy        | Полноценный signal                |
| Metadata                       | Ограниченно                 | Полноценно                        |
| Поиск по всей структуре        | Нет                         | Да                                |
| Ошибка верхнего уровня         | Фатальна                    | Не обязательно                    |
| Несколько гипотез              | Нет                         | Да                                |
| Backtracking                   | Нет                         | Фактически появляется             |
| Reranking                      | E5 среди local candidates   | Отдельный глобальный этап         |
| LLM                            | Принимает решение           | Предлагает refinement             |
| Confidence                     | LLM self-report             | Evidence-based                    |
| Альтернативы                   | Обычно нет                  | Явные top-N                       |
| Explainability                 | Path + Gemini choice        | Evidence по каждому кандидату     |
| Semantic branch representation | title + начало              | Можно иметь Branch Profile        |
| Проверка изменения hierarchy   | **Есть, хорошая**           | Обязательно сохранить             |
| Inbox fallback                 | **Есть, хорошая**           | Обязательно сохранить             |

---

# 14. Поэтому лучший вариант — не «старый ИЛИ новый»

Я бы сделал:

```text
                       NOTE
                         │
                         ▼
                  Query Processor
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
       ▼                 ▼                 ▼
   raw text          entities          metadata
       │                 │                 │
       └─────────────────┼─────────────────┘
                         ▼
               Structural Target Index
             reachable #main / #key only
                         │
          ┌──────────────┼───────────────┐
          ▼              ▼               ▼
       BM25           Vector          Entity
          │              │               │
          ▼              ▼               ▼
      Metadata         Graph        Branch Profiles
          │              │               │
          └──────────────┼───────────────┘
                         ▼
                   Candidate Set
                         │
                         ▼
                       Fusion
                         │
                         ▼
                      Reranker
                         │
                         ▼
                  Relation Expansion
                         │
                         ▼
                 Path Consistency Check
                         │
                         ▼
                 Confidence Evaluator
                     ┌───┴────┐
                    high      low
                     │         │
                     │         ▼
                     │      Curator
                     │         │
                     │    hypothesis
                     │         │
                     │         ▼
                     │   second retrieval
                     │         │
                     └────┬────┘
                          ▼
                Placement Recommendation
                          │
                    ┌─────┴─────┐
                    │           │
               confident     ambiguous
                    │           │
                    ▼           ▼
                auto place     Inbox
                    │
                    ▼
           hierarchy checksum verify
                    │
                    ▼
                   save
```

Вот это уже я бы считал целевым механизмом.

---

# 15. Что из старого Crusher обязательно сохранить

Четыре вещи я бы вообще не трогал концептуально:

1. **Жёсткое определение допустимых placement nodes через структурную иерархию.** Retriever не должен неожиданно выбрать любую случайную заметку.

2. **Inbox как нормальный результат.** Отказ выбрать лучше ошибочного auto-placement.

3. **Повторная проверка hierarchy checksum перед mutation.** Это очень хорошая защита от TOCTOU: решение принималось над одной структурой, а сохраняться может уже в другую.

4. **Не перезаписывать существующие файлы и отделять placement decision от фактической записи.**

Это сильные свойства существующей реализации.

---

# 16. Что я бы заменил первым

Не надо сразу переписывать весь Crusher.

Наиболее выгодный порядок:

```text
STEP 1
Убрать dependence placement только от summary/topics.
Добавить raw note embedding + entities.
```

↓

```text
STEP 2
Создать PlacementProfile для каждого #main/#key.
```

↓

```text
STEP 3
Сделать global retrieval по всем reachable structural nodes.
BM25 + Vector + Entity + Graph.
```

↓

```text
STEP 4
Оставлять top-N кандидатов и делать общий Reranker.
```

↓

```text
STEP 5
Заменить Gemini confidence на Confidence Evaluator.
```

↓

```text
STEP 6
Только потом добавить Curator для ambiguous cases.
```

Причём я ожидаю, что **основная часть прироста придёт ещё до Curator**.

Curator должен исправлять хвост сложных случаев, а не компенсировать слабый Retriever.

---

# 17. Как доказать, что новый действительно точнее

Здесь нужен benchmark, иначе мы будем сравнивать архитектуры на ощущениях.

Я бы собрал, например, несколько сотен реальных нот:

```yaml
note: ...
correct_target:
  - "[[Saturn/Uploads]]"

acceptable_targets:
  - "[[Saturn]]"

must_inbox: false
```

Для неоднозначных:

```yaml
correct_target: null
must_inbox: true
```

И прогонял обе реализации.

Главные метрики для Crusher я бы сделал не просто `accuracy`.

### Top-1 placement accuracy

```text
правильный target стоит первым
```

### Top-3 recall

```text
правильный target присутствует среди трёх гипотез
```

Очень полезно при разработке Retriever.

### Auto-placement precision

Самая важная метрика:

```text
из всех нот, которые система решила разместить автоматически,
сколько действительно размещены правильно
```

### Coverage

```text
какой процент нот система вообще решается разместить автоматически
```

Здесь получится кривая:

```text
confidence threshold ↑

precision ↑
coverage ↓
```

И уже по реальной базе можно выбрать threshold.

### False auto-placement

Особенно важно отдельно считать:

```text
система была уверена,
но положила не туда
```

Для knowledge base это хуже, чем лишний Inbox.

---

# 18. И обязательно делать ablation

Чтобы понять, что реально помогает:

```text
A — current Crusher

B — A + full note representation

C — B + Placement Profiles

D — C + global Vector

E — D + Entity/Graph retrieval

F — E + new Reranker

G — F + evidence confidence

H — G + Curator
```

Тогда будет видно, например:

```text
Current                  81%
+ Placement Profiles     88%
+ Global Retriever       92%
+ Graph/Entity           94%
+ Curator                95%
```

Цифры здесь лишь иллюстрация, но именно такой эксперимент позволит понять реальный вклад каждого слоя.

---

## Итог

Если кратко:

**старый механизм — хороший консервативный hierarchical classifier; новый — полноценная retrieval/ranking system.**

Старый:

```text
локально хороший выбор
+
очень строгая структура
+
безопасный Inbox
```

но страдает от:

```text
summary bottleneck
+
greedy descent
+
beam width = 1
+
локального candidate recall
+
слабого использования graph/entities
+
некалиброванного LLM confidence
```

Новый механизм решает почти все эти проблемы.

Но наиболее сильная целевая архитектура — **гибрид**:

> **старый Crusher определяет hard constraints, structural validity, Inbox и безопасное сохранение; новый Retriever/Reranker определяет семантически лучшее место внутри этих границ; Curator вмешивается только при реальной неоднозначности.**

И я бы особенно выделил три изменения с наибольшим потенциальным эффектом: **глобальный поиск по всем допустимым structural nodes, `PlacementProfile` для каждой ветки и отказ от greedy `одна ветка за шаг` в пользу сравнения нескольких полных placement hypotheses.**
