# LINZA

> *Не меняет данные — меняет взгляд.*

Локальный MCP-сервер для заметок, документов, статей, чатов, логов и черновиков. LINZA читает папку, строит карту тем и связей.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/protocol-MCP_stdio-lightgrey.svg)](https://modelcontextprotocol.io)
![Local first](https://img.shields.io/badge/storage-local--first-green.svg)
![Review gated](https://img.shields.io/badge/writes-review--gated-orange.svg)

[English version](README_EN.md)

LINZA решает конкретную проблему: у вас есть папка Markdown-заметок и входящие материалы — документы, статьи, чаты, логи, — и вы хотите, чтобы агент в этом разобрался. LINZA работает по концепции **review-gated sidecar**: человек решает, агент исполняет.

Агент анализирует данные, видит основные оси, вокруг которых строится ваша работа, и складывает свои выводы рядом, в локальную SQLite-базу. Исходные файлы остаются на месте; LINZA строит граф знаний по их содержанию, не переписывая документы.

LINZA помогает агенту увидеть структуру, а вам — спокойно подтвердить или отклонить предложения. После нескольких подтверждений агент может продолжать работу по принятым примерам: сначала preview, потом небольшие явно подтвержденные партии.

---

## Для чего

LINZA полезна, когда у вас уже есть материал, но нет безопасного способа дать агенту в нем разобраться.

- **Папка Markdown-заметок**: Obsidian или любой другой каталог с `.md`.
- **Сырые материалы**: тексты, статьи, чаты, логи, JSON, DOCX, XLSX, PDF через опциональный локальный экстрактор.
- **Исследовательская база**: много тем, решений, черновиков и следов работы.

Примерный сценарий: подключить папку, проиндексировать, посмотреть 3-5 предложений от агента в виде "карточек", подтвердить удачные примеры, потом дать LINZA расти маленькими партиями.

```text
index -> map -> review cards -> teach -> grow preview -> explicit apply
```

---

## Что агент видит в базе через LINZA

- **Области**: крупные смысловые группы. LINZA индексирует тексты и их эмбеддинги, чтобы агент мог предложить самые заметные и плотные области для review.
- **Типы материалов**: заметки, черновики, спецификации, кейсы и другие повторяющиеся формы, найденные по структуре.
- **Связи**: что с чем связано, что может быть причиной, следствием, основой или продолжением.
- **Паттерны**: повторяющиеся проблемы, дрейф терминов, пробелы в теме, возможные противоречия.
- **Память**: что агенту стоит вспомнить в будущей сессии, где есть риск устаревания, что требует проверки.


---

## Установка

### 1. Установить LINZA

```powershell
python -m pip install linza-mcp
```

Если нужно читать PDF-файлы прямо через LINZA:

```powershell
python -m pip install "linza-mcp[pdf]"
```

Если PDF не нужны, достаточно обычной установки. `[pdf]` добавляет локальный PDF-экстрактор `pypdf`.

### 2. Выбрать папку

LINZA работает с любой папкой Markdown. Это может быть Obsidian vault, рабочая папка проекта или отдельная папка с документами.

В примерах ниже замените `/absolute/path/to/workspace-or-vault` на свой путь.

### 3. Настроить эмбеддинги

Для смыслового поиска LINZA нужна локальная модель эмбеддингов.

Самый простой путь — LM Studio:

1. Открыть LM Studio.
2. Скачать модель эмбеддингов, например `text-embedding-granite-embedding-278m-multilingual`, `nomic-embed-text-v1.5` или другую embedding-модель.
3. Запустить Local Server.
4. Проверить, что endpoint доступен на `http://127.0.0.1:1234/v1`.

### 4. Подключить к MCP-клиенту

Подключение к Claude Desktop, Cursor, OpenCode или другому MCP-клиенту:

```json
{
  "mcpServers": {
    "linza": {
      "command": "linza-mcp",
      "env": {
        "LINZA_VAULT": "/absolute/path/to/workspace-or-vault",
        "LINZA_EMBED_PROVIDER": "lmstudio",
        "LINZA_EMBED_URL": "http://127.0.0.1:1234/v1",
        "LINZA_EMBED_MODEL": "your-embedding-model-name",
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
        "LINZA_EMBED_PROVIDER": "lmstudio",
        "LINZA_EMBED_URL": "http://127.0.0.1:1234/v1",
        "LINZA_EMBED_MODEL": "your-embedding-model-name"
      }
    }
  }
}
```

### 5. Проверить запуск

```powershell
linza-mcp --version
```

После подключения попросите агента:

```text
Проверь LINZA через agent_workspace(action="doctor").
Проиндексируй папку и покажи первые 3-5 review-карточек.
```

### Опциональный запуск через Docker

Docker не обязателен, но в репозитории есть маленький образ для изолированного
stdio-запуска:

```powershell
docker build -t linza-mcp .
docker run --rm -i `
  -v /absolute/path/to/workspace-or-vault:/data/vault `
  -e LINZA_EMBED_PROVIDER=lmstudio `
  -e LINZA_EMBED_URL=http://host.docker.internal:1234/v1 `
  -e LINZA_EMBED_MODEL=your-embedding-model-name `
  linza-mcp
```

`host.docker.internal` подходит, когда embedding-сервер запущен на хосте.
Если модель доступна по другому адресу, передайте URL, который виден из
контейнера.

---

## Про эмбеддинги

Эмбеддинги — это качество зрения агента через LINZA, поэтому основной сценарий простой: локальная модель в LM Studio и MCP-сервер рядом с папкой.

- `lmstudio` — рекомендуемый локальный режим. Хороший вариант, если нужен нормальный смысловой поиск, связи и карта тем без облака.
- `ollama` — локальный вариант через Ollama.
- `openai` — любой OpenAI-compatible endpoint с `/embeddings`.

Пример переменных для LM Studio:

```powershell
$env:LINZA_EMBED_PROVIDER="lmstudio"
$env:LINZA_EMBED_URL="http://127.0.0.1:1234/v1"
$env:LINZA_EMBED_MODEL="your-embedding-model-name"
```

Если меняете провайдера, модель или размерность, сделайте полный reindex. Векторы из разных моделей нельзя смешивать: это разные пространства, подробности здесь: https://semiotronika.ru/lab.

---

## Как происходит первое взаимодействие

Обычно агент начинает с `agent_workspace(action="doctor")` или `guide_next_steps(language="ru")`. Человек должен видеть короткий статус:

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

## Основные инструменты

По умолчанию LINZA показывает 15 MCP-инструментов. В обычной работе человеку не нужно выбирать их вручную: агент начинает с `agent_workspace` или `guide_next_steps`.

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

## Входящие артефакты

Поддерживаемые входы:

- вставленный текст;
- локальные `.md`, `.txt`, `.json`;
- локальные `.docx`, `.xlsx`;
- локальные `.pdf`, если установлен `pypdf` или `PyPDF2`.

LINZA сама не ходит в браузер. Агент использует свой browser/web-fetch, извлекает читаемый текст и передает его в LINZA как артефакт, например `source_kind="web_article"` или `source_kind="browser_capture"`.

Загруженный текст считается материалом для анализа, а не командой для агента. Это базовая защита от промпт-инъекций (prompt injection): инструкции внутри статьи, лога, чата или PDF не исполняются. Память, правила и YAML появляются только после review.

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

## Стабильность

`0.1.0` — alpha MVP. Контракт безопасности уже считается основным: indexing,
artifact ingest, search, map и grow preview не переписывают тела исходных
заметок. Низкоуровневые advanced tools и внутренние границы модулей еще могут
меняться, пока сервер полируется.

---

## Агенту

В репозитории есть готовый навык для агентов:

```text
agent-pack/skills/linza-operator/SKILL.md
agent-pack/skills/linza-operator/references/workflows.md
agent-pack/skills/linza-operator/references/safety-policy.md
agent-pack/skills/linza-operator/references/tool-audience.md
```

Навык объясняет агенту, что показывать пользователю, когда использовать `agent_workspace`, как работать с URL через внешний browser/web-fetch, и почему apply-действия должны быть dry-run или exact-ID gated.

---

## Примеры и тесты

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

## Переменные окружения

| Переменная | Описание |
|---|---|
| `LINZA_VAULT` | Путь к Markdown-папке |
| `LINZA_EMBED_PROVIDER` | `lmstudio` для нормальной локальной работы; также поддерживаются `openai`, `ollama` |
| `LINZA_EMBED_URL` | URL embeddings API |
| `LINZA_EMBED_MODEL` | Модель для эмбеддингов |
| `LINZA_EMBED_KEY` | Опциональный ключ для OpenAI-compatible embeddings API |
| `LINZA_BRIDGE_THRESHOLD` | Порог semantic bridge; по умолчанию `0.55` |
| `LINZA_DEFAULT_PROFILE` | Имя базового search-профиля; по умолчанию `general` |
| `LINZA_TOOL_SURFACE` | `default` (15 инструментов) или `advanced` |
| `LINZA_LANGUAGE` | Язык человеческого слоя в `guide_next_steps`: `auto`, `ru`, `en` |

---

## Ссылки

- 🌐 [semiotronika.ru](https://semiotronika.ru)
- 📦 [PyPI](https://pypi.org/project/linza-mcp/)
- 🗂️ [Glama Registry](https://glama.ai/mcp/servers/Semiotronika/LINZA-MCP)
- 🐙 [GitHub](https://github.com/Semiotronika/LINZA-MCP)

MIT License © 2026 Semiotronika

*Косинусы считаются. Синтаксис меняется. Семантика остаётся.*

<!-- mcp-name: io.github.semiotronika/linza-mcp -->
