'''
Created on Oct 5, 2017

@author: SamRagusa
'''
from grpc.beta import implementations
from numba_board import get_info_for_tensorflow, generate_move_to_enumeration_dict, TURN_WHITE
from diff_tensorflow_serving.apis import prediction_service_pb2
from tensorflow_serving.apis import regression_pb2
from tensorflow_serving.apis import classification_pb2
import numpy as np


MOVE_TO_INDEX_ARRAY = np.zeros(shape=[64,64],dtype=np.int32)
for key, value in generate_move_to_enumeration_dict().items():
    MOVE_TO_INDEX_ARRAY[key[0],key[1]] = value


def fill_example_from_board_state(example, board_state):
    """
    Fills the given tf.train.Example with the relevant information from the given board state.
    """
    board_info = get_info_for_tensorflow(board_state)

    example.features.feature["occupied_w"].int64_list.value.append(board_info[0])
    example.features.feature["occupied_b"].int64_list.value.append(board_info[1])
    example.features.feature["kings"].int64_list.value.append(board_info[2])
    example.features.feature["queens"].int64_list.value.append(board_info[3])
    example.features.feature["rooks"].int64_list.value.append(board_info[4])
    example.features.feature["bishops"].int64_list.value.append(board_info[5])
    example.features.feature["knights"].int64_list.value.append(board_info[6])
    example.features.feature["pawns"].int64_list.value.append(board_info[7])
    example.features.feature["castling_rights"].int64_list.value.append(board_info[8])
    example.features.feature["ep_square"].int64_list.value.append(board_info[9])


# @profile
def fill_example_from_board_state_with_moves(example, game_node):
    """
    Fills the given tf.train.Example with the relevant information from the given board state.
    """
    board_info = get_info_for_tensorflow(game_node.board_state)

    example.features.feature["occupied_w"].int64_list.value.append(board_info[0])
    example.features.feature["occupied_b"].int64_list.value.append(board_info[1])
    example.features.feature["kings"].int64_list.value.append(board_info[2])
    example.features.feature["queens"].int64_list.value.append(board_info[3])
    example.features.feature["rooks"].int64_list.value.append(board_info[4])
    example.features.feature["bishops"].int64_list.value.append(board_info[5])
    example.features.feature["knights"].int64_list.value.append(board_info[6])
    example.features.feature["pawns"].int64_list.value.append(board_info[7])
    example.features.feature["castling_rights"].int64_list.value.append(board_info[8])
    example.features.feature["ep_square"].int64_list.value.append(board_info[9])
    if game_node.board_state.turn != TURN_WHITE:        #THE ANNs DON'T SCORE BOARDS FOR THE RIGHT PLAYER SO THIS IS SWITCHED
        example.features.feature["legal_move_indices"].int64_list.value.extend(
            MOVE_TO_INDEX_ARRAY[game_node.unexplored_moves["from_square"], game_node.unexplored_moves["to_square"]])
    else:
        example.features.feature["legal_move_indices"].int64_list.value.extend(
            MOVE_TO_INDEX_ARRAY[
                # This is for the rotation of the board, and will be done better and likely in TensorFlow in the longer term
                8 * (7 - (game_node.unexplored_moves["from_square"] >> 3)) + (game_node.unexplored_moves["from_square"] & 7),
                8 * (7 - (game_node.unexplored_moves["to_square"] >> 3)) + (game_node.unexplored_moves["to_square"] & 7)])




class ANNEvaluator:
    def __init__(self, the_board, host="172.17.0.2", port=9000, model_name='evaluation_ann', model_desired_signature='serving_default', for_white=True):#
        self.host = host
        self.port = port
        self.model_name = model_name
        self.model_desired_signature=model_desired_signature
        self.channel = implementations.insecure_channel(host, port)
        self.stub = prediction_service_pb2.beta_create_PredictionService_stub(self.channel)
        self.request = regression_pb2.RegressionRequest()
        self.request.model_spec.name = self.model_name
        self.request.model_spec.signature_name = self.model_desired_signature
        self.board = the_board
        self.for_white = for_white
        self.total_evaluated_nodes = 0
        self.total_evaluations = 0





    def async_evaluate_boards_batch(self, game_nodes, timeout=10):
        """
        This functions sends a ProtoBuf representing an array of GameNode JitClass objects to
        TensorFlow Serving, and returns a future representing the values of the given nodes (done by regression).

        IMPORTANT NOTES:
        1) The current implementation seems like a very slow method of doing this, and will (very) likely not be
        used long term (it was created to verify other implementations before going too in depth).
        Using fancy Numpy and TensorFlow Serving techniques (likely buffers), I will hopefully send all this
        information at once without any seemingly tedious method calls like get_info_for_tensorflow(board_state),
        and without any loops. The functionality of this method (really) should be running from a compiled
        function/method, which seems like cannot be done currently using just the core functionality of Numba,
        and will likely have to be written in C and incorporated into the Numba compiled code.
        2) This only scores boards where it's white's turn
        """

        self.request.input.Clear()

        list(map(
            fill_example_from_board_state,
            (self.request.input.example_list.examples.add() for _ in range(len(game_nodes))),
            (node.board_state for node in game_nodes)))

        self.total_evaluations += 1
        self.total_evaluated_nodes += len(game_nodes)

        return self.stub.Regress.future(self.request, timeout)


    def async_evaluate_move_batch(self, game_nodes, timeout=10):
        """
        This functions sends a ProtoBuf representing an array of GameNode JitClass objects to
        TensorFlow Serving, and returns a future representing the scoring of possible moves from the
        given positions (done by classification).

        IMPORTANT NOTES:
        1) The current implementation seems like a very slow method of doing this, and will (very) likely not be
        used long term (it was created to verify other implementations before going too in depth).
        Using fancy Numpy and TensorFlow Serving techniques (likely buffers), I will hopefully send all this
        information at once without any seemingly tedious method calls like get_info_for_tensorflow(board_state),
        and without any loops. The functionality of this method (really) should be running from a compiled
        function/method, which seems like cannot be done currently using just the core functionality of Numba,
        and will likely have to be written in C and incorporated into the Numba compiled code.
        """
        request = classification_pb2.ClassificationRequest()
        request.model_spec.name = self.model_name
        request.model_spec.signature_name = self.model_desired_signature

        list(map(
            fill_example_from_board_state_with_moves,
            (request.input.example_list.examples.add() for _ in range(len(game_nodes))),
            game_nodes))

        self.total_evaluations += 1
        self.total_evaluated_nodes += len(game_nodes)

        return self.stub.Classify.future(request, timeout)


    def for_numba_score_batch(self, game_nodes, timeout=10):
        """
        Scores an array of GameNode JitClass objects using TensorFlow Serving.  It does this by creating a
        Protocol Buffer of the boards, and sending it to the TensorFlow Serving instance,
        then returning the value received back.

        NOTES:
        1) This method is only currently being used during database generation.
        """
        self.request.input.Clear()

        list(map(
            fill_example_from_board_state,
            (self.request.input.example_list.examples.add() for _ in range(len(game_nodes))),
            (node.board_state for node in game_nodes)))

        self.total_evaluations += 1
        self.total_evaluated_nodes += len(game_nodes)

        return self.stub.Regress(self.request, timeout).result.regressions