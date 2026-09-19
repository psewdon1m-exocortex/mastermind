# Mastermind Retrieval & Curator Pipeline — концепция механизма

**Статус:** концептуальная архитектура  
**Версия:** 0.1  
**Область:** только механизм `Query → Retriever → Candidate Set → Reranker` и локальное подключение `Curator`  
**Вне области:** персональные агенты, Agent Runtime, Astra/Mira/Forge, внешние LLM, коммуникационные gateway, Context Builder и дальнейшее потребление результатов

---

# 1. Цель

Нужен автономный механизм внутри Mastermind, который получает **поисковую или аналитическую задачу над knowledge base**, собирает релевантные кандидаты несколькими независимыми способами, ранжирует их и возвращает структурированный результат с объяснимым provenance.

Базовый pipeline:

```text
Query
  ↓
Query Processor
  ↓
Retriever
  ↓
Candidate Set
  ↓
Deduplication
  ↓
Reranker
  ↓
Relation Expansion
  ↓
Confidence Check
  ├─ enough → Final Result
  └─ not enough → Curator Assist
                      ↓
                 refined query /
                 entity hints /
                 graph suggestions
                      ↓
                  Retriever
                      ↓
                  Final Result
```

Ключевой принцип:

> **Retriever ищет. Reranker оценивает. Curator помогает понять сложный смысл, когда алгоритмического retrieval недостаточно.**

Curator не является заменой Retriever и не должен стоять на пути каждого запроса.

---

# 2. Термины

## 2.1. Query

**Query** — формализованная задача, которую необходимо решить над knowledge base.

Query не обязательно является обычным текстовым поиском.

Примеры:

```text
Найди всё, что Андрей говорил про Saturn за последние полгода.
```

```text
Найди ноты, связанные с механизмом загрузки больших файлов.
```

```text
Определи, куда логически лучше всего поместить эту ноту.
```

```text
Найди существующую entity, которой соответствует упомянутый в ноте человек.
```

Таким образом, Query содержит не только строку поиска, но и **тип задачи**.

---

## 2.2. Query Processor

**Query Processor** — детерминированный программный слой перед Retriever.

Он преобразует входную задачу в машинный `Query Plan`.

Он должен выделять, где это возможно:

- тип задачи;
- исходный текст;
- ключевые термины;
- известные entity;
- временной диапазон;
- metadata constraints;
- допустимые retrieval strategies;
- лимиты;
- требуемый тип результата.

Query Processor сам не ищет знания и не принимает семантических решений, требующих LLM.

---

## 2.3. Retriever

**Retriever** — программный оркестратор нескольких поисковых механизмов.

Он отвечает на вопрос:

> **Какие существующие знания наиболее вероятно полезны для текущей Query?**

Retriever не является одной моделью или одним индексом.

---

## 2.4. Candidate

**Candidate** — найденный объект knowledge base, который потенциально относится к Query.

Candidate может представлять:

- note;
- chunk;
- entity;
- relation;
- graph neighborhood;
- metadata-defined object;
- placement target;
- иной индексируемый объект Mastermind.

---

## 2.5. Candidate Set

**Candidate Set** — объединённый пул кандидатов, полученных Retriever из разных retrieval strategies до окончательного ранжирования.

Candidate Set является промежуточным рабочим набором и может содержать:

- дубли;
- пересекающиеся chunks;
- слабые совпадения;
- несколько представлений одного объекта;
- результаты с разной природой score.

---

## 2.6. Reranker

**Reranker** — компонент, который получает Candidate Set и пересчитывает порядок кандидатов относительно **конкретной Query**.

Его задача:

> **не найти новые знания, а определить, какие из уже найденных кандидатов действительно наиболее релевантны.**

---

## 2.7. Curator

**Curator** — маленькая локальная модель внутри Mastermind, которая подключается только в тех случаях, когда обычный retrieval не дал достаточно уверенного результата.

В рамках данного механизма Curator используется для:

- query expansion;
- entity reasoning;
- entity resolution в неоднозначных случаях;
- поиска неявных смысловых признаков;
- graph suggestions;
- placement hypotheses;
- интерпретации сложной естественно-языковой Query.

Curator не является владельцем knowledge base и не применяет изменения самостоятельно.

---

## 2.8. Confidence

**Confidence** — оценка того, достаточно ли имеющихся retrieval evidence для формирования результата без дополнительного семантического прохода Curator.

Confidence должен рассчитываться программно из наблюдаемых сигналов, а не только из самооценки LLM.

