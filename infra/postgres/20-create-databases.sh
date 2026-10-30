#!/bin/sh
# One PostgreSQL server, one database and one role per service.
# Services cannot read each other's databases.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v catalog_password="$CATALOG_DB_PASSWORD" \
    -v booking_password="$BOOKING_DB_PASSWORD" <<'SQL'
CREATE ROLE catalog LOGIN PASSWORD :'catalog_password';
CREATE DATABASE catalog OWNER catalog;
REVOKE ALL ON DATABASE catalog FROM PUBLIC;

CREATE ROLE booking LOGIN PASSWORD :'booking_password';
CREATE DATABASE booking OWNER booking;
REVOKE ALL ON DATABASE booking FROM PUBLIC;
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname booking <<'SQL'
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL
