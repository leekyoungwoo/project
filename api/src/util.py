import ast
import copy
import importlib
import json
import os
import re
import smtplib
import urllib
from ast import literal_eval
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

import pytz
from flask import Response, request, current_app, g, send_file
from flask_babel import gettext
from flask_restful import abort
from inflection import camelize, underscore
from simplejson import dumps as json_dumps

import db


def _make_json(data, status):
    res = Response(
        json_dumps(data, ensure_ascii=False, sort_keys=True),
        content_type="application/json; charset=utf-8", status=status)
    # res.headers['Pragma'] = "ssg"
    # res.headers['ssg'] = "ssg"

    return res


def _transform_keys(data, key_transformer):
    """
    dict 이나 set 의 value를 camelcase로 변환.
    :param data:
    :param key_transformer:
    :return:
    """
    if isinstance(data, dict):
        transformed = {}
        for key, value in data.items():
            camel_key = key_transformer(key)
            transformed[camel_key] = _transform_keys(value, key_transformer)
        return transformed

    if isinstance(data, (list, tuple)):
        new_data = []
        for i, name in enumerate(data):
            new_data.append(_transform_keys(name, key_transformer))
        return new_data
    return data


def keys_to_camelcase(data):
    return _transform_keys(data, str_to_camelcase)


def keys_to_snakecase(data):
    return _transform_keys(data, str_to_snakecase)


# 값의 instance 따라 literal_eval 적용해서 return
def using_literal_eval(context):
    if isinstance(context, list):
        return context
    elif isinstance(context, dict):
        return context
    else:
        try:
            return literal_eval(context)
        except Exception:
            return context


def make_raw_response(status, data=None):
    data = keys_to_camelcase(data)
    return _make_json(data, status)


def make_response(status, datas=None, result=None, error=None, add_res={}):
    """
    Response와 Response Data 구조를 정의한다.
    :param add_res:
    :param result:
    :type datas: object
    :param status:
    :param error:
    """
    data = dict()
    data['list'] = keys_to_camelcase(datas)
    data['error'] = error
    if result:
        data['result'] = result
    data['status'] = status
    for key in add_res:
        data[key] = add_res[key]

    return _make_json(data, status)


def make_filter(filter_dic, sort_filter=list()):
    result = list()
    if len(filter_dic) > 0:
        for key, value in filter_dic.items():
            if 'search' in key and value and 'searchType' in value and value['searchType']:
                if 'searchText' in value and not value['searchText']:
                    value['searchText'] = ''

                if value['searchType'] in sort_filter:
                    result_dic = __make_filter_dict(
                        str_to_snakecase(
                            value['searchType']) + '::TEXT',
                        'ILIKE',
                        '%' + value['searchText'] + '%')
                    result.append(result_dic)

                elif len(value['searchType'].split(',')) > 1:
                    result_dic = __make_filter_dict(
                        'concat_space(' + value['searchType'] + ')',
                        'ILIKE',
                        '%' + value['searchText'] + '%')
                    result.append(result_dic)

                else:
                    pass

            elif re.match(r'^\w+Array$', key):
                result_dic = __make_filter_dict(str_to_snakecase(key[:-5]), 'IN', value.replace(' ', '').split(','))
                result.append(result_dic)

            elif re.match(r'^\w+Epoch$', key):
                if 'start' in value:
                    result_dic = __make_filter_dict(str_to_snakecase(key), '>=', value['start'])
                    result.append(result_dic)

                if 'end' in value:
                    result_dic = __make_filter_dict(str_to_snakecase(key), '<=', value['end'])
                    result.append(result_dic)

            else:
                result_dic = __make_filter_dict(str_to_snakecase(key), '=', value)
                result.append(result_dic)

    return result


def __make_filter_dict(search_type, operator, text):
    result_dic = dict()
    result_dic['type'] = search_type
    result_dic['operator'] = operator
    result_dic['text'] = text

    return result_dic


