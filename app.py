# coding: utf-8
import os
import sys
from datetime import datetime

import leancloud
from flask import Flask, jsonify, request
from flask_sockets import Sockets
from leancloud import LeanCloudError
from wechatpy import create_reply, parse_message
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.replies import ArticlesReply
from wechatpy.utils import check_signature

from views.todos import todos_view

# 处理异常情况或忽略

app = Flask(__name__)
sockets = Sockets(app)
# routing
app.register_blueprint(todos_view, url_prefix='/todos')


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


@app.route('/', methods=['GET'])
def msg_validate():
    signature = request.args.get('signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')
    echostr = request.args.get('echostr', '')
    token = os.environ.get('WEIXIN_TOKEN')
    print("signature: %s, timestamp: %s, nonce: %s, echostr: %s, token: %s" % (
        signature, timestamp, nonce, echostr, token))
    try:
        check_signature(token, signature, timestamp, nonce)
    except InvalidSignatureException:
        return 'Invalid signature'
    return echostr


@app.route('/', methods=['POST'])
def msg_reply():
    signature = request.args.get('signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')
    token = os.environ.get('WEIXIN_TOKEN')
    try:
        check_signature(token, signature, timestamp, nonce)
    except InvalidSignatureException:
        return 'Invalid signature'
    msg = parse_message(request.data)
    if msg.type == 'text':
        if msg._data['Content'] == 'hello':
            reply = ArticlesReply(message=msg, articles=[
                {
                    'title': u'标题1',
                    'description': u'描述1',
                    'url': u'http://www.qq.com',
                    'image': 'http://img.qq.com/1.png',
                },
                {
                    'title': u'标题2',
                    'description': u'描述2',
                    'url': u'http://www.qq.com',
                    'image': 'http://img.qq.com/1.png',
                },
            ])
        else:
            reply = create_reply(msg.content, msg)
    else:
        reply = create_reply('Sorry, can not handle this for now', msg)
    return reply.render()
