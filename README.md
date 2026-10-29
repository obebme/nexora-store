# NEXORA — городской streetwear-магазин

[English](README.en.md) | Русский

Портфолио-проект интернет-магазина одежды, кроссовок и аксессуаров. Frontend: React + TypeScript + Vite. Backend: FastAPI + PostgreSQL + SQLAlchemy 2 + Alembic.

## Запуск в Docker

1. Создайте `.env`, если его ещё нет:

```powershell
Copy-Item .env.example .env
```

Укажите в `.env` секретный `JWT_SECRET` и свои SMTP/OAuth параметры. Сгенерировать случайный секрет можно командой `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Приложение откажется запускаться с отсутствующим, коротким или шаблонным JWT-секретом. Для локального запуска замените `POSTGRES_PASSWORD` на свой пароль (используйте буквы, цифры и дефис). `.env` передаётся только запущенному backend и исключён из Docker-образов.

Для оплаты через ЮKassa заполните `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY` из кабинета продавца. Используйте тестовые учётные данные, пока проверяете интеграцию. Backend создаёт платёж на сервере по сохранённой сумме заказа, использует ключи идемпотентности для платежа и полного возврата, а входящие уведомления сверяет через API ЮKassa. В настройках уведомлений магазина укажите публичный HTTPS URL `/api/payments/yookassa/webhook` и включите `payment.succeeded`, `payment.canceled`, `refund.succeeded` и `refund.canceled`. Для локальной проверки webhook нужен HTTPS-туннель; не публикуйте backend или секретный ключ напрямую. Добавьте URL возврата (`YOOKASSA_RETURN_URL`) в разрешённые адреса кабинета ЮKassa, если это требуется настройками магазина.

Приём заказов защищён feature flag `SALES_ENABLED=false` и по умолчанию выключен. Backend не создаёт заказ и не инициирует оплату, пока флаг явно не включён после проверки доставки. Frontend также блокирует checkout.

Интеграция не передаёт фискальный чек в запросе платежа. Владелец сообщил, что автоматические чеки включены по договору ЮKassa, но это необходимо проверить в тестовом и боевом кабинетах до продаж и подтвердить соответствие налоговому режиму.

2. Соберите и запустите приложение:

```powershell
docker compose up --build -d
```

Откройте магазин по адресу [http://localhost:8080](http://localhost:8080). Compose публикует HTTP только на loopback-интерфейсе этого компьютера; не снимайте это ограничение без настройки HTTPS для внешнего доступа. Миграции базы данных применяются при запуске backend. Для наполнения каталога и создания администратора выполните:

```powershell
docker compose exec backend python -m nexora_backend.seed
docker compose exec backend python -m nexora_backend.create_admin admin@example.com
```

Для входа через Google добавьте `http://localhost:8080/oauth/callback` в список разрешённых redirect URI OAuth-клиента Google. Ссылки подтверждения почты также ведут на `http://localhost:8080`.

Полезные команды:

```powershell
docker compose logs -f
docker compose stop
docker compose down
```

База данных и загруженные фотографии сохраняются в Docker volumes при остановке и пересоздании контейнеров. `docker compose down -v` удалит эти данные. Указанные настройки предназначены для разработки: перед production укажите домен в URL-переменных `.env`, задайте надёжные секреты, настройте HTTPS и резервное копирование.

## Локальный запуск

1. В корне проекта настройте `.env` на основе `.env.example`. Для локального Vite на `http://localhost:5173` укажите этот origin в `FRONTEND_ORIGINS` и выставьте `EMAIL_VERIFICATION_BASE_URL` и OAuth redirect URI на `http://localhost:5173`. Для production установите `ENVIRONMENT=production`, используйте HTTPS для всех публичных URL и задайте уникальный `JWT_SECRET` длиной от 32 символов.
2. Примените миграции и наполните каталог:

```powershell
uv run --package nexora-backend alembic upgrade head
uv run --package nexora-backend python -m nexora_backend.seed
uv run --package nexora-backend uvicorn nexora_backend.main:app --reload --app-dir backend/src
```

3. Во втором терминале запустите интерфейс:

```powershell
cd frontend
npm install
npm run dev
```

Если `npm` не установлен, сначала установите Node.js LTS с npm; `uv` управляет только Python-зависимостями.

## Проверки frontend

Сборка также выполняет проверку TypeScript. Браузерные end-to-end сценарии можно запустить так:

```powershell
cd frontend
npx playwright install chromium
npm run typecheck:e2e
npm run test:e2e
```

E2E проверки поднимают локальный Vite и используют изолированные ответы API; они не подключаются к реальным платежам или доставке.

## Первичный администратор

После применения миграций создайте или назначьте администратора (команда попросит ввести пароль и не выводит его):

```powershell
uv run --package nexora-backend python -m nexora_backend.create_admin admin@example.com
```

## Подготовка к production

Перед публичным запуском:

