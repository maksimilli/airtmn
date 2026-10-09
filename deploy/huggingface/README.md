---
title: Каталог электронных компонентов
emoji: 🔌
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

Каталог электронных компонентов с поиском и распознаванием PDF-даташитов.
Посетители просматривают каталог, администраторы добавляют и изменяют карточки.

Перед запуском в **Settings → Variables and secrets** добавьте:

- Secret `DATABASE_URL`: строка подключения PostgreSQL из Neon (с `sslmode=require`).
- Secret `CATALOG_ADMIN_PASSWORD`: пароль администратора, от 12 до 200 символов.
- Variable `CATALOG_PUBLIC_ORIGIN`: прямой HTTPS-адрес приложения без завершающего `/`.
  Для Space `Maximkrutoy/datasheet`: `https://maximkrutoy-datasheet.hf.space`.

Логин по умолчанию: `admin`. Не записывайте пароль в файлы Space.
Для входа открывайте прямой адрес приложения в отдельной вкладке: браузер может
блокировать cookie в рамке на странице huggingface.co.

Карточки, исходные PDF и аккаунты хранятся в PostgreSQL, независимо от временного
диска Space. Не удаляйте проект Neon; следите за лимитами бесплатного тарифа и
сохраняйте резервные копии. Space и база могут засыпать при отсутствии запросов.

Исходный проект: https://github.com/maksimilli/airtmn
