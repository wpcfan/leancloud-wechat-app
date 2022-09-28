# coding: utf-8
import os
import sys
from datetime import datetime

import leancloud
from flask import Flask, jsonify, request
from flask_sockets import Sockets
from leancloud import LeanCloudError
from weixin import WeixinMsg

from views.todos import todos_view

app = Flask(__name__)
sockets = Sockets(app)
app.config.from_object(dict(
    WEIXIN_APP_ID=os.environ.get('WEIXIN_APP_ID'),
    WEIXIN_APP_SECRET=os.environ.get('WEIXIN_APP_SECRET'),
    WEIXIN_TOKEN=os.environ.get('WEIXIN_TOKEN'),))
# routing
app.register_blueprint(todos_view, url_prefix='/todos')

msg = WeixinMsg(os.environ.get('WEIXIN_TOKEN'))


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


@app.route('/wechat/access_token', methods=['GET'])
def access_token():
    return msg.access_token


app.add_url_rule("/", view_func=msg.view_func)


@msg.all
def all(**kwargs):
    """
    监听所有没有更特殊的事件
    """
    return msg.reply(kwargs['sender'], sender=kwargs['receiver'], content='all')


@msg.text()
def hello(**kwargs):
    """
    监听所有文本消息
    """
    return "hello too"


@msg.text("help")
def world(**kwargs):
    """
    监听help消息
    """
    return dict(content="hello world!")


@msg.subscribe
def subscribe(**kwargs):
    """
    监听订阅消息
    """
    print(kwargs)
    return "欢迎订阅我们的公众号"
