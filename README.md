# LINZA

<!-- mcp-name: io.github.semiotronika/linza-mcp -->

**Не меняет данные — меняет взгляд.**

У тебя есть папка с заметками, статьями, логами, черновиками, чатами. В ней уже есть структура, связи, эволюция мысли — просто она скрыта за объёмом. LINZA делает невидимое видимым.

Она не переписывает твои файлы. Не навязывает категории. Не решает за тебя. Она наблюдает, находит паттерны, показывает связи с доказательствами — а ты решаешь, что из этого важно.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/protocol-MCP_stdio-lightgrey.svg)](https://modelcontextprotocol.io)
![Local first](https://img.shields.io/badge/storage-local--first-green.svg)
![Review gated](https://img.shields.io/badge/writes-review--gated-orange.svg)

🇬🇧 [English version](README_EN.md)

---

## Что ты увидишь

- **Области** — LINZA находит смысловые кластеры в сырой базе и предлагает назвать их
- **Типы материалов** — шаблоны, кейсы, заметки, спецификации обнаруживаются по структуре
- **Связи** — какие заметки относятся друг к другу, какие решения привели к каким результатам
- **Паттерны** — повторяющиеся проблемы, дрейф терминологии, противоречия между заметками, пробелы в покрытии темы
- **Память** — что стоит запомнить для будущих сессий, когда перепроверить, что могло устареть

Каждое предложение LINZA сопровождается **доказательствами**: почему она думает что эти заметки связаны, какие сигналы использовала, насколько уверена. Ты видишь не только результат, но и причину.

---

## Как это работает

```
подключил папку → проиндексировал → показал карточки → ты подтвердил → карта готова
```

Записи в твои файлы происходят только после явного подтверждения. По умолчанию — dry-run. Всё что LINZA «думает» живёт в `.linza/linza.db` — sidecar-базе рядом с твоими файлами. Твои заметки остаются твоими.

Базовый контракт:

```text
load/index → analyze → review cards → explicit apply → context export
```

Человек решает смысл. Агент управляет инструментами.

---

## Для кого

- **Solo builders** с папкой Markdown-заметок (Obsidian или любой другой), которые хотят чтобы агент разобрался в материале без риска
- **Исследователи и писатели** — скармливаешь статьи и черновики, получаешь карту тем и связей
- **Команды с agent workflow** — LINZA ловит ошибки агентов, предлагает улучшения, хранит контекст между сессиями
- **Любой, у кого есть папка Markdown** — не обязательно Obsidian, не обязательно размеченный

---

## Быстрый старт

После публикации пакет можно будет установить из PyPI:

```powershell
pip install linza-mcp
$env:LINZA_VAULT="C:\path\to\your\notes"
linza-mcp
```

Для PDF-извлечения установите optional extra:

```powershell
pip install "linza-mcp[pdf]"
```

До публикации или для разработки запускайте из исходников:

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

VS Code / Copilot MCP использует другой верхний ключ:

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

По умолчанию LINZA использует offline hashing embeddings: сервер запускается без сети и без внешнего embedding API. Для более сильной семантики можно явно указать `LINZA_EMBED_PROVIDER=openai` или `LINZA_EMBED_PROVIDER=ollama`.

---

## Как выглядит первый ответ

Обычно агент начинает с `agent_workspace(action="doctor")` или `guide_next_steps`.
Человек видит не сырую простыню JSON, а короткий статус и следующий шаг:

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
Предложение: объединить "Retrieval Quality Note" и "Source Policy"
Почему: общий словарь, ссылки на review flow, близкие chunks
Что изменится: пока ничего; при подтверждении появится sidecar-связь
```

---

## Основные инструменты

По умолчанию LINZA показывает 15 инструментов. Нормальная работа начинается не с полного списка, а с `agent_workspace` или `guide_next_steps`.

| Инструмент | Зачем |
| --- | --- |
| `agent_workspace` | Единый фасад: карта, ingest, review, grow, connect, memory search, context export, calibr, doctor |
| `guide_next_steps` | Показать следующий безопасный шаг |
| `index_all` | Проиндексировать Markdown-базу в `.linza/linza.db` |
| `search` | Семантический поиск по заметкам |
| `read_file` | Прочитать файл из vault |
| `build_review_apply_queue` | Сформировать review-карточки с устойчивыми `rq-*` ID |
| `approve_review_queue_items` | Dry-run или применение выбранных карточек |
| `list_approved_items` | Посмотреть, что уже принято |
| `explain_node` | Объяснить один узел: ссылки, мосты, контекст |
| `explain_relationship` | Объяснить связь между двумя узлами |
| `who_depends` | Показать зависимости и соседей узла |
| `show_flow` | Найти маршрут или поток между узлами |
| `create_context_pack` | Собрать компактный пакет контекста для агента |
| `get_stats` | Статистика sidecar |
| `scan_vault` | Read-only диагностика базы |

Расширенная поверхность для разработки и отладки:

```powershell
$env:LINZA_TOOL_SURFACE="advanced"
```

Полное описание каждого инструмента: [LINZA_TOOL_CATALOG.md](LINZA_TOOL_CATALOG.md).

---

## Входящие артефакты

Поддерживаемые текстовые входы:

- вставленный текст;
- локальные `.md`, `.txt`, `.json`;
- локальные `.docx`, `.xlsx` (извлечение через стандартные библиотеки);
- локальные `.pdf`, если установлен `pypdf` или `PyPDF2`.

Логи не требуют отдельного формата — вставляй как текст или сохраняй как `.txt`.

**Веб-страницы:** LINZA сама не ходит в интернет. Агент использует свой browser или web-fetch, извлекает текст и передаёт в LINZA как артефакт с `source_kind="web_article"`. Загруженный текст — недоверенные данные, он не становится инструкцией без review.

---

## Безопасность

LINZA проектируется как локальный review-gated sidecar:

- исходные тексты заметок **не меняются** при индексации, анализе и импорте;
- сырые артефакты хранятся локально в SQLite;
- отчёты пишутся только в `.linza/reports`;
- context packs пишутся только в `.linza/context-packs`;
- видимые YAML-изменения компактны и требуют явного review/apply;
- причинные связи, иерархия, память, calibr-уроки и approvals живут в sidecar, пока человек не попросит экспорт.

LINZA **не является** browser-автоматизацией, облачной памятью или автопилотом, который сам меняет правила, skills, память и заметки.

---

## Agent Pack

В репозитории есть переносимый пакет инструкций для агентов:

```text
agent-pack/skills/linza-operator/SKILL.md
agent-pack/skills/linza-operator/references/workflows.md
agent-pack/skills/linza-operator/references/safety-policy.md
agent-pack/skills/linza-operator/references/tool-audience.md
```

Skill объясняет агенту что показывать человеку, когда использовать `agent_workspace`, как работать с URL через внешний browser/web-fetch, и почему apply-действия должны быть dry-run или exact-ID gated.

---

## Пример и проверка

Синтетический private-safe пример лежит в:

```text
examples/sample-vault/
examples/artifacts/
examples/expected/
```

Запустить полный regression suite:

```powershell
python -m unittest
```

Проверка example pack:

```powershell
python -m unittest test_agent_workspace.AgentWorkspaceTests.test_examples_sample_pack_runs_end_to_end
```

Тесты покрывают MCP surface, artifact flow, review-card filtering, generated-write safety, example pack и calibr trace review.

---

## Переменные окружения

| Переменная | Описание |
|---|---|
| `LINZA_VAULT` | Путь к папке с Markdown |
| `LINZA_EMBED_PROVIDER` | `hash` (offline default), `openai`, `ollama` |
| `LINZA_EMBED_URL` | URL embeddings API |
| `LINZA_EMBED_MODEL` | Модель для эмбеддингов |
| `LINZA_EMBED_KEY` | Опциональный ключ для совместимого embeddings API |
| `LINZA_BRIDGE_THRESHOLD` | Порог semantic bridge; по умолчанию `0.55` |
| `LINZA_DEFAULT_PROFILE` | Имя базового search-профиля; по умолчанию `general` |
| `LINZA_TOOL_SURFACE` | `default` (15 инструментов) или `advanced` (полный набор) |