---

# 3. Граница механизма

Рассматриваемая система начинается на входе `Query` и заканчивается на структурированном `Final Result`.

```text
IN SCOPE

Query
↓
Query Processor
↓
Retriever
↓
Candidate Set
↓
Deduplication
↓
Reranker
↓
Relation Expansion
↓
Confidence Check
↓
optional Curator Assist
↓
Final Result
```

Не рассматриваются:

```text
Final Result
↓
Context Builder
↓
Agent / LLM
↓
действия во внешнем мире
```

Также здесь не рассматриваются:

- пользовательские personas;
- Astra / Mira / Forge;
- Agent Runtime;
- Task Runtime общего назначения;
- внешние модели;
- Scylla как общесистемная policy-система;
- Saturn;
- Communication Gateway;
- Network Gateway.

Механизм должен быть пригоден к использованию другими частями системы, но не зависеть от них архитектурно.

---

# 4. Архитектурный принцип

Retriever должен иметь достаточно сильный алгоритмический набор инструментов, чтобы большинство запросов решались **без Curator**.

```text
                         QUERY
                           │
                           ▼
                    Query Processor
                           │
          ┌────────────────┼─────────────────┐
          │                │                 │
          ▼                ▼                 ▼
       FTS/BM25        Vector Search      Entity Search
          │                │                 │
          ▼                ▼                 ▼
      Metadata          Graph            Temporal
       Search          Traversal          Search
          │                │                 │
          └────────────────┼─────────────────┘
                           │
                    Candidate Pool
                           │
                     Deduplication
                           │
                      Reranking
                           │
                 Relation Expansion
                           │
                    Confidence Check
                       ┌───┴───┐
                      yes      no
                       │       │
                       │       ▼
                       │    Curator
                       │   ├─ query expansion
                       │   ├─ entity reasoning
                       │   ├─ graph suggestions
                       │   └─ placement hypotheses
                       │       │
                       └───┬───┘
                           ▼
                      Final Result
```

Curator является **fallback / assist-механизмом**, а не обязательной стадией каждого запроса.

---

# 5. Query Model

Рекомендуемый внутренний формат:

```yaml
query_id: q_01H...
type: placement_analysis

input:
  note_id: note_123
  text: |
    ...

constraints:
  time_range: null
  object_types:
    - note
    - entity
  domains: []
  metadata: {}

retrieval:
  strategies:
    - full_text
    - vector
    - entity
    - graph
    - metadata
  candidate_limit: 100
  rerank_limit: 20
  graph_depth: 2

output:
  type: placement_recommendation
  alternatives: 3
  require_evidence: true

curator:
  allowed: true
  max_passes: 1
```

Query должен быть сохраняемым и воспроизводимым.

---

# 6. Query Processor

Query Processor формирует `Query Plan`.

Пример:

```text
Query:
"Что Андрей говорил про Saturn за последние полгода?"
```

План:

```yaml
query_type: knowledge_lookup

entities:
  - raw: Андрей
    expected_type: person

topics:
  - Saturn

time_range:
  relative: 6_months

strategies:
  - entity
  - full_text
  - vector
  - graph
  - temporal

expand_relations:
  depth: 2

limits:
  candidates: 100
  rerank: 20
  final: 10
```

Для простых структурированных запросов Query Processor должен работать без LLM.

Если запрос невозможно надёжно декомпозировать, он может сохранить исходную формулировку для последующей эскалации Curator.

---

# 7. Инструменты Retriever

## 7.1. FTS / BM25

Используется для точных совпадений:

- имена;
- названия;
- термины;
- идентификаторы;
- точные словоформы;
- цитаты;
- явные упоминания.

Пример:

```text
Saturn
```

может напрямую найти документы, где присутствует строка `Saturn`.

---

## 7.2. Vector Search

Используется для семантических совпадений.

Например запрос:

```text
механизм загрузки больших файлов
```

может найти ноту, где используется формулировка:

```text
буферизация крупных upload на промежуточном сервере
```

даже без совпадения слов.

---

## 7.3. Entity Search

Ищет конкретные сущности:

```text
person
project
service
organization
event
topic
```

Поддерживает:

- canonical ID;
- canonical name;
- aliases;
- handles;
- известные внешние идентификаторы.

---

## 7.4. Metadata Search

Фильтрует и ищет по структурированным свойствам:

```text
type
tags
domain
source
created_at
updated_at
status
author
sensitivity
project
entity_refs
```

