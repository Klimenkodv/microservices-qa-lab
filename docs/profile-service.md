# День 6: Profile Service, gRPC и Protobuf

## Назначение и границы данных

Auth владеет email, хешем пароля и учётной записью. Profile Service владеет именем, фамилией, датой рождения, городом, страной и описанием. Он не читает `auth.db`, не хранит пароли и не отправляет письма.

1. Auth сохраняет пользователя и outbox одной транзакцией, возвращает `201` и JWT.
2. Publisher отправляет `user.registered.v1` в Kafka.
3. Новая группа `profile-service-group` независимо от Notification и Statistics создаёт пустой профиль.
4. React запрашивает `GET /api/v1/profile` у Auth. Auth проверяет JWT, определяет user_id и вызывает gRPC `GetProfile`.
5. Сохранение формы вызывает `PATCH /api/v1/profile`, затем gRPC `UpdateProfile`.

Это eventual consistency: `201` от регистрации не гарантирует немедленное наличие профиля. UI опрашивает отсутствующий профиль до 10 раз с интервалом 2 секунды, затем остаётся доступна ручная кнопка обновления. Недоступность Profile не удаляет сессию или Auth-запись.

## Запуск и адреса

Нужен Docker Desktop с Compose v2. Сервис включён в общий `compose.yaml`, отдельная установка Python/Node/gRPC для запуска не нужна.

```bash
# Первый запуск: только если .env ещё нет
cp .env.example .env
docker compose up --build -d
docker compose ps
curl -fsS http://localhost:8003/health
curl -fsS http://localhost:8003/ready
```

В PowerShell для копирования: `Copy-Item .env.example .env`. Не перезаписывайте настроенный `.env` при обновлении. Достаточно `docker compose up --build -d`. `DEMO_MODE=true` включает reflection и управляющие demo endpoints, `JWT_SECRET` должен совпадать у Auth и Profile. `PROFILE_GRPC_TIMEOUT=2` задаёт deadline вызова из Auth в секундах.

| Компонент | С хоста | Внутри Compose |
|---|---|---|
| Profile gRPC | `localhost:50051`, TLS выключен | `profile-service:50051` |
| Profile Operations Swagger | http://localhost:8003/docs | `profile-service:8003` |
| Profile DB, read-only | http://localhost:8087 | файл `/data/profile.db` |
| Auth REST Swagger | http://localhost:8000/docs | `auth-service:8000` |
| Frontend | http://localhost:5173 | `frontend:80` |
| Kafka UI | http://localhost:8080 | `kafka-ui:8080` |
| Grafana | http://localhost:3000, `admin` / `admin` | `grafana:3000` |

`50051` не HTTP/Swagger URL: нужен gRPC-клиент. Swagger на `8003` описывает только эксплуатационные HTTP endpoints. Бизнес-контракт находится в [profile.proto](../shared/proto/profile.proto).

## gRPC-контракт

Полное имя сервиса: `qa.profile.v1.ProfileService`. Оба метода unary.

| Метод | Запрос | Результат |
|---|---|---|
| `GetProfile` | `GetProfileRequest { user_id }` | `Profile` |
| `UpdateProfile` | `UpdateProfileRequest { user_id, optional fields }` | обновлённый `Profile` |

`CreateProfile` намеренно не опубликован: создание выполняется только по событию регистрации. Это предотвращает произвольное создание профилей через форму/gRPC.

У каждого RPC передаются metadata:

```text
authorization: Bearer <access_token из ответа регистрации>
x-trace-id: lesson6-profile-001
```

JWT проверяется и в Auth, и в Profile. `sub` должен совпадать с `user_id` запроса. Получить или изменить чужой профиль нельзя. При вызове через REST клиент не задаёт user_id: Auth берёт его из проверенной учётной записи.

Пример GetProfile в Postman:

```json
{"user_id":"<user_id из ответа регистрации>"}
```

Пример UpdateProfile:

```json
{
  "user_id": "<тот же user_id>",
  "first_name": "Вадим",
  "last_name": "Звягинцев",
  "birth_date": "1990-05-21",
  "city": "Москва",
  "country": "Россия",
  "description": "Изучаю тестирование микросервисов"
}
```

Не переданное optional-поле остаётся прежним. Явная пустая строка очищает значение, включая дату рождения. Не передавайте `null`: используйте `""` для очистки, а для сохранения значения исключите поле. Пустой набор изменений запрещён. `created_at`, `updated_at` и `user_id` не редактируются. Имя/фамилия/город/страна: до 100 символов, описание: до 2000. Дата: существующая дата `YYYY-MM-DD`, не позже текущей даты сервера. У optional-полей присутствие отличается от значения по умолчанию. Номера полей в `.proto` нельзя переиспользовать для других значений.

