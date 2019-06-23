import os
import sys
import json
import re
import copy
from collections import namedtuple, defaultdict
from .time_composition import TimeCompositionManager
from .num_ex import str2num
 
HERE = os.path.dirname( os.path.abspath( __file__ ) )
RULE_FILE = f'{HERE}/../rule/strRule.json'
GENGO_FILE = f'{HERE}/../rule/gengo.json'

Match = namedtuple('Match', ('begin_strid', 'end_strid', 'rule_id', 'obj'))

class ApplyRule(object):
    def __init__(self, debug=False):
        self.debug = debug
        self.rules = []
        with open(RULE_FILE) as f:
            strRuleList = json.load(f)
            for i in range(len(strRuleList)):
                pattern = strRuleList[i][u"pattern"]
                repattern = re.compile(pattern)
                strRuleList[i][u"repattern"] = repattern
            self.rules.extend(strRuleList)
        self.rule_len = len(self.rules)

        with open(GENGO_FILE) as f:
            self.gengo_dicts = json.load(f)


    def __matching_rule(self, masked_sent, timexes):
        def arrange_span(span, rule):
            for datetypedict in rule['datetypelist']:
                if "rangelimit" in datetypedict:
                    rangelimit = datetypedict["rangelimit"]
                    if rangelimit[-1] == ':': # :で終わっている場合
                        start = int(rangelimit[:-1])
                        return (span[0]+start,span[1])
                    elif rangelimit[0] == ':':
                        end = int(rangelimit[1:])
                        return (span[0],span[1]+end)
                    else:
                        start,end = map(int,rangelimit.split(':'))
                        return (span[0]+start,span[1]+end)
            return span

        def search_successive_matches(timex_matches):
            begin2match = defaultdict(list) # {begin_strid:[match, ..]}
            for m in timex_matches:
                begin2match[m.begin_strid].append(m)
            # 連続するmatch
            suc_matches = [[x] for x in timex_matches]
            stack = [[x] for x in timex_matches]
            while stack:
                matches = stack.pop()
                if matches[-1].end_strid not in begin2match:
                    suc_matches.append(matches)
                else:
                    for next_match in begin2match[matches[-1].end_strid]:
                        stack.append(matches+[next_match])
                        suc_matches.append(matches+[next_match])
            return suc_matches


        # Matching all rules
        matches = []
        for rule_id,rule in enumerate(self.rules):
            repattern = rule[u"repattern"]
            for matchObj in re.finditer(repattern, masked_sent):
                begin_strid, end_strid = arrange_span(matchObj.span(), rule) # rangelimitに対応
                matches.append(Match(   begin_strid=begin_strid, 
                                        end_strid=end_strid, 
                                        rule_id=rule_id, 
                                        obj=matchObj))

        # 時間表現に対してルールマッチング
        best_matches = []
        for timex in timexes:
            timex_matches = [m for m in matches \
                                if set(range(timex.begin_strid, timex.end_strid)) >= \
                                        set(range(m.begin_strid, m.end_strid))]
            if not timex_matches:
                best_matches.append([])
                continue
            timex_matches = search_successive_matches(timex_matches)
            # position filtering
            timex_matches = [ms for ms in timex_matches \
                    if all(self.rules[m.rule_id].get('poslimit','') != 'TAIL' for m in ms[:-1])]
            timex_matches = [ms for ms in timex_matches \
                    if all(self.rules[m.rule_id].get('poslimit','') != 'SINGLE' for m in ms) or len(ms) == 1]
            if timex.TYPE == 'DURATION':
                timex_matches = [ms for ms in timex_matches \
                    if all(self.rules[m.rule_id].get('type','DURATION') in ('DURATION','MOD','FUN','NUM') for m in ms)]
            elif timex.TYPE == 'DATE':
                timex_matches = [ms for ms in timex_matches \
                    if any(self.rules[m.rule_id].get('type',timex.TYPE) == timex.TYPE for m in ms)]
            # match num filtering
            match_lens = [x[-1].end_strid-x[0].begin_strid for x in timex_matches]
            timex_matches = [timex_matches[i] for i,x in enumerate(match_lens) \
                                    if x==max(match_lens)]
            if timex_matches:
                best_matches.append(sorted(timex_matches, key=lambda x:len(x))[0])
            else:
                best_matches.append([])
        if self.debug:
            print(best_matches)
        return best_matches


    def get_time_compositions(self, doc, dct=None):
        time_manager = TimeCompositionManager(dct, self.debug)
        for sent_id, (sentence,timexes) in enumerate(doc):
            masked_sent = self.__mask_sent(sentence, timexes) # Masking
            if self.debug:
                print(sentence)
                print(masked_sent)

            # Make TimeComposition objects
            for i,matches in enumerate(self.__matching_rule(masked_sent, timexes)):
                timex = timexes[i]
                time_manager.make_new_composition(timex.TYPE, sent_id, timex.begin_strid, timex.end_strid)

                # 検出したがルールにマッチしない場合 
                if not matches:
                    continue

                # match --> TimeComposition
                for match in matches:
                    for dt in self.rules[match.rule_id]['datetypelist']:
                        tc = dt['timeclass']
                        if tc == 'MOD':
                            continue
                            
                        val = ''
                        if 'num' in dt: # 数値の検出
                            num_span = match.obj.span(dt['num'])
                            num_str = sentence[num_span[0]:num_span[1]]
                            masked_num_str = masked_sent[num_span[0]:num_span[1]]
                            if '&' in masked_num_str:
                                if '#' not in masked_num_str: # 数年 "&"
                                    val = 'X'
                                elif masked_num_str.split('&')[0] == '#'*len(masked_num_str.split('&')[0]):  # 十数年 "#&"
                                    val = str2num(num_str[:masked_num_str.find('&')])[:-1]+'X'
                            else: 
                                val = str2num(num_str)
                        if 'gengo' in dt and (val or 'norm' in dt): # 元号の処理
                            if 'norm' in dt:
                                val = dt['norm']
                            gengo_span = match.obj.span(dt['gengo'])
                            gengo = sentence[gengo_span[0]:gengo_span[1]]
                            for gd in self.gengo_dicts:
                                if gd['pattern'] == gengo:
                                    gengo_begin_year = gd['process_type']
                                    if gengo == '平成': 
                                        val = f'H{int(val):02}'
                                    elif gengo == '昭和': 
                                        val = f'S{int(val):02}'
                                    elif gengo == '令和': 
                                        val = f'R{int(val):02}'
                                    else:
                                        val = str(int(val)+gengo_begin_year)
                                    break

                        # マッチしたルール情報をTimeCompositionに加える
                        if tc in ('PHRASE','JUN', 'SEASON', 'YOUBI'):
                            time_manager.add(tc, dt['norm'])
                        elif tc == 'YEARX':
                            time_manager.add(tc, val[:-1]+'X')
                        elif tc == 'FUN':
                            if 'fixnum' in dt:
                                if timex.TYPE in ('DURATION', 'SET'): 
                                    if time_manager.get_last_cp().get_last_tcobj().value.isdigit(): # 1時間半 --> PT1.5H
                                        prev_obj = time_manager.get_last_cp().get_last_tcobj()
                                        val = str(int(prev_obj.value) + float(dt['fixnum']))
                                        time_manager.add(prev_obj.tc, val, prev_obj.ref, prev_obj.relation)
                                    else: # 半年間
                                        val = dt['fixnum']
                                        time_manager.add(tc, val)
                                elif timex.TYPE == 'TIME' and dt['fixnum'] == '0.5':
                                    # 1時半 --> XXXX-XX-XXT01:30
                                    if time_manager.get_last_cp().get_last_tcobj().tc =='HOUR':
                                        time_manager.add('MINUTE', '30')
                                    elif time_manager.get_last_cp().get_last_tcobj().tc =='MINUTE':
                                        time_manager.add('SECOND', '30')
                            if 'fixnum' not in dt:
                                if 'DCTrelation' in dt: # N年前とか
                                    time_manager.add(tc, None, ref='DCT', relation=dt['DCTrelation'])
                                elif 'relation' in dt:
                                    time_manager.add(tc, None, ref='REF', relation=dt['relation'])
                        else:
                            if timex.TYPE in ('DURATION', 'SET'):  # default値も使用「年間」--> P1Y
                                if 'norm' in dt and not val:
                                    val = dt['norm']
                                if val == '':
                                    val = '1'
                                time_manager.add(tc, val)
                            elif timex.TYPE in ('DATE', 'TIME'):
                                if 'DCTrelation' in dt: # 昨年
                                    time_manager.add(tc, '1', ref='DCT', relation=dt['DCTrelation'])
                                elif 'relation' in dt:
                                    time_manager.add(tc, '1', ref='REF', relation=dt['relation'])
                                elif tc == 'HOUR' and time_manager.get_last_cp().get_tcobj(tc).value in ('AF','NI'):
                                    val = str(12+int(val))
                                    time_manager.add(tc, val)
                                elif 'norm' in dt and not tc.startswith('GYEAR'): # except "元年"
                                    if dt['norm'] == 'AF' and tc == 'HOUR' and val.isdigit(): # 午後X時
                                        val = str(12+int(val))
                                        time_manager.add(tc, val)
                                    elif dt['norm'] == 'MO' and tc == 'HOUR' and val.isdigit(): # 午前X時
                                        time_manager.add(tc, val)
                                    else:
                                        time_manager.add(tc, dt['norm'])
                                elif val != '':
                                    time_manager.add(tc, val)
                if self.debug:
                    print(time_manager.time_compositions[-1].timedict)

        time_manager.resolve_parallel() # NUMの解消
        time_manager.resolve_functions() # fixnum=0.5の解消, 半年/半日など
        return time_manager



    def __mask_sent(self, sentence, timexes):
        masked_sent = sentence
        for timex in timexes:
            for i in range(timex.begin_strid, timex.end_strid):
                string = sentence[i]
                if string.isdigit() or str2num(string) is not None: # digit --> #
                    masked_sent = f'{masked_sent[:i]}#{masked_sent[i+1:]}'
                elif string in [u'数', u'何']:
                    masked_sent = f'{masked_sent[:i]}&{masked_sent[i+1:]}'
                elif i+1 < timex.end_strid and sentence[i:i+2] == 'ゼロ':
                    masked_sent = f'{masked_sent[:i]}##{masked_sent[i+2:]}'
            timex_text = sentence[timex.begin_strid:timex.end_strid]
            for gengo in [x['pattern'] for x in self.gengo_dicts]:
                if gengo in timex_text:
                    for i in range(timex.begin_strid+timex_text.index(gengo), 
                                    timex.begin_strid+timex_text.index(gengo)+len(gengo)):
                        masked_sent = f'{masked_sent[:i]}%{masked_sent[i+1:]}'
        return masked_sent

