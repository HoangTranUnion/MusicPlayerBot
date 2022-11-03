from collections import defaultdict
from typing import Dict, List


class Vault:
    """A general vault for storing datas that are not immediately processed between classes. 
    """
    def __init__(self):
        self._data: Dict[int, List] = defaultdict(list)

    def add_data(self, id_, data):
        self._data[id_].append(data)

    def get_data(self, id_):
        return self._data[id_].pop(0)

    def isEmpty(self, id_):
        return not self._data[id_]

    def __getitem__(self, item):
        if item in self._data:
            return self._data[item]

    
class Sender:
    """A sender to send the items to the Vault.
    """
    def __init__(self, id_:int, vault: Vault):
        self._vault = vault
        self._id = id_

    def send(self, data):
        self._vault.add_data(self._id, data)
