from copy import copy

from pyote.operations import DeleteOperation
from pyote.utils import TransactionSequence, OperationNode, DeleteOperationNode, State


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

        :param int site_id: An id which uniquely identifies this site across all peers
        """
        #: The unique id for this site
        self.site_id = site_id
        """:type: int"""
        #: The state of the most recently applied operation
        self.last_state = None
        """:type: State"""
        #: The inserts for this site stored in effect order as a linked list
        self._inserts = None
        """:type: pyote.utils.InsertOperationNode"""
        self._inserts.value.state = self.last_state
        #: The deletes for this site stored in effect order as a linked list
        self._deletes = None
        """:type: pyote.utils.DeleteOperationNode"""
        #: The current time stamp for operations that have been integrated into the history
        self._time_stamp = 0
        """:type: int"""

    def integrate_remote(self, remote_sequence):
        """
        Integrates the sequence of operations given by `remote_sequence` into the local history.  The ordering
        properties of the local history (see :meth:__init__) will be maintained, and a sequence of operations that
        can be applied to the local state will be returned.
        :param remote_sequence: A transaction sequence representing the operations to integrate into local history
        :type remote_sequence: pyote.utils.TransactionSequence
        :return: A Transaction Sequence that can be applied to the local data
        :rtype: pyote.utils.TransactionSequence
        """

        # Get all the local inserts that have happened since the last sync with the remote site
        local_concurrent_inserts = self._get_concurrent(remote_sequence.starting_state, self._inserts)

        # Transform the remote inserts so that they account for the changes from the local inserts
        transformed_remote_inserts = self._transform_insert_insert(remote_sequence.inserts, local_concurrent_inserts)

        # Transform the remote inserts so that they account for the changes from the local deletes
        new_remote_inserts = self._transform_insert_delete(transformed_remote_inserts, self._deletes)

        self._assign_timestamps(transformed_remote_inserts)

        # Merge the transformed remote inserts with the local.  Note that we use the inserts that have not been
        # transformed by deletes, as the local inserts always preceded the deletes.
        self._inserts = self._merge_sequence(self._inserts, transformed_remote_inserts)

        # Adjust the local deletes with the remote inserts that have been merged into the local inserts
        transformed_local_deletes = self._transform_delete_insert(self._deletes, transformed_remote_inserts)

        # Transform the remote deletes with all of the local inserts that happened since the last sync
        transformed_remote_deletes = self._transform_delete_insert(remote_sequence.deletes, local_concurrent_inserts)

        # Transform the remote deletes with ALL of the local deletes.
        new_remote_deletes = self._transform_delete_delete(transformed_remote_deletes, transformed_local_deletes)

        self._assign_timestamps(new_remote_deletes)

        # Merge the remote deletes that have taken all the local operations into effect with the local deletes
        self._deletes = self._merge_sequence(transformed_local_deletes, new_remote_deletes)

        return TransactionSequence(remote_sequence.starting_state, new_remote_inserts, new_remote_deletes)

    def process_transaction(self, outgoing_sequence):
        """
        Processes a series of operations prior to being sent out to remote sites.  The operations must
        have been performed on the data after every operation in the local history, but no others.  The
        operations in the transaction must also be effect order, with the inserts preceding the deletes.
        :param pyote.utils.TransactionSequence outgoing_sequence: The sequence of operations to process
        :return: A transaction sequence appropriate to send to other peers.  This transaction sequence will not have
                 any deletes from the local history included.
        :rtype: TransactionSequence
        """

        # Record the current state so that when we transmit this sequence, we can place it within the history
        outgoing_state = self.last_state
        self._assign_timestamps(outgoing_sequence.inserts)
        self._assign_timestamps(outgoing_sequence.deletes)

        # Swap the execution order of the outgoing insert operations so that they happen before the local deletes
        transformed_inserts, transformed_deletes = self._swap_sequence_delete_insert(self._deletes,
                                                                                     outgoing_sequence.inserts)

        # Swap the execution order of the outgoing delete operations so they happen before the local deletes
        new_deletes, _ = self._swap_sequence_delete_delete(transformed_deletes, outgoing_sequence.deletes)

        # Record that we've performed the outgoing insertion operations
        self._inserts = self._merge_sequence(self._inserts, transformed_inserts)

        # Record that we've performed the outgoing delete operations
        self._deletes = self._merge_sequence(transformed_deletes, outgoing_sequence.deletes)

        return TransactionSequence(outgoing_state, transformed_inserts, new_deletes)

    def _assign_timestamps(self, sequence):
        """
        Assigns a sequential local timestamp to every node in the sequence.  If the node is lacking
        a remote timestamp, it will add one of those too (because this sequence was locally generated)
        :param OperationNode sequence:  The sequence of operations to assign timestamps to
        """
        node = sequence
        while node:
            self._time_stamp += 1
            if node.value.state:
                node.value.state.local_time = self._time_stamp
            else:
                node.value.state = State(self.site_id, self._time_stamp, self._time_stamp)
            node = node.next

    def _get_concurrent(self, starting_state, insert_sequence):
        """
        Gets all operations in the insertion sequence which happened after the given starting state
        :param pyote.utils.State starting_state: The state to use as a reference
        :param  insert_sequence: The sequence of events to look for events within
        :type insert_sequence: pyote.utils.InsertOperationNode
        :rtype: pyote.utils.InsertOperationNode
        """
        if not starting_state:
            return insert_sequence
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
        node = insert_sequence

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

    @staticmethod
    def _transform_insert_insert(incoming_sequence, existing_sequence):
        """
        Performs inclusive transformation on sequence1 with sequence2, meaning that the effects of `existing sequence`
        are incorporated in `incoming_sequence`
        :param pyote.utils.InsertOperationNode incoming_sequence: The sequence that will be transformed
        :param pyote.utils.InsertOperationNode existing_sequence: The sequence with operations that will perform the
                                                                   transformation
        :returns: The incoming sequence with the operations in the existing sequence taken into account
        :rtype: pyote.utils.InsertOperationNode
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

    @staticmethod
    def _transform_delete_insert(incoming_sequence, existing_sequence):
        """
        Performs inclusive transformation on sequence1 with sequence2, meaning that the effects of `existing sequence`
        are incorporated in `incoming_sequence`
        :param pyote.utils.DeleteOperationNode incoming_sequence: The sequence that will be transformed
        :param pyote.utils.InsertOperationNode existing_sequence: The sequence with operations that will perform the
                                                                   transformation
        :returns: The incoming sequence with the operations in the existing sequence taken into account
        :rtype: pyote.utils.DeleteOperationNode
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

    @staticmethod
    def _transform_insert_delete(incoming_sequence, existing_sequence):
        """
        Performs inclusive transformation on `incoming_sequence` with `existing_sequence`, meaning that the effects of
        `existing sequence` are incorporated in `incoming_sequence`
        :param pyote.utils.InsertOperationNode incoming_sequence: The sequence that will be transformed
        :param pyote.utils.DeleteOperationNode existing_sequence: The sequence with operations that will perform the
                                                                   transformation
        :returns: A copy of `incoming_sequence` with the operations in the existing sequence taken into account
        :rtype: pyote.utils.InsertOperationNode
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

    @staticmethod
    def _transform_delete_delete(incoming_sequence, existing_sequence):
        """
        Performs inclusive transformation on sequence1 with sequence2, meaning that the effects of `existing sequence`
        are incorporated in `incoming_sequence`
        :param pyote.utils.DeleteOperationNode incoming_sequence: The sequence that will be transformed
        :param pyote.utils.DeleteOperationNode existing_sequence: The sequence with operations that will perform the
                                                                   transformation
        :returns: The incoming sequence with the operations in the existing sequence taken into account
        :rtype: pyote.utils.DeleteOperationNode
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
                                                                  existing_pos - existing_node.value.length))
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
        `sequence2`. Essentially this works as a two way merge operation.  As a result, state from the last operation
        in `sequence2` will be recorded as the most recently applied state.

        :param pyote.utils.OperationNode sequence1: The first sequence to merge
        :param pyote.utils.OperationNode sequence2: The second sequence to merge.  Must have incorporated the effects of
                                                    `sequence1` already, and cannot contain any overlaps with the
                                                    effects of `sequence1` (if they are both delete operations)
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
                    merged_node.next = copy(node2)
                    merged_node = merged_node.next
                else:
                    merged_node = copy(node2)
                    merged_sequence = merged_node
                value_size += node2.value.get_increment()
                self.last_state = node2.value.state
                node2 = node2.next
            else:
                node1.value.position += value_size
                if merged_node:
                    merged_node.next = copy(node1)
                    merged_node = merged_node.next
                else:
                    merged_node = copy(node1)
                    merged_sequence = merged_node
                node1 = node1.next
        while node2:
            if merged_node:
                merged_node.next = copy(node2)
                merged_node = merged_node.next
            else:
                merged_node = copy(node2)
                merged_sequence = merged_node
            value_size += node2.value.get_increment()
            self.last_state = node2.value.state
            node2 = node2.next
        while node1:
            node1.value.position += value_size
            if merged_node:
                merged_node.next = copy(node1)
                merged_node = merged_node.next
            else:
                merged_node = copy(node1)
                merged_sequence = merged_node
            node1 = node1.next

        return merged_sequence

    @staticmethod
    def _swap_sequence_delete_insert(sequence2, sequence1):
        """
        Swaps the execution order of the two input sequences.  That is, previously sequence2 was executed
        before sequence1, now it is exectuted afterwards
        :param DeleteOperationNode sequence2:
        :param InsertOperationNode sequence1:
        :return: A tuple with the two sequence's order of execution swapped.  They are in the order
                 sequence1', sequence2'
        :rtype: (InsertOperationNode, DeleteOperationNode):

        """
        new_sequence1 = None
        new_sequence2 = None
        new_node1 = None
        new_node2 = None
        node1 = sequence1
        node2 = sequence2
        size1 = 0
        size2 = 0
        while node1 and node2:
                if node2.value.position <= node1.value.position - size1:
                    if new_sequence2:
                        new_node2.next = copy(node2)
                        new_node2 = new_node2.next
                    else:
                        new_node2 = copy(node2)
                        new_sequence2 = new_node2
                    new_node2.value.position += size1
                    size2 -= node2.value.get_increment()
                    node2 = node2.next
                else:
                    if new_sequence1:
                        new_node1.next = copy(node1)
                        new_node1 = new_node1.next
                    else:
                        new_node1 = copy(node1)
                        new_sequence1 = new_node1
                    new_node1.value.position += size2
                    size1 += node1.value.get_increment()
                    node1 = node1.next
        while node1:
            if new_sequence1:
                new_node1.next = copy(node1)
                new_node1 = new_node1.next
            else:
                new_node1 = copy(node1)
                new_sequence1 = new_node1
            new_node1.value.position += size2
            size1 += node1.value.get_increment()
            node1 = node1.next
        while node2:
            if new_sequence2:
                new_node2.next = copy(node2)
                new_node2 = new_node2.next
            else:
                new_node2 = copy(node2)
                new_sequence2 = new_node2
            new_node2.value.position += size1
            size2 -= node2.value.get_increment()
            node2 = node2.next

        return new_sequence1, new_sequence2

    @staticmethod
    def _swap_sequence_delete_delete(sequence2, sequence1):
        """
        Swaps the execution order of the two input sequences.  That is, previously sequence2 was executed
        before sequence1, now it is exectuted afterwards
        :param DeleteOperationNode sequence2:
        :param DeleteOperationNode sequence1:
        :return: A tuple with the two sequence's order of execution swapped.  They are in the order
                 sequence1', sequence2'
        :rtype: (DeleteOperationNode, DeleteOperationNode):

        """
        new_sequence1 = None
        new_sequence2 = None
        new_node1 = None
        new_node2 = None
        node1 = sequence1
        node2 = sequence2
        size1 = 0
        size2 = 0
        while node1 and node2:
            if node2.value.position <= node1.value.position + size1:
                if new_sequence2:
                    new_node2.next = copy(node2)
                    new_node2 = new_node2.next
                else:
                    new_node2 = copy(node2)
                    new_sequence2 = new_node2
                new_node2.value.position -= size1
                size2 -= node2.value.get_increment()
                node2 = node2.next
            else:
                if new_sequence1:
                    new_node1.next = copy(node1)
                    new_node1 = new_node1.next
                else:
                    new_node1 = copy(node1)
                    new_sequence1 = new_node1
                next_node = node1.next
                if node1.value.position + size1 + node1.value.length > node2.value.position:
                    new_node1.value.length = node2.value.position - node1.value.position - size1
                    next_node = DeleteOperationNode(
                        DeleteOperation(node1.value.position, node1.value.length - new_node1.value.length))
                    next_node.next = node1.next

                new_node1.value.position += size2
                size1 -= new_node1.value.get_increment()
                node1 = next_node
        while node1:
            if new_sequence1:
                new_node1.next = copy(node1)
                new_node1 = new_node1.next
            else:
                new_node1 = copy(node1)
                new_sequence1 = new_node1
            new_node1.value.position += size2
            size1 -= node1.value.get_increment()
            node1 = node1.next
        while node2:
            if new_sequence2:
                new_node2.next = copy(node2)
                new_node2 = new_node2.next
            else:
                new_node2 = copy(node2)
                new_sequence2 = new_node2
            new_node2.value.position += size1
            size2 -= node2.value.get_increment()
            node2 = node2.next

        return new_sequence1, new_sequence2
