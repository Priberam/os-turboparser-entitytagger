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
# #GEVENT
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
from sortedcontainers import SortedDict
import sys
import os 
import pprint
from multiprocessing import cpu_count
#NEW VERSION DEV#from EntityDiscoveryLinkingPythonCli import ner_document__core


can_fork = hasattr(os, "fork")

default_headers = {"Content-Type": "application/json", 
                   "Access-Control-Allow-Origin" :"*",
                   "Access-Control-Allow-Methods":"GET,PUT,POST,DELETE" ,
                   "Access-Control-Allow-Headers":"Content-Type"} 

argparser = argparse.ArgumentParser()
argparser.add_argument("-ts", "--el_ts", help="Seconds between EL api layer service first call retries", type=int, default = 3)
argparser.add_argument("-ne", "--el_ns", help="Number of EL api layer service first call retries", type=int, default = 10)
argparser.add_argument("-u", "--url", help="URL of the other ETL layer", default = "http://localhost:5002/edl_webservice/api/v2.0/")
argparser.add_argument("-r", "--route", help="Route for this webservice", default = "/EntityTagging/api")
argparser.add_argument("-p", "--port", help="Port to listen to future connections", default = 5001)
argparser.add_argument("-v", "--verbose", help="Verbose Option")
scriptargs = argparser.parse_args()

