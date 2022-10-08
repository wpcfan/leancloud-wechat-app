# coding: utf-8
import os
from io import BytesIO

import leancloud
from flask import Flask, jsonify, request
from flask_sockets import Sockets
from leancloud import LeanCloudError
from wechatpy import WeChatClient, create_reply, parse_message
from wechatpy.client import WeChatClient
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.replies import ArticlesReply
from wechatpy.utils import check_signature

from views.articles import articles_view

# 处理异常情况或忽略

app = Flask(__name__)
sockets = Sockets(app)
# routing
app.register_blueprint(articles_view, url_prefix='/articles')
client = WeChatClient(os.environ.get('WEIXIN_APP_ID'),
                      os.environ.get('WEIXIN_APP_SECRET'))


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


ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/api/assets', methods=['POST'])
def add_asset():
    # check if the post request has the file part
    if 'file' not in request.files:
        resp = jsonify({'message': 'No file part in the request'})
        resp.status_code = 400
        return resp
    file = request.files['file']
    if file.filename == '':
        resp = jsonify({'message': 'No file selected for uploading'})
        resp.status_code = 400
        return resp
    if file and allowed_file(file.filename):
        fileContent = file.read()
        fileObj = BytesIO(fileContent)

        title = request.form['title']
        introduction = request.form['introduction']
        media_type = request.form['media_type']

        res = client.material.add(
            media_type=media_type,
            media_file=fileObj,
            title=title,
            introduction=introduction)
        print("res: ", res)
        resp = jsonify({'message': 'File successfully uploaded'})
        resp.status_code = 201
        return resp
    else:
        resp = jsonify(
            {'message': 'Allowed file types are txt, pdf, png, jpg, jpeg, gif'})
        resp.status_code = 400
        return resp


@app.route('/api/assets', methods=['GET'])
def get_assets():
    try:
        asset_list = leancloud.Query(leancloud.Object.extend(
            'Asset')).descending('createdAt').find()
    except LeanCloudError as e:
        if e.code == 101:  # Class does not exist on the cloud.
            return jsonify([])
        else:
            raise BadGateway(e.error, e.code)
    else:
        return jsonify([article.dump() for article in asset_list])


@app.route('/api/articles', methods=['POST'])
def add_article():
    try:
        title = request.json['title']
        description = request.json['description']
        url = request.json['url']
        image = request.json['image']
        keywords = request.json['keywords']
    except KeyError:
        raise BadRequest(
            '''receives malformed POST title (proper schema: '
            {
                "title": "ARTICLE TITLE", 
                "description": "ARTICLE DESCRIPTION",
                "url": "ARTICLE URL",
                "image": "ARTICLE IMAGE URL",
                "keywords": "ARTICLE KEYWORDS"
            }
            ')''')
    mappedKeywords = map(lambda keyword: keyword.lower(), keywords)
    article = leancloud.Object.extend('Article')()
    article.set('title', title)
    article.set('description', description)
    article.set('url', url)
    article.set('image', image)
    article.set('keywords', list(mappedKeywords))
    try:
        article.save()
    except LeanCloudError as e:
        raise BadGateway(e.error, e.code)
    else:
        return jsonify(success=True)


@app.route('/api/articles', methods=['GET'])
def get_articles():
    try:
        article_list = leancloud.Query(leancloud.Object.extend(
            'Article')).descending('createdAt').find()
    except LeanCloudError as e:
        if e.code == 101:  # Class does not exist on the cloud.
            return jsonify([])
        else:
            raise BadGateway(e.error, e.code)
    else:
        return jsonify([article.dump() for article in article_list])


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
    print("msg: ", msg)
    if msg.type == 'text' and msg.content is not None:
        query = leancloud.Query(leancloud.Object.extend(
            'Article')).descending('createdAt')
        query.contains('keywords', msg.content.lower())
        article_list = query.find()
        if len(article_list) > 0:
            reply = ArticlesReply(message=msg, articles=article_list)
        else:
            reply = create_reply(msg.content, msg)
    elif msg.type == 'event':
        if msg.event == 'subscribe':
            # 关注事件

            reply = create_reply('欢迎关注', msg)
        elif msg.event == 'unsubscribe':
            print("取消关注 %s" % msg.source)
            return 'success'
        elif msg.event == 'subscribe_scan':
            # 未关注用户扫描带参数二维码事件
            print("未关注用户扫描带参数二维码事件 msg", msg)
        elif msg.event == 'scan':
            # 已关注用户扫描带参数二维码事件
            print("已关注用户扫描带参数二维码事件 msg", msg)
        elif msg.event == 'location':
            # 上报地理位置事件
            print("上报地理位置事件 msg", msg)
        elif msg.event == 'click':
            # 自定义菜单事件
            print("自定义菜单事件 msg", msg)
        elif msg.event == 'view':
            # 点击菜单跳转链接时的事件推送
            print("点击菜单跳转链接时的事件推送 msg", msg)
        elif msg.event == 'masssendjobfinish':
            # 群发消息完成事件
            print("群发消息完成事件 msg", msg)
        elif msg.event == 'templatesendjobfinish':
            # 模板消息发送任务完成事件
            print("模板消息发送任务完成事件 msg", msg)
        elif msg.event == 'scancode_push':
            # 扫码推事件的事件推送
            print("扫码推事件的事件推送 msg", msg)
        elif msg.event == 'scancode_waitmsg':
            # 扫码推事件且弹出“消息接收中”提示框的事件推送
            print("扫码推事件且弹出“消息接收中”提示框的事件推送 msg", msg)
        elif msg.event == 'pic_sysphoto':
            # 弹出系统拍照发图的事件推送
            print("弹出系统拍照发图的事件推送 msg", msg)
        elif msg.event == 'pic_photo_or_album':
            # 弹出拍照或者相册发图的事件推送
            print("弹出拍照或者相册发图的事件推送 msg", msg)
        elif msg.event == 'pic_weixin':
            # 弹出微信相册发图器的事件推送
            print("弹出微信相册发图器的事件推送 msg", msg)
        elif msg.event == 'location_select':
            # 弹出地理位置选择器的事件推送
            print("弹出地理位置选择器的事件推送 msg", msg)
        elif msg.event == 'user_scan_product':
            # 用户扫描商品事件
            print("用户扫描商品事件 msg", msg)
        elif msg.event == 'user_scan_product_enter_session':
            # 用户进入商品详情事件
            print("用户扫描商品进入公众号事件 msg", msg)
        elif msg.event == 'user_scan_product_async':
            # 地理位置信息异步推送事件
            print("地理位置信息异步推送事件 msg", msg)
        elif msg.event == 'user_scan_product_verify_action':
            # 商品审核结果事件
            print("商品审核结果事件 msg", msg)
        elif msg.event == 'subscribe_scan_product':
            # 用户扫描商品关注公众号事件
            print("用户扫描商品关注公众号事件 msg", msg)
        elif msg.event == 'user_authorize_invoice':
            # 用户授权开票事件
            print("用户授权开票事件 msg", msg)
        elif msg.event == 'update_invoice_status':
            # 更新发票状态事件
            print("更新发票状态事件 msg", msg)
        elif msg.event == 'submit_invoice_title':
            # 用户提交发票抬头事件
            print("用户提交发票抬头事件 msg", msg)
        else:
            reply = create_reply('收到事件推送', msg)
    else:
        reply = create_reply('Sorry, can not handle this for now', msg)
    return reply.render()
