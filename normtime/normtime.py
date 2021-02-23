import os
from datetime import datetime
from collections import namedtuple
from .rule import ApplyRule
from .time_composition import resolver

TIMEX = namedtuple('TIMEX', ('str', 'begin_strid', 'end_strid', 'TYPE'))

def normalize(text, TYPE="DATE", dct=datetime.now().strftime('%Y-%m-%d')):
    timex = TIMEX(str=text, begin_strid=0, end_strid=len(text), TYPE=TYPE)
    vfs, v = NormTime().normalize([(text,[timex])], dct).__next__()
    return v


class NormTime(object):
    def __init__(self, debug=False):
        self.apply_rule = ApplyRule(debug)

    def normalize(self, doc, dct):
        time_compositions = self.apply_rule.get_time_compositions(doc)
        for vfs, v in resolver(time_compositions, dct):
            yield vfs, v
