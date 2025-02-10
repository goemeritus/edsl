import pytest
import uuid
from edsl.exceptions.questions import (
    QuestionAnswerValidationError,
    QuestionResponseValidationError,
)
from edsl.questions import Settings
from edsl.questions.QuestionBase import QuestionBase
from edsl.questions.QuestionMultipleChoice import QuestionMultipleChoice


def test_QuestionMultipleChoice_main():
    # main()
    pass


valid_question = {
    "question_text": "How are you?",
    "question_options": ["OK", "Bad"],
    "question_name": "how_are_you",
}


def test_QuestionMultipleChoice_construction():
    """Test QuestionMultipleChoice construction."""

    q = QuestionMultipleChoice(**valid_question)
    assert isinstance(q, QuestionMultipleChoice)
    assert q.question_name == valid_question["question_name"]
    assert q.question_text == valid_question["question_text"]
    assert q.question_options == valid_question["question_options"]

    assert q.data == valid_question

    # should raise an exception if question_text is missing
    invalid_question = valid_question.copy()
    invalid_question.pop("question_text")
    with pytest.raises(Exception):
        QuestionMultipleChoice(**invalid_question)

    # should raise an exception if question_text is empty
    invalid_question = valid_question.copy()
    invalid_question.update({"question_text": ""})
    with pytest.raises(Exception):
        QuestionMultipleChoice(**invalid_question)

    # should raise an exception if question_text is too long
    # invalid_question = valid_question.copy()
    # invalid_question.update({"question_text": "a" * (Settings.MAX_QUESTION_LENGTH + 1)})
    # with pytest.raises(Exception):
    #     QuestionMultipleChoice(**invalid_question)

    # should raise an exception if question_options is missing
    invalid_question = valid_question.copy()
    invalid_question.pop("question_options")
    with pytest.raises(Exception):
        QuestionMultipleChoice(**invalid_question)

    # should raise an exception if question_options is empty
    invalid_question = valid_question.copy()
    invalid_question.update({"question_options": []})
    with pytest.raises(Exception):
        QuestionMultipleChoice(**invalid_question)
    invalid_question.update({"question_options": ["OK"]})
    # or has 1 item
    with pytest.raises(Exception):
        QuestionMultipleChoice(**invalid_question)
    # or has duplicates
    invalid_question.update({"question_options": ["OK", "OK"]})
    with pytest.raises(Exception):
        QuestionMultipleChoice(**invalid_question)
    # or too many items
    # invalid_question.update(
    #     {
    #         "question_options": [
    #             str(uuid.uuid4()) for _ in range(Settings.MAX_NUM_OPTIONS + 1)
    #         ]
    #     }
    # )
    # with pytest.raises(Exception):
    #     QuestionMultipleChoice(**invalid_question)
    # or not of type list of strings
    # invalid_question.update({"question_options": ["OK", 2]})
    # with pytest.raises(Exception):
    #     QuestionMultipleChoice(**invalid_question)
    invalid_question.update({"question_options": ["OK", ""]})
    with pytest.raises(Exception):
        QuestionMultipleChoice(**invalid_question)

    invalid_question.update({"question_options": {"OK": "OK", "BAD": "BAD"}})
    with pytest.raises(Exception):
        QuestionMultipleChoice(**invalid_question)

    # should raise an exception if unexpected attribute is present
    invalid_question = valid_question.copy()
    invalid_question.update({"unexpected_attribute": "unexpected_attribute"})
    with pytest.raises(Exception):
        QuestionMultipleChoice(**invalid_question)

    # should raise an exception if question_name is a Python keyword
    invalid_question = valid_question.copy()
    invalid_question.update({"question_name": "for"})
    with pytest.raises(Exception):
        QuestionMultipleChoice(**invalid_question)
    invalid_question.update({"question_name": "!x12889"})
    with pytest.raises(Exception):
        QuestionMultipleChoice(**invalid_question)


def test_QuestionMultipleChoice_serialization():
    """Test QuestionMultipleChoice serialization."""

    # serialization should add a "type" attribute
    q = QuestionMultipleChoice(**valid_question)
    print(q.to_dict())
    assert {
        "question_name": "how_are_you",
        "question_text": "How are you?",
        "question_options": ["OK", "Bad"],
        "question_type": "multiple_choice",
    }.items() <= q.to_dict().items()

    # deserialization should return a QuestionMultipleChoiceEnhanced object
    q_lazarus = QuestionBase.from_dict(q.to_dict())
    assert isinstance(q_lazarus, QuestionMultipleChoice)
    assert type(q) == type(q_lazarus)
    assert repr(q) == repr(q_lazarus)

    # serialization from bad data should raise an exception
    with pytest.raises(Exception):
        QuestionBase.from_dict({"type": "multiple_choice"})
    with pytest.raises(Exception):
        QuestionBase.from_dict({"type": "multiple_choice", "question_text": 1})
    with pytest.raises(Exception):
        QuestionBase.from_dict({"type": "multiple_choice", "question_text": ""})
    with pytest.raises(Exception):
        QuestionBase.from_dict(
            {
                "type": "multiple_choice",
                "question_text": "a" * (Settings.MAX_QUESTION_LENGTH + 1),
            }
        )
    with pytest.raises(Exception):
        QuestionBase.from_dict(
            {
                "type": "multiple_choice",
                "question_text": "How are you?",
                "question_options": [],
            }
        )


