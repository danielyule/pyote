import json


class Operation(object):
    def __init__(self, position):
        """
        Creates a new operation that is based on the given state
        :param int position: The position in the buffer that this operation takes effect in
        """
        self.state = None
        self.position = position

    def __getstate__(self):
        """
        Generates a dictionary that stores information for this operation
        :rtype: dict [str, object]
        """
        return {
            'state': self.state,
            'position': self.position,
        }

    def __setstate__(self, state):
        self.state = state['state']
        self.position = state['position']

    def __repr__(self):
        return json.dumps(self, default=lambda o: o.__getstate__())

    def __eq__(self, other):
        return self.__repr__() == other.__repr__()

    def get_increment(self):
        """
        Gets the amount that this operation will adjust the position of operations that come after it
        """
        return 0


class InsertOperation(Operation):
    """
    Inserts a value into the buffer at the specified position
    """
    __slots__ = ['state', 'position', 'value']

    def __init__(self, position, value):
        Operation.__init__(self, position)
        self.value = value

    def __getstate__(self):
        sstate = Operation.__getstate__(self)
        sstate.update({
            'type': 'insert',
            'value': self.value
        })
        return sstate

    def __setstate__(self, state):
        Operation.__setstate__(self, state)
        self.value = state['value']

    def get_increment(self):
        """
        Gets the amount that this operation will adjust the position of operations that come after it
        """
        return len(self.value)

    def __repr__(self):
        return "{{'position': {}, 'value': \"{}\"}}".format(self.position, self.value)


class DeleteOperation(Operation):
    """
    Deletes some amount of values from the buffer at the specified position
    """
    __slots__ = ['state', 'position', 'length']

    def __init__(self, position, length):
        Operation.__init__(self, position)
        self.length = length

    def __getstate__(self):
        sstate = Operation.__getstate__(self)
        sstate.update({
            'type': 'remove',
            'length': self.length
        })
        return sstate

    def __setstate__(self, state):
        Operation.__setstate__(self, state)
        self.length = state['length']

    def get_increment(self):
        """
        Gets the amount that this operation will adjust the position of operations that come after it
        """
        return -self.length

    def __repr__(self):
        return "{{'position': {}, 'length': {}}}".format(self.position, self.length)
