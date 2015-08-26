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

from mock import call, Mock
import pytest

from yoyo.connections import parse_uri, BadConnectionURI


class TestParseURI:

    def test_it_parses_all_fields(self):
        parsed = parse_uri('protocol://scott:tiger@server:666/db?k=1')
        assert tuple(parsed) == ('protocol', 'scott', 'tiger', 'server', 666,
                                 'db', {'k': '1'})

    def test_it_parses_escaped_username(self):
        parsed = parse_uri('protocol://scott%40example.org:tiger@localhost/db')
        assert parsed.username == 'scott@example.org'

    def test_it_requires_scheme(self):
        with pytest.raises(BadConnectionURI):
            parse_uri('//scott:tiger@localhost/db')

    def test_it_roundtrips(self):
        cases = ['proto://scott%40example.org:tiger@localhost/db',
                 'proto://localhost/db?a=1+2',
                 'proto://localhost/db?a=a%3D1',
                 ]
        for case in cases:
            parsed = parse_uri(case)
            assert parsed.uri == case


def test_connections():

    from yoyo import connections
    u = parse_uri('odbc://scott:tiger@db.example.org:42/northwind?foo=bar')
    cases = [
        (connections.connect_odbc,
         call('UID=scott;PWD=tiger;ServerName=db.example.org;'
              'Port=42;Database=northwind;foo=bar')),
        (connections.connect_mysql, call(user='scott', passwd='tiger',
                                         host='db.example.org', port=42,
                                         db='northwind', foo='bar')),
        (connections.connect_sqlite, call('northwind')),
        (connections.connect_postgres,
         call('user=scott password=tiger port=42 '
              'host=db.example.org dbname=northwind')),

    ]

    for cls, connect_args in cases:
        driver = Mock()
        cls(driver, *u[1:])
        assert driver.connect.call_args == connect_args
