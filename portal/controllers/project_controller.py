#!/usr/bin/env python2

from flask import Blueprint, Flask, render_template, request, abort
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search, Q
from elasticsearch_dsl.query import MoreLikeThis
from models.index_search import IndexSearch

project_controller = Blueprint('projects', __name__, url_prefix='/projects')
client = Elasticsearch()

@project_controller.route('/<int:project_id>')
def show(project_id):
    baseSearch = BaseSearch()

    s = Search(using=client, index="xstane34_projects") \
        .query("match", id=project_id)
    response = s.execute()

    if response.success() == False or response.hits.total == 0:
        abort(404)

    project = response.hits[0]

    similar_search = Search(using=client, index="xstane34_projects") #{'_id': project.id, '_index': 'xstane34_projects'}
    similar_search = similar_search.query(MoreLikeThis(like={'_id': project.id, '_index': 'xstane34_projects'}))
    similar_response = similar_search.execute()


    return render_template('projects/show.html',
                           layout_data=baseSearch.layout_data,
                           project=project,
                           similar_projects=similar_response[:3]
                           )