current_version = "/v3.0"
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
                          call,
                          version,
                          arguments):
    if request.method == 'OPTIONS':
        r = make_response("", 200)
        for key, value in default_headers.items():
            r.headers.add(key, value)
        return r
    if request.method == 'POST':    
        #request body
        #************************************************************************
        #------------------------------- BODY -----------------------------------
        #************************************************************************
        if not request.json:
            request.get_json(force=True) #force to get the payload as JSON

        if call=="processDocument":
            if version == "/v2.0":
                document_json = request.json
                if not 'instances' in document_json:
                    return make_response(jsonify({'error': 'No field called instances was found in the json'}), 400)
                document_instances = document_json["instances"]
                if len(document_instances) < 1:
                    return make_response(jsonify({'error': 'Field instances has no instance'}), 400)

                if not 'id' in document_json:
                    return make_response(jsonify({'error': 'No field called id was found in the json'}), 400)
                document_id = document_json["id"]
                arguments["document_id"] = document_id
                if not 'metadata' in document_instances[0]:
                    return make_response(jsonify({'error': 'No field called metadata was found in the json instances field'}), 400)
                metadata = document_instances[0]["metadata"]
                if not 'originalLanguage' in metadata:
                    return make_response(jsonify({'error': 'No field called originalLanguage was found in the json metadata field'}), 400)
                originalLanguage = metadata["originalLanguage"]
      
                use_native = True
                use_default_en = False
                if originalLanguage in native_langs:
                    if originalLanguage in modules_per_language:
                        use_native = True
                        use_default_en = False
                    else:
                        use_native = False
                        use_default_en = True
                else:
                    use_native = False
                    use_default_en = True
            
                edl_input_json = {}    
                language = ""
                for document_instance in document_instances:
                    if not 'metadata' in document_instance:
                        return make_response(jsonify({'error': 'No field called metadata was found in the json instances field'}), 400)
                    if not 'language' in metadata:
                        return make_response(jsonify({'error': 'No field called language was found in the json metadata field'}), 400)
                    language = metadata["language"]
                    if not ((use_default_en and language == "en") or (use_native and language == originalLanguage)):
                        continue
                    else:            
                        edl_input_json = {}
                        edl_input_json["body"] = document_instance["body"]
                        edl_input_json["title"] = document_instance["title"]
                        break
                if len(edl_input_json) == 0:
                    if use_default_en:
                        return make_response(jsonify({'error': 'No english document instance was found'}), 400)
                    if use_native:
                        return make_response(jsonify({'error': 'No originalLanguage document instance was found'}), 400)
 
                arguments["language"] = language

                arguments["doc_content"]={}
                arguments["doc_content"]["title"]=edl_input_json["title"]
                arguments["doc_content"]["body"]=edl_input_json["body"]
                arguments["doc_aux"] = {}
            elif version == "/v3.0":   
                new_document={}
                new_document["title"]=""
                new_document["body"]=""       
                new_doc_aux={}    
                new_doc_aux["offsets_title_mapping"]=SortedDict()
                new_doc_aux["offsets_body_mapping"]=SortedDict()
                for index, chunk in enumerate(request.json):
                    if "text" not in chunk:
                        continue
                    disable_title=True
                    if (not disable_title) and "type" in chunk and chunk["type"]=="title":
                        if new_document["title"] !="":
                            new_document["title"]+="\n\n"

                        new_doc_aux["offsets_title_mapping"][len(new_document["title"])] = index #{"chunk":index, "offset":0}
                        new_document["title"]+=chunk["text"]
                    else:
                        if new_document["body"] !="":
                            new_document["body"]+="\n\n"

                        new_doc_aux["offsets_body_mapping"][len(new_document["body"])] = index #{"chunk":index, "offset":0}
                        new_document["body"]+=chunk["text"]
                arguments["doc_content"] = new_document
                arguments["doc_aux"] = new_doc_aux   
            else:
                return make_response(jsonify({'error': 'API version ' + version + ' not recognized'}), 400)  
        elif call=="processRelatedDocuments":
            arguments["document_id"]={}
            arguments["document_id"]["documents"]=[]
            arguments["doc_content"] = {}
            arguments["doc_content"]["documents"]=[]
            arguments["doc_aux"] = {}
            arguments["doc_aux"]["documents"]=[]
            documents_json = request.json
            if version == "/v2.0":
                if not 'documents' in documents_json:
                    return make_response(jsonify({'error': 'No field called documents was found in the json'}), 400)
                documents = documents_json["documents"]
                if len(documents) < 1:
                    return make_response(jsonify({'error': 'Field documents has no document'}), 400)
                for doc_index, document in enumerate(documents):


                    if not 'instances' in document:
                        return make_response(jsonify({'error': 'No field called instances was found in the json'}), 400)
                    document_instances = document["instances"]
                    if len(document_instances) < 1:
                        return make_response(jsonify({'error': 'Field instances has no instance'}), 400)

                    if not 'id' in document:
                        return make_response(jsonify({'error': 'No field called id was found in the json'}), 400)
                    document_id = document["id"]
                    arguments["document_id"] = document_id
                    if not 'metadata' in document_instances[0]:
                        return make_response(jsonify({'error': 'No field called metadata was found in the json instances field'}), 400)
                    metadata = document_instances[0]["metadata"]
                    if not 'originalLanguage' in metadata:
                        return make_response(jsonify({'error': 'No field called originalLanguage was found in the json metadata field'}), 400)
                    originalLanguage = metadata["originalLanguage"]
      
                    use_native = True
                    use_default_en = False
                    if originalLanguage in native_langs:
                        if originalLanguage in modules_per_language:
                            use_native = True
                            use_default_en = False
                        else:
                            use_native = False
                            use_default_en = True
                    else:
                        use_native = False
                        use_default_en = True
            
                    edl_input_json = {}    
                    language = ""
                    for document_instance in document_instances:
                        if not 'metadata' in document_instance:
                            return make_response(jsonify({'error': 'No field called metadata was found in the json instances field'}), 400)
                        if not 'language' in metadata:
                            return make_response(jsonify({'error': 'No field called language was found in the json metadata field'}), 400)
                        language = metadata["language"]
                        if not ((use_default_en and language == "en") or (use_native and language == originalLanguage)):
                            continue
                        else:            
                            edl_input_json = {}
                            edl_input_json["body"] = document_instance["body"]
                            edl_input_json["title"] = document_instance["title"]
                            break
                    if len(edl_input_json) == 0:
                        if use_default_en:
                            return make_response(jsonify({'error': 'No english document instance was found'}), 400)
                        if use_native:
                            return make_response(jsonify({'error': 'No originalLanguage document instance was found'}), 400)
 
                    arguments["doc_content"]["documents"][i]={}
                    arguments["doc_content"]["documents"][i]["title"]=edl_input_json["title"]
                    arguments["doc_content"]["documents"][i]["body"]=edl_input_json["body"]    
                    arguments["doc_aux"]["documents"][i]={}      
                    arguments["doc_aux"]["documents"][i]=document["document_id"]    
                    arguments["language"]["documents"][i] = language
            elif version=="/v3.0":
                for doc_index, document in enumerate(request.json):
                    new_document={}
                    new_document["title"]=""
                    new_document["body"]=""
                    new_doc_aux = {}
                    new_doc_aux["offsets_title_mapping"]=[]
                    new_doc_aux["offsets_body_mapping"]=[]
                    for chunk_index, chunk in enumerate(document):
                        if "text" not in chunk:
                            continue
                        if "type" in chunk and chunk["type"]=="title":
                            if new_document["title"] !="":
                                new_document["title"]+="\n\n"

                            new_doc_aux["offsets_title_mapping"][len(new_document["title"])] = index #{"chunk":index, "offset":0}
                            new_document["title"]+=chunk["text"]
                        else:
                            if new_document["body"] !="":
                                new_document["body"]+="\n\n"

                            new_doc_aux["offsets_body_mapping"][len(new_document["body"])] = index #{"chunk":index, "offset":0}
                            new_document["body"]+=chunk["text"]
                    arguments["doc_content"]["documents"][i] = new_document
                    arguments["doc_aux"]["documents"][i] = new_doc_aux
            else:
                return make_response(jsonify({'error': 'API version ' + version + ' not recognized'}), 400)  
  

        #************************************************************************
  

        #request arguments
        #************************************************************************
        #------------------------------ LANGUAGE --------------------------------
        #************************************************************************
        if call=="processDocument" and version=="/v3.0":
            arguments["language"] = request.args.get('language',default=None)   
        #************************************************************************
        #---------------------------- DOCUMENT_ID -------------------------------
        #************************************************************************
        if call=="processDocument" and version=="/v3.0":
            arguments["document_id"] = request.args.get('document_id',default='0000000001')   

        #************************************************************************

        #************************************************************************
        #----------------------------- NER MODEL --------------------------------
        #************************************************************************
        #arguments["ner_model"] = request.args.get('model',default=None)  
        arguments["ner_model"]="turboparser" 
        #************************************************************************
    
    return None

