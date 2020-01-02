# import importlib
# import inspect
import logging
import os
# import re
import sys

# import structlog as structlog
# from flasgger import Swagger
from flask import Flask, request
# from flask_babel import Babel
from flask_cors import CORS
from flask_restful import Api

from config import CONFIG
# from db import init_query_dict
# from util import str_to_camelcase

app = Flask(__name__)
# init_query_dict()

# 환경변수에 따른 실행모드 설정 START
if os.environ.get('DEBUG_MOD') == 'development':
    app.config.from_object(CONFIG['development'])
else:
    app.config.from_object(CONFIG['production'])

# babel = Babel(app)

cors = CORS(app, resources={r"/api/*": {"origins": "*"}})

api = Api(app)

# swagger = Swagger(
#     app,
#     config=app.config['SWAGGER_CONFIG'])

# importlib.import_module('apis')
# # apis 모듈 동적 add_resource
# for module in list(m for m in sys.modules.keys() if m.find('apis.') == 0):
#     for api_name, obj in inspect.getmembers(sys.modules[module]):
#         if inspect.isclass(obj) and 'apis' in obj.__module__ and obj.__module__ == module:
#             if hasattr(obj, 'MAIN_CLASS') and obj.MAIN_CLASS:
#                 api.add_resource(obj, '/api/v1/{}'.format(obj.__name__), endpoint=obj.__name__)
#             else:
#                 url = '/api/v1/{}/{}'.format(str_to_camelcase(obj.__module__.split('.')[-1], True),
#                                              obj.__name__)
#                 api.add_resource(obj, url, endpoint=url)
#
# importlib.import_module('exec')
# # exec 모듈 동적 add_resource
# for module in list(m for m in sys.modules.keys() if m.find('exec.') == 0):
#     for api_name, obj in inspect.getmembers(sys.modules[module]):
#         if inspect.isclass(obj) and 'exec' in obj.__module__ and obj.__module__ == module:
#             if hasattr(obj, 'MAIN_CLASS') and obj.MAIN_CLASS:
#                 api.add_resource(obj, '/exec/{}'.format(obj.__name__), endpoint=obj.__name__)
#             else:
#                 url = '/exec/{}/{}'.format(str_to_camelcase(obj.__module__.split('.')[-1], True),
#                                            obj.__name__)
#                 api.add_resource(obj, url, endpoint=url)


# @babel.localeselector
# def get_locale():
#     if 'lang' in request.cookies:
#         return request.cookies['lang']
#     else:
#         return 'ko'


@app.route('/')
@app.route('/api/')
def index_page():
    return 'Welcome To Note RESTful web service.' \
           'See doc /api/v1/docs'


if __name__ == '__main__':
    extra_files = None
    if app.config['DEBUG']:
        extra_dirs = ['./query']
        extra_files = extra_dirs[:]
        for extra_dir in extra_dirs:
            for dirname, dirs, files in os.walk(extra_dir):
                for filename in files:
                    filename = os.path.join(dirname, filename)
                    if os.path.isfile(filename):
                        extra_files.append(filename)

    logging.basicConfig(
        format='%(asctime)s [%(levelname)s]: %(message)s', stream=sys.stdout, level=logging.INFO
        )

    # structlog.configure(
    #     processors=[
    #         structlog.stdlib.filter_by_level,
    #         structlog.stdlib.add_logger_name,
    #         structlog.stdlib.add_log_level,
    #         structlog.stdlib.PositionalArgumentsFormatter(),
    #         structlog.processors.StackInfoRenderer(),
    #         structlog.processors.format_exc_info,
    #         structlog.processors.KeyValueRenderer(),
    #         # structlog.processors.JSONRenderer(),
    #         ],
    #     context_class=dict,
    #     logger_factory=structlog.stdlib.LoggerFactory(),
    #     wrapper_class=structlog.stdlib.BoundLogger,
    #     cache_logger_on_first_use=True,
    #     )

    app.run(host=app.config['HOST'], port=app.config['PORT'], extra_files=extra_files if extra_files else None)
