#This module is part of “Priberam’s TurboParser Entity Tagging”, an open-source version of SUMMA’s Entity Tagging module, made on top of TurboParser.
#Copyright 2018 by PRIBERAM INFORMÁTICA, S.A. - www.priberam.com
#You have access to this product in the scope of Project "SUMMA - Project Scalable Understanding of Multilingual Media", Project Number 688139, H2020-ICT-2015.
#Usage subject to The terms & Conditions of the "Priberam TurboParser Entity Tagging OS Software License" available at https://www.priberam.pt/docs/Priberam_TurboParser_Entity_Tagging_OS_Software_License.pdf

#Import the modules
#WEB SERVER: FLASK
from flask import Flask, jsonify, abort, make_response, request, render_template, flash, redirect
from flask_cors import CORS, cross_origin
#WEB SERVER: TORNADO
from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
#WEB SERVER: FALCON
#import falcon
#WEB SERVER: WAITRESS
#if os.name == 'nt':
#    from waitress import serve
#GEVENT
from gevent.pywsgi import WSGIServer
from gevent import monkey
# need to patch sockets to make requests async
monkey.patch_all()
from wtforms import Form, TextField, TextAreaField, BooleanField, StringField, SubmitField, PasswordField, validators
import requests
import json
import time
import argparse
from collections import defaultdict, Counter
import sys
import os 
import pprint
from multiprocessing import cpu_count

can_fork = hasattr(os, "fork")

default_headers = {"Content-Type": "application/json", 
                   "Access-Control-Allow-Origin" :"*",
                   "Access-Control-Allow-Methods":"GET,PUT,POST,DELETE" ,
                   "Access-Control-Allow-Headers":"Content-Type"} 

argparser = argparse.ArgumentParser()
argparser.add_argument("-tp", "--turboparser_path", help="Path to turbo parser data/config folder")
argparser.add_argument("-r" , "--route", help="Route for this webservice", default = "/edl_webservice/api")
argparser.add_argument("-p" , "--port", help="Port to listen to future connections", default = 5000)
argparser.add_argument("-v" , "--verbose", help="Verbose Option")
scriptargs = argparser.parse_args()

current_version = "/v2.0"
latest_supported_version="/v2.0"

def relaxed_url_get(url, max_tries=10, headers=default_headers,secs_between_calls=1):
    # requests max_tries option is not ok since it does not have sleep option
    remaining_tries = max_tries
    while remaining_tries > 0:
        try:
            return requests.get(url, headers)
        except:
            time.sleep(secs_between_calls)
        remaining_tries -= 1
    raise Exception("Timed-out connection to " + url + " service ...")

#FLASK
app = Flask(__name__)
CORS(app)

#FLASK & TORNADO-compatible
class LoggingMiddleware(object):
    def __init__(self, app):
        self._app = app

    def __call__(self, environ, resp):
        errorlog = environ['wsgi.errors']
        pprint.pprint(('REQUEST', environ["HTTP_HOST"], environ["REMOTE_ADDR"], environ["REQUEST_METHOD"], environ["PATH_INFO"], environ["QUERY_STRING"]), stream=errorlog)

        def log_response(status, headers, *args):
            pprint.pprint(('RESPONSE', status #, headers
                           ), stream=errorlog)
            return resp(status, headers, *args)

        return self._app(environ, log_response)

def validate_and_get_args(request, 
                          arguments):
    if request.method == 'OPTIONS':
        r = make_response("")         #or make_response("", 200)
        for key, value in default_headers.items():
            r.headers.add(key, value)
        return r, 200                 #or return r
    if request.method == 'POST':        
        #request body
        #************************************************************************
        #------------------------------- BODY -----------------------------------
        #************************************************************************
        if not request.json:
            request.get_json(force=True) #force to get the payload as JSON
        arguments["doc_content"]=request.json
        if not 'body' in arguments["doc_content"]:
            return make_response(jsonify({'error': 'No field called \'body\' was found in the json'}), 400)
        #************************************************************************


        #request arguments
        #************************************************************************
        #----------------------------- NER MODEL --------------------------------
        #************************************************************************  
        ner_model = request.args.get('ner',default=None)     
        if ner_model == None or ner_model == "":
            return make_response(jsonify({'error': 'Missing request argument \'ner\' model'}), 400)
        arguments["ner_model"]=ner_model
        #************************************************************************

    
        #************************************************************************  
        #----------------------------- EL_MODULE --------------------------------   
        #************************************************************************
        el_module = request.args.get('el_module',default=None)       
        if el_module == None or el_module  == "":
            return make_response(jsonify({'error': 'Missing request argument \'el_module\''}), 400)
        arguments["el_module"]=el_module
        #************************************************************************
    return None