## Postman: пошагово

1. Зарегистрируйте нового пользователя в UI или Auth Swagger (`POST /api/v1/register`). Сохраните `user_id` и `access_token` из ответа API. Не публикуйте JWT в скриншотах/логах.
2. В Postman создайте новый **gRPC request**. Укажите `localhost:50051`, без `http://`, отключите TLS для локального стенда.
3. Загрузите методы через server reflection. Альтернатива: импортируйте `shared/proto/profile.proto` через Service definition.
4. Выберите `qa.profile.v1.ProfileService / GetProfile`.
5. Добавьте metadata `authorization` и `x-trace-id`, тело с user_id. Выполните Invoke.
6. После доставки Kafka-события ожидайте `OK` и пустые личные поля. До появления профиля возможен `NOT_FOUND`.
7. Выберите UpdateProfile, измените поля, затем повторите GetProfile и проверьте БД на `8087`.

Для REST используйте Auth Swagger: откройте метод, нажмите Try it out и в поле `authorization` укажите `Bearer <JWT>`. Методы: `GET /api/v1/profile`, `PATCH /api/v1/profile` с JSON личных полей **без user_id**.

## Коды ошибок

| gRPC status | Причина | REST-ответ Auth |
|---|---|---|
| `OK` | профиль получен/изменён | 200 |
| `INVALID_ARGUMENT` | некорректный UUID, дата, длина поля или пустое обновление | 400 `INVALID_PROFILE` |
| `NOT_FOUND` | профиль ещё не создан в БД | 404 `PROFILE_NOT_READY` |
| `UNAUTHENTICATED` | нет JWT, неверная подпись или истёк срок | 401 `UNAUTHORIZED` |
| `PERMISSION_DENIED` | JWT другого пользователя | 403 `FORBIDDEN` |
| `UNAVAILABLE` | gRPC-сервис недоступен | 503 `PROFILE_UNAVAILABLE` |
| `DEADLINE_EXCEEDED` | истёк deadline клиента | 504 `PROFILE_TIMEOUT` |
| `INTERNAL` | ошибка хранения/обработки | 502 `PROFILE_ERROR` |

Ошибки структуры HTTP JSON перехватывает Pydantic/Auth до gRPC, возвращая HTTP 400 с `detail`. Ошибку неизвестного UUID при чужом JWT ожидайте как `PERMISSION_DENIED`, а не `NOT_FOUND`: проверка владения предшествует чтению БД. Для воспроизведения `NOT_FOUND` используйте собственного нового пользователя при остановленной обработке Kafka.

## База данных

`data/profile.db` создаётся автоматически, SQLite WAL. Изменения в таблицах разрешены только сервису; UI read-only.

| profiles | Тип / назначение |
|---|---|
| user_id | TEXT PRIMARY KEY, идентификатор из Auth/Kafka |
| first_name, last_name | TEXT NOT NULL DEFAULT '' |
| birth_date | TEXT NOT NULL DEFAULT '', дата без часового пояса |
| city, country, description | TEXT NOT NULL DEFAULT '' |
| created_at | TEXT NOT NULL, время регистрации из события |
| updated_at | TEXT NOT NULL, время последнего обновления |

`processed_events`: `event_id TEXT PRIMARY KEY`, `user_id TEXT NOT NULL`, `consumer_name TEXT NOT NULL`, `processed_at TEXT NOT NULL`.

Профиль и отметка обработанного события создаются в одной локальной транзакции. Повторный event_id пропускается. Новое событие для существующего user_id также не стирает отредактированные поля. Между Auth и Profile нет общей SQL-транзакции или межбазового внешнего ключа.

Старые пользователи: новая группа читает доступную историю Kafka с earliest, если у неё нет сохранённого offset. Если broker был пересоздан и история утрачена, старые Auth-записи сами по себе не создадут профили. Используйте новую регистрацию, не удаляя БД. В учебном варианте нет автоматического backfill из Auth.

## Практика: задержка появления профиля

```bash
curl -X POST http://localhost:8003/internal/demo/pause-consumer
# Зарегистрируйте НОВОГО пользователя.
# /api/v1/me работает, /api/v1/profile возвращает 404 PROFILE_NOT_READY.
# Прямой GetProfile с его JWT: NOT_FOUND. Группа Profile отстаёт.
curl -X POST http://localhost:8003/internal/demo/resume-consumer
# Дождитесь появления profiles / processed_events и успешного GetProfile.
```

