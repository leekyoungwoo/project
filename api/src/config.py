# coding=utf-8
import os


class Config:

    # SECRET_KEY = 'asldkhaslkfhalhf@ O@#TRNO@!#NTRONI O@#TRIN#OITN'
    # SECURITY_PASSWORD_SALT = 'ssrinc!123qpxkepah!123'
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    # DB config
    DB_NAME = 'notedb'
    DB_USER = 'noteadmin'
    DB_PASS = 'note!123'
    DB_HOST = 'localhost'
    DB_PORT = '5432'

    HOST = '0.0.0.0'
    PORT = 5001

    CVE_ROOT_DIR = '/SolidStep-CVE/api/src'
    # FILE_ROOT_DIR = '/GOPEN/fdata'

    # SWAGGER = {
    #     'title': 'SolidStep CVE API',
    #     'uiversion': 2,
    #     'version': '0.1',
    #     'description': '공개용 SolidStep CVE API',
    # }
    #
    # SWAGGER_CONFIG = {
    #     "headers": [
    #     ],
    #     "specs": [
    #         {
    #             "endpoint": 'api',
    #             "route": '/api/api.json',
    #             "rule_filter": lambda rule: True,  # all in
    #             "model_filter": lambda tag: True,  # all in
    #         }
    #     ],
    #     "static_url_path": "/api/static",
    #     "specs_route": "/api/docs"
    # }

    # 기본 업로드 허용 크기 10MB
    MAX_CONTENT_LENGTH = 1024 * 1024 * 10

    BLOCK_IP_LIST = ['211.249.40.2']
    BLOCK_AGENT_LIST = ['carbon']


class DevelopmentConfig(Config):
    DEBUG = True
    CVE_ROOT_DIR = 'C:\\workspace\\c-project\\api\\src'
    # FILE_ROOT_DIR = 'C:\\fdata'
    PRINT_SQL = True


# class TestingConfig(Config):
#     TESTING = True
#     DB_NAME = 'CVEdb_test'
#     LOG_FILE_PATH = '../log/api.log'


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    PRINT_SQL = False
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    LOG_FILE_PATH = '/var/log/sscve/api.log'


CONFIG = {
    'development': DevelopmentConfig,
    # 'testing': TestingConfig,
    'production': ProductionConfig,
    'default': ProductionConfig
}


if os.environ.get('GOPEN_MOD') == 'development':
    GLOBAL_CONFIG = CONFIG['development']
else:
    GLOBAL_CONFIG = CONFIG['production']