def make_sort_query(sort_list, target_list, default):
    if sort_list:
        sort_sql = ''
        for sort in sort_list:
            if 'field' in sort and 'order' in sort and (
                    sort['order'].upper() == 'ASC' or sort['order'].upper() == 'DESC'):
                if sort['field'] in target_list:
                    sort_sql += __make_sort_sql(str_to_snakecase(sort['field']), sort['order'].upper(), True)
                else:
                    sort_sql = '{} ASC\n'.format(default)
                    break
    else:
        sort_sql = '{} ASC\n'.format(default)

    return sort_sql


def __make_sort_sql(target_name, order_type, reverse=False):
    if order_type == 'ASC':
        if reverse:
            order_type = 'DESC NULLS LAST'
    else:
        if reverse:
            order_type = 'ASC NULLS FIRST'

    sql = '{} {}\n'.format(target_name, order_type)

    return sql


def use_p():
    try:
        if request.args:
            p = request.args.to_dict().copy()
        elif request.form:
            p = request.form.copy()
        elif request.data:
            p = json.loads(force_decode(request.data))
        elif request.get_json():
            p = request.get_json()
        else:
            p = {}
    except Exception:
        p = {}

    for k in p:
        if p[k] not in [None, '']:
            p[k] = guess_type(p[k])
        else:
            pass

    return p


def guess_type(value):
    try:
        nullable_value = value.replace('null', '\"\"') if isinstance(value, str) else value
        value = ast.literal_eval(nullable_value)
    except Exception:
        return value

    return value


# 강제디코딩
def force_decode(string):
    for i in ['utf8', 'cp949']:
        try:
            return string.decode(i)
        except UnicodeDecodeError:
            pass


def use_db():
    _db = importlib.import_module('db')
    _db.connect()

    return _db


def check_param_is_none(p, target, rm_space=False):
    ret = str(p[target]).strip() if target in p and p[target] else None
    if ret and rm_space:
        ret = re.sub(r'\s{2,}', ' ', ret)
    return ret


def make_sort_query(sort, target_list, default):
    if sort:
        sort_sql = ''
        if 'field' in sort and sort['field'] and 'order' in sort and sort['order'] and (
                sort['order'].upper() == 'ASC' or sort['order'].upper() == 'DESC'):
            if sort['field'] in target_list:
                sort_sql += __make_sort_sql(str_to_snakecase(sort['field']), sort['order'].upper(), True)
            else:
                sort_sql = '{} ASC\n'.format(default)
        else:
            sort_sql = '{} ASC\n'.format(default)
    else:
        sort_sql = '{} ASC\n'.format(default)

    return sort_sql


def make_directory(check_path):
    # 디렉토리 존재 확인 후 없을 경우 새로 생성
    if not os.path.isdir(check_path):
        os.mkdir(check_path)


def _check_regex(rp):
    if isinstance(rp, str):
        if re.search(r'^\d+$', rp):
            return int(rp)
        elif re.search(r'^\s*$', rp):
            # 빈공백일때 처리 생각
            return None
        else:
            return rp
    else:
        return rp


class MakeAutoCountName:
    def __init__(self, name, start_num):
        self.name = str(name)
        self.current_num = int(start_num)

    def __iter__(self):
        return self

    def __next__(self):
        self.current_num += 1
        return f"{self.name} - ({str(self.current_num)})"

    def next_name(self):
        return self.__next__()


def set_macn(group_name, name_set):
    name_dict = dict()
    for name_ in name_set:
        name_count = get_group_name(group_name, name_)
        name_dict[name_] = MakeAutoCountName(name_, name_count)
        # print(name_, ':', name_count)
    return name_dict


def get_group_name(group_name, name):
    """
    :param group_name: group name
    :return: group name
    ex) get_group_name('group63', 'copy')
    현재 type은 사용하지 않음    """

    asset_tag_name = ''
    name_ = re.compile(r'(\<|\>|\(|\)|\[|\]|\^|\||\*|\.|\+|\?)').sub(r'\\\g<1>', name)
    if group_name == 'asset_group':
        asset_tag_name = 'ag_name'
    elif group_name == 'tag_group':
        asset_tag_name = 'tag_name'
    else:
        pass

    with db.cursor() as cus:
        sql = """
select
    (regexp_matches({}, '{} - \(([0-9]+)\)','g'))[1]::int as snum
from {}
order by snum desc
limit 1
        """.format(asset_tag_name, name_, group_name)

        query_result = cus.query(sql)
        if query_result is not None and len(query_result) > 0:
            return query_result[0]['snum']
        else:
            return 0


