import os
import json
import re
from dataclasses import dataclass
from collections import defaultdict
from .time_composition import TimeComposition, TimeData
from .num_ex import str2num
from .const import TimeClass, TimexType, RefType

HERE = os.path.dirname(os.path.abspath(__file__))
RULE_FILE = f'{HERE}/../rule/strRule.json'
GENGO_FILE = f'{HERE}/../rule/gengo.json'

@dataclass
class RuleMatch:
    begin_strid: int
    end_strid: int
    rule_id: int
    matchobj: str


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

        with open(GENGO_FILE) as f:
            self.gengo_dicts = json.load(f)


    def matching_rule(self, masked_sent, timexes):
        """ Rule matching to the given timexes.

        Args:
            masked_sent (str)
            timexes (List(TIMEX))

        Returns:
            List[List[RuleMatch]]
        """
        def arrange_span(span, rule):
            for datetypedict in rule['datetypelist']:
                if "rangelimit" in datetypedict:
                    rangelimit = datetypedict["rangelimit"]
                    if rangelimit[-1] == ':': # :で終わっている場合
                        start = int(rangelimit[:-1])
                        return (span[0]+start, span[1])
                    elif rangelimit[0] == ':':
                        end = int(rangelimit[1:])
                        return (span[0], span[1]+end)
                    else:
                        start, end = map(int, rangelimit.split(':'))
                        return (span[0]+start, span[1]+end)
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

        def check_poslimit_restriction(rms, rules):
            if any(rules[rm.rule_id].get('poslimit','') == 'TAIL' for rm in rms[:-1]):
                return False
            if len(rms) != 1 \
                and any(rules[rm.rule_id].get('poslimit','') == 'SINGLE' for rm in rms):
                return False
            return True

        def check_timex_type_restriction(rms, rules):
            if timex.TYPE == TimexType.DURATION \
                and any(rules[rm.rule_id].get('type', TimexType.DURATION) 
                        not in (TimexType.DURATION, TimeClass.MOD, TimeClass.FUN, TimeClass.NUM) for rm in rms):
                return False
            if timex.TYPE == TimexType.DATE \
                and all(rules[rm.rule_id].get('type', timex.TYPE) != timex.TYPE for rm in rms):
                return False
            return True


        # Matching all rules
        matches = []
        for rule_id, rule in enumerate(self.rules):
            repattern = rule[u"repattern"]
            for matchObj in re.finditer(repattern, masked_sent):
                begin_strid, end_strid = arrange_span(matchObj.span(), rule) # rangelimitに対応
                matches.append(
                    RuleMatch(begin_strid=begin_strid, 
                              end_strid=end_strid, 
                              rule_id=rule_id, 
                              matchobj=matchObj))

        # 対象となる各時間表現に該当するルールを探索
        rms_list = []
        for timex in timexes:
            # List up candidate RuleMatch
            cand_rms = []
            for rm in matches:
                if set(range(timex.begin_strid, timex.end_strid)) \
                    >= set(range(rm.begin_strid, rm.end_strid)):
                    cand_rms.append(rm)
            if not cand_rms:
                rms_list.append([])
                continue

            # Merge RuleMatches
            cand_rms_list = search_successive_matches(cand_rms)

            # position filtering
            for i, rms in list(enumerate(cand_rms_list))[::-1]:
                if not (check_poslimit_restriction(rms, self.rules) \
                    or check_timex_type_restriction(rms, self.rules)):
                    cand_rms_list.pop(i)

            # Use the max length RuleMatches
            if not cand_rms_list:
                rms_list.append([])
            else:
                match_lens = [x[-1].end_strid-x[0].begin_strid for x in cand_rms_list]
                cand_rms_list = [cand_rms_list[i] for i,x in enumerate(match_lens) \
                                 if x==max(match_lens)]
                rms_list.append(sorted(cand_rms_list, key=lambda x:len(x))[0])

        if self.debug:
            print(rms_list)
        return rms_list


    def get_time_compositions(self, doc):
        """ Convert given timexes into list of TimeComposition.

        Returns:
            List[TimeComposition]
        """
        time_compositions = []

        for sent_id, (sentence, timexes) in enumerate(doc):
            masked_sent = self.mask_sent(sentence, timexes) # Masking
            if self.debug:
                print(sentence)
                print(masked_sent)

            # Make TimeComposition objects
            for i, matches in enumerate(self.matching_rule(masked_sent, timexes)):
                timex = timexes[i]
                timecomp = TimeComposition(TYPE=timex.TYPE,
                                           sent_id=sent_id,
                                           begin_strid=timex.begin_strid,
                                           end_strid=timex.end_strid)

                # 検出したがルールにマッチしない場合 
                if not matches:
                    time_compositions.append(timecomp)
                    continue

                # RuleMatch --> TimeComposition
                for match in matches:
                    for dt in self.rules[match.rule_id]['datetypelist']:
                        tc = dt['timeclass']
                        if tc == 'MOD':
                            continue

                        val = ''
                        if 'num' in dt: # 数値の検出
                            num_span = match.matchobj.span(dt['num'])
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
                            gengo_span = match.matchobj.span(dt['gengo'])
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
                        if tc in (TimeClass.PHRASE, TimeClass.JUN,
                                  TimeClass.SEASON, TimeClass.YOUBI):
                            timecomp.add(
                                TimeData(timeclass=tc, value=dt['norm']))
                        elif tc == TimeClass.YEARX:
                            timecomp.add(
                                TimeData(timeclass=tc, value=val[:-1]+'X'))
                        elif tc == TimeClass.FUN:
                            if 'fixnum' in dt: # 「半」
                                if timex.TYPE in (TimexType.DURATION, TimexType.SET):
                                    if timecomp.get_finest_timedata().value.isdigit(): # 1時間半 --> PT1.5H
                                        prev_timedata = timecomp.get_finest_timedata()
                                        val = str(int(prev_timedata.value) + float(dt['fixnum']))
                                        timecomp.add(
                                            TimeData(timeclass=prev_timedata.timeclass,
                                                     value=val,
                                                     ref=prev_timedata.ref,
                                                     rel=prev_timedata.rel))
                                    else: # 半年間
                                        val = dt['fixnum']
                                        timecomp.add(
                                            TimeData(timeclass=tc, value=val))
                                elif timex.TYPE == TimexType.TIME and dt['fixnum'] == '0.5':
                                    # 1時半 --> XXXX-XX-XXT01:30
                                    if timecomp.get_finest_timedata().timeclass == TimeClass.HOUR:
                                        timecomp.add(
                                            TimeData(timeclass=TimeClass.MINUTE, value="30"))
                                    elif timecomp.get_finest_timedata().timeclass == TimeClass.MINUTE:
                                        timecomp.add(
                                            TimeData(timeclass=TimeClass.SECOND, value="30"))
                            if 'fixnum' not in dt:
                                if 'DCTrelation' in dt:
                                    timecomp.add(
                                        TimeData(timeclass=tc, value="1",
                                                 rel=dt['DCTrelation']))
                                elif 'relation' in dt:
                                    timecomp.add(
                                        TimeData(timeclass=tc, value="1",
                                                 ref=RefType.REF, rel=dt['relation']))
                        else:
                            if timex.TYPE in (TimexType.DURATION, TimexType.SET):
                                # default値も使用「年間」--> P1Y
                                val = dt['norm'] if ('norm' in dt and not val) \
                                    else val if val else "1"
                                timecomp.add(
                                    TimeData(timeclass=tc, value=val))
                            elif timex.TYPE in (TimexType.DATE, TimexType.TIME):
                                if 'DCTrelation' in dt: # 「昨年」「来年」
                                    timecomp.add(
                                        TimeData(timeclass=tc, value="1",
                                                 ref=RefType.DCT, rel=dt['DCTrelation']))
                                elif 'relation' in dt:
                                    timecomp.add(
                                        TimeData(timeclass=tc, value="1",
                                                 ref=RefType.REF, rel=dt['relation']))
                                elif tc == TimeClass.HOUR \
                                    and timecomp.get_timedata(tc).value in ('AF','NI'):
                                    val = str(12+int(val))
                                    timecomp.add(
                                        TimeData(timeclass=tc, value=val))
                                elif 'norm' in dt and not re.match("GYEARX?", tc): # except "元年"
                                    if dt['norm'] == 'AF' and tc == TimeClass.HOUR and val.isdigit(): # 午後X時
                                        val = str(12+int(val))
                                        timecomp.add(
                                            TimeData(timeclass=tc, value=val))
                                    elif dt['norm'] == 'MO' and tc == TimeClass.HOUR and val.isdigit(): # 午前X時
                                        timecomp.add(
                                            TimeData(timeclass=tc, value=val))
                                    else:
                                        timecomp.add(
                                            TimeData(timeclass=tc, value=dt['norm']))
                                elif val != '':
                                    timecomp.add(
                                        TimeData(timeclass=tc, value=val))
                time_compositions.append(timecomp)

        return time_compositions



    def mask_sent(self, sentence, timexes):
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