Metadata Search не должен заменяться vector search там, где условие может быть проверено точно.

---

## 7.5. Graph Traversal

Исследует существующие отношения между объектами.

Пример:

```text
person:andrey
   ↓ discussed
service:saturn
   ↓ mentioned_in
note:...
```

Graph Traversal должен иметь жёсткие ограничения:

- максимальная depth;
- допустимые relation types;
- максимальное количество visited nodes;
- cycle protection.

---

## 7.6. Temporal Search

Работает с временной осью:

- материалы за период;
- последнее состояние;
- события до/после даты;
- последовательность изменений;
- recent-first retrieval.

---

## 7.7. Relation Expansion

После первичного rerank Retriever может расширить top-кандидаты через близкие связи графа.

Например найдено:

```text
note → Saturn
```

Relation Expansion может добавить:

```text
Saturn → upload subsystem
Saturn → related design decision
Saturn → person:Andrey
```

Expansion выполняется ограниченно и не должен превращаться в бесконтрольный обход графа.

---

# 8. Сбор Candidate Set

Все retrieval strategies возвращают результаты в единый нормализованный формат.

Пример:

```yaml
candidate_id: cand_001
object_ref: note_827
object_type: note

source_strategy:
  - full_text
  - graph

scores:
  bm25: 12.4
  vector: 0.83
  graph: 0.71
  temporal: 0.92

matched:
  terms:
    - Saturn
  entities:
    - service:saturn
  relations:
    - discussed_with:person:andrey

evidence:
  - chunk_827_03
  - relation_191
```

Score разных поисковых движков нельзя напрямую считать одной шкалой.

Перед fusion требуется нормализация.

---

# 9. Candidate Fusion

Retriever должен объединять результаты разных стратегий.

Допустимые подходы:

- Reciprocal Rank Fusion;
- нормализованный weighted score;
- rank voting;
- strategy-specific boosts.

Рекомендуемый начальный вариант — **Reciprocal Rank Fusion**, поскольку он не требует считать BM25-score и cosine similarity одной и той же величиной.

Пример:

```text
FTS rank      → 2
Vector rank   → 5
Graph rank    → 1
Temporal rank → 3

        ↓

combined retrieval rank
```

Вес конкретного retrieval strategy должен зависеть от `query_type`.

---

# 10. Deduplication

Перед Reranker Candidate Set очищается от дублей.

Дубли могут возникать, если одна нота найдена одновременно через:

- FTS;
- vector;
- entity relation;
- graph traversal;
- metadata.

Нужно различать:

### Exact duplicate

Один и тот же `object_ref`.

### Chunk overlap

Несколько сильно пересекающихся chunks одной ноты.

### Semantic duplicate

Два объекта содержат практически одинаковое знание.

Exact duplicate устраняется детерминированно.

Chunk overlap объединяется программно.

Semantic duplicate может определяться embeddings + threshold; Curator для этого не требуется по умолчанию.

---

# 11. Reranker

Reranker получает:

```text
Query
+
Candidate Set
```

и возвращает:

```text
ordered relevant candidates
```

Reranker не должен владеть поисковыми индексами.

Его интерфейс должен быть независимым:

```text
rerank(query, candidates) → ranked_candidates
```

Каждый результат должен содержать:

```yaml
object_ref: note_827
rank: 1
score: 0.91

relevance:
  direct: true
  entity_match: true
  temporal_match: true
  semantic_match: 0.88

evidence:
  - chunk_827_03
```

Начальная реализация может состоять из deterministic scoring + lightweight reranker model.

---

# 12. Confidence Check

После reranking система должна определить, можно ли считать результат достаточно надёжным.

Confidence не равен top-1 reranker score.

Он должен учитывать несколько сигналов.

Пример:

```text
top_score
score_gap(top1, top2)
agreement_between_strategies
entity_resolution_confidence
number_of_independent_evidence
graph_consistency
metadata_consistency
```

Пример концептуальной формулы:

```text
confidence =
    relevance_score
  + strategy_agreement
  + evidence_support
  + entity_certainty
  - ambiguity_penalty
```

Точные веса являются частью последующей калибровки.

---

# 13. Когда вызывается Curator

Curator подключается только при выполнении определённых условий.

Примеры:

### Неоднозначная entity

```text
Саша
```

совпадает с несколькими объектами.

### Недостаточный score gap

```text
candidate A = 0.81
candidate B = 0.80
candidate C = 0.79
```

и система не может уверенно выбрать один вариант.

### Сложный смысловой запрос

