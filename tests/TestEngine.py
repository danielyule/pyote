import random
from unittest import TestCase
from pyote.engine import Engine
from pyote.operations import InsertOperation, DeleteOperation
from pyote.utils import TransactionSequence, State, InsertOperationNode, DeleteOperationNode


def get_dummy_state(site_id):
    """
    Get a state that we can use for testing transformation functions
    :return State:
    """
    time_stamp = random.randrange(0, 10000) + 1
    return State(site_id, time_stamp, time_stamp)


def convert_insert_list(insert_list, site_id):
    inserts = InsertOperationNode.from_list(insert_list)
    node = inserts
    while node:
        node.value.state = get_dummy_state(site_id)
        node = node.next

    return inserts


def convert_delete_list(insert_list, site_id):
    deletes = DeleteOperationNode.from_list(insert_list)
    node = deletes
    while node:
        node.value.state = get_dummy_state(site_id)
        node = node.next

    return deletes


def insert_with_state(position, value, state):
    op = InsertOperation(position, value)
    op.state = state
    return op


class EngineTests(TestCase):

    def test_get_concurrent(self):
        engine = Engine(1)
        engine._inserts = InsertOperationNode.from_list([
            insert_with_state(2, 1, State(1, 3, 2)),
            insert_with_state(6, 3, State(2, 2, 5)),
            insert_with_state(8, 4, State(1, 7, 4)),
            insert_with_state(15, 7, State(6, 6, 4)),
            insert_with_state(18, 4, State(6, 8, 10)),
            insert_with_state(19, 3, State(1, 5, 3)),
            insert_with_state(20, 3, State(2, 10, 16)),
            insert_with_state(21, 2, State(1, 11, 20)),
        ])
        result = engine._get_concurrent(State(1, 5, 3), engine._inserts).to_list()
        self.assertEqual(result, [
            insert_with_state(8, 4, State(1, 7, 4)),
            insert_with_state(15, 7, State(6, 6, 4)),
            insert_with_state(18, 4, State(6, 8, 10)),
            insert_with_state(20, 3, State(2, 10, 16)),
            insert_with_state(21, 2, State(1, 11, 20)),
        ])

    def test_transform_insert_insert(self):
        engine = Engine(1)
        # Starting with the buffer "The quick brown fox"
        sequence1 = convert_insert_list([
            # Add an "ee" after "the"
            InsertOperation(3, "ee"),
            # Add another "k" on the end of "quick"
            InsertOperation(11, "k"),
            # Add "wnwnwn" to the end of "brown"
            InsertOperation(18, "wnwnwn"),
            # Add "xx!" to the end of "fox"
            InsertOperation(28, "xx!"),
        ], 2)
        # After sequence1 is applied, we would have "Theee quickk brownwnwnwn foxxx!"
        sequence2 = convert_insert_list([
            # insert "very " after "the"
            InsertOperation(4, "very "),
            # insert "ly" after "quick"
            InsertOperation(14, "ly"),
            # insert "u" after the 'o' in "brown"
            InsertOperation(20, "u"),
        ], 1)
        # After sequence2 is applied, we would have "The very quickly brouwn fox"
        self.assertListEqual(engine._transform_insert_insert(sequence1, sequence2).to_list(), [
            # Add an "ee" after "the"
            InsertOperation(3, "ee"),
            # Add another "k" on the end of "quickly"
            InsertOperation(18, "k"),
            # Add "wnwnwn" to the end of "brouwn"
            InsertOperation(26, "wnwnwn"),
            # Add "xx!" to the end of "fox"
            InsertOperation(36, "xx!"),
        ])
        # If sequence 2 is applied after sequence 1, we would have "Theee very quicklyk brouwnwnwnwn foxxx!"

    def test_transform_delete_insert(self):
        engine = Engine(1)
        # Starting with the buffer "The very quickly brouwn fox"
        sequence1 = convert_delete_list([
            # delete the "e" from "the"
            DeleteOperation(2, 1),
            # delete the "e" from "very"
            DeleteOperation(4, 1),
            # delete the "ui" from "quickly"
            DeleteOperation(8, 2),
            # delete the "ou" from "brouwn"
            DeleteOperation(15, 2),
            # delete the "o" from "fox"
            DeleteOperation(19, 1),
        ], 1)
        # after sequence1 is applied, we would have "Th vry qckly brwn fx"
        sequence2 = convert_insert_list([
            # Add an "ee" after "the"
            InsertOperation(3, "ee"),
            # Add another "k" on the end of "quickly"
            InsertOperation(18, "k"),
            # Add "wnwnwn" to the end of "brouwn"
            InsertOperation(26, "wnwnwn"),
            # Add "xx!" to the end of "fox"
            InsertOperation(36, "xx!"),
        ], 2)
        # After sequence2 is applied, we will have "Theee very quicklyk brouwnwnwnwn foxxx!"
        results = engine._transform_delete_insert(sequence1, sequence2).to_list()
        self.assertEqual(results, [
            # delete the first "e" from "theee"
            DeleteOperation(2, 1),
            # delete the "e" from "very"
            DeleteOperation(6, 1),
            # delete the "ui" from "quicklyk"
            DeleteOperation(10, 2),
            # delete the "ou" from "brouwnwnwnwn"
            DeleteOperation(18, 2),
            # delete the "o" from "foxxx!"
            DeleteOperation(28, 1),
        ])
        # After running sequence1 then sequence2, we get "Thee vry qcklyk brwnwnwnwn fxxx!"

    def test_transform_delete_delete(self):
        engine = Engine(1)
        # Starting with buffer "The quick brown fox jumped over the lazy dog"
        sequence1 = convert_delete_list([
            # Delete "quick bro"
            DeleteOperation(4, 9),
            # Delete "ed over"
            DeleteOperation(15, 7),
            # Delete "laz"
            DeleteOperation(20, 3),
        ], 2)
        # After sequence1 is applied, we will have "The wn fox jump the y dog"
        sequence2 = convert_delete_list([
            # Delete "he qu"
            DeleteOperation(1, 5),
            # Delete "ck"
            DeleteOperation(2, 2),
            # Delete "rown"
            DeleteOperation(4, 4),
            # Delete "the lazy dog"
            DeleteOperation(21, 12),
        ], 1)
        # After sequence2 is applied, we will have "Ti b fox jumped over"

        self.assertEqual(engine._transform_delete_delete(sequence1, sequence2).to_list(), [
            # Delete "i"
            DeleteOperation(1, 1),
            # Delete " b"
            DeleteOperation(1, 2),
            # Delete "ed over"
            DeleteOperation(10, 7),
            # Delete ""
            DeleteOperation(11, 0),
        ])
        # After both sequences are applied, we will have "T fox jump "
        self.assertEqual(engine._transform_delete_delete(sequence2, sequence1).to_list(), [
            # Delete "he "
            DeleteOperation(1, 3),
            # Delete ""
            DeleteOperation(1, 0),
            # Delete "wn"
            DeleteOperation(1, 2),
            # Delete "the "
            DeleteOperation(11, 4),
            # Delete "y dog"
            DeleteOperation(11, 5),
        ])

    def test_transform_delete_delete_with_0_length_deletes(self):
        engine = Engine(1)
        # Starting with buffer "The quick brown fox jumped over the lazy dog"
        sequence1 = convert_delete_list([
            # Delete "h"
            DeleteOperation(1, 1),
            # Delete "" after "T"
            DeleteOperation(1, 0),
            # Delete "ck "
            DeleteOperation(6, 3),
            # Delete "" after "n"
            DeleteOperation(11, 0),
        ], 2)
        # After sequence1 is applied, we will have "Te quibrown fox jumped over the lazy dog"
        sequence2 = convert_delete_list([
            # Delete "e"
            DeleteOperation(2, 1),
            # Delete "c"
            DeleteOperation(6, 1),
            # Delete "ow"
            DeleteOperation(10, 2),
            # Delete "mp"
            DeleteOperation(18, 2),
            # Detete " " after "the
            DeleteOperation(28, 1),
        ], 1)
        # After sequence2 is applied, we will have "Th quik brn fox jued over thelazy dog"
        result = engine._transform_delete_delete(sequence2, sequence1).to_list()
        self.assertEqual(result, [
            # Delete "e"
            DeleteOperation(1, 1),
            # Delete "" (was delete "c")
            DeleteOperation(5, 0),
            # Delete "wn"
            DeleteOperation(7, 2),
            # Delete "mp"
            DeleteOperation(15, 2),
            # Delete " " after "the"
            DeleteOperation(25, 1),
        ])

    def test_transform_delete_delete_simple(self):
        engine = Engine(1)
        # starting with buffer "The quick brown fox jumped over the lazy dog"
        sequence1 = convert_delete_list([
            # Delete "The"
            DeleteOperation(0, 3),
            # Delete "brown"
            DeleteOperation(7, 5),
            # Delete "jumped"
            DeleteOperation(12, 6),
            # Delete "the"
            DeleteOperation(18, 3),
            # Delete "dog"
            DeleteOperation(24, 3),
        ], 1)
        # After these operations run, we will have " quick  fox  over  lazy "
        sequence2 = convert_delete_list([
            # Delete "quick"
            DeleteOperation(4, 5),
            # Delete "fox"
            DeleteOperation(11, 3),
            # Delete "over"
            DeleteOperation(19, 4),
            # Delete "lazy"
            DeleteOperation(24, 4),
        ], 2)
        # After these operations, we will have "The  brown  jumped  the  dog"

        result = engine._transform_delete_delete(sequence1, sequence2).to_list()
        self.assertEqual(result, [
            # Delete "The"
            DeleteOperation(0, 3),
            # Delete "brown"
            DeleteOperation(2, 5),
            # Delete "jumped"
            DeleteOperation(4, 6),
            # Delete "the"
            DeleteOperation(6, 3),
            # Delete "dog"
            DeleteOperation(8, 3),
        ])

        result = engine._transform_delete_delete(sequence2, sequence1).to_list()
        self.assertEqual(result, [
            # Delete "quick"
            DeleteOperation(1, 5),
            # Delete "fox"
            DeleteOperation(3, 3),
            # Delete "over"
            DeleteOperation(5, 4),
            # Delete "lazy"
            DeleteOperation(7, 4),
        ])

    def test_merge_sequence_inserts(self):
        engine = Engine(1)
        # Starting with the buffer "The quick brown fox"
        sequence1 = convert_insert_list([
            # insert "very " after "the"
            InsertOperation(4, "very "),
            # insert "ly" after "quick"
            InsertOperation(14, "ly"),
            # insert "u" after the 'o' in "brown"
            InsertOperation(20, "u"),
        ], 1)

        sequence2 = convert_insert_list([
            # Add an "ee" after "the"
            InsertOperation(3, "ee"),
            # Add another "k" on the end of "quickly"
            InsertOperation(18, "k"),
            # Add "wnwnwn" to the end of "brouwn"
            InsertOperation(26, "wnwnwn"),
            # Add "xx!" to the end of "fox"
            InsertOperation(36, "xx!"),
        ], 2)

        result = engine._merge_sequence(sequence1, sequence2).to_list()
        self.assertListEqual(result, [
            # Add an "ee" after "the"
            InsertOperation(3, "ee"),
            # insert "very " after "theee"
            InsertOperation(6, "very "),
            # insert "ly" after "quick"
            InsertOperation(16, "ly"),
            # Add another "k" on the end of "quickly"
            InsertOperation(18, "k"),
            # insert "u" after the 'o' in "brown"
            InsertOperation(23, "u"),
            # Add "wnwnwn" to the end of "brouwn"
            InsertOperation(26, "wnwnwn"),
            # Add "xx!" to the end of "fox"
            InsertOperation(36, "xx!"),
        ])

    def test_integrate_sequences(self):
        engine = Engine(1)
        engine._inserts = convert_insert_list([
            InsertOperation(0, "The quick brown fox"),
            # insert "very " after "the"
            InsertOperation(4, "very "),
            # insert "ly" after "quick"
            InsertOperation(14, "ly"),
            # insert "u" after the 'o' in "brown"
            InsertOperation(20, "u"),
        ], 1)
        engine._inserts.value.state = State(1, 0, 0)
        # After the inserts are applied, we would have "The very quickly brouwn fox"

        engine._deletes = convert_delete_list([
            # delete the "e" from "the"
            DeleteOperation(2, 1),
            # delete the "e" from "very"
            DeleteOperation(4, 1),
            # delete the "ui" from "quickly"
            DeleteOperation(8, 2),
            # delete the "ou" from "brouwn"
            DeleteOperation(15, 2),
            # delete the "o" from "fox"
            DeleteOperation(19, 1),
        ], 1)

        # After the deletes are applied, we would have "Th vry qckly brwn fx"

        sequence = TransactionSequence(State(1, 0, 0), convert_insert_list([
            # Add an "ee" after "the"
            InsertOperation(3, "ee"),
            # Add another "k" on the end of "quick"
            InsertOperation(11, "k"),
            # Add "wnwnwn" to the end of "brown"
            InsertOperation(18, "wnwnwn"),
            # Add "xx!" to the end of "fox"
            InsertOperation(28, "xx!"),
        ], 2), convert_delete_list([  # After the inserts, we would have "Theee quickk brownwnwnwn foxxx!"
            # Delete the "he" from "theee"
            DeleteOperation(1, 2),
            # Delete "bro" from "brownwnwnwn"
            DeleteOperation(11, 3),
            # Delete "f" from "foxxx"
            DeleteOperation(20, 1)
        ], 2))
        # After the deletes, we would have "Tee quickk wnwnwnwn oxxx!"

        new_transaction = engine.integrate_remote(sequence)

        self.assertListEqual(new_transaction.inserts.to_list(), [
            # Add an "ee" after "th"
            InsertOperation(2, "ee"),
            # Add a "k" after "qckly"
            InsertOperation(14, "k"),
            # Add a "wnwnwn" after "brwn"
            InsertOperation(20, "wnwnwn"),
            # Add "xx!" after "fx"
            InsertOperation(29, "xx!")
        ])
        # After these are applied, we would have "Thee vry qcklyk brwnwnwnwn fxxx!"
        self.assertListEqual(new_transaction.deletes.to_list(), [
            # Delete the "h" in "thee"
            DeleteOperation(1, 1),
            # Delete "" after "t"
            DeleteOperation(1, 0),
            # Delete "br"
            DeleteOperation(15, 2),
            # Delete "f"
            DeleteOperation(24, 1)
        ])
        # After these are applied, we would have "Tee vry qcklyk wnwnwnwn xxx!"

        self.assertEqual(engine._inserts.to_list(), [
            InsertOperation(0, "The quick brown fox"),
            # Add an "ee" after "the"
            InsertOperation(3, "ee"),
            # insert "very " after "theee "
            InsertOperation(6, "very "),
            # insert "ly" after "quick"
            InsertOperation(16, "ly"),
            # Add another "k" on the end of "quick"
            InsertOperation(18, "k"),
            # insert "u" after the 'o' in "brown"
            InsertOperation(23, "u"),
            # Add "wnwnwn" to the end of "brown"
            InsertOperation(26, "wnwnwn"),
            # Add "xx!" to the end of "fox"
            InsertOperation(36, "xx!"),

        ])
        # After all the inserts are applied, we should have "Theee very quicklyk brouwnwnwnwn foxxx!"
        self.assertEqual(engine._deletes.to_list(), [
            # Delete the "h" from "thee"
            DeleteOperation(1, 1),
            # delete the first "e" from "teee"
            DeleteOperation(1, 1),
            # Delete the "" from "tee"
            DeleteOperation(1, 0),
            # delete the "e" from "very"
            DeleteOperation(5, 1),
            # delete the "ui" from "quicklyk"
            DeleteOperation(9, 2),
            # Delete "br" from "brouwnwnwnwn"
            DeleteOperation(15, 2),
            # delete the "ou" from "brouwn"
            DeleteOperation(15, 2),
            # Delete "f" from "foxxx!"
            DeleteOperation(24, 1),
            # delete the "o" from "oxxx!"
            DeleteOperation(24, 1),


        ])
        # After all the deletes are applied, we should have "Tee vry qcklyk wnwnwnwn xxx!"

    def test_swap_sequence_delete_insert(self):
        engine = Engine(1)
        # Starting with the buffer "The quick brown fox"
        sequence1 = convert_insert_list([
            # insert "very " after "t "
            InsertOperation(2, "very "),
            # insert "ly" after "quick"
            InsertOperation(12, "ly"),
            # insert "u" before the 'w'  in "wn"
            InsertOperation(15, "u"),
        ], 1)
        # After this runs, we will have "T very quickly uwn ox"
        sequence2 = convert_delete_list([
            # Delete the "he" from "the"
            DeleteOperation(1, 2),
            # Delete "bro" from "brown"
            DeleteOperation(8, 3),
            # Delete "f" from "fox"
            DeleteOperation(11, 1)
        ], 2)
        # After this runs, we will have  "T quick wn ox"
        updated_sq1, updated_sq2 = engine._swap_sequence_delete_insert(sequence2, sequence1)
        self.assertEqual(updated_sq1.to_list(), [
            # insert "very " after "the "
            InsertOperation(4, "very "),
            # insert "ly" after "quick"
            InsertOperation(14, "ly"),
            # insert "u" after the 'o' in "brown"
            InsertOperation(20, "u"),
        ])
        # After this runs, we will have "The very quickly brouwn fox"
        self.assertEqual(updated_sq2.to_list(), [
            # Delete the "he" from "the"
            DeleteOperation(1, 2),
            # Delete "bro" from "brouwn"
            DeleteOperation(15, 3),
            # Delete "f" from "fox"
            DeleteOperation(19, 1)
        ])
        # After this runs, we will have "T very quickly uwn ox"

    def test_swap_sequence_delete_delete(self):
        engine = Engine(1)
        # starting with buffer "The quick brown fox jumped over the lazy dog"
        sequence1 = convert_delete_list([
            # Delete "The"
            DeleteOperation(0, 3),
            # Delete "brown"
            DeleteOperation(2, 5),
            # Delete "jumped"
            DeleteOperation(4, 6),
            # Delete "the"
            DeleteOperation(6, 3),
            # Delete "dog"
            DeleteOperation(8, 3),
        ], 1)
        # After these operations run, we will have " quick  fox  over  lazy "
        sequence2 = convert_delete_list([
            # Delete "quick"
            DeleteOperation(4, 5),
            # Delete "fox"
            DeleteOperation(11, 3),
            # Delete "over"
            DeleteOperation(19, 4),
            # Delete "lazy"
            DeleteOperation(24, 4),
        ], 2)
        # After these operations, we will have "The  brown  jumped  the  dog"

        updated_sq1, updated_sq2 = engine._swap_sequence_delete_delete(sequence2, sequence1)
        self.assertEqual(updated_sq1.to_list(), [
            # Delete "The"
            DeleteOperation(0, 3),
            # Delete "brown"
            DeleteOperation(7, 5),
            # Delete "jumped"
            DeleteOperation(12, 6),
            # Delete "the"
            DeleteOperation(18, 3),
            # Delete "dog"
            DeleteOperation(24, 3),
        ])

        self.assertEqual(updated_sq2.to_list(), [
            # Delete "quick"
            DeleteOperation(1, 5),
            # Delete "fox"
            DeleteOperation(3, 3),
            # Delete "over"
            DeleteOperation(5, 4),
            # Delete "lazy"
            DeleteOperation(7, 4),
        ])

    def test_swap_delete_delete_with_overlap(self):
        engine = Engine(1)
        # starting with buffer "The quick brown fox jumped over the lazy dog"
        sequence1 = convert_delete_list([
            # Delete "The  brown"
            DeleteOperation(0, 10),
            # Delete "jumped  the  dog"
            DeleteOperation(2, 16),
        ], 1)
        # After these operations run, we will have " "
        sequence2 = convert_delete_list([
            # Delete "quick"
            DeleteOperation(4, 5),
            # Delete "fox"
            DeleteOperation(11, 3),
            # Delete "over"
            DeleteOperation(19, 4),
            # Delete "lazy"
            DeleteOperation(24, 4),
        ], 2)
        # After these operations, we will have "The  brown  jumped  the  dog"

        updated_sq1, updated_sq2 = engine._swap_sequence_delete_delete(sequence2, sequence1)
        self.assertEqual(updated_sq1.to_list(), [
            # Delete "The "
            DeleteOperation(0, 4),
            # Delete " brown"
            DeleteOperation(5, 6),
            # Delete "jumped "
            DeleteOperation(10, 7),
            # Delete " the "
            DeleteOperation(14, 5),
            # Delete " dog"
            DeleteOperation(18, 4),
        ])
        # After these, we will have "quick fox overlazy"
        self.assertEqual(updated_sq2.to_list(), [
            # Delete "quick"
            DeleteOperation(0, 5),
            # Delete "fox"
            DeleteOperation(1, 3),
            # Delete "over"
            DeleteOperation(2, 4),
            # Delete "lazy"
            DeleteOperation(2, 4),
        ])

    def test_process_transaction(self):
        engine = Engine(1)
        engine._inserts = convert_insert_list([
            InsertOperation(0, "The quick brown fox"),
            # insert "very " after "the"
            InsertOperation(4, "very "),
            # insert "ly" after "quick"
            InsertOperation(14, "ly"),
            # insert "u" after the 'o' in "brown"
            InsertOperation(20, "u"),
        ], 1)
        # After the inserts are applied, we would have "The very quickly brouwn fox"

        engine._deletes = convert_delete_list([
            # delete the "e" from "the"
            DeleteOperation(2, 1),
            # delete the "e" from "very"
            DeleteOperation(4, 1),
            # delete the "ui" from "quickly"
            DeleteOperation(8, 2),
            # delete the "ou" from "brouwn"
            DeleteOperation(15, 2),
            # delete the "o" from "fox"
            DeleteOperation(19, 1),
        ], 1)

        # After the deletes are applied, we would have "Th vry qckly brwn fx"

        sequence = TransactionSequence(State(1, 0, 0), InsertOperationNode.from_list([
            # Add an "ee" after "th"
            InsertOperation(2, "ee"),
            # Add another "k" on the end of "quickly"
            InsertOperation(14, "k"),
            # Add "wnwnwn" to the end of "brown"
            InsertOperation(20, "wnwnwn"),
            # Add "xx!" to the end of "fox"
            InsertOperation(29, "xx!"),
            # After the inserts, we would have "Thee vry qcklyk brwnwnwnwn fxxx!"
        ]), DeleteOperationNode.from_list([
            # Delete the "h" from "thee"
            DeleteOperation(1, 1),
            # Delete "br" from "brwnwnwnwn"
            DeleteOperation(15, 2),
            # Delete "f" from "foxxx!"
            DeleteOperation(24, 1)
        ]))
        # After the deletes, we would have "Tee vry qcklyk wnwnwnwn oxxx!"

        new_transaction = engine.process_transaction(sequence)

        self.assertListEqual(new_transaction.inserts.to_list(), [
            # Add an "ee" after "th"
            InsertOperation(3, "ee"),
            # Add a "k" after "qckly"
            InsertOperation(18, "k"),
            # Add a "wnwnwn" after "brwn"
            InsertOperation(26, "wnwnwn"),
            # Add "xx!" after "fx"
            InsertOperation(36, "xx!")
        ])
        # After the inserts are applied, we would have "Theee very quicklyk brouwnwnwnwn foxxx!"
        self.assertListEqual(new_transaction.deletes.to_list(), [
            # Delete the "h" in "theee"
            DeleteOperation(1, 1),
            # Delete "br"
            DeleteOperation(19, 2),
            # Delete "f"
            DeleteOperation(30, 1)
        ])
        # After these are applied, we would have "Teee very quicklyk ouwnwnwnwn oxxx!"

        self.assertEqual(engine._inserts.to_list(), [
            InsertOperation(0, "The quick brown fox"),
            # Add an "ee" after "the"
            InsertOperation(3, "ee"),
            # insert "very " after "theee "
            InsertOperation(6, "very "),
            # insert "ly" after "quick"
            InsertOperation(16, "ly"),
            # Add another "k" on the end of "quick"
            InsertOperation(18, "k"),
            # insert "u" after the 'o' in "brown"
            InsertOperation(23, "u"),
            # Add "wnwnwn" to the end of "brown"
            InsertOperation(26, "wnwnwn"),
            # Add "xx!" to the end of "fox"
            InsertOperation(36, "xx!"),

        ])
        # After all the inserts are applied, we should have "Theee very quicklyk brouwnwnwnwn foxxx!"
        self.assertEqual(engine._deletes.to_list(), [
            # Delete the "h" from "thee"
            DeleteOperation(1, 1),
            # delete the first "e" from "teee"
            DeleteOperation(1, 1),
            # delete the "e" from "very"
            DeleteOperation(5, 1),
            # delete the "ui" from "quicklyk"
            DeleteOperation(9, 2),
            # Delete "br" from "brouwnwnwnwn"
            DeleteOperation(15, 2),
            # delete the "ou" from "brouwn"
            DeleteOperation(15, 2),
            # Delete "f" from "foxxx!"
            DeleteOperation(24, 1),
            # delete the "o" from "oxxx!"
            DeleteOperation(24, 1),
        ])
        # After all the deletes are applied, we should have "Tee vry qcklyk wnwnwnwn xxx!"
