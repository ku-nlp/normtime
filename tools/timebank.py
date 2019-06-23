#!/usr/bin/env python -S
# -*- coding: utf-8 -*-

import sys
import codecs
import os
import re
from xml.dom import minidom
from optparse import OptionParser

eventAttribs = ['eid',  'class']
timexAttribs = ['type', 'value', 'valueFromSurface', 'tid', 'mod', 'quant']
makeInstanceAttribs = ['eiid', 'eventID', 'signalID', 'pos', 'tense', 'aspect', 'cardinality', 'polarity', 'modality', 'vform', 'mood', 'pred']
tlinkAttribs = ['lid', 'relType', 'eventInstanceID', 'relatedToEventInstance', 'relTypeA', 'relTypeB', 'relTypeC']

class TimeBankDoc(object):
    def __init__(self, did, dct, txt_file, lang=None):
        self.did = did
        self.dct = dct
        self.txt_file = txt_file
        self.sentences = []
        self.event_nodes = {}
        self.lang = lang

    def __str__(self):
        str = 'did: %s' % self.did
        str = str + '\n' + '\n'.join([ '%s' % s for s in self.sentences])
        str = str + '\n' 'events'
        str = str + '\n' + '\n'.join([ '%s' % e for e in self.event_nodes.values()])
        return str
    
    def append_sentence(self, sentence):
        self.sentences.append(sentence)

    def set_event_nodes(self, event_nodes):
        self.event_nodes = event_nodes

    def set_timex_nodes(self, timex_nodes):
        self.timex_nodes = timex_nodes


    def align_word_id(self, parse_sentences, lang=None):
        if lang == 'ja':
            self.align_word_id_ja(parse_sentences)
        else:
            for i, sent in enumerate(self.sentences):
                if len(self.sentences[i].annotation) > 0:
                    pos = 0
                    eid_index = 0
                    while eid_index < len(self.sentences[i].annotation):
                        eid = self.sentences[i].annotation[eid_index]
                        word_num = len(parse_sentences.sentences[i].words)
                        while pos < word_num:
                            if self.event_nodes[eid].text == parse_sentences.sentences[i].words[pos].str:
                                if self.event_nodes[eid].sid != i:
                                    print('Error!', self.event_nodes[eid].sid, i, eid)
                                self.event_nodes[eid].set_wordid(pos)
                                eid_index += 1
                                break
                            else:
                                pos += 1
                        else:
                            print('Not Found:', parse_sentences.sentences[i].words[pos].str)
                            eid_index += 1

    def align_word_id_ja(self, parse_sentences):
        for i, sent in enumerate(self.sentences):
            if len(self.sentences[i].annotation) > 0:
                # posは文節ID
                pos = 0
                eid_index = 0
                current_char_pos = 0
                while eid_index < len(self.sentences[i].annotation):
                    eid = self.sentences[i].annotation[eid_index]
                    bnsts = parse_sentences.sentences[i].bnst_list()
                    phrase_num = len(bnsts)
                    while pos < phrase_num:
                        string = ''.join([ mrph.midasi for mrph in bnsts[pos].mrph_list()])
                        if self.event_nodes[eid].char_position <= current_char_pos:
                            if self.event_nodes[eid].char_position != current_char_pos:
                                print("Pos mismatch", string, eid, self.event_nodes[eid].char_position, current_char_pos)
                            elif self.event_nodes[eid].sid != i:
                                print('Error!', self.event_nodes[eid].sid, i, eid)
                            else:
                                self.event_nodes[eid].set_wordid(pos)
                            eid_index += 1
                            break
                        else:
                            pos += 1
                        current_char_pos += len(string)
                    else:
                        print('Not Found:', self.event_nodes[eid].text, self.event_nodes[eid].char_position)
                        eid_index += 1
            
class TimeBankSentence(object):
    def __init__(self, id, text, annotation=None):
        self.id = id
        self.text = text
        self.annotation = annotation
        
    def __str__(self):
        str = "%d: %s" % (self.id, self.text)
        str = str + ' ann:' + ','.join([ '%s' % (e_id) for e_id in self.annotation ])
        return str

    def set_text_annotation(self, word_id, eid):
        self.text_annotation[word_id] = eid


class EventNode(object):
    def __init__(self, id, eiid, tense, aspect, polarity, pos=None):
        self.id = id
        self.eiid = eiid
        self.text = ''
        self.tense = tense
        self.aspect = aspect
        self.polarity = polarity
        self.pos = pos
        self.sid = None
        self.word_id = None
        self.relatedEvent = {}
        self.char_position = None

    def __str__(self):
        return 'id:%s, eiid:%s, sid:%s, word_id:%s, text:%s, tense:%s, aspect:%s, polarity:%s, pos:%s' % (self.id, self.eiid, self.sid, self.word_id, self.text, self.tense, self.aspect, self.polarity, self.pos)

    def set_wordid(self, word_id):
        self.word_id = word_id

    def set_class(self, classname):
        self.classname = classname

    def set_text(self, text):
        self.text = text

    def set_sid(self, sid):
        self.sid = sid
        
    def set_char_position(self, char_position):
        self.char_position = char_position

