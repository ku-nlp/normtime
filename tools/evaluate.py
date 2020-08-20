import os
import sys
import argparse
import random
from datetime import datetime
from collections import defaultdict
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.append(f'{HERE}/..')
from normtime import NormTime, TIMEX
from timebank import read_input

def evaluate(xml_dir, debug):
    timebank_docs = []
    for xml_fname in os.listdir(xml_dir):
        if not xml_fname.endswith('xml'):
            continue
        timebank_doc = read_input(txt_file=f'{xml_dir}/{xml_fname}', lang='ja')
        timebank_docs.append(timebank_doc)


    nt = NormTime(debug) 
    vfs_match_cnt, v_match_cnt, ans_cnt = 0,0,0
    for timebank_doc in timebank_docs:
        sentid2timexids = defaultdict(list) # {sent_id: [timex_id]}
        for tnid,timex_node in enumerate(timebank_doc.timex_nodes):
            sentid2timexids[timex_node.sentence_id].append(tnid)
        
        doc = []
        doc_timex_ids = []
        for sent_id,sent_timex_ids in sorted(sentid2timexids.items()):
            sent = timebank_doc.sentences[sent_id].text # string
            sent_timexes = []
            i = 0
            for timex_id in sent_timex_ids:
                timex_node = timebank_doc.timex_nodes[timex_id]
                begin_strid = sent[i:].index(timex_node.text)
                sent_timexes.append(TIMEX(  str=timex_node.text,
                                                begin_strid=i+begin_strid,
                                                end_strid=i+begin_strid+len(timex_node.text),
                                                TYPE=timex_node.TYPE))
                i += begin_strid+len(timex_node.text)
                doc_timex_ids.append(timex_id)
            doc.append((sent,sent_timexes))

        for timex_id, (vfs,v) in zip(doc_timex_ids, nt.normalize(doc, timebank_doc.dct)):
            text = timebank_doc.timex_nodes[timex_id].text
            TYPE = timebank_doc.timex_nodes[timex_id].TYPE

            gold_vfs = timebank_doc.timex_nodes[timex_id].valueFromSurface
            gold_v = timebank_doc.timex_nodes[timex_id].value

            vfs_match_cnt += int(vfs==gold_vfs)
            v_match_cnt += int(v==gold_v)
            ans_cnt += 1
        
            print(f'{timebank_doc.txt_file}\t{text}\t{TYPE}\tvalueFromSurface:: sys:{vfs} gold:{gold_vfs} {vfs==gold_vfs}\tvalue:: sys:{v} gold:{gold_v} {v==gold_v}')
    print(f'ACC: ValueFromSurface {vfs_match_cnt/ans_cnt:.3f} ({vfs_match_cnt}/{ans_cnt})  Value {v_match_cnt/ans_cnt:.3f} ({v_match_cnt}/{ans_cnt})')


def test(txt_file, dct):
    doc = []
    doc_timexes = []
    with open(txt_file) as f:
        sent = ''
        sent_timexes = []
        for line in f.readlines():
            if line.startswith('\t'):
                begin_strid, end_strid, TYPE = line.strip().split('\t')
                timex = TIMEX(str=sent[int(begin_strid):int(end_strid)],
                                begin_strid=int(begin_strid), 
                                end_strid=int(end_strid), 
                                TYPE=TYPE)
                sent_timexes.append(timex)
                doc_timexes.append(timex)
                        
            else:
                if sent:
                    doc.append((sent, sent_timexes))
                    sent_timexes = []
                sent = line.strip()
        if sent:
            doc.append((sent, sent_timexes))

    nt = NormTime() 
    for timex, (vfs, v) in zip(doc_timexes, nt.normalize(doc, dct)):
        print(f'{timex.str}\t{vfs}\t{v}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-x', '--xml_dir', help="TIMEX xml directory for evaluation.")
    parser.add_argument('-t', '--test_txt')
    parser.add_argument('--dct', '--test_json', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    if args.xml_dir:
        evaluate(args.xml_dir, args.debug)
    elif args.test_txt:
        test(args.test_txt, args.dct)
