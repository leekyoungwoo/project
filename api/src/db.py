# coding=utf-8
import os
import sys

import psycopg2
import psycopg2.extras
import psycopg2.pool
import yaml
from flask_restful import abort

from config import CONFIG, GLOBAL_CONFIG
import re

_POOL = None
QUERY = {}


# Postgresql 에서 새로운 Connection을 만드는것은 비용이 많이드는 일이다.
# 그러므로 불특정 다수의 사용자들이 동시에 Database의 Connection을 요구한다면 최악의 경우 server가 down되기도 한다
# 어플리케이션 내의 오류가 확인되지 않은 상태에서 out of memory 가 발생 하거나, DB Server 쪽에 일시적으로 문제가 발생시에 웹서버가
# 뻗어 버리는 경우가 간혹 생기는 부분을 발견하였다.


# 각각 장단점을 설명하면,
# 커넥션 풀이 크다면 당연히 메모리 소모가 클것이고
# 커넥션 풀이 작다면 커넥션이 많이 발생할 경우 대기시간이 발생할 것이다.
# 즉 웹 사이트 동시 접속자수 등 서버 부하에 따라 크기를 조정해야 할것이다.

# 전역 쿼리 객체
# def init_query_dict():
#     for file in [
#         file for file in os.listdir(
#             os.path.join(
#             GLOBAL_CONFIG.CVE_ROOT_DIR,
#             'query')) if file.endswith(".yaml")]:
#         with open(os.path.join(GLOBAL_CONFIG.CVE_ROOT_DIR, 'query', file), encoding='utf8') as stream:
#             try:
#                 QUERY[file] = yaml.safe_load(stream)
#             except yaml.YAMLError as exc:
#                 print(exc)
def connect(
        database=CONFIG['default'].DB_NAME,
        user=CONFIG['default'].DB_USER,
        password=CONFIG['default'].DB_PASS,
        host=CONFIG['default'].DB_HOST,
        port=CONFIG['default'].DB_PORT,
        minimum=1,
        maximum=100):
    global _POOL
    if not _POOL:
        # Connection 풀에는 아래와 같은 방법이 있다.
        # 1. SimpleConnectionPool : 서로다른 쓰레드에서 공유 할수 없는 Pool ( 쓰레드에 안전 X )
        # 2. ThreadedConnectionPool : Thread를 통해 작동하는 Pool ( 쓰레드에 안전 O )
        # 3. PersistentConnectionPool : 쓰레드에 영구연결을 할당, 이 연결풀은 쓰레드 ID를 활용해서 필요한 키를 단독으로 생성하고
        # 쓰레드가 연결을 끊을때까지 항상 동일한 연결 객체를 가지고 온다. 즉, 쓰레드 풀에서 하나 이상의 단일 연결을 사용 할 수
        # 없다.

        _POOL = psycopg2.pool.ThreadedConnectionPool(minimum, maximum,

                                                     database=database,
                                                     user=user,
                                                     password=password,
                                                     host=host,
                                                     port=port)


_OPERATORS = {'lt': '<',
              'gt': '>',
              'ne': '!=',
              're': '~',
              'like': 'LIKE',
              'not_like': 'NOT LIKE',
              'in': 'IN'
              }

_UPDATE_OPERATORS = {'': "%(field)s = %%(%(key)s)s",
                     'add': "%(field)s = %(field)s + %%(%(key)s)s",
                     'sub': "%(field)s = %(field)s - %%(%(key)s)s",
                     'append': "%(field)s = %(field)s || %%(%(key)s)s",
                     'func': "%(field)s = %(val)s",
                     }


def _where(where):
    if where:
        __where = []
        for f in where.keys():
            field, _, operator = f.partition('__')
            if operator == 'in':
                _values = ['(%s)' % v for v in where[f]]
                __where.append(
                    '%s %s ( %s )' %
                    (field, _OPERATORS.get(
                        operator, operator) or 'in', ','.join(_values)))
            else:
                __where.append(
                    '%s %s %%(%s)s' %
                    (field, _OPERATORS.get(
                        operator, operator) or '=', f))
        return ' WHERE ' + ' AND '.join(__where)
    else:
        return ''


