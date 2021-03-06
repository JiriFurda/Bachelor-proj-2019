#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#---------------------------------------------------------------------------#
#-----------------             BAKALÁŘSKÁ PRÁCE            -----------------#
#----------------- Aktualizace portálu evropských projektů -----------------#
#-----------------     a jeho rozšíření o identifikaci     -----------------#
#-----------------     výsledků, souvisejících s tématy    -----------------#
#-----------------          nově vypisovaných výzev        -----------------#
#-----------------              FIT VUT v Brně             -----------------#
#----------------- Autor: Jiří Furda (2018-2019)           -----------------#
#----------------- Vedoucí: Doc. RNDr. Pavel Smrž, Ph.D.   -----------------#
#----------------------- Poslední úpravy: 13.5.2019 ------------------------#
#--- Soubor: index_search.py                                  Verze: 1.0 ---#
#-------- http://knot.fit.vutbr.cz/wiki/index.php/rrs_eu_projects14 --------#
#--------------------- Licence: BUT Open source licence --------------------#
#---------------------------------------------------------------------------#


from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search, Q
from flask import request
from models.facet import Facet
from flask_paginate import Pagination, get_page_args
import copy, json


# Create Elasticsearch client instance
client = Elasticsearch()


class IndexSearch:
    ''' Class used for simpler creating Elasticsearch search queries '''
    def __init__(self, index, highlight, fields):
        # Process parameters
        self.index = index
        self.highlight = highlight
        self.fields = fields

        # Set default values
        self.per_page = 10
        self.page = 1

        # Prepare queries
        self.search_raw = self.buildSearch()    # Raw query
        self.search = self.buildAggregationsSearch()  # Query with facets aggregations

        # Initialize empty result data
        self.response = None
        self.layout_data = None
        self.pagination = None


    def execute(self):
        ''' Executes search '''
        self.response = self.search.execute()
        self.layout_data = self.prepareLayoutData()
        self.pagination = Pagination(page=self.page,
                                     per_page=self.per_page,
                                     total=self.response.hits.total,
                                     css_framework='bootstrap4')


    def buildSearch(self):
        ''' Builds raw query '''

        # Init Elasticsearch search instance
        es_search = Search(using=client, index=self.index)
        es_search = es_search.highlight(self.highlight)


        # Prepare query string
        if request.args.has_key('query') and request.args.get('query') != '':
            query = request.args.get('query')
        else:
            query = '*'

        # Add query string to the search query
        query_string_query = Q('query_string', query=query, fields=self.fields)

        # Apply filters to the query
        filters_query = IndexSearch.getFiltersQuery()
        es_search = es_search.query('bool', must=[query_string_query, filters_query])

        # Sort by last update if no search was executed
        if query == '*' and self.getSearchType() in ['projects', 'deliverables']:
            es_search = es_search.sort({
                'lastUpdate.keyword':
                    {
                        'order': 'desc',
                        'unmapped_type': 'keyword' # Do not fail in case of missing value
                    }
            })

        es_search = self.preparePagination(es_search)

        return es_search


    def preparePagination(self, es_search):
        ''' Prepares query for pagination '''
        self.page, self.per_page, offset = get_page_args(page_parameter='page',
                                               per_page_parameter='per_page')
        paginate_from = (self.page - 1) * self.per_page
        paginate_to = paginate_from + self.per_page
        es_search = es_search[paginate_from:paginate_to]  # @todo Change to scan API becuase of large amount of data

        return es_search


    @staticmethod
    def getFiltersQuery():
        ''' Apply used filters to the search query '''
        filter_queries = []

        # Loop through every GET argument
        for arg_name, arg_value in request.args.iteritems(True):
            facet = Facet.get(arg_name)
            if facet is not None: # If argument name corresponds to a facet
                facet_values = json.loads(arg_value)
                facet_name = facet.underscoreField()

                # Process every value of the current facet
                value_queries = []
                for facet_value in facet_values:
                    value_queries.append(Q('match', **{facet_name: facet_value['value']}))

                # Create OR query between these values
                filter_queries.append(Q('bool', should=value_queries))

        return Q('bool', must=filter_queries)


    def buildAggregationsSearch(self):
        ''' Build new search query including aggregations '''
        es_search = copy.copy(self.search_raw)

        # Append every existing facet
        facets = Facet.all()
        for facet in facets:
            es_search.aggs.bucket(facet.name, 'terms', field=facet.field, size=6)

        return es_search


    def prepareLayoutData(self):
        ''' Prepare data for Vue.js components '''
        facets = Facet.all()

        # Loop through every existing facet
        vue_facets = ''
        for facet in facets:
            facet_dict = facet.toDict()

            # Parse Elasticsearch aggreagation data
            aggregation = eval('self.response.aggregations.' + facet.name).buckets
            option_list = []
            for option in aggregation:
                option_list.append({
                    'value': option.key,
                    'text': option.key,
                    'count': option.doc_count,
                })
            facet_dict.update({'mostFrequentOptions': option_list})

            # Parse checked options in GET arguments
            checkedOptions = []
            if facet.name in request.args:
                checkedOptions = json.loads(request.args.get(facet.name))

            # Update the options count to correspond with current search
            for k, checkedOption in enumerate(checkedOptions):
                count = 0
                for option in option_list:
                    if option['value'] == checkedOption['value']:
                        count = option['count']

                checkedOptions[k]['count'] = count

            # Sort checked options from highest
            checkedOptions.sort(key=lambda x: x['count'], reverse=True)

            facet_dict.update({'checkedOptions': checkedOptions})

            vue_facets += json.dumps(facet_dict)
            vue_facets += ','

        # Update created string to be valid JSON
        vue_facets = '[' + vue_facets[:-1] + ']'

        # Convert current Elasticsearch query to JSON
        vue_elastic_search = json.dumps(self.search_raw.to_dict())

        # Create result dict
        result = {
            'vue_facets': vue_facets,
            'vue_elastic_search': vue_elastic_search,
            'get_arguments': request.args
        }

        return result


    @staticmethod
    def createForIndex(index):
        ''' Creates predefined IndexSearch '''
        if index == 'projects':
            return IndexSearch('xstane34_projects',
                              'objective',
                              ['acronym^6', 'title^5', 'objective^3', 'fundedUnder.subprogramme^2', 'website.origWeb'])

        if index == 'deliverables':
            return IndexSearch('xstane34_deliverables',
                              'deliv.plainText',
                              ['deliv.sourceInfo.title^3', 'deliv.plainText'])

        if index == 'topics':
            return IndexSearch('xfurda00_topics',
                              'description',
                              ['identifier^6', 'title^5', 'tags^3', 'description'])

        return None


    @staticmethod
    def getSearchType():
        ''' Findout type of current search from the GET arguments '''
        if request.args.get('type') == 'deliverables' or request.args.get('type') == 'topics':
            return request.args.get('type')

        return 'projects'


    # Mass action methods
    @staticmethod
    def createForEveryIndex():
        ''' Creates predefined IndexSearch for every available search type '''
        return {
            'projects': IndexSearch.createForIndex('projects'),
            'deliverables': IndexSearch.createForIndex('deliverables'),
            'topics': IndexSearch.createForIndex('topics')
        }


    @staticmethod
    def executeMany(searches):
        ''' Executes every IndexSearch given '''
        for (name, search) in searches.items():
            search.execute()