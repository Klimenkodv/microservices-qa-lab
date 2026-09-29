# Инструкция по запуску Microservices QA Lab

## 1. Требования

- Docker Desktop с Compose v2 (проверка: `docker compose version`)
- 6 ГБ свободной оперативной памяти
- Свободные порты: 3000, 5173, 8000, 8001, 8002, 8025, 8080, 8085, 8086, 9090
- Для автотестов интеграции (опционально): Python 3

## 2. Запуск

1. Откройте терминал в папке проекта:

```bash
cd /Users/vadim/Documents/Codex/2026-09-29/files-mentioned-by-the-user-v1/outputs/microservices-qa-lab
```

2. Убедитесь, что Docker Desktop запущен (иконка кита в строке меню, статус «Running»).

3. Создайте файл окружения:

```bash
cp .env.example .env
```

4. Соберите и запустите все сервисы:

```bash
docker compose up --build
```

(или `make up`). Первый запуск скачивает образы и собирает сервисы — это может занять несколько минут. Терминал будет занят логами; для запуска в фоне добавьте `-d`.

## 3. Проверка готовности

В другом терминале:

```bash
docker compose ps
curl -fsS http://localhost:8000/ready
curl -fsS http://localhost:8001/ready
curl -fsS http://localhost:8002/ready
```

Все контейнеры должны быть в состоянии `running`/`healthy`, а `/ready` — отвечать успешно.

## 4. Адреса

| Компонент | Адрес | Назначение |
|---|---|---|
| Frontend | http://localhost:5173 | Регистрация и профиль |
| Auth Swagger | http://localhost:8000/docs | REST API |
| Notification Swagger | http://localhost:8001/docs | Consumer, fault injection |
| Statistics Swagger | http://localhost:8002/docs | Consumer, fault injection |
| Kafka UI | http://localhost:8080 | Топики, события, lag |
| Mailpit | http://localhost:8025 | Перехваченные письма |
| Grafana | http://localhost:3000 | `admin` / `admin`, dashboard `Registration flow` |
| Prometheus | http://localhost:9090 | Метрики |
| auth.db | http://localhost:8085 | SQLite UI |
| statistics.db | http://localhost:8086 | SQLite UI |

## 5. Быстрая проверка, что всё работает

Откройте http://localhost:5173/register и зарегистрируйтесь (например, `student@example.com` / `Password123`). После `201 Created` откроется `/profile`. Затем проверьте:

- Mailpit (http://localhost:8025) — пришло письмо;
- Kafka UI (http://localhost:8080) — событие в топике `user.registered.v1`, lag = 0;
- statistics.db (http://localhost:8086) — запись в `registration_events`.

То же через API:

```bash
curl -i http://localhost:8000/api/v1/register \
  -H 'Content-Type: application/json' \
  -H 'X-Trace-ID: lesson-success-001' \
  -d '{"email":"student2@example.com","password":"Password123"}'
```

## 6. Остановка и очистка

Остановить, сохранив данные:

```bash
docker compose down
```

Полная очистка (контейнеры, volumes, файлы `data/*.db`):

```bash
make clean
```

## 7. Тесты (опционально)

```bash
make test-backend
make test-frontend

# при запущенном стенде
python3 -m pip install -r tests/requirements.txt
make test-integration
```

## 8. Частые проблемы

| Симптом | Решение |
|---|---|
| `Cannot connect to the Docker daemon` | Запустите Docker Desktop и дождитесь готовности |
| `port is already allocated` | Освободите порт (`lsof -i :8000`) или остановите конфликтующий процесс |
| Сервисы падают / перезапускаются | Выделите Docker Desktop ≥ 6 ГБ (Settings → Resources) |
| Frontend не достучался до API | Проверьте `docker compose ps` и `curl http://localhost:8000/ready` |
| Нужно начать с чистого состояния | `make clean`, затем `docker compose up --build` |
| Логи конкретного сервиса | `docker compose logs -f auth-service` |

Сценарии с ошибками, fault injection, DLQ и поиском причин сбоев описаны в [README.md](README.md).
