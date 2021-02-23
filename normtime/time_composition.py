import re
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import copy
from collections import OrderedDict, namedtuple, defaultdict
from .const import TimeClass, TimexType, RefType

@dataclass
class TimeData:
    timeclass: str # Elements of TimeClass
    value: str
    ref: str = ""
    rel: str = None # One of: -1, 0, 1, None



class TimeComposition(object):
    """ A timex consists of Several TimeData classes.
    """
    def __init__(self, TYPE, sent_id=-1, begin_strid=-1, end_strid=-1):
        self.timedict = OrderedDict()
        self.sent_id = sent_id
        self.TYPE = TYPE
        self.begin_strid = begin_strid
        self.end_strid = end_strid

    def add(self, timedata):
        self.timedict[timedata.timeclass] = timedata

    def get_finest_timedata(self):
        if not self.timedict:
            return TimeData(timeclass='', value='', ref='', rel=None)
        return list(self.timedict.values())[-1]

    def get_timedata(self, tc, default_value=''):
        if tc not in self.timedict:
            return TimeData(timeclass='', value=default_value, ref='', rel=None)
        return self.timedict[tc]

    def isValid(self):
        return len(self.timedict)



def resolver(time_compositions, dct):
    """ Given a list of TimeComposition and DCT, returns vfs and value.

    Args:
        time_compositions (List[TimeComposition])
        dct (str)

    Yields:
        Tuple[str, str]: valueFromSurface and value.
    """
    time_compositions = resolve_parallel(time_compositions)
    time_compositions = resolve_functions(time_compositions)
    vfs_list = calc_vfs(time_compositions)
    v_list = calc_value(time_compositions, vfs_list, dct)
    for vfs, v in zip(vfs_list, v_list):
        yield vfs, v



