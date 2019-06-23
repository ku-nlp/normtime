import os
from .rule import ApplyRule

class NormTime(object):
    def __init__(self, debug=False):
        self.AR = ApplyRule(debug)

    def normalize(self, doc, dct):
        time_manager = self.AR.get_time_compositions(doc, dct=dct)
        for vfs, v in time_manager.get_values():
            yield vfs, v