def str_to_camelcase(str_value, capitalize=False):
    """
    string 을 camelcase로 변환.
    :param str_value:
    :param capitalize:
    :return:
    """
    return camelize(str(str_value), capitalize)


def str_to_snakecase(str_value):
    """
    string 을 snakecase로 변환.
    :param str_value:
    :return:
    """
    return underscore(str_value)


def log_decorators(log_title, log_type=None):
    def decorator(func):
        @wraps(func)
        def newFunc(*args, **kwargs):
            req_p = copy.deepcopy(args[0].p) if hasattr(args[0], 'p') else {}
            # if 'sort' in args[0].p and args[0].p:
            #     req_p['sort'] = json.loads(args[0].p['sort'])
            # if 'filter' in args[0].p and args[0].p:
            #     req_p['filter'] = json.loads(args[0].p['filter']) if 'filter' in args[0].p and args[0].p['filter'] else None

            ret = func(*args, **kwargs)
            _log_title = gettext(log_title)
            _log_type = log_type

            if request.headers.getlist("X-Forwarded-For"):
                remote_ip = request.headers.getlist("X-Forwarded-For")[0]
            else:
                remote_ip = request.remote_addr

            if not _log_type:
                _log_type = 4 if 'user' in g and g.user['isRoot'] else 8

            # 로그인 하였고, 정상적인 결과일 경우 로그 기록
            p = json.loads(ret.data.decode('utf-8'))

            if hasattr(args[0], 'p'):
                if 'userPasswd' in req_p:
                    del req_p['userPasswd']

                if 'beforePasswd' in req_p:
                    del req_p['beforePasswd']

                if 'newPasswd' in req_p:
                    del req_p['newPasswd']

                if 'licenseDetailEnc__func' in req_p:
                    del req_p['licenseDetailEnc__func']

                if 'licenseHashEnc__func' in req_p:
                    del req_p['licenseHashEnc__func']

            log_detail = {
                'req': req_p,
                'res': p['list'] if 'list' in p else p['error']}

            if 'user' in g and not ('error' in p and p['error']):
                db.insert(
                    'system_log', {
                        'ui_no': g.user['uiNo'],
                        'ui_id': g.user['uiId'],
                        'ui_name': g.user['uiName'],
                        'ui_email': g.user['uiEmail'],
                        'log_type': _log_type,
                        'log_title': _log_title,
                        'log_detail': json_dumper(log_detail),
                        'api_name': args[0].__class__.__name__,
                        'ip': remote_ip})

            return ret

        return newFunc

    return decorator


def system_log(p, log_title, log_category, log_type=None):
    _log_type = log_type

    if request.headers.getlist("X-Forwarded-For"):
        remote_ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        remote_ip = request.remote_addr

    if not _log_type:
        _log_type = 4 if 'user' in g and g.user['isRoot'] else 8

    if isinstance(p, dict) and 'userPasswd' in p:
        del p['userPasswd']

    cv_log_title = gettext(log_title)

    # 로그인 하였으면 기록
    if 'user' in g:
        db.insert(
            'system_log', {
                'ui_no': g.user['uiNo'],
                'ui_id': g.user['uiId'],
                'ui_name': g.user['uiName'],
                'ui_email': g.user['uiEmail'],
                'log_type': _log_type,
                'log_title': cv_log_title,
                'log_detail': json_dumper(p),
                'api_name': log_category,
                'ip': remote_ip})