def calc_vfs(time_compositions):
    """ Calculate valueFromSurface from TimeComposition.

    Args:
        time_compositions (List[TimeComposition])

    Returns:
        List[str]: List of valueFromSurface
    """
    vfs_list = [None] * len(time_compositions)
    for cpid, cp in enumerate(time_compositions):
        if not cp.isValid(): # ルールがマッチしなかった場合
            vfs_list[cpid] = ''
            continue

        if cp.TYPE in (TimexType.DATE, TimexType.TIME):
            # 2年前 → Q-2Y
            if any(td.timeclass==TimeClass.FUN for td in cp.timedict.values()):
                vfs = 'Q+' if cp.get_timedata('FUN').rel == 1 \
                        else 'Q-' if cp.get_timedata('FUN').rel == -1 \
                        else 'Q'
                for td in cp.timedict.values():
                    if td.timeclass in [TimeClass.FUN, TimeClass.MOD]:
                        continue
                    vfs += td.value+td.timeclass[0]
                vfs_list[cpid] = vfs
                continue

            # XXXX-XX-XXTXX:XX:XX形式
            # 各要素の値埋め
            phrase = None
            slots = [None]*6 # 6 slots
            for td in cp.timedict.values():
                tc = td.timeclass
                if not td.timeclass:
                    continue
                strnum = td.value
                if tc == TimeClass.CENTURY and slots[0] is None:
                    slots[0] = 'XXXX' if td.ref \
                        else f'{int(strnum)-1}XX' if strnum.isdigit() \
                        else strnum
                if tc == TimeClass.GYEAR and slots[0] is None:
                    slots[0] = strnum
                elif tc == TimeClass.GYEARX and slots[0] is None:
                    slots[0] = f'{strnum[:-1]}X'
                elif tc in (TimeClass.YEAR, TimeClass.YEARX) and slots[0] is None:
                    if td.ref:
                        slots[0] = 'XXXX'
                    elif len(strnum) <= 2: # 02年, 直前が平成XX年の場合はH02とする
                        if cpid > 0 and vfs_list[cpid-1].startswith('H') and strnum.isdigit():
                            slots[0] = f'H{int(strnum):02}'
                        elif cpid > 0 and vfs_list[cpid-1].startswith('S') and strnum.isdigit():
                            slots[0] = f'S{int(strnum):02}'
                        else: 
                            slots[0] = 'X'*(4-len(strnum))+strnum
                    else:
                        slots[0] = strnum
                    if tc == TimeClass.YEARX:
                        slots[0] = f'{slots[0][:-1]}X'
                elif tc == TimeClass.GFYEAR and slots[0] is None:
                    slots[0] = f'FY{strnum}'
                elif tc == TimeClass.FYEAR and slots[0] is None:
                    slots[0] = 'FYXXXX' if td.ref \
                                else 'FY'+'X'*(4-len(strnum))+strnum if len(strnum) <= 2\
                                else f'FY{strnum}'
                elif tc in [TimeClass.MONTH, TimeClass.SEASON, TimeClass.YOUBI] and slots[1] is None:
                    slots[1] = 'XX' if strnum == 'X' or td.ref\
                                    else '0'*(2-len(strnum))+strnum
                elif tc == TimeClass.WEEK and slots[1] is None:
                    slots[1] = 'WXX'
                elif tc in [TimeClass.DAY, TimeClass.JUN] and slots[2] is None:
                    slots[2] = 'XX' if strnum == 'X' or td.ref\
                                    else '0'*(2-len(strnum))+strnum
                elif tc == TimeClass.HOUR and slots[3] is None:
                    slots[3] = 'XX' if strnum == 'X' or td.ref\
                                else '0'*(2-len(strnum))+strnum
                elif tc == TimeClass.MINUTE and not slots[4]:
                    slots[4] = 'XX' if strnum == 'X' or td.ref\
                                else '0'*(2-len(strnum))+strnum
                elif tc == TimeClass.SECOND and not slots[5]:
                    slots[5] = 'XX' if strnum == 'X' or td.ref\
                                else '0'*(2-len(strnum))+strnum
                elif tc == TimeClass.PHRASE:
                    phrase = strnum

            vfs = slots2format(slots)
            if vfs == '' and phrase:
                vfs = phrase
            vfs_list[cpid] = vfs

        elif cp.TYPE == TimexType.SET \
            and cp.get_timedata(TimeClass.YOUBI).value: # 毎週火曜日 --> XXXX-WXX-2
            vfs_list[cpid] = f'XXXX-{cp.get_timedata("YOUBI").value}'

        else: # DURATION
            vfs = 'P'
            phrase = ''
            Flag = True
            used_tcs = [] # P16Y16Yみたいなことがないように
            for td in cp.timedict.values():
                tc = td.timeclass
                if tc == TimeClass.PHRASE:
                    phrase = td.value
                    continue
                if Flag and (tc in [TimeClass.HOUR, TimeClass.MINUTE, TimeClass.SECOND]):
                    vfs += 'T'
                    Flag = False
                if tc not in used_tcs and td.value:
                    if tc == TimeClass.NUM:
                        continue
                    if tc == TimeClass.FYEAR:
                        vfs += f'{td.value}FY'
                    else:
                        vfs += f'{td.value}{tc[0]}'
                    used_tcs.append(tc)
            if vfs == '' and phrase:
                vfs = phrase
            if vfs == 'P' and cp.get_timedata('NUM').value: # FIXME とりあえずNUMはYearと見なす
                vfs += f'{cp.get_timedata("NUM").value}Y'

            if vfs == 'P': # 正規化に失敗
                vfs = 'None'

            vfs_list[cpid] = vfs
    return vfs_list