def Core_processDocument(document_json,
                         language,
                         ner_model,
                         arguments):
    json_request_json = json.dumps(document_json)
    if(scriptargs.verbose):
        print(json.dumps(document_json, sort_keys=True, indent=2))
                
    el_module = ""
    
    if len(modules_per_language[language]) < 1:
        return make_response(jsonify({'error': 'No valid modules for this language: ' + language }), 400)


    el_module = modules_per_language[language][0]
    selected_ner = "turboparser"

    

     #NEW VERSION DEV#arguments["json_response"] = ner_document__core(selected_ner, language, document_json)

    response = requests.post(edl_url + "do-edl-document" 
        + "?" + "ner"               + "=" + selected_ner 
        + "&" + "el_module"         + "=" + el_module, 
        data=json_request_json,
        headers=default_headers)
    if(response.status_code != 200):
        return (response.content, response.status_code, response.headers.items()) 
        #return response
    arguments["json_response"] = response.json()

    #with open("out_tmp_dbg", "w", encoding="utf8") as fo:
    #    fo.write(json.dumps(sorted(arguments["json_response"]["mentions"],
    #    key=lambda x: int(x['total_offset']))))

    #print(arguments["json_response"])
    return None

def aggregate_entities(entities_dict, 
                       document_id, 
                       language, 
                       json_response, 
                       NILcounter,
                       applyEntityLinking,
                       version,
                       doc_aux):
    tokens_to_ents = {} 
    for entity_mention in json_response['mentions']:
        entity_id = entity_mention['freebase_mid']
        entity_name = entity_mention["entity_name"]
        is_nill = ((applyEntityLinking and entity_mention['freebase_mid'][0:3] == "NIL") or \
            ((not applyEntityLinking) and entity_mention['freebase_mid'] == ""))
        is_nill_without_id = is_nill and entity_mention['freebase_mid'] == "NIL"
        if not is_nill_without_id:
            continue
        
        mention_surface_lower = entity_mention["mention_surface"].lower()
        #handling nils
        if mention_surface_lower in tokens_to_ents:
            continue
        else:
            tokens_to_ents[mention_surface_lower] = {}
            tokens_to_ents[mention_surface_lower]["nilcluster"] = None
            tokens_to_ents[mention_surface_lower]["ner_tag"] = entity_mention["ner_tag"]
            subtokens_mention = mention_surface_lower.split(" ")
            at_least_one_match = False
            if len(subtokens_mention) > 1:
                for subtoken_mention in subtokens_mention:
                    if subtoken_mention in tokens_to_ents:
                        at_least_one_match = True
                        if entity_mention["ner_tag"] == tokens_to_ents[subtoken_mention]["ner_tag"]:
                            tokens_to_ents[mention_surface_lower]["nilcluster"] = tokens_to_ents[subtoken_mention]["nilcluster"]
                        else: #if no same ner tag match substring match occurred yet, settle for a different
                              #ner tag substring match
                            if tokens_to_ents[mention_surface_lower]["nilcluster"] == None:
                                tokens_to_ents[mention_surface_lower]["nilcluster"] = tokens_to_ents[subtoken_mention]["nilcluster"]

            if at_least_one_match == False:
                #no match
                NILcounter+=1
                entity_id+=str(NILcounter).zfill(7)
                entity_name = entity_id                
                tokens_to_ents[mention_surface_lower]["nilcluster"] = entity_name
       
    tokens_to_ents_keys = tokens_to_ents.keys()
    for tokens_to_ents_key in tokens_to_ents_keys:
        for key, value in tokens_to_ents.items():
                if tokens_to_ents_key != key and tokens_to_ents_key in key :
                    if value["ner_tag"] == tokens_to_ents[tokens_to_ents_key]["ner_tag"]:
                        tokens_to_ents[tokens_to_ents_key]["nilcluster"] = value["nilcluster"]      


    for entity_mention in json_response['mentions']:
        entity_id = entity_mention['freebase_mid']
        entity_name = entity_mention["entity_name"]
        is_nill = ((applyEntityLinking and entity_mention['freebase_mid'][0:3] == "NIL") or \
            ((not applyEntityLinking) and entity_mention['freebase_mid'] == ""))
        is_nill_without_id = is_nill and entity_mention['freebase_mid'] == "NIL"
        if is_nill_without_id:
            entity_id = tokens_to_ents[entity_mention["mention_surface"].lower()]["nilcluster"]
            entity_name = entity_id
        if entity_id not in entities_dict:
            entities_dict[entity_id] = {}
            entities_dict[entity_id]["entity"] = {}
            entities_dict[entity_id]["entity"]["currlangForm"] = entity_name
            if language == "en" or is_nill :
                entities_dict[entity_id]["entity"]["baseForm"] = entity_name
            else:
                arguments = {}
                retval = get_default_baseform(entity_id, arguments) 
                if retval != None:
                    entities_dict[entity_id]["entity"]["baseForm"] = entity_name
                else:
                    default_baseform_json = arguments["json_response"]
                    entities_dict[entity_id]["entity"]["baseForm"] = default_baseform_json["baseform"]
            entities_dict[entity_id]["entity"]["id"] = entity_id
            entities_dict[entity_id]["mentions"] = []
                        
            #NER type voting scheme
            entities_dict[entity_id]["entity"]["types_counter"] = Counter()
        entities_dict[entity_id]["entity"]["types_counter"][entity_mention["ner_tag"]] += 1

        mention_obj = {}
        mention_obj["ner_type"] = entity_mention["ner_tag"]
        mention_obj["text"] = entity_mention["mention_surface"]
        startPosition = int(entity_mention["total_offset"])
        endPosition = int(entity_mention["total_offset"]) + entity_mention["length"]
        if version== "/v3.0":
            chunks_irange = list(doc_aux['offsets_body_mapping'].irange(maximum=startPosition))
            chunk_offset = chunks_irange[len(chunks_irange)-1]
            chunk_index = doc_aux['offsets_body_mapping'][chunk_offset]

            mention_obj["startPosition"] = {"chunk":chunk_index, "offset": startPosition-chunk_offset}
            mention_obj["endPosition"] ={"chunk":chunk_index, "offset": endPosition-chunk_offset} 
        elif  version== "/v2.0":
            mention_obj["startPosition"] = startPosition
            mention_obj["endPosition"] = endPosition
        mention_obj["souceDocument"] = {}
        mention_obj["souceDocument"]["id"] = document_id
        mention_obj["souceDocument"]["language"] = language
        entities_dict[entity_id]["mentions"].append(mention_obj)
    return NILcounter