Выполняйте сценарий без параллельных регистраций и всегда возвращайте consumer в resume. Пауза обработчика не равна остановке процесса. Notification и Statistics продолжают работать независимо.

## Практика: отказ и deadline

```bash
docker compose stop profile-service
# Учётная запись /api/v1/me доступна; профиль через Auth: 503 или 504.
# Прямой gRPC вызов: UNAVAILABLE (или клиентский timeout при сетевых условиях).
docker compose start profile-service

curl -X POST http://localhost:8003/internal/demo/grpc-delay \
  -H 'Content-Type: application/json' -d '{"delay_ms":3000}'
# При PROFILE_GRPC_TIMEOUT=2 чтение через Auth: 504 PROFILE_TIMEOUT.
# В Postman задайте deadline/request timeout меньше задержки.
curl -X POST http://localhost:8003/internal/demo/grpc-delay \
  -H 'Content-Type: application/json' -d '{"delay_ms":0}'
```

Задержка действует на GetProfile/UpdateProfile после авторизации и валидации, до операции с БД. При отмене во время искусственного sleep запись не начинается. В общем случае timeout обновления не доказывает отсутствие эффекта: операция уже могла записать данные, поэтому перепроверьте GetProfile. Повтор Get безопасен для данных; автоматические повторы обновлений в Auth не включены.

При остановке контейнера конкретный результат зависит от транспорта и состояния канала: быстро обнаруженный отказ даст UNAVAILABLE/503, а истечение deadline при подключении или ожидании даст DEADLINE_EXCEEDED/504. Оба результата означают недоступность операции профиля, но описывают разные наблюдения клиента.

## Наблюдаемость и восстановление

```bash
docker compose logs --tail=100 profile-service auth-service
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:29092 --describe --group profile-service-group
```

Loki: `{service="profile-service"} | json | trace_id="lesson6-profile-001"`. На сервере есть записи `gRPC GetProfile OK`, `gRPC UpdateProfile INVALID_ARGUMENT`, `Profile event processed` и `Duplicate profile event skipped`. Auth передаёт trace_id в gRPC metadata. Для ошибок consumer ищите также event_id. Ни JWT, ни полные поля профиля не пишутся в логи.

PromQL: `sum by (method,status) (rate(grpc_server_requests_total[5m]))`. Клиент при deadline видит `DEADLINE_EXCEEDED`, сервер при отмене может зафиксировать `CANCELLED`: это разные точки наблюдения.

Dashboard `Registration flow` включает Profile в `Flow by trace_id`, а также панели `Profile gRPC results` и `Profile logs by event_id`.

Profile использует существующий consumer retry/DLQ механизм: три попытки handler, затем `user.registered.dlq.v1`, затем commit. Ошибки JSON/схемы до handler имеют те же ограничения, что разобраны на дне 5. В общей DLQ поле payload содержит исходный event, а reason/source_topic описывают сбой; имя исходной consumer group не добавлено. Нулевой lag не доказывает существование профиля.

Для восстановления: `docker compose start profile-service`, resume-consumer, delay_ms=0, затем контрольная регистрация и проверка БД. Обновления не требуют `down -v`. Остановка с сохранением БД: `docker compose stop`.

## Разработка и тесты

Генерируемые `profile_pb2.py` и `profile_pb2_grpc.py` сохранены в Git. Для обычного Docker-запуска protoc не нужен. После изменения `.proto` пересоздайте их из корня:

```bash
python -m pip install -r services/profile-service/requirements.txt
python -m grpc_tools.protoc -I . --python_out=. --grpc_python_out=. shared/proto/profile.proto
make test-backend
make test-frontend
```

Прямые gRPC tests запускаются настоящим сервером на свободном локальном порту. Integration tests требуют запущенный стенд: установите `tests/requirements.txt`, затем `RUN_INTEGRATION=1 python -m pytest tests/integration/test_profile_flow.py` (PowerShell: `$env:RUN_INTEGRATION="1"`).

## Безопасность учебного стенда

Прямые бизнес-RPC требуют JWT и доступа только к своему user_id. Health/reflection открыты для локальной диагностики, demo controls доступны только при DEMO_MODE=true. gRPC PLAINTEXT и общий HS256 secret предназначены для локального занятия, не production. Для production нужны TLS, управление секретами и разграничение межсервисного доступа. Kafka-производители в локальном стенде не защищены ACL: ручная публикация обходит Auth и допускается только как учебная практика.

## Официальные материалы

- https://grpc.io/docs/languages/python/basics/
- https://grpc.io/docs/guides/status-codes/
- https://grpc.io/docs/guides/deadlines/
- https://grpc.io/docs/guides/reflection/
- https://protobuf.dev/programming-guides/field_presence/