class TimexNode(object):
    def __init__(self, sentence_id, tid, text, TYPE, value, valueFromSurface, mod, quant='None'):
        self.sentence_id = sentence_id
        self.tid = tid if tid != "" else "None"
        self.text = text
        self.value = value
        self.valueFromSurface = valueFromSurface
        self.mod = mod
        self.quant = quant
        self.TYPE = TYPE


def read_input(txt_file, lang=None, output_raw_sentence=None, ouput_timex_info=None):
    xdoc = minidom.parse(txt_file)

#    if lang == 'ja' and not output_raw_sentence and len(xdoc.getElementsByTagName('TLINK')) == 0:
#        return None
    
    if lang == 'ja':
        did = xdoc.getElementsByTagName('article').item(0).getAttribute('articleID')
        dct = xdoc.getElementsByTagName('TIMEX3').item(0).getAttribute('value')
    else:
        did = xdoc.getElementsByTagName('DOCID').item(0).childNodes[0].data
        dct = xdoc.getElementsByTagName('TIMEX3').item(0).getAttribute('value')
    timebank_doc = TimeBankDoc(did, dct, txt_file, lang=lang)

    if lang == 'ja':
        delete_ruby(xdoc)

    # 本文以外の処理
    event_nodes = {}     # {eventID:EventNode}
    eiid2EventID = {}    # {eiid:eventID}
    # MAKEINSTANCEの処理
    for node in xdoc.getElementsByTagName('MAKEINSTANCE'):
        # <MAKEINSTANCE eventID="e20" eiid="ei392" tense="PAST" aspect="NONE" polarity="POS" pos="VERB" />
        nodeData = {}
        for attrib in makeInstanceAttribs:
            if node.hasAttribute(attrib):
                nodeData[attrib] = node.getAttribute(attrib)
            else:
                nodeData[attrib] = None
        event_node = EventNode(nodeData['eventID'], nodeData['eiid'], nodeData['tense'], nodeData['aspect'], nodeData['polarity'], pos=nodeData['pos'])
        event_nodes[nodeData['eventID']] = event_node # eiid -> EventID
        # eiid -> EventID
        eiid2EventID[nodeData['eiid']] = nodeData['eventID']
    # TLINKの処理
    for node in xdoc.getElementsByTagName('TLINK'):
        nodeData = {}
        # <TLINK lid="l1" relType="BEFORE" eventInstanceID="ei377" relatedToEventInstance="ei378" />
        # <TLINK lid="l29" relType="DURING" eventInstanceID="ei414" relatedToTime="t0" />
        for attrib in tlinkAttribs:
            if node.hasAttribute(attrib):
                nodeData[attrib] = node.getAttribute(attrib)
        if 'eventInstanceID' in nodeData and 'relatedToEventInstance' in nodeData:
            if nodeData['eventInstanceID'] in eiid2EventID and nodeData['relatedToEventInstance'] in eiid2EventID:
                if lang == 'ja':
                    # relTypeA,B,Cが一致した時のみ採用
                    if nodeData['relTypeA'] == nodeData['relTypeB'] == nodeData['relTypeC']:
                        nodeData['relType'] = nodeData['relTypeA']
                    else:
                        continue
                event_nodes[eiid2EventID[nodeData['eventInstanceID']]].relatedEvent[eiid2EventID[nodeData['relatedToEventInstance']]] = nodeData['relType']
            else:
                print('Error')
                
    # 本文の処理
    sentence_id = 0
    annotation = []
    timex_nodes = []
    if lang == 'ja':
        text_tag = 'sentence'
    else:
        text_tag = 'TEXT'
    for node in xdoc.getElementsByTagName(text_tag):
        sentence = ''
        for child in node.childNodes:
            if child.nodeName == 'quote':
                for child_child in child.childNodes:
                    sentence, sentence_id, annotation = process_child_node(child_child, sentence, sentence_id, annotation, timebank_doc, event_nodes, timex_nodes, lang=lang)
            else:
                sentence, sentence_id, annotation = process_child_node(child, sentence, sentence_id, annotation, timebank_doc, event_nodes, timex_nodes, lang=lang)

        # 残り
        if sentence:
            timebank_sentence = TimeBankSentence(sentence_id, sentence, annotation=annotation)
            timebank_doc.append_sentence(timebank_sentence)
            sentence = ''
            sentence_id += 1
            annotation = []

    timebank_doc.set_event_nodes(event_nodes)
    timebank_doc.set_timex_nodes(timex_nodes)
    return timebank_doc 

