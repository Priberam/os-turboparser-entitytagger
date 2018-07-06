from turboparser import PyCPBSSink, PyCppToPyTurboSink, PyCTurboTextAnalysis, PyLoadOptions, PyAnalyseOptions
import os

#Custom client-defined sink with custom put_token and put_feature/document_feature.
class ExtractSentencesSink(PyCppToPyTurboSink):
    def __init__(self, allocate=True):
        self.sentences_start_offsets=[]
        self.sentences_end_offsets=[]
        self.starting_sentence=True;
        self.last_token_starting_pos=0;
        self.last_token_length=0;

    def put_token(self,
                  word, 
                  length,
                  start_pos,
                  kind):
        if self.starting_sentence == True:
            self.sentences_start_offsets.append(start_pos);
            self.starting_sentence=False;
        self.last_token_starting_pos=start_pos;
        self.last_token_length=length;

    def put_feature(self,  feature,  value):
        pass

    def end_sentence(self):        
        self.starting_sentence=True;
        self.sentences_end_offsets.append(self.last_token_starting_pos+ self.last_token_length);

    def put_document_feature(self, feature, value):
        pass

class TurboTextAnalysisServer():
    def __init__(self, 
                 data_path='C:\\Projects\\TurboTextAnalysis\\Data\\',
                 valid_languages=['en']):  
        self.valid_languages = valid_languages
        
        self.turbotextanalysis = PyCTurboTextAnalysis()
        load_options = PyLoadOptions()
        load_options.load_tagger = True
        load_options.load_parser = False
        load_options.load_morphological_tagger = False
        load_options.load_entity_recognizer = True
        load_options.load_semantic_parser = False
        load_options.load_coreference_resolver = False
        
        #print("data_path=",data_path)
        if data_path[-1]!=(os.sep):
            data_path=data_path+os.sep
            #print("data_path=",data_path)
        for lang in valid_languages:
            retval = self.load_turbotextanalysis_language(lang, data_path, load_options)

    def load_turbotextanalysis_language(self,language, data_path, load_options):
        retval = self.turbotextanalysis.load_language(language, data_path, load_options)
        if retval != 0:
            print("ERROR in PyCTurboTextAnalysis load_language")
            print("Return value: ", retval)
            exit()
        return retval

    
    def detect_sentence_boundaries(self,text, language, sink):
        options = PyAnalyseOptions()
        options.use_tagger = False
        options.use_parser = False
        options.use_morphological_tagger = False
        options.use_entity_recognizer = False
        options.use_semantic_parser = False
        options.use_coreference_resolver = False
        retval = self.turbotextanalysis.analyse(language, text, sink, options)
        if retval != 0:
            print("ERROR in PyCTurboTextAnalysis analyse")
            print("Return value: ", retval)
            exit()
        return retval

    def obtain_mentions_per_sentence(self,sentence, 
                        sentence_id,
                        sentence_offset,
                        language, mentions):
        sink = PyCppToPyTurboSink(True)
        options = PyAnalyseOptions()
        options.use_tagger = True
        options.use_parser = False
        options.use_morphological_tagger = False
        options.use_entity_recognizer = True
        options.use_semantic_parser = False
        options.use_coreference_resolver = False
        retval = self.turbotextanalysis.analyse(language, 
                                           sentence, 
                                           sink, 
                                           options)
        if retval != 0:
            print("ERROR in PyCTurboTextAnalysis analyse")
            print("Return value: ", retval)
            exit()

        tokens_info = sink.get_tokens_info()
        current_entity = None
        for x in tokens_info:
            for y in x["features"]:
                if y == "entity_tag":
                    if x["features"][y][0] == "O" and current_entity is not None:
                        current_index = len(mentions)
                        current_entity["mention_id"] = current_index   
                        current_entity["near_context"] = sentence
                        mentions.append(current_entity)
                        current_entity = None
                    elif x["features"][y][0] == "B":
                        if current_entity is not None:
                            current_index = len(mentions)
                            current_entity["mention_id"] = current_index    
                            current_entity["near_context"] = sentence
                            mentions.append(current_entity)
                            current_entity = None
                        if current_entity is None:
                            current_entity = {}
                            current_entity["mention"] = x["word"]
                            current_entity["length"] = x["len"]
                            current_entity["sentence_offset"] = x["start_pos"]
                            current_entity["total_offset"] = sentence_offset + x["start_pos"]
                            current_entity["end_offset"] = current_entity["total_offset"] + current_entity["length"]
                            current_entity["near_context"] = sentence
                            current_entity["sentence_id"] = sentence_id
                            current_entity["ner_tag"] = x["features"][y][2:]
                            current_entity["ner_type"] = "NAM"
                    elif x["features"][y][0] == "I":
                            current_entity["mention"] += " " + x["word"]
                            current_entity["length"] = x["start_pos"]+ x["len"]-current_entity["sentence_offset"]
                            current_entity["end_offset"] = current_entity["total_offset"] + current_entity["length"]
        return retval

    def obtain_mentions(self,language,text, mentions):
        sentence_sink = ExtractSentencesSink(True)
        self.detect_sentence_boundaries(text=text,
                                   language = language,
                                   sink = sentence_sink)   
        
        sentences_offsets = []
        for s, e in zip(sentence_sink.sentences_start_offsets, 
                        sentence_sink.sentences_end_offsets):
            sentences_offsets.append((s, e))
        
        print("Num sentences:",len(sentences_offsets))

        sentence_id = 0
        for sentence in sentences_offsets:
            s = sentence[0]
            e = sentence[1]
            
            if(False):
                print("Sentence:")
                print(s, e)
                print(text[s:e]) 
            self.obtain_mentions_per_sentence(sentence = text[s:e],
                        sentence_id = sentence_id,
                        sentence_offset = s,
                        language = language,
                        mentions = mentions) #keep appending to mentions
            #print("mentions",mentions)
            sentence_id+=1
        return True