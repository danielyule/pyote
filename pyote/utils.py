from copy import deepcopy


class TransactionSequence(object):
    def __init__(self, starting_state=None, inserts=None, deletes=None):
        """

        :param State starting_state:
        :param InsertOperationNode inserts:
        :param DeleteOperationNode deletes:
        :return:
        """
        self.starting_state = starting_state
        """:type: pyote.utils.State"""
        self.inserts = inserts
        """:type: pyote.utils.InsertOperationNode"""
        self.deletes = deletes
        """:type: pyote.utils.DeleteOperationNode"""

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

    def __getstate__(self):
        return {
            'inserts': self.inserts.to_list(),
            'deletes': self.deletes.to_list(),
            'starting_state': self.starting_state
        }


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

    def to_list(self):
        """
        Converts a linked list to a standard python list
        :param OperationNode self: The linked list to convert
        :return: The converted list
        :rtype: list
        """
        lst = []
        node = self
        while node:
            lst.append(node.value)
            node = node.next
        return lst


class InsertOperationNode(OperationNode):
    __slots__ = ["value", "next"]

    def __init__(self, value):
        """
        Create a new node in a linked list of InsertionOperations
        :param pyote.operations.InsertOperation value: The value this node holds
        """
        OperationNode.__init__(self, value)

    @classmethod
    def from_list(cls, lst):
        """
        Converts a standard python list into a linked list that the engine can use
        :param list[InsertOperation] lst: The list to convert
        :return: A linked list
        :rtype: pyote.utils.InsertOperationNode
        """
        if len(lst) == 0:
            return None
        llist = InsertOperationNode(lst.pop(0))
        head = llist
        for op in lst:
            llist.next = InsertOperationNode(op)
            llist = llist.next

        return head

    def __copy__(self):
        new_node = InsertOperationNode(deepcopy(self.value))
        new_node.next = self.next
        return new_node


class DeleteOperationNode(OperationNode):
    __slots__ = ["value", "next"]

    def __init__(self, value):
        """
        Create a new node in a linked list of DeleteOperations
        :param pyote.operations.DeleteOperation value: The value this node holds
        """
        OperationNode.__init__(self, value)

    @classmethod
    def from_list(cls, lst):
        """
        Converts a standard python list into a linked list that the engine can use
        :param list[DeleteOperation] lst: The list to convert
        :return: A linked list
        :rtype: DeleteOperationNode
        """
        if len(lst) == 0:
            return None
        llist = DeleteOperationNode(lst.pop(0))
        head = llist
        for op in lst:
            llist.next = DeleteOperationNode(op)
            llist = llist.next

        return head

    def __copy__(self):
        new_node = DeleteOperationNode(deepcopy(self.value))
        new_node.next = self.next
        return new_node


class State(object):
    def __init__(self, site_id, local_time, remote_time):
        self.site_id = site_id
        self.local_time = local_time
        self.remote_time = remote_time

    def __getstate__(self):
        return {
            'site_id': self.site_id,
            'local_time': self.local_time,
            'remote_time': self.remote_time,
        }

    def __setstate__(self, state):
        self.site_id = state['site_id']
        self.local_time = state['local_time']
        self.remote_time = state['remote_time']