def base_encode(obj):
    """
    simplejson에서 사용하는 JSONEncoder의 하위클래스
    특수값의 인코딩을 처리하는데 사용
    """

    if isinstance(obj, datetime):
        # 모든 datetime을 RFC 1123 형식으로 변환
        return date_to_str(obj)
    elif isinstance(obj, set):
        # set객체는 list로 변환
        return list(obj)
    else:
        return obj


def date_to_str(date):
    """
     datetime의 값을 Config에 정의된 포맷으로 변환.
    """
    return datetime.strftime(
        date, current_app.config['DATE_FORMAT']) if date else None


def json_dumper(data):
    return json_dumps(data, ensure_ascii=False, default=base_encode, sort_keys=True)


def composed_decorators(*decorators):
    def decorated(f):
        for decorator in reversed(decorators):
            f = decorator(f)
        return f

    return decorated


def get_language():
    if request.accept_languages[0][0].find('ja'):
        return 'ja'
    else:
        return 'ko'


def epoch_to_datetime(epoch):
    """
    epoch를 config에 정의한 date_format으로 변환.
    :param epoch:
    :return:
    """
    return datetime.utcfromtimestamp(int(float(epoch)))


def epoch_to_local_datetime(epoch):
    if epoch:
        return datetime.fromtimestamp(int(float(epoch)), tz=pytz.timezone('Asia/Seoul'))
    else:
        return None


def process_io_download(byte_io, mimetype, file_name):
    res = send_file(byte_io, mimetype)
    res.headers.add('content-length', byte_io.getbuffer().nbytes)
    res.headers["Accept"] = mimetype

    if request.referrer and 'api/docs' in request.referrer:
        _, ext = os.path.splitext(file_name)
        res.headers["Content-Disposition"] = "attachment; " \
                                             "filename={}".format(
            'file_sample' + ext
        )
    else:
        res.headers["Content-Disposition"] = "attachment; " \
                                             "filename*=UTF-8''{quoted_filename}".format(
            quoted_filename=urllib.parse.quote(file_name.encode('utf8'))
        )
    return res


def get_system_config(parameter=None):
    bind_param = []

    sql = """
SELECT parameter
    ,COALESCE(value, default_value) AS value
FROM system_config
"""

    if parameter:
        sql += """
        WHERE parameter = %s
"""
        bind_param.append(parameter)

    return db.query_dict(sql, 'parameter', bind_param)


def send_template_email(user_email, title, content):
    config = get_system_config()
    system_url = config['systemUrl']['value']

    email_content = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
</head>
<body>
<table style="
position: relative;
width: 650px;
border: 8px solid #f3f3f3;
border-spacing: 0;
margin: auto;">
<!-- 로고 -->
<tr>
  <td style="padding:34px 36px 0 0; text-align:right;">
    <img src="{}/fdata/img/mf_logo2.png" alt="Gopeneye" style="
    font-size: 24px;
    font-weight: bold;" />
  </td>
</tr>
<!-- 내용 -->
<tr>
  <td style="padding:0 70px 0; font-family: '{}', sans-serif; letter-spacing:-1px;">
    {}
  </td>
</tr>
<!-- 고객센터 -->
<tr>
  <td style="padding:0 70px 35px; font-family: '{}', sans-serif;">
      <div style="
      display:flex;
      font-size: 16px;
      margin-bottom: 10px;
      line-height:20px;
      color:#000000">
      <div style="font-size:17px; font-weight:bold; margin-right:18px; letter-spacing:-2px;">{}</div>
      <em style="margin:3px 15px 0 0; width:1px; height:15px; border-left:1px solid #cdcdcd;"></em>
      <div style="font-size:14px;">
""".format(system_url,
           'Nanum Gothic' if not current_app.config['IS_JAPAN'] else 'MEIRYO',
           content,
           'Nanum Gothic' if not current_app.config['IS_JAPAN'] else 'MEIRYO',
           gettext('<span style="letter-spacing:0">SolidStep CVE</span> 고객 센터'))

    if current_app.config['IS_JAPAN']:
        email_content += """\
        <div>{} : <a href="mailto:support-m@jsecurity.co.jp" style="font-weight:bold; color: #3caa73">support-m@jsecurity.co.jp</a></div>