```text
Почему отношения с этим человеком ухудшились?
```

### Слабое пересечение retrieval strategies

FTS, vector и graph возвращают совершенно разные top-кандидаты.

### Неявный placement

У ноты есть несколько логически обоснованных мест.

### Недостаточная graph connectivity

Найдено семантическое совпадение, но нет достаточных структурных связей.

---

# 14. Что получает Curator

Curator не получает всю knowledge base.

Для каждого вызова формируется минимальный пакет:

```yaml
task:
  type: placement_analysis

query:
  ...

subject:
  note_id: note_123
  text: ...

taxonomy:
  ...

top_candidates:
  - ...
  - ...
  - ...

graph_slice:
  ...

ambiguities:
  - ...
```

Curator видит:

1. исходный Query;
2. анализируемый объект;
3. taxonomy;
4. top-N кандидатов;
5. ограниченный релевантный graph slice;
6. конкретную причину эскалации.

---

# 15. Что возвращает Curator

Curator возвращает только структурированный `Proposal`.

Пример:

```yaml
proposal_type: retrieval_refinement

query_expansion:
  terms:
    - file upload
    - large uploads
    - upload buffering

entity_resolution:
  - raw: Saturn
    entity_ref: service:saturn
    confidence: 0.98

graph_hints:
  - from: service:saturn
    relation: has_subsystem
    target_type: subsystem

placement_hypotheses:
  - target_ref: topic:file_upload
    rationale: >
      Note primarily concerns upload buffering and is linked
      to Saturn as implementation context.

request_second_pass: true
```

Curator **не возвращает команды изменения knowledge base**.

---

# 16. Второй retrieval pass

Если Curator предложил refinement, Retriever выполняет новый ограниченный проход.

```text
Initial Query
   ↓
Retriever
   ↓
Reranker
   ↓
low confidence
   ↓
Curator Proposal
   ↓
Query Plan v2
   ↓
Retriever second pass
   ↓
Reranker
   ↓
Final Result
```

Количество проходов должно быть ограничено.

Для MVP:

```text
max_curator_passes = 1
```

Это защищает механизм от бесконечного reasoning loop.

---

# 17. Основной сценарий: определить место для новой ноты

Это один из ключевых сценариев данного механизма.

Вход:

```text
"Рассчитай, куда эта нота встанет лучше всего."
```

и сама нота.

---

## 17.1. Шаг 1 — Query Processor

Формируется:

```yaml
query_type: placement_analysis

subject:
  object_type: note
  note_ref: draft:123

expected_result:
  - best_placement
  - alternatives
  - evidence
  - confidence
```

---

## 17.2. Шаг 2 — Retriever

Retriever извлекает поисковые признаки из содержимого ноты программными средствами, где это возможно:

- title;
- explicit links;
- tags;
- metadata;
- known entity mentions;
- lexical terms;
- embedding.

После этого параллельно выполняются:

```text
FTS/BM25
Vector Search
Entity Search
Metadata Search
Graph Traversal
```

Цель — найти не просто похожие тексты, а **объекты, которые могут объяснить потенциальное место ноты в существующей структуре**.

---

## 17.3. Шаг 3 — Candidate Set

Например:

```text
candidate 1: Project / Saturn
candidate 2: Topic / File Upload
candidate 3: Architecture / Storage
candidate 4: Note / Saturn Upload Buffer
candidate 5: Entity / Saturn
```

Для каждого кандидата сохраняются причины попадания.

---

## 17.4. Шаг 4 — Reranker

Reranker оценивает кандидатов относительно задачи `placement_analysis`.

Это важно: одинаковый Candidate Set может иметь другой порядок для другой Query.

Для placement score может учитывать:

```text
semantic similarity
entity overlap
graph proximity
taxonomy compatibility
metadata compatibility
existing-link density
topic specificity
```

---

## 17.5. Шаг 5 — Relation Expansion

Top-кандидаты расширяются на один ограниченный graph-hop.

Например:

```text
Saturn
├── Storage
├── Upload subsystem
├── Buffering
└── Architecture decisions
```

Это позволяет найти более специфичное место, которое не попало в первичный поиск.

---

## 17.6. Шаг 6 — Confidence Check

Возможны два результата.

### Высокая уверенность

```text
1. Topic / File Upload       0.93
2. Project / Saturn          0.71
3. Architecture / Storage   0.48
```

Система может завершить анализ без Curator.

### Низкая уверенность