class cursor(object):
    connection = None
    cursor = None

    # RealDictCursor : 핻을 기본으로 Dic 유형으로 사용함
    def __init__(self, cursor_factory=psycopg2.extras.RealDictCursor):
        self.cursor_factory = cursor_factory
        if not _POOL:
            raise ValueError("No database pool")

    def __enter__(self):
        self.connection = _POOL.getconn()
        self.cursor = self.connection.cursor(
            cursor_factory=self.cursor_factory)
        return self

    def __exit__(self, types, value, traceback):
        if GLOBAL_CONFIG.PRINT_SQL and self.cursor.query:
            CRED = '\033[93m'
            CEND = '\033[0m'
            print(
                "{}{}{}".format(
                    CRED,
                    re.sub(
                        r'[\t ]*([\r\n]+[\t ]*[\r\n]+)',
                        '\n',
                        self.cursor.query.decode("utf-8")),
                    CEND),
                file=sys.stderr)
        self.commit()
        self.cursor.close()
        _POOL.putconn(self.connection)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def execute(self, sql, params=None):
        self.cursor.execute(sql, params)
        return self.cursor.rowcount

    def query(self, sql, params=None):
        self.execute(sql, params)
        return self.cursor.fetchall()

    def query_one(self, sql, params=None):
        self.execute(sql, params)
        return self.cursor.fetchone()

    def query_dict(self, sql, key, params=None):
        d_obj = {}
        for row in self.query(sql, params):
            d_obj[row[key]] = row
        return d_obj

    def query_cnt_to_str(self, sql, params=None, column_name=None):
        self.execute(sql, params)
        return self.cursor.fetchone()[column_name]

    def insert(self, table: object, values: dict,
               returning: object = None, donothing: object = None,
               where: object = None) -> object:
        list_insert = False
        _values = []
        for v, l in values.items():
            if isinstance(l, list):
                list_insert = True
                if isinstance(l[0], int):
                    _values.append('jsonb_array_elements_text(to_jsonb(%%(%s)s))::integer' % v)
                else:
                    _values.append('jsonb_array_elements_text(to_jsonb(%%(%s)s))' % v)
            else:
                _values.append('%%(%s)s' % v)

        if list_insert:
            sql = 'INSERT INTO %s (%s) SELECT %s' % (
                table, ','.join(values.keys()), ','.join(_values))
        else:
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
                table, ','.join(values.keys()), ','.join(_values))

        if donothing:
            if where:
                sql += ' ON CONFLICT (%s) DO NOTHING' % donothing
            else:
                sql += ' ON CONFLICT (%s) DO NOTHING' % donothing
        if returning:
            sql += ' RETURNING %s' % returning
            return self.query(sql, values)
        else:
            return self.execute(sql, values)

    def multi_insert(self, table: object, values: dict,
                     returning: object = None) -> object:
        if len(values) != 2:
            abort(500)

        _values = []
        for v, l in values.items():
            if isinstance(l[0], int):
                _values.append('jsonb_array_elements_text(to_jsonb(%%(%s)s))::integer' % v)
            else:
                _values.append('jsonb_array_elements_text(to_jsonb(%%(%s)s))' % v)

        sql = 'INSERT INTO %s (%s) SELECT * FROM %s CROSS JOIN (%s) A' % (
            table, ','.join(values.keys()), _values[0], _values[1])
        if returning:
            sql += ' RETURNING %s' % returning
            return self.query(sql, values)
        else:
            return self.execute(sql, values)

    def delete(self, table, where=None, returning=None):
        sql = 'DELETE FROM %s' % table + _where(where)
        if returning:
            sql += ' RETURNING %s' % returning
            return self.query(sql, where)
        else:
            return self.execute(sql, where)

    def update(self, table, values, where=None, returning=None):
        _update = []
        for key, value in values.items():
            f, _, operator = key.partition('__')
            _update.append(_UPDATE_OPERATORS[operator] % {
                'key': key, 'val': value, 'field': f, 'op': operator})
        sql = 'UPDATE %s SET %s' % (table, ','.join(_update))
        sql = self.cursor.mogrify(sql, values)
        if where:
            sql += self.cursor.mogrify(_where(where), where)
        if returning:
            sql += (' RETURNING %s' % returning).encode()
            return self.query(sql)
        else:
            return self.execute(sql)


