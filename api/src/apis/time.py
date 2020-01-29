# coding=utf-8

from flask_restful import Resource

from util import make_response, use_db, use_p


class Time(Resource):
    MAIN_CLASS = True

    def __init__(self):
        self.db = use_db()
        self.p = use_p()

    def get(self):
        """
        시간
        ---
        tags:
          - Time
        responses:
          200:
            description: 서버 기준 시간 반환
            schema:
              id: Time
              type: object
              properties:
                status:
                  type: integer
                  default: 결과코드
                list:
                  type: array
                  items:
                    type: object
                    properties:
                      nowEpoch:
                        type: integer
                        default: 서버 기준 시간 Epoch초
        """
        bind_param = []

        sql = """\
SELECT date_part('epoch', now()) AS now_epoch;
"""

        return make_response(200, self.db.query(sql, bind_param))