1. Выберите домен, хостинг и почтового провайдера; в `.env` задайте публичные HTTPS URL, PostgreSQL и секреты. Production-конфигурация отклоняет HTTP URL, SQLite и неполные SMTP-настройки.
2. Примените миграции, создайте отдельного администратора и ограничьте доступ к `/admin` на уровне инфраструктуры, если панель не должна быть публичной.
3. Непрерывный Docker worker каждые 30 секунд проверяет неоплаченные заказы. По умолчанию резерв товара истекает через 30 минут (`ORDER_RESERVATION_MINUTES`, допустимо 5–120); связанный ожидающий платёж сначала проверяется и отменяется через ЮKassa. Если статус провайдера неизвестен, товар не возвращается в продажу. На production должно работать ровно одно основное расписание worker; проверьте его логи и алерты.
4. Полный возврат можно запустить из админ-панели для оплаченного заказа. Статус подтверждается webhook/API ЮKassa; возврат товара на склад остаётся отдельной ручной операцией после фактического получения и проверки вещи.
5. Интеграция СДЭК для тарифа, выбора ПВЗ/курьера, этикеток и отслеживания ещё не подключена. Выбраны оба способа доставки, отправление из Москвы и только Россия. Нужны договор/аккаунт СДЭК и тестовые API-реквизиты, точный адрес и контакты отправителя, размеры/вес упаковок, проверенные тарифы и полный тест создания/отмены отправления. Реализация должна сверяться с [официальной документацией СДЭК](https://apidoc.cdek.ru/). До готовности интеграции не устанавливайте `SALES_ENABLED=true`.
6. Проверьте, что договор ЮKassa реально отправляет фискальные чеки автоматически в тестовом и боевом режимах. Согласуйте с бухгалтером налоговый режим, правила продажи/доставки/возврата и тексты согласий/политики персональных данных; юридические документы нельзя корректно заполнить без реквизитов продавца.
7. Перед внешним доступом настройте TLS reverse proxy, обновления зависимостей, мониторинг ошибок, уведомления о сбоях worker, резервные копии БД и каталога загрузок. `scripts/backup.ps1` делает архив PostgreSQL в `backups/`; фотографии хранятся отдельно в Docker volume и должны копироваться/сниматься снапшотом независимо. Периодически проверяйте восстановление на отдельной БД.
8. Соберите frontend командой `npm run build` из `frontend`. Раздавайте `frontend/dist` по HTTPS, направьте `/api`, `/health` и `/uploads` на backend и настройте SPA fallback для `/products/{slug}`. Проверьте сценарии на ширине 360, 390, 768 и 1280 пикселей.

Не включайте реальные продажи, пока не пройдены сквозные тесты ЮKassa и СДЭК, проверены чеки, юридические документы, восстановление из резервной копии и production-HTTPS. Домена, хостинга и тестовых аккаунтов интеграций в рабочем окружении пока нет; реальные платежи/доставка здесь не запускались.

Миграция `91d8a4c73e21` преобразует старый общий остаток в размерный: общее количество делится поровну между размерами, остаток распределяется по первым размерам. Суммарное количество сохраняется, но это оценочное распределение — проверьте его в админке по фактическому складу.

## API

- `GET /api/products`, `GET /api/categories` — каталог.
- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/resend-verification`, `GET /api/auth/verify-email`, `POST /api/auth/password-reset/request`, `POST /api/auth/password-reset/confirm`, `GET /api/auth/me` — регистрация с подтверждением email, сброс пароля и JWT после подтверждения.
- `GET /api/cart`, `PUT /api/cart`, `POST /api/cart/items`, `PATCH/DELETE /api/cart/items/{product_id}/{size}` — корзина пользователя; `PUT /api/cart` сверяет корзину с актуальными остатками и ценами.
- `POST /api/orders`, `GET /api/orders` — создание и просмотр заказов только с доставкой по России; заказ резервирует остаток на 30 минут.
- `POST /api/orders/{order_id}/payment` — создание/повтор платежа ЮKassa при настроенных реквизитах.
- `POST /api/payments/yookassa/webhook` — сверка платежных и возвратных уведомлений через API ЮKassa.
- `POST /api/admin/orders/{order_id}/refund` — запуск полного возврата через ЮKassa для оплаченного заказа.
- `/api/admin/*` — операции для пользователя с ролью `admin`. Остатки учитываются отдельно для каждого размера; у товара поддерживается галерея до 10 изображений. В панели можно указать ссылки или загрузить JPEG, PNG, GIF либо WebP размером до 5 МБ; файлы хранятся в `backend/uploads`, для production нужен постоянный том.
- `GET /api/admin/orders` принимает фильтры `status`, `q`, `date_from` и `date_to` и возвращает данные доставки для обработки администратором.
- `GET /api/admin/products` возвращает полный каталог администратору, включая скрытые товары; `PATCH /api/admin/products/{product_id}` обновляет данные товара.
- `/health`, `/health/db` — проверки доступности.

## Проверки

```powershell
uv run --package nexora-backend --group dev pytest
uv run --package nexora-backend --group dev ruff check backend/src backend/tests
uv run --package nexora-backend --group dev ruff format --check backend/src backend/tests
```

Фото в каталоге — примеры с Unsplash; см. лицензию и ссылки в `backend/src/nexora_backend/seed.py`. Перед коммерческим запуском проверьте права на каждое изображение, настройте реальные фото и подключите платежного провайдера, доставку, уведомления и production-секреты.

## Вход через Google

Обычная регистрация и вход по email и паролю продолжают работать. Для входа через Google создайте OAuth 2.0 Client ID типа **Web application** в Google Cloud Console и добавьте точный адрес callback в список **Authorized redirect URIs**. Для локальной разработки укажите `http://localhost:5173/oauth/callback`. Затем заполните в корневом `.env`:

```dotenv
GOOGLE_OAUTH_CLIENT_ID=ваш-client-id
GOOGLE_OAUTH_CLIENT_SECRET=ваш-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:5173/oauth/callback
```

Этот же callback должен быть доступен frontend по адресу, который совпадает с `GOOGLE_OAUTH_REDIRECT_URI`. Не добавляйте реальные OAuth-секреты в git. После изменения `.env` перезапустите backend и примените миграции:

```powershell
uv run --package nexora-backend alembic upgrade head
```

При первом успешном входе Google с подтверждённым email создаётся аккаунт магазина; если такой email уже зарегистрирован, Google связывается с ним. Вход реализован через Authorization Code + PKCE, а backend проверяет подпись и claims ID token. Реальный вход требует настроенных credentials и зарегистрированного callback в Google Cloud Console.

## Подтверждение email и почтовый сервер

При регистрации по email и паролю пользователь получает приветственное письмо со ссылкой подтверждения, действующей 24 часа. До подтверждения вход и доступ к заказам закрыты. После перехода по ссылке открывается страница результата, а на подтверждённый адрес отправляется отдельное письмо-уведомление. Повторную ссылку можно запросить из окна аккаунта. Вход через Google использует его подтверждённый email и не требует отдельной ссылки.

Если пользователь забыл пароль, в форме входа нажимает **«Забыли пароль?»** и указывает email аккаунта. На подтверждённый адрес приходит одноразовая ссылка для создания нового пароля; она действует 1 час. Для аккаунта, созданного через Google, можно использовать кнопку Google или задать пароль через сброс по подтверждённому email. Столбцы токена сброса пароля добавлены миграцией `4d7a9b15e260`.

Для доставки писем настройте SMTP в корневом `.env` (учётные данные SMTP выдаёт ваш почтовый провайдер):

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=ваш-smtp-пользователь
SMTP_PASSWORD=ваш-smtp-пароль
SMTP_FROM_EMAIL=shop@example.com
SMTP_USE_SSL=false
SMTP_STARTTLS=true
EMAIL_VERIFICATION_BASE_URL=http://localhost:5173
```

Для SMTP-порта 465 обычно включают `SMTP_USE_SSL=true` и `SMTP_STARTTLS=false`; для порта 587 используют STARTTLS. В production задайте `EMAIL_VERIFICATION_BASE_URL` как публичный HTTPS-адрес магазина. Не коммитьте SMTP-пароль. После добавления переменных перезапустите backend и примените миграции:

```powershell
uv run --package nexora-backend alembic upgrade head
```

Приложение не ограничивает домены получателей: одна настроенная SMTP-учётная запись может отправлять письма на Gmail, Outlook/Hotmail, Yahoo, iCloud, Яндекс.Почту, Mail.ru, `list.ru`, `inbox.ru`, `bk.ru`, `vk.com`, Rambler и другие адреса. Настройки ниже относятся к **почте-отправителю**, а не к адресам покупателей. Получатель задаётся при регистрации и берётся из подтверждаемого email.

Примеры SMTP-серверов популярных почтовых сервисов для исходящей отправки:

| Сервис отправителя | `SMTP_HOST` | Порт | Настройки TLS |
|---|---|---:|---|
| Gmail / Google Workspace | `smtp.gmail.com` | 587 | `SMTP_USE_SSL=false`, `SMTP_STARTTLS=true` |
| Outlook.com / Microsoft 365 | `smtp-mail.outlook.com` | 587 | `SMTP_USE_SSL=false`, `SMTP_STARTTLS=true` |
| Yahoo Mail | `smtp.mail.yahoo.com` | 465 | `SMTP_USE_SSL=true`, `SMTP_STARTTLS=false` |
| Яндекс.Почта | `smtp.yandex.ru` | 465 | `SMTP_USE_SSL=true`, `SMTP_STARTTLS=false` |
| Mail.ru | `smtp.mail.ru` | 465 | `SMTP_USE_SSL=true`, `SMTP_STARTTLS=false` |

Требования к паролям приложений и доступу по SMTP зависят от сервиса. Для массовых и более надёжных транзакционных отправок предпочтителен специализированный email-провайдер или SMTP вашего домена. Чтобы письма не терялись и не попадали в спам, подтвердите домен отправителя и настройте выданные провайдером SPF, DKIM и DMARC DNS-записи. Доставка в конкретный почтовый ящик зависит также от правил и фильтров его провайдера и не может быть безусловно гарантирована приложением.
