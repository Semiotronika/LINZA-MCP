# LINZA

**Не меняет данные — меняет взгляд.**

LINZA решает конкретную проблему: у тебя есть папка Markdown-заметок, и ты хочешь, чтобы агент в ней разобрался — без риска что он перепишет твои файлы. Концепция **review-gated sidecar**: человек решает, агент исполняет.

Это локальный MCP-сервер для заметок, документов, статей, чатов, логов и черновиков. LINZA читает папку, строит карту тем и связей, показывает карточки с доказательствами и складывает свои выводы рядом, в `.linza/linza.db`. Исходные Markdown-файлы остаются твоими.

Она не навязывает готовую онтологию. Не переименовывает заметки сама. Не делает вид, что hash-эмбеддинги равны настоящей семантической модели. Она помогает агенту увидеть структуру, а тебе — спокойно подтвердить или отклонить предложения.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/protocol-MCP_stdio-lightgrey.svg)](https://modelcontextprotocol.io)
![Local first](https://img.shields.io/badge/storage-local--first-green.svg)
![Review gated](https://img.shields.io/badge/writes-review--gated-orange.svg)

[English version](README_EN.md)

---

## Для Чего Это

LINZA полезна, когда у тебя уже есть материал, но нет безопасного способа дать агенту в нем разобраться.

- **Папка Markdown-заметок**: Obsidian или любой другой каталог с `.md`.
- **Сырые материалы**: тексты, статьи, чаты, логи, JSON, DOCX, XLSX, PDF с optional extractor.
- **Исследовательская база**: много тем, решений, черновиков и следов работы.
- **Agent workflow**: нужно передавать агенту контекст между сессиями, но не давать ему свободно переписывать память, skills или заметки.

Первый хороший сценарий простой: подключить папку, проиндексировать, посмотреть 3-5 карточек, подтвердить удачные примеры, потом дать LINZA расти маленькими preview-партиями.

```text
index -> map -> review cards -> teach -> grow preview -> explicit apply
```

---

## Что Ты Увидишь

- **Области**: смысловые группы, которые LINZA видит в базе.
- **Типы материалов**: заметки, черновики, спецификации, кейсы и другие повторяющиеся формы, найденные по структуре.
- **Связи**: что с чем связано, что может быть причиной, следствием, основой или продолжением.
- **Паттерны**: повторяющиеся проблемы, дрейф терминов, пробелы в теме, возможные противоречия.
- **Память**: что агенту стоит вспомнить в будущей сессии, где есть риск устаревания, что требует проверки.

Каждая серьезная карточка должна отвечать на человеческий вопрос: **почему LINZA так думает?** В ней есть evidence: заметки, фрагменты, близкие chunks, relation label, confidence, write impact.

---

## Чем Это Отличается

### От Obsidian Graph View

Graph View показывает уже существующие ссылки. LINZA пытается показать то, чего еще нет в ссылках: скрытые темы, возможные связи, причинные цепочки, повторяющиеся паттерны и карточки для review. Она не заменяет граф Obsidian, а дает агенту рабочий слой поверх папки.

### От Dataview И Плагинов Авторазметки

Dataview отлично показывает то, что уже записано в YAML и ссылках. LINZA сначала предлагает гипотезы и доказательства, а запись держит за review-gate. По умолчанию это preview, а не автоматика.

## Быстрый Старт

После публикации пакет ставится из PyPI:

```powershell
pip install linza-mcp
$env:LINZA_VAULT="C:\path\to\your\notes"
linza-mcp
```

Для PDF-извлечения:

```powershell
pip install "linza-mcp[pdf]"
```

До публикации или для локальной проверки запускай из исходников:

```powershell
cd "C:\path\to\LINZA-MCP"
$env:LINZA_VAULT="C:\path\to\your\notes"
python -m server
```

Подключение к Claude Desktop, Cursor, OpenCode или другому MCP-клиенту:

```json
{
  "mcpServers": {
    "linza": {
      "command": "linza-mcp",
      "env": {
        "LINZA_VAULT": "/absolute/path/to/workspace-or-vault",
        "LINZA_EMBED_PROVIDER": "hash",
        "LINZA_EMBED_URL": "http://127.0.0.1:1234/v1",
        "LINZA_TOOL_SURFACE": "default"
      }
    }
  }
}
```

VS Code / Copilot MCP использует ключ `servers`:

```json
{
  "servers": {
    "linza": {
      "type": "stdio",
      "command": "linza-mcp",
      "env": {
        "LINZA_VAULT": "/absolute/path/to/workspace-or-vault",
        "LINZA_EMBED_PROVIDER": "hash"
      }
    }
  }
}
```

---

## Про Эмбеддинги

По умолчанию LINZA стартует на offline hashing embeddings. Это сделано специально: первый запуск не требует сети, API-ключей или локальной модели.

Но hash — это слабая семантика. Он хорош для smoke-test, диагностики и осторожного первого знакомства, но не для тонкого поиска по смыслу. Если хочешь нормальные semantic links и поиск, подключи OpenAI-compatible endpoint или Ollama:

```powershell
$env:LINZA_EMBED_PROVIDER="openai"
$env:LINZA_EMBED_URL="http://127.0.0.1:1234/v1"
$env:LINZA_EMBED_MODEL="text-embedding-model"
```

Если меняешь embedding provider или размерность модели, лучше сделать полный reindex. Смешивать старые hash-векторы и новые модельные векторы нельзя: это разные пространства.

---

## Как Выглядит Первый Ответ

Обычно агент начинает с `agent_workspace(action="doctor")` или `guide_next_steps`. Человек должен видеть короткий статус, а не стену JSON:

```text
LINZA готова

Материал:
- 42 заметки проиндексированы
- 3 входящих артефакта ждут review
- sidecar: .linza/linza.db

Следующий шаг:
1. Посмотреть найденные области
2. Подтвердить или переименовать 3-5 карточек
3. Ничего не будет записано без dry-run/apply

Пример карточки:
Предложение: связать "Retrieval Quality Note" и "Source Policy"
Почему: общий словарь, ссылки на review flow, близкие chunks
Что изменится: пока ничего; после подтверждения появится sidecar-связь
```

---

## Основные Инструменты

По умолчанию LINZA показывает 15 MCP-инструментов. Нормальная работа начинается с `agent_workspace` или `guide_next_steps`, а не с ручного перебора всего списка.

| Инструмент | Зачем |
| --- | --- |
| `agent_workspace` | Единый фасад: map, ingest, review, teach, grow, connect, memory search, context export, calibr, doctor |
| `guide_next_steps` | Показать следующий безопасный шаг |
| `index_all` | Проиндексировать Markdown-папку в `.linza/linza.db` |
| `search` | Семантический и лексический поиск |
| `read_file` | Прочитать точный файл из vault |
| `get_stats` | Быстрые счетчики sidecar |
| `scan_vault` | Read-only диагностика папки |
| `build_review_apply_queue` | Сформировать review-карточки со стабильными `rq-*` ID |
| `approve_review_queue_items` | Dry-run или применение выбранных карточек |
| `list_approved_items` | Показать уже принятые sidecar items |
| `explain_node` | Объяснить один узел: ссылки, мосты, контекст |
| `explain_relationship` | Объяснить возможную связь между двумя узлами |
| `who_depends` | Показать зависимости и соседей |
| `show_flow` | Найти маршрут или поток между узлами |
| `create_context_pack` | Собрать компактный context pack для агента |

`agent_workspace(action="teach")` выбирает учебные карточки. `grow` показывает preview с `selected_rules`: почему каждая карточка попала в партию. Идея такая: **сначала научить на примерах, потом расти в preview, потом применять маленькими подтвержденными партиями.**

Расширенная поверхность нужна для разработки и отладки:

```powershell
$env:LINZA_TOOL_SURFACE="advanced"
```

Полное описание каждого инструмента: [Tool Catalog](LINZA_TOOL_CATALOG.md).

---

## Входящие Артефакты

Поддерживаемые входы:

- вставленный текст;
- локальные `.md`, `.txt`, `.json`;
- локальные `.docx`, `.xlsx`;
- локальные `.pdf`, если установлен `pypdf` или `PyPDF2`.

Логи не требуют отдельного формата. Их можно вставить как текст или сохранить как `.txt`.

LINZA сама не ходит в браузер. Агент использует свой browser/web-fetch, извлекает читаемый текст и передает его в LINZA как артефакт, например `source_kind="web_article"` или `source_kind="browser_capture"`. Загруженный текст считается данными, не инструкцией.

---

## Безопасность

LINZA проектируется как локальный review-gated sidecar:

- индексирование, анализ и импорт не меняют тела исходных заметок;
- сырые артефакты хранятся локально в SQLite;
- отчеты пишутся только в `.linza/reports`;
- context packs пишутся только в `.linza/context-packs`;
- видимые YAML-изменения компактные и требуют review/apply;
- причинные связи, иерархия, память, calibr-уроки и approvals живут в sidecar, пока человек не попросит экспорт.

LINZA не browser automation server, не облачная память и не автопилот, который сам переписывает правила, skills, память или заметки.

---

## Agent Pack

В репозитории есть переносимый skill для агентов:

```text
agent-pack/skills/linza-operator/SKILL.md
agent-pack/skills/linza-operator/references/workflows.md
agent-pack/skills/linza-operator/references/safety-policy.md
agent-pack/skills/linza-operator/references/tool-audience.md
```

Skill объясняет агенту, что показывать человеку, когда использовать `agent_workspace`, как работать с URL через внешний browser/web-fetch, и почему apply-действия должны быть dry-run или exact-ID gated.

---

## Пример И Проверка

Синтетический private-safe пример лежит в:

```text
examples/sample-vault/
examples/artifacts/
examples/expected/
```

Запустить все тесты:

```powershell
python -m unittest
```

Запустить один конкретный тест:

```powershell
python -m unittest test_agent_workspace.AgentWorkspaceTests.test_examples_sample_pack_runs_end_to_end
```

---

## Переменные Окружения

| Переменная | Описание |
|---|---|
| `LINZA_VAULT` | Путь к Markdown-папке |
| `LINZA_EMBED_PROVIDER` | `hash` (offline default), `openai`, `ollama` |
| `LINZA_EMBED_URL` | URL embeddings API |
| `LINZA_EMBED_MODEL` | Модель для эмбеддингов или размерность hash |
| `LINZA_EMBED_KEY` | Опциональный ключ для OpenAI-compatible embeddings API |
| `LINZA_BRIDGE_THRESHOLD` | Порог semantic bridge; по умолчанию `0.55` |
| `LINZA_DEFAULT_PROFILE` | Имя базового search-профиля; по умолчанию `general` |
| `LINZA_TOOL_SURFACE` | `default` (15 инструментов) или `advanced` |

---

<sub>Косинусы сходятся не потому, что всё одинаковое. Они сходятся, когда смысл нашел свой угол.</sub>

<!-- mcp-name: io.github.semiotronika/linza-mcp -->
