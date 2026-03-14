# План реализации Task 1: Call an LLM from Code

## LLM Provider

**Provider:** OpenRouter  
**Model:** `nvidia/nemotron-3-nano-30b-a3b:free`  
**API Base:** `https://openrouter.ai/api/v1`

### Почему OpenRouter?

- Бесплатный доступ без кредитной карты
- Поддержка OpenAI-compatible API
- Несколько бесплатных моделей на выбор

### Ограничения

- 50 запросов в день на бесплатном тарифе
- Возможны 429 ошибки при высокой нагрузке
- Некоторые модели могут быть временно недоступны — используем альтернативы

## Архитектура агента

### Входные данные

- Вопрос пользователя через аргумент командной строки: `uv run agent.py "Вопрос"`

### Выходные данные

- JSON на stdout: `{"answer": "...", "tool_calls": []}`
- Все логи/отладочная информация — на stderr

### Компоненты

1. **CLI Parser** — разбор аргументов командной строки (argparse)
2. **LLM Client** — HTTP запрос к OpenRouter API через httpx
3. **Response Parser** — извлечение ответа из JSON ответа API
4. **Output Formatter** — форматирование результата в требуемый JSON

### Поток данных

```
User question (CLI arg)
    → Parse arguments
    → Build prompt
    → HTTP POST to LLM API
    → Parse response
    → Format JSON output
    → stdout
```

### Обработка ошибок

- Timeout 60 секунд на ответ LLM
- HTTP ошибки — логирование на stderr, exit code != 0
- Пустой ответ — ошибка на stderr

### Зависимости

- `httpx` — HTTP клиент (уже есть в pyproject.toml)
- `pydantic-settings` — загрузка конфига из .env (уже есть)
- `sys` — для stdout/stderr

## Структура файлов

```
agent.py              # Основной CLI скрипт
.env.agent.secret     # Конфигурация (LLM_API_KEY, LLM_API_BASE, LLM_MODEL)
AGENT.md              # Документация
tests/test_agent.py   # Регрессионный тест
```

## План работ

1. [x] Создать этот план
2. [x] Создать `.env.agent.secret` с credentials
3. [x] Реализовать `agent.py`
4. [x] Создать `AGENT.md`
5. [x] Написать регрессионный тест
6. [ ] Протестировать вручную
7. [ ] Git workflow: issue, branch, PR