""".format(gettext('이메일'))

    else:
        email_content += """\
        <div>{} : <a href="mailto:MudFix-support@ssrinc.co.kr" style="font-weight:bold; color: #3caa73">MudFix-support@ssrinc.co.kr</a></div>
""".format(gettext('이메일'))

    email_content += """\
      </div>
"""
    email_content += """\
    </div>
  </td>
</tr>
<!-- 기업 소개 -->
<tr>
  <td style="
    font-family: '{}', sans-serif;
    background-color: #f3f3f3;
    padding: 30px 44px 20px;
    color: #757575;
    font-size: 11px;
    text-align: left;">
""".format(
        'Nanum Gothic' if not current_app.config['IS_JAPAN'] else 'MEIRYO',
    )

    if current_app.config['IS_JAPAN']:
        email_content += """\
        <div>
            <img src="https://mudfix.jp/img/logo/JSecuritylogoS.png" style="width:130px; vertical-align:bottom; margin-right: 10px;"/>
            <div style="color:#757575; margin-top: 10px;">
              <a style="font-size:12px; margin:0; font-weight:bold; color:#757575;" href="https://www.jsecurity.co.jp/">
                株式会社 JSecurity
              </a>
              <p style="font-size:11px; margin:0;">〒105-0021 東京都港区東新橋2-12-1 PMO東新橋7階</p>
              <p style="font-size:11px; margin:0;">TEL : 03-6826-1915　FAX : 03-6826-1916</p>
            </div>
        </div>
""".format(
            'Nanum Gothic' if not current_app.config['IS_JAPAN'] else 'MEIRYO',
            'Nanum Gothic' if not current_app.config['IS_JAPAN'] else 'MEIRYO',
        )

    else:
        email_content += """\
        <div style="display:flex; ">
            <img src="{}/img/logo/ssr_logo.png" alt="ssr" style="margin-right:20px; object-fit: contain; font-size: 24px; font-weight: bold;" />
            <div style="color:#757575">
                <p style="font-size:12px; margin:0; font-weight:bold;">{}</p>
                <p style="font-size:11px; margin:0;">{}</p>
                <p style="font-size:11px; margin:0;">{}</p>
                <p style="font-size:11px; margin:0;">{}</p>
            </div>
        </div>
""".format(system_url,
            gettext('(주) 에스에스알'),
            gettext('대표이사 : 정진석, 윤두식 / 사업자 등록번호 : 113-86-42090'),
            gettext('사업장 소재지 : 서울시 구로구 디지털로 26길 111 JnK디지털타워 1606호'),
            gettext('TEL : 02-6959-8039 / FAX : 02-6959-0130 / 통신판매 신고번호 : 제 2015-서울구로-1351호')
           )

        email_content += """\
  </td>
</tr>
</table>
</body>
</html>
"""

    # TODO 임시 메일 발송
    config = db.query_dict("""\
SELECT parameter
    ,COALESCE(value, default_value) AS value