```text
1. Topic / File Upload       0.81
2. Project / Saturn          0.79
3. Architecture / Storage   0.77
```

Вызывается Curator.

---

## 17.7. Шаг 7 — Curator Assist

Curator получает:

```text
note
+
taxonomy
+
top candidates
+
local graph
+
reason = ambiguous_placement
```

и может предложить:

```text
Основная тема ноты = upload buffering.
Saturn = implementation context.
Искать более специфичный узел около
Topic/File Upload и связать его с Saturn.
```

Это является **гипотезой**, а не окончательным решением.

---

## 17.8. Шаг 8 — второй retrieval pass

Retriever проверяет предложенную гипотезу обычными индексами и графом.

Если найден:

```text
topic:large_file_upload
```

со связями:

```text
topic:large_file_upload
    → part_of → service:saturn
    → related_to → storage
```

он может стать новым top-1.

---

# 18. Результат placement analysis

Механизм не должен просто отвечать строкой:

```text
Положи в Saturn.
```

Он должен возвращать структурированный результат.

Пример:

```yaml
query_id: q_01H...
result_type: placement_recommendation

subject:
  note_ref: draft:123

recommended:
  target_ref: topic:large_file_upload
  score: 0.94
  confidence: high

reasons:
  - strongest semantic match
  - direct relation to service:saturn
  - matches taxonomy topic
  - 4 neighboring notes share same subject

alternatives:
  - target_ref: service:saturn
    score: 0.79
    reason: broader project-level placement

  - target_ref: topic:storage
    score: 0.63
    reason: related but less specific

evidence:
  - note:827
  - note:932
  - relation:191
  - entity:service:saturn

curator_used: true
retrieval_passes: 2
```

Человек или другой компонент системы после этого может решить, применять рекомендацию или нет.

---

# 19. Explainability и provenance

Каждый Final Result должен позволять восстановить путь решения.

Минимальный trace:

```yaml
query_id: ...
query_plan_version: 2

strategies_used:
  - full_text
  - vector
  - graph
  - entity

candidate_count:
  initial: 114
  deduplicated: 76
  reranked: 20

curator:
  used: true
  reason: ambiguous_placement
  passes: 1

evidence_refs:
  - ...

ranking_version: reranker-v1
index_versions:
  fts: ...
  vector: ...
  graph: ...
```

Это позволяет ответить на вопрос:

> **Почему механизм предложил именно это место?**

---

# 20. Детерминированность и обратимость

Механизм должен разделять:

```text
analysis
```

и

```text
mutation
```

Данный pipeline только анализирует и возвращает результат.

Он не должен самостоятельно:

- перемещать ноту;
- менять metadata;
- создавать relation;
- удалять relation;
- переименовывать entity;
- изменять taxonomy.

Если позже будет добавлено применение результата, оно должно быть отдельной операцией.

Таким образом:

```text
Query → Analysis → Proposal
```

не равно:

```text
Query → Mutation
```

---

# 21. Failure modes

## 21.1. Ничего не найдено

Возвращается:

```yaml
status: insufficient_evidence
reason: no_candidates
```

а не выдуманный placement.

---

## 21.2. Слишком много равных кандидатов

```yaml
status: ambiguous
```

с top alternatives и evidence.

---

## 21.3. Curator не помог

Система возвращает исходную неоднозначность.

Curator не имеет права создавать уверенность там, где evidence отсутствует.

---

## 21.4. Индекс недоступен

Результат должен явно показывать degraded mode:

```yaml
degraded:
  vector_search: unavailable
```

и confidence должен снижаться.

---

## 21.5. Graph содержит конфликтующие связи

Конфликт сохраняется в результате:

```yaml
conflicts:
  - ...
```

а не скрывается выбором одной версии.

---

# 22. Интерфейсы модулей

Минимальный набор внутренних интерфейсов:

```text
QueryProcessor.build(query_input)
    → QueryPlan

Retriever.retrieve(query_plan)
    → CandidateSet

Deduplicator.process(candidate_set)
    → CandidateSet

Reranker.rerank(query_plan, candidate_set)
    → RankedSet

RelationExpander.expand(query_plan, ranked_set)
    → RankedSet

ConfidenceEvaluator.evaluate(query_plan, ranked_set)
    → ConfidenceDecision

Curator.assist(curator_context)
    → CuratorProposal

Retriever.refine(query_plan, curator_proposal)
    → QueryPlan v2

ResultBuilder.build(...)
    → FinalResult
```

Каждый модуль должен быть заменяемым независимо.

---

