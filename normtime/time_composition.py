import re
from datetime import datetime, timedelta
import math
import copy
from collections import OrderedDict, namedtuple, defaultdict

TimeClass = namedtuple('TimeClass', ('tc', 'value', 'ref', 'relation'))

class TimeComposition(object):
    def __init__(self, TYPE, sent_id=-1, begin_strid=-1, end_strid=-1):
        self.timedict = OrderedDict()
        self.sent_id = sent_id
        self.TYPE = TYPE
        self.begin_strid = begin_strid
        self.end_strid = end_strid

    def add(self, timeclass, value, ref=None, relation=None):
        assert ref in (None, 'DCT', 'REF')
        self.timedict[timeclass] = TimeClass(tc=timeclass, value=value, ref=ref, relation=relation)

    def get_last_tcobj(self):
        if not self.timedict:
            return TimeClass(tc='', value='', ref='', relation='')
        return list(self.timedict.values())[-1]

    def get_tcobj(self, tc, default_value=''):
        if tc not in self.timedict:
            return TimeClass(tc='', value=default_value, ref='', relation='')
        return self.timedict[tc]

    def get_tcobjs(self):
        for tcobj in self.timedict.values():
            yield tcobj

    def isValid(self):
        return len(self.timedict)



class TimeCompositionManager(object):
    def __init__(self, dct, debug=False):
        self.time_compositions = []
        self.dct = dct
        self.vfs_list = []
        self.vs_list = []
        self.debug = debug

    def make_new_composition(self, *args):
        self.time_compositions.append(TimeComposition(*args))

    def get_last_cp(self):
        return self.time_compositions[-1]

    def add(self, timeclass, value, ref=None, relation=None):
        self.time_compositions[-1].add(timeclass, value, ref=ref, relation=relation)

    def resolve_parallel(self):
        """
            並列処理 ex. 17、18日
        """
        for cpid,cp in reversed(list(enumerate(self.time_compositions[:-1]))):
            if  cp.isValid() and \
                    all(tcobj.tc=='NUM' for tcobj in cp.get_tcobjs()) and \
                    self.time_compositions[cpid+1].sent_id == cp.sent_id and \
                    self.time_compositions[cpid+1].begin_strid-cp.end_strid == 1 and \
                    len(list(self.time_compositions[cpid+1].get_tcobjs()))==1:
                tc = list(self.time_compositions[cpid+1].get_tcobjs())[0].tc
                new_cp = TimeComposition(cp.TYPE, cp.begin_strid, cp.end_strid)
                if tc.endswith('X'): # YEARX
                    new_cp.add(tc, f'{cp.get_tcobj("NUM").value[:-1]}X')
                else:
                    new_cp.add(tc, cp.get_tcobj('NUM').value)
                self.time_compositions[cpid] = new_cp


    def resolve_functions(self):
        """
            FUNCTION (ex. 半日) の0.5倍の処理
        """
        for cpid,cp in enumerate(self.time_compositions):
            if cp.TYPE in ('DURATION', 'SET') and cp.get_tcobj('FUN').value == '0.5' and \
                    all(tcobj.value.isdigit() for tcobj in cp.get_tcobjs() if tcobj.tc != 'FUN'):
                new_cp = TimeComposition(cp.TYPE, cp.begin_strid, cp.end_strid)
                for tcobj in cp.get_tcobjs():
                    if tcobj.tc == 'FUN':
                        continue
                    val = float(cp.get_tcobj(tcobj.tc).value)/2
                    if val.is_integer(): # 整数
                        new_cp.add(tcobj.tc, str(int(val)))
                    else:
                        new_cp.add(tcobj.tc, f'{val:.1f}')
                self.time_compositions[cpid] = new_cp


    def get_values(self):
        self.vfs_list = [None] * len(self.time_compositions)
        self.__get_valueFromSurface()

        self.v_list = copy.deepcopy(self.vfs_list)
        self.__get_value()

        for vfs, v in zip(self.vfs_list, self.v_list):
            yield vfs, v

    def __get_valueFromSurface(self):
        for cpid, cp in enumerate(self.time_compositions):
            if not cp.isValid(): # ルールがマッチしなかった場合
                self.vfs_list[cpid] = ''
                continue

            if cp.TYPE in ('DATE', 'TIME'):
                # N年前など
                if any(tcobj.tc=='FUN' for tcobj in cp.get_tcobjs()):
                    vfs = 'Q+' if cp.get_tcobj('FUN').relation == 1 \
                            else 'Q-' if cp.get_tcobj('FUN').relation == -1 \
                            else 'Q'
                    for tcobj in cp.get_tcobjs():
                        if tcobj.tc in ['FUN','MOD']: 
                            continue 
                        vfs += tcobj.value+tcobj.tc[0]
                    self.vfs_list[cpid] = vfs
                    continue

                # XXXX-XX-XXTXX:XX:XX形式
                # 各要素の値埋め
                phrase = None
                slots = [None]*6 # 6 slots
                for tcobj in cp.get_tcobjs():
                    tc = tcobj.tc
                    if not tcobj.tc:
                        continue
                    strnum = tcobj.value
                    if tc == 'CENTURY' and slots[0] is None:
                        slots[0] = 'XXXX' if tcobj.ref \
                            else f'{int(strnum)-1}XX' if strnum.isdigit() else strnum
                    if tc == 'GYEAR' and slots[0] is None:
                        slots[0] = strnum
                    elif tc in ('GYEARX',) and slots[0] is None:
                        slots[0] = f'{strnum[:-1]}X'
                    elif tc in ['YEAR', 'YEARX'] and slots[0] is None:
                        if tcobj.ref:
                            slots[0] = 'XXXX' 
                        elif len(strnum) <= 2: # 02年, 直前が平成XX年の場合はH02とする
                            if cpid > 0 and self.vfs_list[cpid-1].startswith('H') and strnum.isdigit():
                                slots[0] = f'H{int(strnum):02}' 
                            elif cpid > 0 and self.vfs_list[cpid-1].startswith('S') and strnum.isdigit():
                                slots[0] = f'S{int(strnum):02}' 
                            else: 
                                slots[0] = 'X'*(4-len(strnum))+strnum
                        else:
                            slots[0] = strnum
                        if tc == 'YEARX':
                            slots[0] = f'{slots[0][:-1]}X'
                    elif tc == 'GFYEAR' and slots[0] is None:
                        slots[0] = f'FY{strnum}' 
                    elif tc == 'FYEAR' and slots[0] is None:
                        slots[0] = 'FYXXXX' if tcobj.ref \
                                    else 'FY'+'X'*(4-len(strnum))+strnum if len(strnum) <= 2\
                                    else f'FY{strnum}'
                    elif tc in ['MONTH', 'SEASON', 'YOUBI'] and slots[1] is None:
                        slots[1] = 'XX' if strnum == 'X' or tcobj.ref\
                                        else '0'*(2-len(strnum))+strnum 
                    elif tc in ['WEEK'] and slots[1] is None:
                        slots[1] = 'WXX'
                    elif tc in ['DAY', 'JUN'] and slots[2] is None:
                        slots[2] = 'XX' if strnum == 'X' or tcobj.ref\
                                        else '0'*(2-len(strnum))+strnum
                    elif tc in ['HOUR'] and slots[3] is None:
                        slots[3] = 'XX' if strnum == 'X' or tcobj.ref\
                                    else '0'*(2-len(strnum))+strnum
                    elif tc in ['MINUTE'] and not slots[4]:
                        slots[4] = 'XX' if strnum == 'X' or tcobj.ref\
                                    else '0'*(2-len(strnum))+strnum
                    elif tc in ['SECOND'] and not slots[5]:
                        slots[5] = 'XX' if strnum == 'X' or tcobj.ref\
                                    else '0'*(2-len(strnum))+strnum
                    elif tc == 'PHRASE':
                        phrase = strnum
                vfs = self.__slots2format(slots)

                if vfs == '' and phrase:
                    vfs = phrase
                self.vfs_list[cpid] = vfs

            elif cp.TYPE == 'SET' and cp.get_tcobj('YOUBI').value: # 毎週火曜日 --> XXXX-WXX-2
                self.vfs_list[cpid] = f'XXXX-{cp.get_tcobj("YOUBI").value}'

            else: # DURATION
                vfs = 'P'
                phrase = ''
                Flag = True
                used_tcs = [] # P16Y16Yみたいなことがないように
                for tcobj in cp.get_tcobjs():
                    tc = tcobj.tc
                    if tc == 'PHRASE':
                        phrase = tcobj.value
                        continue
                    if Flag and (tc in ['HOUR','MINUTE','SECOND']): 
                        vfs += 'T'
                        Flag = False
                    if tc not in used_tcs and tcobj.value:
                        if tc == 'NUM':
                            continue
                        if tc == 'FYEAR':
                            vfs += f'{tcobj.value}FY'
                        else:
                            vfs += f'{tcobj.value}{tc[0]}'
                        used_tcs.append(tc)
                if vfs == '' and phrase:
                    vfs = phrase
                if vfs == 'P' and cp.get_tcobj('NUM').value: # FIXME とりあえずNUMはYearと見なす
                    vfs += f'{cp.get_tcobj("NUM").value}Y'

                if vfs == 'P': # 正規化に失敗
                    vfs = 'None'

                self.vfs_list[cpid] = vfs


    def __slots2format(self, slots, ref_cp=None):
        """
            slotsをTIMEX3のフォーマットに変換
        """
        Flag = False
        vfs = ''
        for i in range(5,-1,-1): # 下から
            if slots[i]:
                if Flag:
                    vfs = slots[i]+'-'+vfs if i in [0,1] \
                            else slots[i]+'T'+vfs if i == 2 \
                            else slots[i]+':'+vfs
                else: # 初めて
                    vfs = slots[i]
                Flag = True
            elif Flag:
                if ref_cp:
                    vfs = f'{ref_cp.get_tcobj("YEAR", default_value="XXXX").value}-{vfs}' if i==0 \
                            else f'{ref_cp.get_tcobj("MONTH", default_value="XX").value}-{vfs}' if i==1 \
                            else f'{ref_cp.get_tcobj("DAY", default_value="XX").value}T{vfs}' if i==2 \
                            else f'{ref_cp.get_tcobj("HOUR", default_value="XX").value}:{vfs}' if i==3 \
                            else f'{ref_cp.get_tcobj("MINUTE", default_value="XX").value}:{vfs}' 
                else:
                    vfs = f'XXXX-{vfs}' if i==0 \
                            else f'XX-{vfs}' if i==1 \
                            else f'XXT{vfs}' if i==2 \
                            else f'XX:{vfs}'

        if vfs.split('-')[0].isdigit() and \
            int(vfs.split('-')[0]) < 1868 and \
            vfs.count('-') == 2:
            vfs += 'Q' # 旧暦
        return vfs


    def get_ref_cp(self, ref2cp, ref=None):
        if (ref == 'DCT' or not ref2cp.get('REF')):
            return ref2cp['DCT']
        return ref2cp['REF']+ref2cp['DCT']


    def __get_value(self):
        for cpid, cp in enumerate(self.time_compositions):
            v = self.v_list[cpid]
            if cp.TYPE in ('DURATION', 'SET'):
                continue

            # 平成/昭和の置換
            if re.search('H(\d\d)', v): #平成
                v = re.sub('H(\d\d)', str(int(re.search('H(\d\d)',v).group(1))+1988), v)
            elif re.search('H(\d)X', v): #平成X年代
                v = re.sub('H(\d)', str(int(re.search('H(\d)',v).group(1))+1988+5)[:-1], v)
            elif re.search('S(\d\d)', v): #昭和
                v = re.sub('S(\d\d)', str(int(re.search('S(\d\d)',v).group(1))+1925), v)
            elif re.search('S(\d)X', v): #昭和X年代
                v = re.sub('S(\d)', str(int(re.search('S(\d)',v).group(1))*10+1925+5)[:-1], v)

            # 正規化済み
            if re.match('\d\d[\dX]X', v) or ('X' not in v and not v.startswith('Q')):
                self.v_list[cpid] = v
                self.__resolve_youbi(cpid, v=v)
                continue

            # Find REF
            ref2cp = defaultdict(list) # {"DCT": dct_cp,  "REF": ref_cp}
            dct_cp = TimeComposition('DATE')
            for tc,val in zip(('YEAR','MONTH','DAY'), self.dct.split('T')[0].split('-')):
                dct_cp.add(tc,val)
            ref2cp['DCT'].append(dct_cp)

            for i in range(cpid-1,-1,-1): # FIXME どのようにREFを選択するか
                bef_cp = self.time_compositions[i]
                bef_v = self.v_list[i]
                if bef_cp.sent_id == cp.sent_id: # 同じ文で先に出現したDATE/TIMEをREFとする
                    if bef_cp.TYPE in ('DATE','TIME'):
                        ref_cp = TimeComposition('DATE')
                        for tc,val in zip(('YEAR','MONTH','DAY'), bef_v.split('T')[0].split('-')):
                            if val.isdigit():
                                ref_cp.add(tc, val)
                            elif re.match('FY\d+', val):
                                ref_cp.add(tc, val[2:])
                            else:
                                break
                        if ref_cp.isValid():
                            if 'T' in bef_v:
                                for tc,val in zip(('HOUR','MINUTE','SECOND'), bef_v.split('T')[1].split(':')):
                                    if val.isdigit():
                                        ref_cp.add(tc, val)
                                    else:
                                        break
                            ref2cp['REF'].append(ref_cp)
                elif not ref2cp['REF'] and i == cpid-1 and \
                        any(tcobj.ref=='REF' for tcobj in cp.get_tcobjs()): # 文の先頭でかつrelationなとき
                    if bef_cp.TYPE not in ('DATE', 'TIME') or \
                        len(list(bef_cp.get_tcobjs())) == 0 or \
                        cp.sent_id-bef_cp.sent_id > 1:
                        break
                    bef_cp_min_tcobj = list(bef_cp.get_tcobjs())[-1]
                    cp_min_tcobj = list(cp.get_tcobjs())[-1]
                    ref_cp = TimeComposition('DATE')
                    for tc,val in zip(('YEAR','MONTH','DAY'), bef_v.split('T')[0].split('-')):
                        if val.isdigit():
                            ref_cp.add(tc, val)
                    if ref_cp.isValid():
                        ref2cp['REF'].append(ref_cp)
                    break
                else:
                    break

            # 「N年前」の正規化
            if any(tcobj.tc=='FUN' for tcobj in cp.get_tcobjs()) and \
                    [x for x in cp.get_tcobjs() if x.tc != 'FUN']:
                val = ''
                ref_cp = self.get_ref_cp(ref2cp)[0]
                rel = cp.get_tcobj('FUN').relation if cp.get_tcobj('FUN').relation else 0 
                cp_min_tc = [x for x in cp.get_tcobjs() if x.tc != 'FUN'][-1].tc
                slots = [None]*6
                for i,tc in enumerate(['YEAR','MONTH','DAY', 'HOUR', 'MINUTE', 'SECOND']):
                    if not ref_cp.get_tcobj(tc).value.isdigit() and \
                            cp.get_tcobj(tc).value != 'X':
                        break
                    if cp.get_tcobj(tc).value.isdigit():
                        diff = int(cp.get_tcobj(tc).value)*rel
                        new_val = int(ref_cp.get_tcobj(tc).value) + diff
                        if tc == 'MONTH' and (new_val < 1 or new_val > 12):
                            slots[0] += new_val//12
                            slots[1] += max(new_val%12, 12)
                        elif tc == 'DAY':
                            ref_date = datetime(int(slots[0]), int(slots[1]), int(ref_cp.get_tcobj(tc).value))
                            new_date = ref_date + timedelta(days=diff)
                            slots[0],slots[1],slots[2] = new_date.strftime('%Y-%m-%d').split('-')
                        else: # FIXME HOUR/MINUTE/SECONDへの対応: ex.「100時間後」
                            slots[i] = str(int(ref_cp.get_tcobj(tc).value) + diff)
                    elif cp.get_tcobj(tc).value == 'X':
                        slots[i] = 'XXXX' if tc == 'YEAR' else 'XX'
                    else:
                        slots[i] = ref_cp.get_tcobj(tc).value

                    if tc == cp_min_tc:
                        break
                self.v_list[cpid] = self.__slots2format(slots)
                continue

            # XXXX-XX-XXTXX:XX:XX形式
            phrase = None
            slots = [None]*6
            for tcobj in cp.get_tcobjs():
                tc = tcobj.tc
                if tc == 'CENTURY' and slots[0] is None:
                    if tcobj.relation is not None:
                        ref_cp = self.get_ref_cp(ref2cp, tcobj.ref)[0]
                        ref_year = ref_cp.get_tcobj('YEAR').value
                        if tcobj.value.isdigit(): # 「前世紀」
                            slots[0] = f'{int(ref_year[:2]) + tcobj.relation*int(tcobj.value)}XX'
                        elif tcobj.relation == 0: # 「今年」
                            slots[0] = f'{int(ref_year[:2])}XX'
                elif tc in ['GYEAR', 'GYEARX', 'YEAR', 'YEARX', 'FYEAR'] and slots[0] is None:
                    ref_cp = self.get_ref_cp(ref2cp, tcobj.ref)[0]
                    ref_year = ref_cp.get_tcobj('YEAR').value
                    if tcobj.relation is not None:
                        if tcobj.value.isdigit(): # 「昨年」
                            slots[0] = str(int(ref_year) + tcobj.relation*int(tcobj.value))
                        elif tcobj.relation == 0: # 「今年」
                            slots[0] = ref_year
                    elif len(tcobj.value) == 2: # 「02年」「30年代」
                        k1 = ref_year[:2] + tcobj.value.replace('X','0')
                        k2 = str(int(ref_year[:2])+1) + tcobj.value.replace('X','0')
                        k3 = str(int(ref_year[:2])-1) + tcobj.value.replace('X','0')
                        ks = [k1,k2,k3]
                        diffs = [math.fabs(int(k)-int(ref_year)) for k in ks]
                        val = ks[diffs.index(min(diffs))] # 候補k1-k3の中で、refと一番近いものを選択
                        if 'X' in tcobj.value:
                            slots[0] = f'{val[:-1]}X'
                        else: # 「N年代」
                            slots[0] = val
                    else: # 「2002年」
                        slots[0] = tcobj.value
                    # 「X年度」
                    if slots[0] and tc == 'FYEAR':
                        slots[0] = f'FY{slots[0]}'

                elif tc in ['WEEK'] and slots[1] is None: 
                    slots[1] = 'WXX'

                elif tc in ['MONTH', 'SEASON', 'YOUBI'] and slots[1] is None: 
                    if tcobj.value == 'X':
                        slots[1] = 'XX'   # "何月"が'0X'とならないように
                    elif tcobj.tc == 'MONTH' and tcobj.ref: # 「先月」「今月」
                        for ref_cp in self.get_ref_cp(ref2cp, tcobj.ref):
                            ref_year = ref_cp.get_tcobj('YEAR').value
                            ref_month = ref_cp.get_tcobj('MONTH').value
                            if not (ref_year and ref_month): # MONTHスロットがない場合
                                continue
                            if tcobj.relation == 0: # 「今月」
                                slots[0] = ref_year
                                slots[1] = f'{int(ref_month):02}'
                            elif  tcobj.value.isdigit():
                                m = int(ref_month) + tcobj.relation*int(tcobj.value)
                                if m > 12:
                                    slots[1] = f'{m-12:02}'
                                    slots[0] = f'{int(ref_year)+1}'
                                elif m < 1:
                                    slots[1] = f'{m+12:02}'
                                    slots[0] = f'{int(ref_year)-1}'
                                else:
                                    slots[1] = f'{m:02}'
                                    slots[0] = ref_year
                            break
                        else: # DCTにMonthがない場合
                            slots[1] = 'XX'
                    else:
                        slots[1] = '0'*(2-len(tcobj.value))+tcobj.value 

                elif tc in ['DAY'] and slots[2] is None:
                    if tcobj.value == 'X':
                        slots[2] = 'XX'   
                    elif tcobj.tc == 'DAY' and tcobj.ref: 
                        for ref_cp in self.get_ref_cp(ref2cp, tcobj.ref):
                            ref_year = ref_cp.get_tcobj('YEAR').value
                            ref_month = ref_cp.get_tcobj('MONTH').value
                            ref_day = ref_cp.get_tcobj('DAY').value
                            if not (ref_year and ref_month and ref_day): # DAYスロットがない場合
                                continue
                            if tcobj.relation == 0: # 今日
                                slots[0] = ref_year
                                slots[1] = ref_month
                                slots[2] = f'{int(ref_day):02}'
                            elif tcobj.value.isdigit():
                                diff_day = tcobj.relation*int(tcobj.value)
                                ref_date = datetime.strptime(f'{ref_year}-{ref_month}-{ref_day}', '%Y-%m-%d')
                                new_date = ref_date + timedelta(days=diff_day)
                                slots[0],slots[1],slots[2] = new_date.strftime('%Y-%m-%d').split('-')
                            break
                        else:
                            slots[2] = 'XX'
                    else:
                        slots[2] = '0'*(2-len(tcobj.value))+tcobj.value 

                elif tc in ['JUN'] and slots[2] is None:
                    slots[2] = 'XX' if tcobj.value == 'X' or tcobj.ref \
                                else '0'*(2-len(tcobj.value))+tcobj.value
                    
                elif tc in ['HOUR'] and slots[3] is None:
                    if tcobj.value == 'X':   
                        slots[3] = 'XX'
                    else:   
                        strnum = tcobj.value
                        if tcobj.value.isdigit() and int(tcobj.value) >= 24: 
                            strnum = str(int(strnum)-24)
                        slots[3] = '0'*(2-len(strnum))+strnum

                elif tc in ['MINUTE'] and slots[4] is None:
                    slots[4] = 'XX' if tcobj.value == 'X' \
                                else '0'*(2-len(tcobj.value))+tcobj.value

                elif tc in ['SECOND'] and cps[5] is None:
                    slots[5] = 'XX' if tcobj.value == 'X' \
                                else '0'*(2-len(tcobj.value))+tcobj.value

                elif tc == 'PHRASE':
                    phrase = tcobj.value

            if not self.__resolve_youbi(cpid, ref2cp=ref2cp, slots=slots):
                v = phrase if phrase and all(x is None for x in slots)\
                        else self.__slots2format(slots, self.get_ref_cp(ref2cp)[0])
                self.v_list[cpid] = v
            if self.debug:
                print(slots)
                print(f'REF: {self.get_ref_cp(ref2cp)[0].timedict}  {v}')


    def __resolve_youbi(self, cpid, v=None, ref2cp=None, slots=None):
        """
        日付と曜日を一貫させる ex.10日(水)
        """
        cp = self.time_compositions[cpid]
        next_cp = None if cpid+1==len(self.time_compositions) else self.time_compositions[cpid+1]
        if next_cp and cp.sent_id==next_cp.sent_id and \
                all(tcobj.tc=='YOUBI' for tcobj in next_cp.get_tcobjs()) and \
                0 <= next_cp.begin_strid-cp.end_strid <= 1:
            if v:
                self.v_list[cpid] = v
                self.v_list[cpid+1] = v
                return True
            elif ref2cp and slots:
                for ref_cp in self.get_ref_cp(ref2cp):
                    tmp_v = self.__slots2format(slots, ref_cp)
                    date = tmp_v.split('T')[0]
                    if len(date.split('-')) == 3 and \
                        all(x.isdigit() for x in date.split('-')) and \
                        f'WXX-{datetime.strptime(date,"%Y-%m-%d").weekday()+1}' == f'{next_cp.get_tcobj("YOUBI").value}':
                        v = tmp_v
                        self.v_list[cpid] = v
                        self.v_list[cpid+1] = v
                        return True
        return False
