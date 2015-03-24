import random
from unittest import TestCase
from pyote.engine import Engine
from pyote.operations import InsertOperation, DeleteOperation
from pyote.utils import TransactionSequence, OperationNode, State


def get_dummy_state(site_id):
    """
    Get a state that we can use for testing transformation functions
    :return State:
    """
    time_stamp = random.randrange(0, 10000) + 1
    return State(site_id, time_stamp, time_stamp)


def convert_to_linked_list(lst):
    """
    Converts a standard python list into a linked list that the engine can use
    :param list lst: The list to convert
    :return: A linked list
    :rtype: OperationNode
    """
    if len(lst) == 0:
        return None
    llist = OperationNode(lst.pop(0))
    head = llist
    for op in lst:
        llist.next = OperationNode(op)
        llist = llist.next

    return head


def convert_from_linked_list(llist):
    """
    Converts a linked list to a standard python list
    :param OperationNode llist: The linked list to convert
    :return: The converted list
    :rtype: list
    """
    lst = []
    node = llist
    while node:
        lst.append(node.value)
        node = node.next
    return lst


class EngineTests(TestCase):

    def test_get_concurrent(self):
        engine = Engine(1)
        engine._inserts = convert_to_linked_list([
            InsertOperation(2, 1, State(1, 3, 2)),
            InsertOperation(6, 3, State(2, 2, 5)),
            InsertOperation(8, 4, State(1, 7, 4)),
            InsertOperation(15, 7, State(6, 6, 4)),
            InsertOperation(18, 4, State(6, 8, 10)),
            InsertOperation(19, 3, State(1, 5, 3)),
            InsertOperation(20, 3, State(2, 10, 16)),
            InsertOperation(21, 2, State(1, 11, 20)),
        ])
        result = convert_from_linked_list(engine._get_concurrent(State(1, 5, 3), engine._inserts))
        self.assertEqual(result, [
            InsertOperation(8, 4, State(1, 7, 4)),
            InsertOperation(15, 7, State(6, 6, 4)),
            InsertOperation(18, 4, State(6, 8, 10)),
            InsertOperation(20, 3, State(2, 10, 16)),
            InsertOperation(21, 2, State(1, 11, 20)),
        ])

    def test_transform_insert_insert(self):
        engine = Engine(1)
        # Starting with the buffer "The quick brown fox"
        states = [get_dummy_state(2), get_dummy_state(2), get_dummy_state(2), get_dummy_state(2)]
        sequence1 = [
            # Add an "ee" after "the"
            InsertOperation(3, "ee", states[0]),
            # Add another "k" on the end of "quick"
            InsertOperation(11, "k", states[1]),
            # Add "wnwnwn" to the end of "brown"
            InsertOperation(18, "wnwnwn", states[2]),
            # Add "xx!" to the end of "fox"
            InsertOperation(28, "xx!", states[3]),
        ]
        # After sequence1 is applied, we would have "Theee quickk brownwnwnwn foxxx!"
        sequence2 = [
            # insert "very " after "the"
            InsertOperation(4, "very ", get_dummy_state(1)),
            # insert "ly" after "quick"
            InsertOperation(14, "ly", get_dummy_state(1)),
            # insert "u" after the 'o' in "brown"
            InsertOperation(20, "u", get_dummy_state(1)),
        ]
        # After sequence2 is applied, we would have "The very quickly brouwn fox"
        self.assertListEqual(convert_from_linked_list(engine._transform_insert_insert(convert_to_linked_list(sequence1),
                                                                                      convert_to_linked_list(sequence2))
                                                      ), [
            # Add an "ee" after "the"
            InsertOperation(3, "ee", states[0]),
            # Add another "k" on the end of "quickly"
            InsertOperation(18, "k", states[1]),
            # Add "wnwnwn" to the end of "brouwn"
            InsertOperation(26, "wnwnwn", states[2]),
            # Add "xx!" to the end of "fox"
            InsertOperation(36, "xx!", states[3]),
        ])
        # If sequence 2 is applied after sequence 1, we would have "Theee very quicklyk brouwnwnwnwn foxxx!"

    def test_transform_delete_insert(self):
        engine = Engine(1)
        # Starting with the buffer "The very quickly brouwn fox"
        sequence1 = convert_to_linked_list([
            # delete the "e" from "the"
            DeleteOperation(2, 1, get_dummy_state(1)),
            # delete the "e" from "very"
            DeleteOperation(4, 1, get_dummy_state(1)),
            # delete the "ui" from "quickly"
            DeleteOperation(8, 2, get_dummy_state(1)),
            # delete the "ou" from "brouwn"
            DeleteOperation(15, 2, get_dummy_state(1)),
            # delete the "o" from "fox"
            DeleteOperation(19, 1, get_dummy_state(1)),
        ])
        # after sequence1 is applied, we would have "Th vry qckly brwn fx"
        sequence2 = convert_to_linked_list([
            # Add an "ee" after "the"
            InsertOperation(3, "ee", get_dummy_state(2)),
            # Add another "k" on the end of "quickly"
            InsertOperation(18, "k", get_dummy_state(2)),
            # Add "wnwnwn" to the end of "brouwn"
            InsertOperation(26, "wnwnwn", get_dummy_state(2)),
            # Add "xx!" to the end of "fox"
            InsertOperation(36, "xx!", get_dummy_state(2)),
        ])
        # After sequence2 is applied, we will have "Theee very quicklyk brouwnwnwnwn foxxx!"
        results = convert_from_linked_list(engine._transform_delete_insert(sequence1, sequence2))
        self.assertEqual(results, [
            # delete the first "e" from "theee"
            DeleteOperation(2, 1, get_dummy_state(1)),
            # delete the "e" from "very"
            DeleteOperation(6, 1, get_dummy_state(1)),
            # delete the "ui" from "quicklyk"
            DeleteOperation(10, 2, get_dummy_state(1)),
            # delete the "ou" from "brouwnwnwnwn"
            DeleteOperation(18, 2, get_dummy_state(1)),
            # delete the "o" from "foxxx!"
            DeleteOperation(28, 1, get_dummy_state(1)),
        ])
        # After running sequence1 then sequence2, we get "Thee vry qcklyk brwnwnwnwn fxxx!"

    def test_transform_delete_delete(self):
        engine = Engine(1)
        # Starting with buffer "The quick brown fox jumped over the lazy dog"
        states1 = [get_dummy_state(2), get_dummy_state(2), get_dummy_state(2)]
        states2 = [get_dummy_state(1), get_dummy_state(1), get_dummy_state(1), get_dummy_state(1)]
        sequence1 = convert_to_linked_list([
            # Delete "quick bro"
            DeleteOperation(4, 9, states1[0]),
            # Delete "ed over"
            DeleteOperation(15, 7, states1[1]),
            # Delete "laz"
            DeleteOperation(20, 3, states1[2]),
        ])
        # After sequence1 is applied, we will have "The wn fox jump the y dog"
        sequence2 = convert_to_linked_list([
            # Delete "he qu"
            DeleteOperation(1, 5, states2[0]),
            # Delete "ck"
            DeleteOperation(2, 2, states2[1]),
            # Delete "rown"
            DeleteOperation(4, 4, states2[2]),
            # Delete "the lazy dog"
            DeleteOperation(21, 12, states2[3]),
        ])
        # After sequence2 is applied, we will have "Ti b fox jumped over"

        self.assertEqual(engine._transform_delete_delete(sequence1, sequence2), convert_to_linked_list([
            # Delete "i"
            DeleteOperation(1, 1, states1[0]),
            # Delete " b"
            DeleteOperation(1, 2, states1[0]),
            # Delete "ed over"
            DeleteOperation(10, 7, states1[1]),
            # Delete ""
            DeleteOperation(11, 0, states1[2]),
        ]))
        # After both sequences are applied, we will have "T fox jump "
        self.assertEqual(engine._transform_delete_delete(sequence2, sequence1), convert_to_linked_list([
            # Delete "he "
            DeleteOperation(1, 3, states2[0]),
            # Delete ""
            DeleteOperation(1, 0, states2[1]),
            # Delete "wn"
            DeleteOperation(1, 2, states2[2]),
            # Delete "the "
            DeleteOperation(11, 4, states2[3]),
            # Delete "y dog"
            DeleteOperation(11, 5, states2[3]),
            ]))

    def test_transform_delete_delete_with_0_length_deletes(self):
        engine = Engine(1)
        # Starting with buffer "The quick brown fox jumped over the lazy dog"
        states1 = [get_dummy_state(2), get_dummy_state(2), get_dummy_state(2), get_dummy_state(2)]
        states2 = [get_dummy_state(1), get_dummy_state(1), get_dummy_state(1), get_dummy_state(1), get_dummy_state(1)]
        sequence1 = convert_to_linked_list([
            # Delete "h"
            DeleteOperation(1, 1, states1[0]),
            # Delete "" after "T"
            DeleteOperation(1, 0, states1[1]),
            # Delete "ck "
            DeleteOperation(6, 3, states1[2]),
            # Delete "" after "n"
            DeleteOperation(11, 0, states1[3]),
            ])
        # After sequence1 is applied, we will have "Te quibrown fox jumped over the lazy dog"
        sequence2 = convert_to_linked_list([
            # Delete "e"
            DeleteOperation(2, 1, states2[0]),
            # Delete "c"
            DeleteOperation(6, 1, states2[1]),
            # Delete "ow"
            DeleteOperation(10, 2, states2[2]),
            # Delete "mp"
            DeleteOperation(18, 2, states2[3]),
            # Detete " " after "the
            DeleteOperation(28, 1, states2[4]),
            ])
        # After sequence2 is applied, we will have "Th quik brn fox jued over thelazy dog"
        result = engine._transform_delete_delete(sequence2, sequence1)
        self.assertEqual(convert_from_linked_list(result), [
            # Delete "e"
            DeleteOperation(1, 1, states2[0]),
            # Delete "" (was delete "c")
            DeleteOperation(5, 0, states2[1]),
            # Delete "wn"
            DeleteOperation(7, 2, states2[2]),
            # Delete "mp"
            DeleteOperation(15, 2, states2[3]),
            # Delete " " after "the"
            DeleteOperation(25, 1, states2[3]),
        ])

    def test_transform_delete_delete_simple(self):
        engine = Engine(1)
        # starting with buffer "The quick brown fox jumped over the lazy dog"
        sequence1 = convert_to_linked_list([
            # Delete "The"
            DeleteOperation(0, 3, get_dummy_state(1)),
            # Delete "brown"
            DeleteOperation(7, 5, get_dummy_state(1)),
            # Delete "jumped"
            DeleteOperation(12, 6, get_dummy_state(1)),
            # Delete "the"
            DeleteOperation(18, 3, get_dummy_state(1)),
            # Delete "dog"
            DeleteOperation(24, 3, get_dummy_state(1)),
        ])
        # After these operations run, we will have " quick  fox  over  lazy "
        sequence2 = convert_to_linked_list([
            # Delete "quick"
            DeleteOperation(4, 5, get_dummy_state(2)),
            # Delete "fox"
            DeleteOperation(11, 3, get_dummy_state(2)),
            # Delete "over"
            DeleteOperation(19, 4, get_dummy_state(2)),
            # Delete "lazy"
            DeleteOperation(24, 4, get_dummy_state(2)),
        ])
        # After these operations, we will have "The  brown  jumped  the  dog"

        result = engine._transform_delete_delete(sequence1, sequence2)
        self.assertEqual(convert_from_linked_list(result), [
            # Delete "The"
            DeleteOperation(0, 3, get_dummy_state(1)),
            # Delete "brown"
            DeleteOperation(2, 5, get_dummy_state(1)),
            # Delete "jumped"
            DeleteOperation(4, 6, get_dummy_state(1)),
            # Delete "the"
            DeleteOperation(6, 3, get_dummy_state(1)),
            # Delete "dog"
            DeleteOperation(8, 3, get_dummy_state(1)),
        ])

        result = engine._transform_delete_delete(sequence2, sequence1)
        self.assertEqual(convert_from_linked_list(result), [
            # Delete "quick"
            DeleteOperation(1, 5, get_dummy_state(2)),
            # Delete "fox"
            DeleteOperation(3, 3, get_dummy_state(2)),
            # Delete "over"
            DeleteOperation(5, 4, get_dummy_state(2)),
            # Delete "lazy"
            DeleteOperation(7, 4, get_dummy_state(2)),
            ])

    def test_merge_sequence_inserts(self):
        engine = Engine(1)
        # Starting with the buffer "The quick brown fox"
        sequence1 = convert_to_linked_list([
            # insert "very " after "the"
            InsertOperation(4, "very ", get_dummy_state(1)),
            # insert "ly" after "quick"
            InsertOperation(14, "ly", get_dummy_state(1)),
            # insert "u" after the 'o' in "brown"
            InsertOperation(20, "u", get_dummy_state(1)),
        ])

        sequence2 = convert_to_linked_list([
            # Add an "ee" after "the"
            InsertOperation(3, "ee", get_dummy_state(2)),
            # Add another "k" on the end of "quickly"
            InsertOperation(18, "k", get_dummy_state(2)),
            # Add "wnwnwn" to the end of "brouwn"
            InsertOperation(26, "wnwnwn", get_dummy_state(2)),
            # Add "xx!" to the end of "fox"
            InsertOperation(36, "xx!", get_dummy_state(2)),
        ])

        result = convert_from_linked_list(engine._merge_sequence(sequence1, sequence2))
        self.assertListEqual(result, [
            # Add an "ee" after "the"
            InsertOperation(3, "ee", sequence2[0].state),
            # insert "very " after "theee"
            InsertOperation(6, "very ", sequence1[0].state),
            # insert "ly" after "quick"
            InsertOperation(16, "ly", sequence1[1].state),
            # Add another "k" on the end of "quickly"
            InsertOperation(18, "k", sequence2[1].state),
            # insert "u" after the 'o' in "brown"
            InsertOperation(23, "u", sequence1[2].state),
            # Add "wnwnwn" to the end of "brouwn"
            InsertOperation(26, "wnwnwn", sequence2[2].state),
            # Add "xx!" to the end of "fox"
            InsertOperation(36, "xx!", sequence2[3].state),
        ])

    def test_integrate_sequences(self):
        engine = Engine(1)
        engine._inserts = convert_to_linked_list([
            InsertOperation(0, "The quick brown fox", State(1, 0, 0)),
            # insert "very " after "the"
            InsertOperation(4, "very ", get_dummy_state(1)),
            # insert "ly" after "quick"
            InsertOperation(14, "ly", get_dummy_state(1)),
            # insert "u" after the 'o' in "brown"
            InsertOperation(20, "u", get_dummy_state(1)),
        ])
        # After the inserts are applied, we would have "The very quickly brouwn fox"

        engine._deletes = convert_to_linked_list([
            # delete the "e" from "the"
            DeleteOperation(2, 1, get_dummy_state(1)),
            # delete the "e" from "very"
            DeleteOperation(4, 1, get_dummy_state(1)),
            # delete the "ui" from "quickly"
            DeleteOperation(8, 2, get_dummy_state(1)),
            # delete the "ou" from "brouwn"
            DeleteOperation(15, 2, get_dummy_state(1)),
            # delete the "o" from "fox"
            DeleteOperation(19, 1, get_dummy_state(1)),
        ])

        # After the deletes are applied, we would have "Th vry qckly brwn fx"

        sequence = TransactionSequence(State(1, 0, 0), convert_to_linked_list([
            # Add an "ee" after "the"
            InsertOperation(3, "ee", get_dummy_state(2)),
            # Add another "k" on the end of "quick"
            InsertOperation(11, "k", get_dummy_state(2)),
            # Add "wnwnwn" to the end of "brown"
            InsertOperation(18, "wnwnwn", get_dummy_state(2)),
            # Add "xx!" to the end of "fox"
            InsertOperation(28, "xx!", get_dummy_state(2)),
        ]), convert_to_linked_list([  # After the inserts, we would have "Theee quickk brownwnwnwn foxxx!"
            # Delete the "he" from "theee"
            DeleteOperation(1, 2, get_dummy_state(2)),
            # Delete "bro" from "brownwnwnwn"
            DeleteOperation(11, 3, get_dummy_state(2)),
            # Delete "f" from "foxxx"
            DeleteOperation(20, 1, get_dummy_state(2))
        ]))
        # After the deletes, we would have "Tee quickk wnwnwnwn oxxx!"

        new_transaction = engine.integrate_remote(sequence)

        self.assertListEqual(convert_from_linked_list(new_transaction.inserts), [
            # Add an "ee" after "th"
            InsertOperation(2, "ee", sequence.inserts[0].state),
            # Add a "k" after "qckly"
            InsertOperation(14, "k", sequence.inserts[1].state),
            # Add a "wnwnwn" after "brwn"
            InsertOperation(20, "wnwnwn", sequence.inserts[2].state),
            # Add "xx!" after "fx"
            InsertOperation(29, "xx!", sequence.inserts[3].state)
        ])
        # After these are applied, we would have "Thee vry qcklyk brwnwnwnwn fxxx!"
        self.assertListEqual(convert_from_linked_list(new_transaction.deletes), [
            # Delete the "h" in "thee"
            DeleteOperation(1, 1, sequence.inserts[0].state),
            # Delete "" after "t"
            DeleteOperation(1, 0, sequence.inserts[1].state),
            # Delete "br"
            DeleteOperation(15, 2, sequence.inserts[2].state),
            # Delete "f"
            DeleteOperation(24, 1, sequence.inserts[3].state)
        ])
        # After these are applied, we would have "Tee vry qcklyk wnwnwnwn xxx!"

        self.assertEqual(convert_from_linked_list(engine._inserts), [
            InsertOperation(0, "The quick brown fox", State(1, 0, 0)),
            # Add an "ee" after "the"
            InsertOperation(3, "ee", sequence.inserts[0].state),
            # insert "very " after "theee "
            InsertOperation(6, "very ", engine._inserts[1].state),
            # insert "ly" after "quick"
            InsertOperation(16, "ly", engine._inserts[2].state),
            # Add another "k" on the end of "quick"
            InsertOperation(18, "k", sequence.inserts[1].state),
            # insert "u" after the 'o' in "brown"
            InsertOperation(23, "u", engine._inserts[3].state),
            # Add "wnwnwn" to the end of "brown"
            InsertOperation(26, "wnwnwn", sequence.inserts[2].state),
            # Add "xx!" to the end of "fox"
            InsertOperation(36, "xx!", sequence.inserts[3].state),

        ])
        # After all the inserts are applied, we should have "Theee very quicklyk brouwnwnwnwn foxxx!"
        self.assertEqual(convert_from_linked_list(engine._deletes), [
            # Delete the "h" from "thee"
            DeleteOperation(1, 1, get_dummy_state(2)),
            # delete the first "e" from "teee"
            DeleteOperation(1, 1, get_dummy_state(1)),
            # Delete the "" from "tee"
            DeleteOperation(1, 0, get_dummy_state(2)),
            # delete the "e" from "very"
            DeleteOperation(5, 1, get_dummy_state(1)),
            # delete the "ui" from "quicklyk"
            DeleteOperation(9, 2, get_dummy_state(1)),
            # Delete "br" from "brouwnwnwnwn"
            DeleteOperation(15, 2, get_dummy_state(2)),
            # delete the "ou" from "brouwn"
            DeleteOperation(15, 2, get_dummy_state(1)),
            # Delete "f" from "foxxx!"
            DeleteOperation(24, 1, get_dummy_state(2)),
            # delete the "o" from "oxxx!"
            DeleteOperation(24, 1, get_dummy_state(1)),


        ])
        # After all the deletes are applied, we should have "Tee vry qcklyk wnwnwnwn xxx!"