def test_QuestionMultipleChoice_answers():
    q = QuestionMultipleChoice(**valid_question)
    llm_response_valid1 = {"answer": "OK", "comment": "I'm good"}
    llm_response_valid2 = {"answer": "Bad"}
    llm_response_invalid1 = {"comment": "I'm good"}

    # LLM response is required to have an answer key, but is flexible otherwise
    # q._validate_response(llm_response_valid1)
    # q._validate_response(llm_response_valid2)
    # with pytest.raises(QuestionResponseValidationError):
    #     q._validate_response(llm_response_invalid1)

    # # answer must be an integer or interpretable as integer
    # q._validate_answer({"answer": "Good"})
    # # TODO: should the following three be allowed?
    # q._validate_answer({"answer": "Good"})
    # q._validate_answer({"answer": True})
    # q._validate_answer({"answer": 0, "comment": "I'm good"})
    # # answer value required
    with pytest.raises(QuestionAnswerValidationError):
        q._validate_answer({"answer": None})
    # answer must be in range of question_options
    # with pytest.raises(QuestionAnswerValidationError):
    #    q._validate_answer({"answer": "2"})
    # answer can't be a random string
    with pytest.raises(QuestionAnswerValidationError):
        q._validate_answer({"answer": "asdf"})
    with pytest.raises(QuestionAnswerValidationError):
        q._validate_answer({"answer": [0, 1]})
    with pytest.raises(QuestionAnswerValidationError):
        q._validate_answer({"answer": {"answer": 0}})

def test_QuestionMultipleChoice_with_option_labels():
    question = QuestionMultipleChoice(
        question_name="favorite_time",
        question_text="What is your favorite time of day?",
        question_options=["morning", "afternoon", "evening", "night"],
        option_labels=[
            "Between 6:00 AM and 12:00 PM",
            "Between 12:00 PM and 6:00 PM",
            "Between 6:00 PM and 12:00 AM",
            "Between 12:00 AM and 6:00 AM",
        ]
    )

    assert question.option_labels is not None
    assert len(question.option_labels) == len(question.question_options)
    assert question.option_labels[1] == "Between 12:00 PM and 6:00 PM"

def test_create_response_model_with_option_labels():
    """Ensure option_labels are correctly included in the response model schema."""
    question = QuestionMultipleChoice(
        question_name="music_preference",
        question_text="Which music genre do you prefer?",
        question_options=["rock", "pop", "jazz", "classical"],
        option_labels=[
            "Rock - Energetic and guitar-driven.",
            "Pop - Catchy and radio-friendly.",
            "Jazz - Improvisational and soulful.",
            "Classical - Timeless and orchestral."
        ]
    )

    response_model = question.create_response_model()
    schema = response_model.schema()

    assert "option_labels" in schema
    assert schema["option_labels"]["rock"] == "Rock - Energetic and guitar-driven."
    assert schema["option_labels"]["pop"] == "Pop - Catchy and radio-friendly."
    assert schema["option_labels"]["jazz"] == "Jazz - Improvisational and soulful."

def test_permissive():
    q = QuestionMultipleChoice(**valid_question | {"permissive": True})
    q._validate_answer({"answer": "Poop"})


def test_instructions_overrride():
    q = QuestionMultipleChoice(**valid_question)
    assert q.answering_instructions is not None
    q = QuestionMultipleChoice(
        **valid_question | {"answering_instructions": "Please answer"}
    )
    assert q.answering_instructions == "Please answer"


def test_not_using_code():
    q = QuestionMultipleChoice(**(valid_question | {"use_code": False}))
    q._validate_answer({"answer": "OK"})


def test_QuestionMultipleChoice_extras():
    """Test QuestionFreeText extra functionalities."""
    q = QuestionMultipleChoice(**valid_question)
    # instructions
    # translate answer code to answer
    # assert q._translate_answer_code_to_answer(0, scenario=None) == "OK"
    # assert q._translate_answer_code_to_answer(1, scenario=None) == "Bad"
    # with pytest.raises(IndexError):
    #     q._translate_answer_code_to_answer(2, scenario=None)

    # _simulate_answer
    # assert q._simulate_answer().keys() == q._simulate_answer(human_readable=True).keys()
    # assert q._simulate_answer(human_readable=False)["answer"] in range(
    #     len(q.question_options)
    # )
    # simulated_answer = q._simulate_answer()
    # assert isinstance(simulated_answer, dict)
    # assert "answer" in simulated_answer
    # assert "comment" in simulated_answer
    # assert isinstance(simulated_answer["answer"], str)
    # assert len(simulated_answer["answer"]) <= Settings.MAX_ANSWER_LENGTH
    # assert len(simulated_answer["answer"]) > 0
    # assert simulated_answer["answer"] in q.question_options