# 23. Что не должно быть монолитным

Не следует объединять в один компонент:

```text
Retriever + Reranker + Curator
```

Причины:

1. Retriever должен быть тестируем без LLM.
2. Reranker должен быть заменяемым.
3. Curator должен иметь жёстко ограниченный вход.
4. Можно отдельно измерять качество каждого этапа.
5. Ошибку можно локализовать.
6. Retrieval можно улучшать без переобучения Curator.
7. Curator можно заменить без перестройки индексов.

---

# 24. Метрики

Механизм должен иметь offline evaluation dataset.

Для retrieval:

```text
Recall@K
Precision@K
MRR
nDCG
```

Для entity resolution:

```text
accuracy
top-k accuracy
abstention quality
```

Для placement:

```text
top-1 accepted placement
top-3 accepted placement
abstention rate
curator escalation rate
```

Отдельно измерять:

```text
latency
candidate count
curator usage rate
second-pass rate
```

Цель Curator — не максимизировать количество своих вызовов, а уменьшать ошибки в сложных случаях.

---

# 25. MVP

Первая рабочая версия может содержать:

```text
Query Processor
│
├── FTS/BM25
├── Vector Search
├── Entity Search
├── Metadata Filter
├── Graph Traversal depth <= 2
└── Temporal Filter

↓
Candidate Fusion
↓
Exact Deduplication
↓
Reranker
↓
Confidence Evaluator
↓
Curator fallback
↓
one bounded second retrieval pass
↓
Final Result + provenance
```

В MVP не обязательны:

- сложная semantic deduplication;
- многошаговый Curator;
- автоматическая mutation knowledge base;
- сложное обучение reranker;
- динамические graph algorithms высокой глубины.

---

# 26. Checkpoints реализации

## Checkpoint 1 — deterministic retrieval

Curator выключен.

Проверить:

```text
Query
↓
FTS + Vector + Entity + Metadata + Graph
↓
Candidate Set
↓
Reranker
↓
Final Result
```

Результат воспроизводим и содержит provenance.

---

## Checkpoint 2 — placement analysis

На тестовом наборе нот механизм должен:

1. получить новую ноту;
2. найти связанные ноты/entities/topics;
3. построить Candidate Set;
4. вернуть top placement candidates;
5. объяснить evidence.

Curator всё ещё выключен.

---

## Checkpoint 3 — confidence

Добавить автоматическое различение:

```text
confident
ambiguous
insufficient_evidence
```

---

## Checkpoint 4 — Curator assist

Curator включается только для `ambiguous`.

Проверить:

```text
initial retrieval
↓
ambiguity
↓
Curator Proposal
↓
second retrieval
↓
improved / unchanged result
```

---

## Checkpoint 5 — offline evaluation

Собрать dataset:

```text
Query
expected relevant objects
expected placement
allowed alternatives
```

и измерять регрессии автоматически.

---

# 27. Итоговая модель

```text
Query
  │
  ▼
Query Processor
  │
  ▼
Retriever
  │
  ├── FTS / BM25
  ├── Vector Search
  ├── Entity Search
  ├── Metadata Search
  ├── Graph Traversal
  └── Temporal Search
  │
  ▼
Candidate Set
  │
  ▼
Deduplication / Fusion
  │
  ▼
Reranker
  │
  ▼
Relation Expansion
  │
  ▼
Confidence Check
  │
  ├── sufficient
  │       │
  │       ▼
  │   Final Result
  │
  └── ambiguous / insufficient
          │
          ▼
       Curator
          │
          ├── query expansion
          ├── entity reasoning
          ├── graph suggestions
          └── placement hypotheses
          │
          ▼
     Query Plan v2
          │
          ▼
       Retriever
          │
          ▼
       Reranker
          │
          ▼
      Final Result
```

Функциональное разделение:

```text
Query Processor
= что именно нужно найти или рассчитать

Retriever
= какие существующие объекты могут быть релевантны

Candidate Set
= рабочий пул потенциальных ответов

Reranker
= какие кандидаты лучше соответствуют конкретной задаче

Curator
= какую дополнительную семантическую гипотезу стоит проверить,
  если обычный retrieval не дал уверенного результата

Final Result
= структурированный вывод с evidence, confidence и provenance
```

Главное архитектурное правило:

> **Curator не заменяет поиск и не выдаёт решение из собственного знания. Он помогает сформировать более сильную поисковую гипотезу, после чего эта гипотеза снова проверяется Retriever по фактическому содержимому knowledge base.**
