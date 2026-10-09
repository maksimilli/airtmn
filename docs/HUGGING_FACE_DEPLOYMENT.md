# Hugging Face Spaces + PostgreSQL

Актуальная инструкция: [Hugging Face Spaces + Neon](POSTGRESQL_DEPLOYMENT.md).

В `deploy/huggingface` находятся два файла для загрузки в Space: Dockerfile и README.
Приложение работает на бесплатном CPU Basic, а каталог, аккаунты и PDF сохраняются
в отдельной PostgreSQL-базе Neon. До запуска добавьте секреты `DATABASE_URL`,
`CATALOG_ADMIN_PASSWORD` и переменную `CATALOG_PUBLIC_ORIGIN` из инструкции.

Прежний пакет на коммите `6d806ef` сохранял SQLite и PDF на временном диске Space.
Установка нового пакета и адреса PostgreSQL открывает новый каталог; существующая
SQLite автоматически не переносится. Для текущего пустого каталога перенос не нужен.