def post_process_entities(entities_dict,entities_response):
    for entity in entities_dict.values():
        #select most voted NER type
        cc = sorted(entity["entity"]["types_counter"].most_common(10), key=lambda x: x[0])

        entity["entity"]["type"] = cc[0][0] #entity["entity"]["types_counter"].most_common(1)[0][0]
        #entity["entity"]["candidate_types"] = cc
        del  entity["entity"]["types_counter"]
        entities_response.append(entity)
    return


edl_url = scriptargs.url
 
native_langs = ["en"]
available_modules = []
modules_per_language={'en':['SmallWiki_EN', 'FullWiki_EN']}
ner_models_per_module={'SmallWiki_EN':['turboparser'], 'FullWiki_EN':['turboparser']}



@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

@app.route(scriptargs.route + current_version + '/docs', methods=['OPTIONS', 'GET'])
def docs():
    docs_file = open("docs.json", 'r', encoding='utf-8')
    json_docs = json.loads(docs_file.read())
    response = jsonify(json_docs)
    for key, value in default_headers.items():
        response.headers.add(key, value)
    return response, 200

@app.route(scriptargs.route + current_version + '/', methods=['OPTIONS', 'GET'])
def root():
    return redirect("http://213.63.185.148/Documentation/#_URL_" + \
"http://localhost:"+str(scriptargs.port) + scriptargs.route + "/docs", code=302)

