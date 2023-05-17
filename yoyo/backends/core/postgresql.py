# Copyright 2015 Oliver Cope
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import warnings
from contextlib import contextmanager

from yoyo.backends.base import DatabaseBackend


class PostgresqlBackend(DatabaseBackend):
    """
    Backend for PostgreSQL and PostgreSQL compatible databases.

    This backend uses psycopg2. See
    :class:`yoyo.backends.core.postgresql.PostgresqlPsycopgBackend`
    if you need psycopg3.
    """

    driver_module = "psycopg2"
    schema = None
    list_tables_sql = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = :schema"
    )

    @property
    def TRANSACTION_STATUS_IDLE(self):
        from psycopg2.extensions import TRANSACTION_STATUS_IDLE

        return TRANSACTION_STATUS_IDLE

    def connect(self, dburi):
        kwargs = {"dbname": dburi.database, "autocommit": True}

        # Default to autocommit mode: without this psycopg sends a BEGIN before
        # every query, causing a warning when we then explicitly start a
        # transaction. This warning becomes an error in CockroachDB. See
        # https://todo.sr.ht/~olly/yoyo/71
        kwargs["autocommit"] = True

        kwargs.update(dburi.args)
        if dburi.username is not None:
            kwargs["user"] = dburi.username
        if dburi.password is not None:
            kwargs["password"] = dburi.password
        if dburi.port is not None:
            kwargs["port"] = dburi.port
        if dburi.hostname is not None:
            kwargs["host"] = dburi.hostname
        self.schema = kwargs.pop("schema", None)
        autocommit = bool(kwargs.pop("autocommit"))
        connection = self.driver.connect(**kwargs)
        connection.autocommit = autocommit
        return connection

    @contextmanager
    def disable_transactions(self):
        with super(PostgresqlBackend, self).disable_transactions():
            saved = self.connection.autocommit
            self.connection.autocommit = True
            yield
            self.connection.autocommit = saved

    def init_connection(self, connection):
        if self.schema:
            cursor = connection.cursor()
            cursor.execute("SET search_path TO {}".format(self.schema))

    def list_tables(self):
        current_schema = self.execute("SELECT current_schema").fetchone()[0]
        return super(PostgresqlBackend, self).list_tables(schema=current_schema)

    def commit(self):
        # The connection is in autocommit mode and ignores calls to
        # ``commit()`` and ``rollback()``, so we have to issue the SQL directly
        self.execute("COMMIT")
        super().commit()

    def rollback(self):
        self.execute("ROLLBACK")
        super().rollback()

    def begin(self):
        if self.connection.info.transaction_status != self.TRANSACTION_STATUS_IDLE:
            warnings.warn(
                "Nested transaction requested; "
                "this will raise an exception in some "
                "PostgreSQL-compatible databases"
            )
        return super().begin()


class PostgresqlPsycopgBackend(PostgresqlBackend):
    """
    Like PostgresqlBackend, but using the newer Psycopg 3.
    """

    driver_module = "psycopg"

    @property
    def TRANSACTION_STATUS_IDLE(self):
        from psycopg.pq import TransactionStatus

        return TransactionStatus.IDLE


class PostgresqlPG8000Backend(PostgresqlBackend):
    """
    Like PostgresqlBackend, but using the PG8000 driver.
    """

    driver_module = "pg8000"

    @property
    def TRANSACTION_STATUS_IDLE(self):
        from pg8000.core import IDLE

        return IDLE

    def connect(self, dburi):
        from pg8000.dbapi import Connection, connect

        kwargs = {"database": dburi.database, "autocommit": True}

        # Default to autocommit mode: without this psycopg sends a BEGIN before
        # every query, causing a warning when we then explicitly start a
        # transaction. This warning becomes an error in CockroachDB. See
        # https://todo.sr.ht/~olly/yoyo/71
        kwargs["autocommit"] = True

        kwargs.update(dburi.args)
        if dburi.username is not None:
            kwargs["user"] = dburi.username
        if dburi.password is not None:
            kwargs["password"] = dburi.password
        if dburi.port is not None:
            kwargs["port"] = dburi.port
        if dburi.hostname is not None:
            kwargs["host"] = dburi.hostname
        self.schema = kwargs.pop("schema", None)
        autocommit = bool(kwargs.pop("autocommit"))
        connection = self.driver.dbapi.connect(**kwargs)
        connection.autocommit = autocommit
        return connection

    def begin(self):
        if self.connection._transaction_status != self.TRANSACTION_STATUS_IDLE:
            warnings.warn(
                "Nested transaction requested; "
                "this will raise an exception in some "
                "PostgreSQL-compatible databases"
            )
        assert not self._in_transaction
        self._in_transaction = True
        self.execute("BEGIN")



class PostgresqlGoogleCloudSQLBackend(PostgresqlPG8000Backend):

    def connect(self, dburi):
        from google.cloud.sql.connector import Connector, IPTypes
        from pg8000.dbapi import Connection
        instance_connection_name = os.environ["INSTANCE_CONNECTION_NAME"]
        ip_type = IPTypes.PRIVATE if os.environ.get("PRIVATE_IP") else IPTypes.PUBLIC

        connector = Connector()

        kwargs = {"autocommit": True}

        kwargs.update(dburi.args)
        self.schema = kwargs.pop("schema", None)
        autocommit = bool(kwargs.pop("autocommit"))
        connection: Connection = connector.connect(
            instance_connection_name,
            "pg8000",
            user=dburi.username,
            password=dburi.password,
            db=dburi.database,
            ip_type=ip_type,
        )
        connection.autocommit = autocommit
        return connection