def process_child_node(child, sentence, sentence_id, annotation, timebank_doc, event_nodes, timex_nodes, lang=None):
    """ sentenceタグの中のタグを分析 """
    if child.nodeType == child.ELEMENT_NODE:
        if child.nodeName == 'sampling':
            return sentence, sentence_id, annotation

        if child.nodeName == 'EVENT' or child.nodeName == 'event':
            nodeData = {}
            for attrib in eventAttribs:
                if child.hasAttribute(attrib):
                    nodeData[attrib] = child.getAttribute(attrib)
            if nodeData['eid'] in event_nodes:
                event_nodes[nodeData['eid']].set_class(nodeData['class'])
                event_nodes[nodeData['eid']].set_text(child.firstChild.data.strip(' \n'))
                event_nodes[nodeData['eid']].set_sid(sentence_id)
                event_nodes[nodeData['eid']].set_char_position(len(sentence))
                annotation.append(nodeData['eid'])
        if child.nodeName == 'TIMEX3':
            nodeData = {}
            for attrib in timexAttribs:
                if child.hasAttribute(attrib):
                    nodeData[attrib] = child.getAttribute(attrib)
            text = ""
            if len(child.childNodes) == 1:
                text = child.firstChild.data.strip()
            else:
                for child_child in child.childNodes:
                    if child_child.nodeType == child_child.TEXT_NODE:
                        text += child_child.data.strip()
            TN = TimexNode(sentence_id, nodeData.get('tid',None), text, nodeData['type'], nodeData['value'], nodeData.get('valueFromSurface',"None"), nodeData.get('mod','None'), nodeData.get('quant', 'None'))
            timex_nodes.append(TN)

        if child.nodeName != 'enclosedCharacter':
            for gchild in child.childNodes:
                if gchild.nodeType == gchild.TEXT_NODE:
                    if lang == 'ja' and gchild.data.strip() == '':
                        continue
                    sentence += gchild.data.strip('\n')
        else: # enclosedCharacter の場合は前後に記号を埋めておく
            for gchild in child.childNodes:
                if gchild.nodeType == gchild.TEXT_NODE:
                    if lang == 'ja' and gchild.data.strip() == '':
                        continue
                    sentence += u"＊"+gchild.data.strip('\n')+u"＊"

    elif child.nodeType == child.TEXT_NODE:
        chars = list(child.data.strip('\n'))
        for pos, char in enumerate(chars):
            # 文頭、または文の最後が空白の場合、空白は捨てる
            if (char == ' ' or char == u'　') and (not sentence or sentence.endswith(' ')):
                pass
            if char == '\n':
                # 余ったダブルクォーテーションは前の文にくっつける
                if sentence == '\'\'':
                    timebank_doc.sentences[-1].text += ' \'\''
                    sentence = ''
            elif lang == 'ja' and (char == u' ' or char == u'　'):
                sentence += u"＊"
            else:
                sentence += char

            # 以下は文を区切らない
            # - Mr., Mrs., Ms., St.
            # - 小数点 (3.1など)
            if (char == '.' and not sentence.endswith(("Mr.", "Mrs.", "Ms.", "Corp.", "St.", "U.", "U.S.", "U.N.")) and not (len(sentence) > 1 and sentence[-2].isdigit() and pos + 1 < len(chars) and chars[pos+1].isdigit())) or char == '?' or char == u'。':
                timebank_sentence = TimeBankSentence(sentence_id, sentence, annotation=annotation)

                timebank_doc.append_sentence(timebank_sentence)
                sentence = ''
                sentence_id += 1
                annotation = []
            
    return sentence, sentence_id, annotation

def delete_ruby(xdoc):
    """ ルビが振られている場合削除 """
    for node in xdoc.getElementsByTagName('ruby'):
        parent = node.parentNode
        if node.firstChild.nodeType == 3:
            text = node.firstChild.data.strip()
        elif node.firstChild.nodeType == 1: # 'ruby' の中に 'missingCharacter' が入れ子になっている
            text = node.firstChild.firstChild.data.strip()
        txt_node = xdoc.createTextNode(text)
        parent.replaceChild(txt_node, node)

if __name__ == "__main__":
#    sys.stdout = codecs.getwriter("utf-8")(sys.stdout)

    parser = OptionParser()
    parser.add_option(
        '-t', '--txt_file',
        type = 'str',
        dest = 'txt_file'
    )
    parser.add_option(
        '-l', '--lang',
        type = 'str',
        dest = 'lang'
    )
    parser.add_option(
        '--output_raw_sentence',
        action = 'store_true',
        dest = 'output_raw_sentence'
    )
    parser.add_option(
        '--output_timex_info',
        action = 'store_true',
    )

    options, args = parser.parse_args()

    timebank_doc = read_input(txt_file=options.txt_file, lang=options.lang, output_raw_sentence=options.output_raw_sentence,
            ouput_timex_info=options.output_timex_info)
    if options.output_raw_sentence:
        for s in timebank_doc.sentences:
            print('%s' % s.text)
    elif options.output_timex_info:
        for tn in timebank_doc.timex_nodes:
            print('%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' % (timebank_doc.txt_file.split('/')[-1], tn.sentence_id, timebank_doc.dct, tn.tid, tn.text, tn.TYPE, tn.value, tn.valueFromSurface, tn.mod))
    else:
        print('%s' % timebank_doc)