@app.route(scriptargs.route + current_version + '/processDocument', methods=['OPTIONS', 'POST'])
def processDocument(version=current_version):
    print("NEW REQUEST")
    arguments = {}
    retval = validate_and_get_args(request, "processDocument", version, arguments)
    if retval != None:
        return retval 
    language = arguments["language"]
    ner_model = arguments["ner_model"]   
    document_id = arguments["document_id"]

    document_json=arguments["doc_content"]
    doc_aux=arguments["doc_aux"]

    arguments = {}
    retval = Core_processDocument(document_json, 
                                  language,
                                  ner_model, 
                                  arguments)
    if retval != None:
        return retval     
    json_response = arguments["json_response"]

    entities_dict = {}
    NILcounter = 0
    NILcounter = aggregate_entities(entities_dict,
                                    document_id,
                                    language,
                                    json_response,
                                    NILcounter,
                                    False,
                                    version,
                                    doc_aux)
 
    entities_response = []
    post_process_entities(entities_dict,entities_response)
    response = jsonify({"entities" : entities_response})    
    for key, value in default_headers.items():
        response.headers.add(key, value)
    print("FINISH")
    return response

@app.route(scriptargs.route + latest_supported_version + '/processDocument', methods=['OPTIONS', 'POST'])
def processDocumentBackwardsCompatible():
    return processDocument(version=latest_supported_version)

@app.route(scriptargs.route + current_version + '/processRelatedDocuments', methods=['OPTIONS', 'POST'])
def processRelatedDocuments(version=current_version):
    if version ==current_version:
        return make_response(jsonify({'error': 'Method not valid in this API version ' + version + '. Please use ' + latest_supported_version + '.'}), 400)  
    arguments = {}
    retval = validate_and_get_args(request, "processRelatedDocuments", version, arguments)
    if retval != None:
        return retval 
    ner_model = arguments["ner_model"]
    fixNILsWithEditDistance = arguments["fixNILsWithEditDistance"]
    #applyCrossDocumentCoherence = arguments["applyCrossDocumentCoherence"]
    applyCrossDocumentCoherence = True #processRelatedDocuments forces usage of CrossDocumentCoherence
    applyCoreference = arguments["applyCoreference"]
    applyEntityLinking = arguments["applyEntityLinking"]
            
    documents_id = arguments["document_id"]
    documents_json = arguments["doc_content"]
    docs_aux=arguments["doc_aux"]
    documents_language = arguments["language"]

    entities_dict = {}
    NILcounter = 0

    for document_id, language, document_json, doc_aux in zip(documents_id, documents_language, documents, docs_aux):
        arguments = {}
        retval = Core_processDocument(document_json,
                                      language,
                                      ner_model, 
                                      arguments)
        if retval != None:
            return retval     
        json_response = arguments["json_response"]

        NILcounter = aggregate_entities(entities_dict,
                                        document_id,
                                        language,
                                        json_response,
                                        NILcounter,
                                        False,
                                        version,
                                        doc_aux)

    entities_response = []
    post_process_entities(entities_dict,entities_response)
    response = jsonify({"entities" : entities_response})  
    for key, value in default_headers.items():
        response.headers.add(key, value)
    return response

@app.route(scriptargs.route + latest_supported_version + '/processRelatedDocuments', methods=['OPTIONS', 'POST'])
def processRelatedDocumentsBackwardsCompatible():
    return processRelatedDocuments(version=latest_supported_version)

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
    used_threads=cpu_count() if cpu_count()<=4 else int(cpu_count()/2)
    print("Start gevent WSGI server with "+ str(used_threads)+ " threads")
    # use gevent WSGI server instead of the Flask
    http = WSGIServer(('', scriptargs.port), app.wsgi_app, spawn=used_threads)
    # TODO gracefully handle shutdown
    http.serve_forever()