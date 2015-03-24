from copy import deepcopy


class TransactionSequence(object):
    def __init__(self, starting_state, inserts=None, deletes=None):
        self.starting_state = starting_state
        self.inserts = inserts
        self.deletes = deletes

    def __repr__(self):
        return "inserts: {}\ndeletes: {}".format(self._print_nodes(self.inserts), self._print_nodes(self.deletes))

    def _print_nodes(self, nodes, first_time=True):
        if first_time:
            if nodes:
                return "[{}{}".format(nodes.value, self._print_nodes(nodes.next, False))
            return "[]"
        if nodes:
            return ", {}{}".format(nodes.value, self._print_nodes(nodes.next, False))
        return "]"


class OperationNode(object):
    __slots__ = ["value", "next"]

    def __init__(self, value):
        self.value = value
        self.next = None

    def __eq__(self, other):
        return self.value == other.value and self.next == other.next

    def __copy__(self):
        new_node = OperationNode(deepcopy(self.value))
        new_node.next = self.next
        return new_node

    def __repr__(self):
        return str(self.value)

    def __getitem__(self, item):
        if item == 0:
            return self.value
        else:
            return self.next[item - 1]


class State(object):
    def __init__(self, site_id, local_time, remote_time):
        self.site_id = site_id,
        self.local_time = local_time
        self.remote_time = remote_time

    def __getstate__(self):
        return {
            'site_id': self.site_id,
            'local_time': self.local_time,
            'remote_time': self.remote_time,
        }

    def __setstate(self, state):
        self.site_id = state['site_id']
        self.local_time = state['local_time']
        self.remote_time = state['remote_time']