FROM system_config
""", 'parameter')

    sender_mail = config['mailSenderEmail']['value']

    msg = MIMEMultipart()

    msg['From'] = sender_mail
    msg['To'] = user_email
    msg['Subject'] = title

    msg.attach(
        MIMEText(
            '<html><head><style>a {text-decoration: none;} a:hover {text-decoration: underline;}</style></head><body style="margin-left: 40px;">' +
            email_content +
            '</body></html>',
            'html',
            'utf-8'))

    try:
        if config['mailProtocol']['value'] == 'SMTP':
            s = smtplib.SMTP(
                config['mailHost']['value'],
                config['mailSmtpPort']['value'],
                timeout=int(
                    config['mailTimeLimit']['value']))
        else:
            s = smtplib.SMTP_SSL(
                config['mailHost']['value'],
                config['mailSmtpPort']['value'],
                timeout=int(
                    config['mailTimeLimit']['value']))

        # tls 사용 여부와 검증
        if config['mailUseTls']['value'] == '1':
            s.starttls()

        # mailId Passwd 검증
        if config['mailId']['value'] and config['mailPassword']['value']:
            s.login(
                config['mailId']['value'], config['mailPassword']['value'])

        s.sendmail(sender_mail, user_email, msg.as_string())
        s.quit()

    except Exception as e:
        print(str(e))
        pass

    return True


def init_parameter(p, params, sort_filter=[]):

    p['isCreate'] = 1 if 'isCreate' in p and p['isCreate'] else None
    p['isRoot'] = 1 if 'isRoot' in g.user and g.user['isRoot'] else 0

    p['filter'] = p['filter'] if 'filter' in p and p['filter'] else {}
    p['sort'] = p['sort'] if 'sort' in p and p['sort'] else {}

    params['uiNo'] = g.user['uiNo']
    if sort_filter:
        params['sortSql'] = make_sort_query(p['sort'], sort_filter, str_to_snakecase(sort_filter[0]))

    return p, params


def check_list(p, params):

    second_col = p['secondCol'] if 'secondCol' in p and p['secondCol'] else {}
    third_col = p['thirdCol'] if 'thirdCol' in p and p['thirdCol'] else {}

    if not second_col:
        return abort(400)

    select_no = second_col['selectNo'] if 'selectNo' in second_col and second_col['selectNo'] else {}
    second_check = second_col['checkList'] if 'checkList' in second_col and second_col['checkList'] else {}

    ag_no_array = set()
    tag_no_array = set()
    atgl_no_array = set()
    atgl_no_exclude_array = set()

    if 'agNo' in select_no and select_no['agNo']:
        params['agNoArray'] = [select_no['agNo']]

    elif 'tagNo' in select_no and select_no['tagNo']:
        params['tagNoArray'] = [select_no['tagNo']]

    elif 'atglNo' in select_no and select_no['atglNo']:
        params['atglNoArray'] = [select_no['atglNo']]

    else:
        if 'agNo' in second_check and second_check['agNo']:
            ag_no_array = atgl_no_array.union(set(second_check['agNo']))

        if 'atglNo' in second_check and second_check['atglNo']:
            atgl_no_array = atgl_no_array.union(set(second_check['atglNo']))

        if 'tagNo' in second_check and second_check['tagNo']:
            for tag_group in second_check['tagNo']:
                if 'type' in tag_group and tag_group['type']:

                    # 단독 자산그룹
                    if 'atglNo' in tag_group['type'] and tag_group['type']['atglNo']:
                        atgl_no_array = atgl_no_array.union(set(tag_group['type']['atglNo']))
                    # 태그추가에서 제외할 자산그룹
                    elif 'exclude' in tag_group['type'] and tag_group['type']['exclude']:
                        atgl_no_exclude_array = atgl_no_exclude_array.union(set(tag_group['type']['exclude']))
                        tag_no_array.add(tag_group['tagNo'])
                    # 태그추가
                    else:
                        if 'checkType' in tag_group and tag_group['checkType'] == 2:
                            tag_no_array.add(tag_group['tagNo'])

        params['agNoArray'] = list(ag_no_array) if len(ag_no_array) > 0 else None
        params['atglNoArray'] = list(atgl_no_array) if len(atgl_no_array) > 0 else None
        params['tagNoArray'] = list(tag_no_array) if len(tag_no_array) > 0 else None
        params['atglNoExcludeArray'] = list(atgl_no_exclude_array) if len(atgl_no_exclude_array) > 0 else None

    if 'searchText' in second_col and second_col['searchText']:
        params['agSearchText'] = second_col['searchText']

    if 'searchText' in third_col and third_col['searchText']:
        params['aiSearchText'] = third_col['searchText']

    if 'selectNo' in third_col and third_col['selectNo']:
        params['assetInclude'] = [third_col['selectNo']]

    elif 'include' in third_col and third_col['include']:
        params['assetInclude'] = third_col['include']

    elif 'exclude' in third_col and third_col['exclude']:
        params['assetExclude'] = third_col['exclude']

    else:
        pass

    return {**p, **params}
