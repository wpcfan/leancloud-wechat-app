# coding: utf-8
import hashlib
import os
import sys
from datetime import datetime

import leancloud
import requests
from flask import Flask, jsonify, request
from flask_sockets import Sockets
from leancloud import LeanCloudError
from weixin import Weixin

from views.todos import todos_view

app = Flask(__name__)
sockets = Sockets(app)

# routing
app.register_blueprint(todos_view, url_prefix='/todos')
weixin = Weixin()
weixin.init_app(app)


@app.route('/time')
def time():
    return str(datetime.now())


@app.route('/version')
def print_version():
    import sys
    return sys.version


@sockets.route('/echo')
def echo_socket(ws):
    while True:
        message = ws.receive()
        ws.send(message)


# REST API example
class BadGateway(Exception):
    status_code = 502

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_json(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return jsonify(rv)


class BadRequest(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_json(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return jsonify(rv)


@app.errorhandler(BadGateway)
def handle_bad_gateway(error):
    response = error.to_json()
    response.status_code = error.status_code
    return response


@app.errorhandler(BadRequest)
def handle_bad_request(error):
    response = error.to_json()
    response.status_code = error.status_code
    return response


@app.route('/api/python-version', methods=['GET'])
def python_version():
    return jsonify({"python-version": sys.version})


@app.route('/api/todos', methods=['GET', 'POST'])
def todos():
    if request.method == 'GET':
        try:
            todo_list = leancloud.Query(leancloud.Object.extend(
                'Todo')).descending('createdAt').find()
        except LeanCloudError as e:
            if e.code == 101:  # Class does not exist on the cloud.
                return jsonify([])
            else:
                raise BadGateway(e.error, e.code)
        else:
            return jsonify([todo.dump() for todo in todo_list])
    elif request.method == 'POST':
        try:
            content = request.get_json()['content']
        except KeyError:
            raise BadRequest(
                '''receives malformed POST content (proper schema: '{"content": "TODO CONTENT"}')''')
        todo = leancloud.Object.extend('Todo')()
        todo.set('content', content)
        try:
            todo.save()
        except LeanCloudError as e:
            raise BadGateway(e.error, e.code)
        else:
            return jsonify(success=True)


def check_signature(signature, token, timestamp, nonce):
    tmp_list = [token, timestamp, nonce]
    tmp_list.sort()
    tmp_str = ''.join(tmp_list)
    tmp_str = hashlib.sha1(tmp_str.encode('utf-8')).hexdigest()
    return tmp_str == signature


@app.route('/wechat/validate', methods=['GET'])
def validate():
    signature = request.args.get('signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')
    echostr = request.args.get('echostr', '')
    token = os.environ['WEIXIN_TOKEN']
    if not signature or not timestamp or not nonce or not echostr:
        return 'invalid', 400

    if not check_signature(signature, token, timestamp, nonce):
        return 'invalid', 400

    return echostr


def get_access_token(app_id, app_secret):
    url = 'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=%s&secret=%s' % (
        app_id, app_secret)
    r = requests.get(url)
    if r.status_code != 200:
        return None
    return r.json().get('access_token')


@app.route('/wechat/access_token', methods=['GET'])
def access_token():
    app_id = os.environ['WEIXIN_APP_ID']
    app_secret = os.environ['WEIXIN_APP_SECRET']
    return get_access_token(app_id, app_secret)


app.add_url_rule("/", view_func=weixin.view_func)
