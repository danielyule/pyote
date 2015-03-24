from copy import deepcopy, copy

from pyote.operations import DeleteOperation
from pyote.utils import TransactionSequence, OperationNode


class OTException(Exception):
    pass


class Engine(object):
    def __init__(self, site_id):
        """
        Initialize the history at this site.
        The history at a site is represented as a sequence of insert operations, followed by a sequence of delete
        operations.  The operations are kept in "effect order," meaning that insertions which happen at a lower
        position in the buffer are stored before those which happen at a higher position, and similarly for
        deletions

        :param integer site_id: An id which uniquely identifies this site across all peers
        """

        #: The inserts for this site stored in effect order as a linked list
        self._inserts = None
        #: The deletes for this site stored in effect order as a linked list
        self._deletes = None
        #: The unique id for this site
        self.site_id = site_id

    def integrate_remote(self, remote_sequence):
        """
        Integrates the sequence of operations given by `remote_sequence` into the local history.  The ordering
        properties of the local history (see :meth:__init__) will be maintained, and a sequence of operations that
        can be applied to the local state will be returned.
        :param remote_sequence: A transaction sequence representing the operation to integrate into local history
        :type remote_sequence: pyote.utils.TransactionSequence
        :rtype: pyote.utils.TransactionSequence
        """
        local_concurrent_inserts = self._get_concurrent(remote_sequence.starting_state, self._inserts)
        transformed_remote_inserts = self._transform_insert_insert(remote_sequence.inserts, local_concurrent_inserts)
        new_remote_inserts = self._transform_insert_delete(transformed_remote_inserts, self._deletes)
        self._inserts = self._merge_sequence(self._inserts, transformed_remote_inserts)

        transformed_local_deletes = self._transform_delete_insert(self._deletes, transformed_remote_inserts)
        transformed_remote_deletes = self._transform_delete_insert(remote_sequence.deletes, local_concurrent_inserts)
        new_remote_deletes = self._transform_delete_delete(transformed_remote_deletes, transformed_local_deletes)
        self._deletes = self._merge_sequence(transformed_local_deletes, new_remote_deletes)

        return TransactionSequence(remote_sequence.starting_state, new_remote_inserts, new_remote_deletes)

    def _get_concurrent(self, starting_state, remote_sequence):
        """
        Gets all operations in the insertion sequence which happened after the given starting state
        :param pyote.utils.State starting_state: The state to use as a reference
        :param  remote_sequence: The sequence of events to look for events within
        :type remote_sequence: list[pyote.operations.DeleteOperation] | list[pyote.operations.InsertOperation]
        :rtype: pyote.utils.OperationNode
        """
        local_ref = -1
        # Look through all operations in our history
        node = self._inserts
        while node:
            operation = node.value
            # If the operation matches the starting state
            if operation.state.site_id == starting_state.site_id and \
                    operation.state.remote_time == starting_state.remote_time:
                # Then record the corresponding local time
                local_ref = operation.state.local_time
                break
            node = node.next

        # If we didn't find a matching operation in the inserts, check in the deletes
        if local_ref == -1:
            node = self._deletes
            while node:
                operation = node.value
                # If the operation matches the starting state
                if operation.state.site_id == starting_state.site_id and \
                        operation.state.remote_time == starting_state.remote_time:
                    # Then record the corresponding local time
                    local_ref = operation.state.local_time
                    break
                node = node.next

        # If we didn't find a matching operation, then we can't yet apply the sequence that relies on the starting state
        if local_ref == -1:
            raise OTException()

        # Find all the operations in the insertion sequence which happened after local_ref
        concurrents = None
        concurrent_head = concurrents
        node = remote_sequence

        while node:
            if node.value.state.local_time > local_ref:
                if concurrents:
                    concurrents.next = OperationNode(node.value)
                    concurrents = concurrents.next
                else:
                    concurrents = OperationNode(node.value)
                    concurrent_head = concurrents
            node = node.next

        return concurrent_head

    def _transform_insert_insert(self, incoming_sequence, existing_sequence):
        """
        Performs inclusive transformation on sequence1 with sequence2, meaning that the effects of `existing sequence`
        are incorporated in `incoming_sequence`
        :param pyote.utils.OperationNode incoming_sequence: The sequence that will be transformed
        :param pyote.utils.OperationNode existing_sequence: The sequence with operations that will perform the
                                                                   transformation
        :returns: The incoming sequence with the operations in the existing sequence taken into account
        :rtype: pyote.utils.OperationNode
        """
        incoming_value_size = 0
        existing_value_size = 0
        transformed_sequence = None
        transformed_head = None
        incoming_node = incoming_sequence
        existing_node = existing_sequence
        # Walk through both sequences, one at a time.
        while existing_node and incoming_node:
            # Calculate what the position of the operation would be if it were performed now, rather than
            # after all other operations before it in the sequence.
            existing_pos = existing_node.value.position - existing_value_size
            incoming_pos = incoming_node.value.position - incoming_value_size
            # If the position of the insert in the existing sequence comes before the insert in the incoming sequence,
            # then record how much it would move the insertion position forward.
            if existing_pos < incoming_pos:
                existing_value_size += existing_node.value.get_increment()
                existing_node = existing_node.next
            elif existing_pos == incoming_pos and \
                existing_node.value.state.site_id < \
                    incoming_node.value.state.site_id:
                existing_value_size += existing_node.value.get_increment()
                existing_node = existing_node.next
            else:
                # Otherwise, update the position of the incoming sequence's operation, and record how much it would
                # move the position forward after it's applied.
                if transformed_sequence:
                    transformed_sequence.next = copy(incoming_node)
                    transformed_sequence = transformed_sequence.next
                else:
                    transformed_sequence = copy(incoming_node)
                    transformed_head = transformed_sequence
                transformed_sequence.value.position += existing_value_size
                incoming_value_size += incoming_node.value.get_increment()
                incoming_node = incoming_node.next

        # Take care of any elements that weren't handled in the above.
        while incoming_node:
            if transformed_sequence:
                transformed_sequence.next = copy(incoming_node)
                transformed_sequence = transformed_sequence.next
            else:
                transformed_sequence = copy(incoming_node)
                transformed_head = transformed_sequence
            transformed_sequence.value.position += existing_value_size
            incoming_node = incoming_node.next
        return transformed_head

    def _transform_delete_insert(self, incoming_sequence, existing_sequence):
        """
        Performs inclusive transformation on sequence1 with sequence2, meaning that the effects of `existing sequence`
        are incorporated in `incoming_sequence`
        :param pyote.utils.OperationNode incoming_sequence: The sequence that will be transformed
        :param pyote.utils.OperationNode existing_sequence: The sequence with operations that will perform the
                                                                   transformation
        :returns: The incoming sequence with the operations in the existing sequence taken into account
        :rtype: pyote.utils.OperationNode
        """
        incoming_value_size = 0
        existing_value_size = 0
        transformed_sequence = None
        transformed_head = None
        incoming_node = incoming_sequence
        existing_node = existing_sequence
        # Walk through both sequences, one at a time.
        while existing_node and incoming_node:
            # Calculate what the position of the operation would be if it were performed now, rather than
            # after all other operations before it in the sequence.
            existing_pos = existing_node.value.position - existing_value_size
            incoming_pos = incoming_node.value.position - incoming_value_size
            # If the position of the insert in the existing sequence comes before the insert in the incoming sequence,
            # then record how much it would move the insertion position forward.
            if existing_pos < incoming_pos:
                existing_value_size += existing_node.value.get_increment()
                existing_node = existing_node.next
            elif existing_pos == incoming_pos and \
                    existing_node.value.state.site_id < \
                    incoming_node.value.state.site_id:
                existing_value_size += existing_node.value.get_increment()
                existing_node = existing_node.next
            else:
                # Otherwise, update the position of the incoming sequence's operation, and record how much it would
                # move the position forward after it's applied.
                if transformed_sequence:
                    transformed_sequence.next = copy(incoming_node)
                    transformed_sequence = transformed_sequence.next
                else:
                    transformed_sequence = copy(incoming_node)
                    transformed_head = transformed_sequence
                transformed_sequence.value.position += existing_value_size
                incoming_value_size += incoming_node.value.get_increment()
                incoming_node = incoming_node.next

        # Take care of any elements that weren't handled in the above.
        while incoming_node:
            if transformed_sequence:
                transformed_sequence.next = copy(incoming_node)
                transformed_sequence = transformed_sequence.next
            else:
                transformed_sequence = copy(incoming_node)
                transformed_head = transformed_sequence
            transformed_sequence.value.position += existing_value_size
            incoming_node = incoming_node.next
        return transformed_head

    def _transform_insert_delete(self, incoming_sequence, existing_sequence):
        """
        Performs inclusive transformation on `incoming_sequence` with `existing_sequence`, meaning that the effects of
        `existing sequence` are incorporated in `incoming_sequence`
        :param pyote.utils.OperationNode incoming_sequence: The sequence that will be transformed
        :param pyote.utils.OperationNode existing_sequence: The sequence with operations that will perform the
                                                                   transformation
        :returns: A copy of `incoming_sequence` with the operations in the existing sequence taken into account
        :rtype: pyote.utils.OperationNode
        """
        incoming_value_size = 0
        existing_value_size = 0
        existing_end_point = 0
        transformed_sequence = None
        transformed_head = None
        incoming_node = incoming_sequence
        existing_node = existing_sequence
        # Walk through both sequences, one at a time.
        while existing_node and incoming_node:
            # Calculate what the position of the operation would be if it were performed now, rather than
            # after all other operations before it in the sequence.
            existing_pos = existing_node.value.position - existing_value_size
            incoming_pos = incoming_node.value.position - incoming_value_size
            # If the position of the insert in the existing sequence comes before the insert in the incoming sequence,
            # then record how much it would move the insertion position forward.
            if existing_pos < incoming_pos:
                existing_value_size += existing_node.value.get_increment()
                existing_end_point = existing_pos + existing_node.value.length
                existing_node = existing_node.next
            elif existing_pos == incoming_pos and \
                    existing_node.value.state.site_id < \
                    incoming_node.value.state.site_id:
                existing_value_size += existing_node.value.get_increment()
                existing_end_point = existing_pos + existing_node.value.length
                existing_node = existing_node.next
            else:
                # Otherwise, update the position of the incoming sequence's operation, and record how much it would
                # move the position forward after it's applied.
                if transformed_sequence:
                    transformed_sequence.next = copy(incoming_node)
                    transformed_sequence = transformed_sequence.next
                else:
                    transformed_sequence = copy(incoming_node)
                    transformed_head = transformed_sequence

                if incoming_pos < existing_end_point:
                    transformed_sequence.value.position = existing_end_point + incoming_value_size
                transformed_sequence.value.position += existing_value_size
                incoming_value_size += incoming_node.value.get_increment()
                incoming_node = incoming_node.next

        # Take care of any elements that weren't handled in the above.
        while incoming_node:
            if transformed_sequence:
                transformed_sequence.next = copy(incoming_node)
                transformed_sequence = transformed_sequence.next
            else:
                transformed_sequence = copy(incoming_node)
                transformed_head = transformed_sequence
            transformed_sequence.value.position += existing_value_size
            incoming_node = incoming_node.next
        return transformed_head

    def _transform_delete_delete(self, incoming_sequence, existing_sequence):
        """
        Performs inclusive transformation on sequence1 with sequence2, meaning that the effects of `existing sequence`
        are incorporated in `incoming_sequence`
        :param pyote.utils.OperationNode incoming_sequence: The sequence that will be transformed
        :param pyote.utils.OperationNode existing_sequence: The sequence with operations that will perform the
                                                                   transformation
        :returns: The incoming sequence with the operations in the existing sequence taken into account
        :rtype: pyote.utils.OperationNode
        """
        existing_value_size = 0
        incoming_value_size = 0
        transformed_sequence = None
        transformed_head = None
        incoming_node = incoming_sequence
        existing_node = existing_sequence
        existing_end_point = 0
        double_count_amount = 0
        # Walk through both sequences, one at a time.
        while existing_node and incoming_node:
            # Calculate what the position of the operation would be if it were performed now, rather than
            # after all other operations before it in the sequence.
            existing_pos = existing_node.value.position + existing_value_size
            incoming_pos = incoming_node.value.position + incoming_value_size
            double_delta = 0
            # If the position of the insert in the existing sequence comes before the insert in the incoming sequence,
            # then record how much it would move the insertion position forward.
            if existing_pos < incoming_pos:
                existing_value_size += existing_node.value.length
                existing_end_point = existing_pos + existing_node.value.length
                existing_node = existing_node.next
            elif existing_pos == incoming_pos and \
                    existing_node.value.state.site_id < \
                    incoming_node.value.state.site_id:
                existing_value_size += existing_node.value.length
                existing_end_point = existing_pos + existing_node.value.length
                existing_node = existing_node.next
            else:
                # Otherwise, update the position of the incoming sequence's operation, and record how much it would
                # move the position forward after it's applied.
                if transformed_sequence:
                    transformed_sequence.next = copy(incoming_node)
                    transformed_sequence = transformed_sequence.next
                else:
                    transformed_sequence = copy(incoming_node)
                    transformed_head = transformed_sequence
                next_node = incoming_node.next
                # There are three possible situations: either the incoming operation  overlaps with
                # the existing operation before it, it overlaps with the existing operation after it, or it overlaps
                # with neither.
                # We begin by checking if the preceding existing operation overlaps with it
                if existing_end_point > incoming_pos:
                    # Now, either this delete is contained completely within the preceding delete, or it isn't.
                    # In either case, we set the start of the incoming delete to the same point as the position
                    # of the preceding delete, and set the length to be whatever is left after the preceding delete
                    # has completed, which could be 0
                    transformed_sequence.value.position = existing_end_point - incoming_value_size
                    transformed_sequence.value.length = max(0, incoming_node.value.length -
                                                            existing_end_point + incoming_pos)
                    # We now check if the next existing operation overlaps with this one
                if incoming_pos + incoming_node.value.length > existing_pos:
                    # If so, then either the incoming operation ends within the existing operation, or it continues past
                    # the end.
                    if incoming_pos + incoming_node.value.length < existing_pos + existing_node.value.length:
                        # If it ends early, then shorten the incoming operation so that it ends at the start of the
                        # existing operation
                        transformed_sequence.value.length = existing_pos - incoming_pos
                    elif incoming_pos != existing_pos + existing_node.value.length:
                        # Otherwise, shorten the operation AND create a new operation
                        # which starts after the existing operation
                        transformed_sequence.value.length -= incoming_pos + incoming_node.value.length - existing_pos
                        next_node = OperationNode(DeleteOperation(existing_pos + existing_node.value.length,
                                                                  incoming_node.value.length + incoming_pos -
                                                                  existing_pos - existing_node.value.length,
                                                                  deepcopy(incoming_node.value.state)))
                        next_node.next = incoming_node.next
                        # Because we are inserting a new node in the incoming sequence, we will double count it when
                        # calculating the amount of deleting that we've done so far, so we subtract the size of the
                        #  newly created node (it will be re-added on the next iteration)
                        incoming_value_size -= next_node.value.length
                        double_delta = -next_node.value.length
                        next_node.value.position -= incoming_value_size + incoming_node.value.length

                transformed_sequence.value.position -= existing_value_size - double_count_amount
                double_count_amount += incoming_node.value.length - transformed_sequence.value.length + double_delta
                incoming_value_size += incoming_node.value.length
                incoming_node = next_node

        # Take care of any elements that weren't handled in the above.
        while incoming_node:
            if transformed_sequence:
                transformed_sequence.next = copy(incoming_node)
                transformed_sequence = transformed_sequence.next
            else:
                transformed_sequence = copy(incoming_node)
                transformed_head = transformed_sequence
            if existing_end_point > incoming_pos:
                # Now, either this delete is contained completely within the preceding delete, or it isn't.
                # In either case, we set the start of the incoming delete to the same point as the position
                # of the preceding delete, and set the length to be whatever is left after the preceding delete
                # has completed, which could be 0
                transformed_sequence.value.position = existing_end_point - incoming_value_size
                transformed_sequence.value.length = max(0, incoming_node.value.length -
                                                        existing_end_point + incoming_pos)

            transformed_sequence.value.position -= existing_value_size - double_count_amount
            double_count_amount += incoming_node.value.length - transformed_sequence.value.length
            incoming_value_size += incoming_node.value.length
            incoming_node = incoming_node.next
        return transformed_head

    def _merge_sequence(self, sequence1, sequence2):
        """
        Merges two sequence that are in effect order into one sequence that maintains effect order.  All of the
        operations in sequence1 must already have been incorporated (via :meth:_transform) into the operations in
        sequence 2.  Essentially this works as a two way merge operation.
        :param pyote.utils.OperationNode sequence1: The first sequence to merge
        :param pyote.utils.OperationNode sequence2: The second sequence to merge.  Must have incorporated the effects of
                                                    sequence1 already
        :return: A new sequence that is effect equivalent to running sequence1 then sequence 2.
        :rtype OperationNode
        """
        value_size = 0
        merged_sequence = None
        merged_node = None
        node1 = sequence1
        node2 = sequence2
        while node1 and node2:
            if node2.value.position - value_size < node1.value.position:
                if merged_node:
                    merged_node.next = OperationNode(node2.value)
                    merged_node = merged_node.next
                else:
                    merged_node = OperationNode(node2.value)
                    merged_sequence = merged_node
                value_size += node2.value.get_increment()
                node2 = node2.next
            else:
                node1.value.position += value_size
                if merged_node:
                    merged_node.next = OperationNode(node1.value)
                    merged_node = merged_node.next
                else:
                    merged_node = OperationNode(node1.value)
                    merged_sequence = merged_node
                node1 = node1.next
        while node2:
            if merged_node:
                merged_node.next = OperationNode(node2.value)
                merged_node = merged_node.next
            else:
                merged_node = OperationNode(node2.value)
                merged_sequence = merged_node
            value_size += node2.value.get_increment()
            node2 = node2.next
        while node1:
            node1.value.position += value_size
            if merged_node:
                merged_node.next = OperationNode(node1.value)
                merged_node = merged_node.next
            else:
                merged_node = OperationNode(node1.value)
                merged_sequence = merged_node
            node1 = node1.next

        return merged_sequence