from TurboTextAnalysisServer import TurboTextAnalysisServer, ExtractSentencesSink

available_modules = []
modules_per_language={'en':['SmallWiki_EN', 'FullWiki_EN']}
ner_models_per_module={'SmallWiki_EN':['turboparser'], 'FullWiki_EN':['turboparser']}
language_of_a_module={'SmallWiki_EN':'en', 'FullWiki_EN':'en'}
valid_languages_turboparser = ['en']

#load TurboParser
print('Loading Turbo Parser...')
tppath = ""
if(not scriptargs.turboparser_path):
    tppath = os.path.join('C:\\','Projects','TurboTextAnalysis', 'Data')
    tppath = tppath + os.sep
else:
    tppath = scriptargs.turboparser_path
turbo_server = TurboTextAnalysisServer(tppath, valid_languages_turboparser)

NER_tag_mapping={
 "PER":"people"
,"ORG":"organization"
,"GPE":"places"
,"LOC":"places"
,"FAC":"places"
,"humanworks":"other"
,"humangroup":"other"
,"disciplines":"other"
}


@app.route(scriptargs.route + current_version +'/do-edl-document', methods=['OPTIONS', 'POST'])
def ner_document__route():
    print("NEW REQUEST")
    arguments = {}
    retval = validate_and_get_args(request,arguments)
    if retval != None:
        return retval 
    ner_model = arguments["ner_model"]
    el_module=arguments["el_module"]

    language = language_of_a_module[el_module]

    doc_content=arguments["doc_content"]
    response_dict = ner_document__core(ner_model, language, doc_content)

    response = jsonify(response_dict)
    for key, value in default_headers.items():
        response.headers.add(key, value)
    print("FINISH")       
    return response

def ner_document__core(ner_model, language, doc_content):
    title =doc_content["title"] 
    body = doc_content["body"]

    mentions = []
    coref_chains = []
            
    if ner_model == "turboparser":
        turbo_server.obtain_mentions(language=language,
                                     text = body,
                                     mentions = mentions)  
    else:   
        return make_response(jsonify({'error': 'Invalid ner tool argument. Choose between /available-modules output.'}),400)
        
    #print("PARSE -------- ",body, mentions)

    for mention in mentions:
        if mention["ner_tag"] in NER_tag_mapping:
            mention["ner_tag"] = NER_tag_mapping[ mention["ner_tag"] ]
        else:
            mention["ner_tag"] = mention["ner_tag"]

    mentions_web_response = []
    if len(mentions) > 0:
        el_disambiguation = []

        for mention in mentions:
            empty_obj = {}
            empty_obj["kbid"] = mention["mention"]
            empty_obj["name"] = mention["mention"]
            el_disambiguation.append(empty_obj)

        for mention_surface, mention_disambiguation in zip(mentions, el_disambiguation):
            mention = {}
            mention["mention_surface"] = mention_surface["mention"]
            mention["ner_tag"] = mention_surface["ner_tag"]
            mention["ner_type"] = mention_surface["ner_type"]
            if "sentence_id" in mention_surface:
                mention["sentence_id"] = mention_surface["sentence_id"]
            if "sentence_offset" in mention_surface:
                mention["sentence_offset"] = mention_surface["sentence_offset"]
            mention["total_offset"] = mention_surface["total_offset"]
            mention["length"] = mention_surface["length"]
            mention["freebase_mid"] = mention_disambiguation["kbid"]
            mention["entity_name"] = mention_disambiguation["name"]
            mention["wikipedia"] = ""
            mentions_web_response.append(mention)
        
    response_dict = {}
    response_dict["mentions"] = mentions_web_response
    if len(coref_chains) > 0:
        response_dict["coref"] = coref_chains 
    return response_dict
    response = jsonify(response_dict)
    for key, value in default_headers.items():
        response.headers.add(key, value)
    print("FINISH")       
    return response
    


if __name__ == '__main__':
    app.wsgi_app = LoggingMiddleware(app.wsgi_app)    
    #app.run(debug=True,
    #        host='0.0.0.0',
    #        port=scriptargs.port,
    #        threaded=True,
    #        #threaded= (True if can_fork == False else False),processes =
    #        #(cpu_count() if can_fork else 1),
    #        use_reloader=False)

    ###TORNADO
    ##http_server = HTTPServer(WSGIContainer(app))
    ##http_server.listen(scriptargs.port)
    ##IOLoop.current().start()

    #GEVENT
    print("Start gevent WSGI server")
    # use gevent WSGI server instead of the Flask
    http = WSGIServer(('', scriptargs.port), app.wsgi_app)
    # TODO gracefully handle shutdown
    http.serve_forever()