def slots2format(slots, ref_cp=None):
    """ Convert slots into TIMEX3 format.

    Args:
        slots (List[str])
        ref_cp (TimeComposition)

    Returns:
        str
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
                vfs = f'{ref_cp.get_timedata("YEAR", default_value="XXXX").value}-{vfs}' if i==0 \
                    else f'{ref_cp.get_timedata("MONTH", default_value="XX").value}-{vfs}' if i==1 \
                    else f'{ref_cp.get_timedata("DAY", default_value="XX").value}T{vfs}' if i==2 \
                    else f'{ref_cp.get_timedata("HOUR", default_value="XX").value}:{vfs}' if i==3 \
                    else f'{ref_cp.get_timedata("MINUTE", default_value="XX").value}:{vfs}'
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


def get_ref_cp(ref2cp, ref=None):
    if (ref == RefType.DCT or not ref2cp.get(RefType.REF)):
        return ref2cp[RefType.DCT]
    return ref2cp[RefType.REF]+ref2cp[RefType.DCT]


def calc_value(time_compositions, vfs_list, dct):
    """ Calculate value from valueFromSurface.

    Args:
        time_compositions (List[TimeComposition])
        vfs_list (List[str])
        dct (str)

    Returns:
        List[str]
    """
    v_list = copy.deepcopy(vfs_list)

    for cpid, cp in enumerate(time_compositions):
        v = v_list[cpid]
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
            v_list[cpid] = v
            _, v_list = resolve_youbi(time_compositions, v_list, cpid, v=v)
            continue

        # Finde REF
        ref2cp = find_refs(cpid, time_compositions, v_list, dct)

        # 「N年前」の正規化
        if len(cp.timedict) > 1 and TimeClass.FUN in cp.timedict:
            val = ''
            ref_cp = get_ref_cp(ref2cp)[0]
            rel = cp.get_timedata('FUN').rel if cp.get_timedata('FUN').rel else 0
            cp_min_tc = [td for td in cp.timedict.values() if td.timeclass != 'FUN'][-1].timeclass

            # 「N週間前」→ WEEK情報をDAY情報に変換
            if TimeClass.WEEK in cp.timedict and cp.timedict[TimeClass.WEEK].value.isdigit():
                if TimeClass.DAY in cp.timedict:
                    if cp.timedict[TimeClass.DAY].isdigit():
                        cp.timedict[TimeClass.DAY].value += 7*int(cp.timedict[TimeClass.WEEK].value)
                else:
                    cp.timedict[TimeClass.DAY] = TimeData(
                        timeclass=TimeClass.DAY,
                        value=str(7*int(cp.timedict[TimeClass.WEEK].value)))

            # Calc slots
            slots = [None]*6
            for i, tc in enumerate([TimeClass.YEAR, TimeClass.MONTH, TimeClass.DAY,
                                    TimeClass.HOUR, TimeClass.MINUTE, TimeClass.SECOND]):
                if not ref_cp.get_timedata(tc).value.isdigit() \
                    and cp.get_timedata(tc).value != 'X':
                    break
                if cp.get_timedata(tc).value.isdigit():
                    diff = int(cp.get_timedata(tc).value)*rel
                    new_val = int(ref_cp.get_timedata(tc).value) + diff
                    if tc == TimeClass.MONTH and (new_val < 1 or new_val > 12):
                        slots[0] = str(int(slots[0]) + new_val//12)
                        slots[1] = str(new_val%12)
                        if len(slots[1]) == 1:
                            slots[1] = f"0{slots[1]}"
                    elif tc == TimeClass.DAY:
                        ref_date = datetime(int(slots[0]), int(slots[1]), int(ref_cp.get_timedata(tc).value))
                        new_date = ref_date + timedelta(days=diff)
                        slots[0], slots[1], slots[2] = new_date.strftime('%Y-%m-%d').split('-')
                    else: # FIXME HOUR/MINUTE/SECONDへの対応: ex.「100時間後」
                        slots[i] = str(int(ref_cp.get_timedata(tc).value) + diff)
                elif cp.get_timedata(tc).value == 'X':
                    slots[i] = 'XXXX' if tc == TimeClass.YEAR else 'XX'
                else:
                    slots[i] = ref_cp.get_timedata(tc).value

                if tc == cp_min_tc:
                    break
            v_list[cpid] = slots2format(slots)
            continue

        # XXXX-XX-XXTXX:XX:XX形式
        phrase = None
        slots = [None]*6
        for td in cp.timedict.values():
            tc = td.timeclass
            if tc == TimeClass.CENTURY and slots[0] is None:
                if td.rel is not None:
                    ref_cp = get_ref_cp(ref2cp, td.ref)[0]
                    ref_year = ref_cp.get_timedata(TimeClass.YEAR).value
                    if td.value.isdigit(): # 「前世紀」
                        slots[0] = f'{int(ref_year[:2]) + td.rel*int(td.value)}XX'
                    elif td.rel == 0: # 「今年」
                        slots[0] = f'{int(ref_year[:2])}XX'
            elif tc in [TimeClass.GYEAR, TimeClass.GYEARX, TimeClass.YEAR,
                        TimeClass.YEARX, TimeClass.FYEAR] \
                and slots[0] is None:
                ref_cp = get_ref_cp(ref2cp, td.ref)[0]
                ref_year = ref_cp.get_timedata(TimeClass.YEAR).value
                if td.rel is not None:
                    if td.value.isdigit(): # 「昨年」「来年」
                        slots[0] = str(int(ref_year) + td.rel*int(td.value))
                    elif td.rel == 0: # 「今年」
                        slots[0] = ref_year
                elif len(td.value) == 2: # 「02年」「30年代」
                    k1 = ref_year[:2] + td.value.replace('X','0')
                    k2 = str(int(ref_year[:2])+1) + td.value.replace('X','0')
                    k3 = str(int(ref_year[:2])-1) + td.value.replace('X','0')
                    ks = [k1,k2,k3]
                    diffs = [math.fabs(int(k)-int(ref_year)) for k in ks]
                    val = ks[diffs.index(min(diffs))] # 候補k1-k3の中で、refと一番近いものを選択
                    if 'X' in td.value:
                        slots[0] = f'{val[:-1]}X'
                    else: # 「N年代」
                        slots[0] = val
                else: # 「2002年」
                    slots[0] = td.value
                # 「X年度」
                if slots[0] and tc == TimeClass.FYEAR:
                    slots[0] = f'FY{slots[0]}'

            elif tc == TimeClass.WEEK and slots[1] is None:
                slots[1] = 'WXX'

            elif tc in (TimeClass.MONTH, TimeClass.SEASON, TimeClass.YOUBI) \
                and slots[1] is None:
                if td.value == 'X':
                    slots[1] = 'XX'   # "何月"が'0X'とならないように
                elif td.timeclass == TimeClass.MONTH and td.ref: # 「先月」「今月」
                    for ref_cp in get_ref_cp(ref2cp, td.ref):
                        ref_year = ref_cp.get_timedata(TimeClass.YEAR).value
                        ref_month = ref_cp.get_timedata(TimeClass.MONTH).value
                        if not (ref_year and ref_month): # MONTHスロットがない場合
                            continue
                        if td.rel == 0: # 「今月」
                            slots[0] = ref_year
                            slots[1] = f'{int(ref_month):02}'
                        elif td.value.isdigit():
                            m = int(ref_month) + td.rel*int(td.value)
                            if m < 1 or m > 12:
                                slots[0] = f'{int(ref_year)+m//12}'
                                slots[1] = f'{m%12:02}'
                            else:
                                slots[1] = f'{m:02}'
                                slots[0] = ref_year
                        break
                    else: # DCTにMonthがない場合
                        slots[1] = 'XX'
                else:
                    slots[1] = '0'*(2-len(td.value))+td.value

            elif tc in ['DAY'] and slots[2] is None:
                if td.value == 'X':
                    slots[2] = 'XX'   
                elif td.timeclass == 'DAY' and td.ref:
                    for ref_cp in get_ref_cp(ref2cp, td.ref):
                        ref_year = ref_cp.get_timedata(TimeClass.YEAR).value
                        ref_month = ref_cp.get_timedata(TimeClass.MONTH).value
                        ref_day = ref_cp.get_timedata(TimeClass.DAY).value
                        if not (ref_year and ref_month and ref_day): # DAYスロットがない場合
                            continue
                        if td.rel == 0: # 今日
                            slots[0] = ref_year
                            slots[1] = ref_month
                            slots[2] = f'{int(ref_day):02}'
                        elif td.value.isdigit():
                            diff_day = td.rel*int(td.value)
                            ref_date = datetime.strptime(f'{ref_year}-{ref_month}-{ref_day}', '%Y-%m-%d')
                            new_date = ref_date + timedelta(days=diff_day)
                            slots[0],slots[1],slots[2] = new_date.strftime('%Y-%m-%d').split('-')
                        break
                    else:
                        slots[2] = 'XX'
                else:
                    slots[2] = '0'*(2-len(td.value))+td.value

            elif tc == TimeClass.JUN and slots[2] is None:
                slots[2] = 'XX' if td.value == 'X' or td.ref \
                            else '0'*(2-len(td.value))+td.value

            elif tc == TimeClass.HOUR and slots[3] is None:
                if td.value == 'X':
                    slots[3] = 'XX'
                else:
                    strnum = td.value
                    if td.value.isdigit() and int(td.value) >= 24:
                        strnum = str(int(strnum)-24)
                    slots[3] = '0'*(2-len(strnum))+strnum

            elif tc == TimeClass.MINUTE and slots[4] is None:
                slots[4] = 'XX' if td.value == 'X' \
                            else '0'*(2-len(td.value))+td.value

            elif tc == TimeClass.SECOND and slots[5] is None:
                slots[5] = 'XX' if td.value == 'X' \
                            else '0'*(2-len(td.value))+td.value

            elif tc == 'PHRASE':
                phrase = td.value

        resolvedFlag, v_list = resolve_youbi(time_compositions, v_list, cpid,
                                             ref2cp=ref2cp, slots=slots)
        if not resolvedFlag:
            v = phrase if phrase and all(x is None for x in slots)\
                    else slots2format(slots, get_ref_cp(ref2cp)[0])
            v_list[cpid] = v
    return v_list


def find_refs(cpid, time_compositions, v_list, dct):
    """
    Returns:
        Dict[str, List[]]
    """
    cp = time_compositions[cpid]
    ref2cp = defaultdict(list) # {"DCT": [dct_cp],  "REF": [ref_cp]}
    tc_ymd = (TimeClass.YEAR, TimeClass.MONTH, TimeClass.DAY)
    tc_hms = (TimeClass.HOUR, TimeClass.MINUTE, TimeClass.SECOND)

    # Add DCT
    dct_cp = TimeComposition(TimexType.DATE)
    dct_ymd = dct.split('T')[0].split('-')
    for tc, val in zip(tc_ymd, dct_ymd):
        dct_cp.add(TimeData(timeclass=tc, value=val))
    ref2cp[RefType.DCT].append(dct_cp)

    # Add refs
    # FIXME どのようにREFを選択するか
    for i in range(cpid-1,-1,-1):
        bef_cp = time_compositions[i]
        bef_v = v_list[i]
        if bef_cp.sent_id == cp.sent_id: # 同じ文で先に出現したDATE/TIMEをREFとする
            if bef_cp.TYPE in (TimexType.DATE, TimexType.TIME):
                ref_cp = TimeComposition(TimexType.DATE)
                for tc,val in zip(tc_ymd, bef_v.split('T')[0].split('-')):
                    if val.isdigit():
                        ref_cp.add(TimeData(timeclass=tc, value=val))
                    elif re.match('FY\d+', val):
                        ref_cp.add(TimeData(timeclass=tc, value=val[2:]))
                    else:
                        break
                if ref_cp.isValid():
                    if 'T' in bef_v:
                        for tc,val in zip(tc_hms, bef_v.split('T')[1].split(':')):
                            if val.isdigit():
                                ref_cp.add(TimeData(timeclass=tc, value=val))
                            else:
                                break
                    ref2cp[RefType.REF].append(ref_cp)
        elif not ref2cp[RefType.REF] and i == cpid-1 and \
                any(td.ref==RefType.REF for td in cp.timedict.values()): # 文の先頭でかつrelationなとき
            if bef_cp.TYPE not in (TimexType.DATE, TimexType.TIME) or \
                len(list(bef_cp.timedict)) == 0 or \
                cp.sent_id-bef_cp.sent_id > 1:
                break
            ref_cp = TimeComposition(TimexType.DATE)
            for tc,val in zip(tc_ymd, bef_v.split('T')[0].split('-')):
                if val.isdigit():
                    ref_cp.add(TimeData(timeclass=tc, value=val))
            if ref_cp.isValid():
                ref2cp[RefType.REF].append(ref_cp)
            break
        else:
            break
    return ref2cp


def resolve_youbi(time_compositions, v_list, cpid, v=None, ref2cp=None, slots=None):
    """ Merge successive date and youbi.

    Returns:
        Tuple[bool, List[str]]
    """
    cp = time_compositions[cpid]
    next_cp = None if cpid+1 == len(time_compositions) \
        else time_compositions[cpid+1]
    if next_cp and cp.sent_id==next_cp.sent_id \
        and len(next_cp.timedict) == 1 \
        and TimeClass.YOUBI in next_cp.timedict \
        and 0 <= next_cp.begin_strid-cp.end_strid <= 1:
        if v:
            v_list[cpid] = v
            v_list[cpid+1] = v
            return True, v_list
        elif ref2cp and slots:
            for ref_cp in get_ref_cp(ref2cp):
                tmp_v = slots2format(slots, ref_cp)
                date = tmp_v.split('T')[0]
                if len(date.split('-')) == 3 and \
                    all(x.isdigit() for x in date.split('-')) and \
                    f'WXX-{datetime.strptime(date,"%Y-%m-%d").weekday()+1}' == f'{next_cp.get_timedata("YOUBI").value}':
                    v = tmp_v
                    v_list[cpid] = v
                    v_list[cpid+1] = v
                    return True, v_list
    return False, v_list


def resolve_parallel(time_compositions):
    """
        並列処理 ex. 17、18日
    """
    for cpid, cp in reversed(list(enumerate(time_compositions[:-1]))):
        if cp.isValid() \
            and all(td.timeclass == TimeClass.NUM for td in cp.timedict.values()) \
            and time_compositions[cpid+1].sent_id == cp.sent_id \
            and time_compositions[cpid+1].begin_strid-cp.end_strid == 1 \
            and len(list(time_compositions[cpid+1].timedict.values()))==1:
            tc = list(time_compositions[cpid+1].timedict.values())[0].timeclass
            new_cp = TimeComposition(cp.TYPE, cp.begin_strid, cp.end_strid)
            if tc.endswith('X'): # YEARX
                new_cp.add(
                    TimeData(timeclass=tc,
                             value=f'{cp.get_timedata(TimeClass.NUM).value[:-1]}X'))
            else:
                new_cp.add(
                    TimeData(timeclass=tc,
                             value=cp.get_timedata(TimeClass.NUM).value))
            time_compositions[cpid] = new_cp
    return time_compositions


def resolve_functions(time_compositions):
    """
        FUNCTION (ex. 半日) の0.5倍の処理
    """
    for cpid, cp in enumerate(time_compositions):
        if cp.TYPE in (TimexType.DURATION, TimexType.SET) \
            and cp.get_timedata('FUN').value == '0.5' \
            and all(td.value.isdigit() for td in cp.timedict.values()
                    if td.timeclass != 'FUN'):
            new_cp = TimeComposition(
                cp.TYPE, begin_strid=cp.begin_strid, end_strid=cp.end_strid)
            for td in cp.timedict.values():
                if td.timeclass == 'FUN':
                    continue
                val = float(cp.get_timedata(td.timeclass).value)/2
                if val.is_integer(): # 整数
                    new_cp.add(
                        TimeData(timeclass=td.timeclass, value=str(int(val))))
                else:
                    new_cp.add(
                        TimeData(timeclass=td.timeclass, value=f'{val:.1f}'))
            time_compositions[cpid] = new_cp
    return time_compositions
