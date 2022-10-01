# coding: utf-8

from flask import Blueprint, redirect, render_template, request, url_for
from leancloud import LeanCloudError, Object, Query


class Article(Object):
    pass


articles_view = Blueprint('articles', __name__)


@articles_view.route('')
def show():
    try:
        articles = Query(Article).descending('createdAt').find()
    except LeanCloudError as e:
        if e.code == 101:  # Class does not exist on the cloud.
            articles = []
        else:
            raise e
    return render_template('articles.html', articles=articles)


@articles_view.route('', methods=['POST'])
def add():
    title = request.form['title']
    description = request.form['description']
    url = request.form['url']
    image = request.form['image']
    article = Article(title=title, description=description,
                      url=url, image=image)
    try:
        article.save()
    except LeanCloudError as e:
        return e.error, 502
    return redirect(url_for('articles.show'))
