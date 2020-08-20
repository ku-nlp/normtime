import os
from datetime import datetime
from collections import namedtuple
from .rule import ApplyRule

TIMEX = namedtuple('TIMEX', ('str', 'begin_strid', 'end_strid', 'TYPE'))

def normalize(text, TYPE="DATE", dct=datetime.now().strftime('%Y-%m-%d')):
    timex = TIMEX(str=text, begin_strid=0, end_strid=len(text), TYPE=TYPE)
    vfs, v = NormTime().normalize([(text,[timex])], dct).__next__()
    return v


class NormTime(object):
    def __init__(self, debug=False):
        self.AR = ApplyRule(debug)

    def normalize(self, doc, dct):
        time_manager = self.AR.get_time_compositions(doc, dct=dct)
        for vfs, v in time_manager.get_values():
            yield vfs, v