def execute(sql, params=None):
    """
        >>> execute("INSERT INTO user_info (name) VALUES ('xxx')")
        1
        >>> execute("DELETE FROM user_info WHERE name = 'xxx'")
        1
    """
    with cursor() as cus:
        return cus.execute(sql, params)


def query(sql, params=None):
    # noinspection InconsistentLineSeparators
    """
            >>> r = query('select name,active,properties FROM user_info ORDER BY user_no')
            >>> r[0] == {'name':'aaaaa','active':True,'properties':{'key':'0'}}
            True
            >>> len(r)
            10
    """
    with cursor() as cus:
        return cus.query(sql, params)


def query_one(sql, params=None):
    with cursor() as cus:
        return cus.query_one(sql, params)


def query_cnt_to_str(sql, params=None, column_name=None):
    with cursor() as cus:
        return cus.query_cnt_to_str(sql, params, column_name)


def query_dict(sql, key, params=None):
    # noinspection InconsistentLineSeparators
    """
            >>> r = query_dict('select name,active,properties FROM user_info ORDER BY name','name')
            >>> r['aaaaa'] == {'name':'aaaaa','active':True,'properties':{'key':'0'}}
            True

            >>> sorted(r.keys())
            ['aaaaa', 'bbbbb', 'ccccc', 'ddddd', 'eeeee', 'fffff', 'ggggg', 'hhhhh', 'iiiii', 'jjjjj']
        """
    with cursor() as cus:
        return cus.query_dict(sql, key, params)


def insert(table, values, returning=None, donothing=None, where=None):
    # noinspection PyUnresolvedReferences
    """
            >>> insert('user_info',{'name':'xxx','properties':{'a':'aa'}})
            1
            >>> insert('user_info',{'name':'yyy','properties':{'a':'bb'}},'name')
            {'name': 'yyy'}
            >>> insert('user_info',values={'name':'zzz','properties':{'a':'cc'}},returning='name')
            {'name': 'zzz'}
            >>> select('user_info',where={'properties__?':'a'},order=('name',),columns=('properties',))
            [{'properties': {'a': 'aa'}}, {'properties': {'a': 'bb'}}, {'properties': {'a': 'cc'}}]
            >>> delete('user_info',where={'name__in':('xxx','yyy','zzz')})
            3
        """
    with cursor() as cus:
        return cus.insert(table, values, returning, donothing, where)


def multi_insert(table, values, returning=None):
    with cursor() as cus:
        return cus.multi_insert(table, values, returning)


def delete(table, where=None, returning=None):
    """
        >>> insert('user_info',{'name':'xxx'})
        1
        >>> insert('user_info',{'name':'xxx'})
        1
        >>> delete('user_info',where={'name':'xxx'},returning='name')
        [{'name': 'xxx'}, {'name': 'xxx'}]
    """
    with cursor() as cus:
        return cus.delete(table, where, returning)


def update(table, values, where=None, returning=None):
    # noinspection PyUnresolvedReferences
    """
            >>> insert('user_info',{'name':'xxx'})
            1
            >>> update('user_info',{'name':'yyy','active':False},{'name':'xxx'})
            1
            >>> update('user_info',values={'count__add':1},where={'name':'yyy'},returning='count')
            [{'count': 1}]
            >>> update('user_info',values={'count__add':1},where={'name':'yyy'},returning='count')
            [{'count': 2}]
            >>> update('user_info',values={'count__func':'floor(pi()*count)'},where={'name':'yyy'},returning='count')
            [{'count': 6}]
            >>> update('user_info',values={'count__sub':6},where={'name':'yyy'},returning='count')
            [{'count': 0}]
            >>> update('user_info',values={'properties':{'x':'1','y':'2','z':'3'}}
            ,where={'name':'yyy'},returning='name')
            [{'name': 'yyy'}]
            >>> select_one('user_info',where={'name':'yyy'},columns=('properties',))['properties'] ==
                    {'x':'1','y':'2','z':'3'}
            True
            >>> delete('user_info',{'name':'yyy'})
            1
        """
    with cursor() as cus:
        return cus.update(table, values, where, returning)
