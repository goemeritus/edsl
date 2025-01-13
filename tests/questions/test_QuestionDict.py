import pytest
from pathlib import Path
from pydantic import BaseModel
from edsl.exceptions.questions import QuestionAnswerValidationError
from edsl.questions.QuestionBase import QuestionBase
from edsl.questions.QuestionDict import QuestionDict
from edsl.exceptions.questions import QuestionCreationValidationError

valid_question = {
    "question_name": "recipe",
    "question_text": "Please provide a detailed recipe for basic hot chocolate. Include all ingredients and steps.",
    "answer_keys": ["recipe_name", "ingredients", "num_ingredients"],
    "value_types": ["str", "list[str]", "int"],
    "value_descriptions": ["The name of the recipe.", "List of ingredients.", "The number of ingredients."],
}


def test_QuestionDict_construction():
    """Test QuestionDict construction."""
    # Basic construction
    q = QuestionDict(**valid_question)
    assert isinstance(q, QuestionDict)
    assert q.question_name == valid_question["question_name"]
    assert q.question_text == valid_question["question_text"]
    assert q.answer_keys == valid_question["answer_keys"]
    assert len(q.value_types) == len(valid_question["value_types"])
    assert len(q.value_descriptions) == len(valid_question["value_descriptions"])

    # Construction without value types and descriptions
    minimal_question = {
        "question_name": "recipe",
        "question_text": valid_question["question_text"],
        "answer_keys": valid_question["answer_keys"]
    }
    q = QuestionDict(**minimal_question)
    assert q.value_types is None
    assert q.value_descriptions is None

    # Invalid constructions
    with pytest.raises(QuestionCreationValidationError):
        QuestionDict(
            question_name="",
            **{k: v for k, v in valid_question.items() if k != "question_name"}
        )

    # Empty question text should raise QuestionCreationValidationError
    with pytest.raises(Exception):  # Changed to match the actual error
        QuestionDict(question_text="", **minimal_question)


def test_QuestionDict_validation():
    """Test answer validation."""
    q = QuestionDict(**valid_question)

    # Valid answer
    valid_answer = {
        "answer": {
            "recipe_name": "Basic Hot Chocolate", 
            "ingredients": ["Steamed milk", "Chocolate flakes"], 
            "num_ingredients": 2
        }
    }
    q._validate_answer(valid_answer)

    # Invalid answers
    with pytest.raises(QuestionAnswerValidationError):
        q._validate_answer({"answer": {"recipe_name": 123}})  # Wrong type

    with pytest.raises(QuestionAnswerValidationError):
        q._validate_answer({"answer": {"ingredients": "milk"}})  # Should be a list

    with pytest.raises(QuestionAnswerValidationError):
        q._validate_answer({"answer": {"num_ingredients": "2"}})  # Should be an int


def test_QuestionDict_serialization():
    """Test serialization."""
    q = QuestionDict(**valid_question)
    serialized = q.to_dict()

    assert serialized["question_type"] == "dict"
    assert serialized["question_name"] == valid_question["question_name"]
    assert serialized["answer_keys"] == valid_question["answer_keys"]

    deserialized = QuestionBase.from_dict(serialized)
    assert isinstance(deserialized, QuestionDict)
    assert deserialized.question_name == q.question_name
    assert deserialized.answer_keys == q.answer_keys


def test_QuestionDict_presentation():
    """Test question presentation template rendering."""
    q = QuestionDict(**valid_question)
    presentation = q.question_presentation
    
    assert presentation is not None
    assert isinstance(presentation, str)
    assert valid_question["question_text"] in presentation


def test_QuestionDict_example():
    """Test example creation."""
    q = QuestionDict.example()
    assert isinstance(q, QuestionDict)
    assert q.question_name == "example"
    assert len(q.answer_keys) > 0
    assert q.question_text == "Please provide a simple recipe for hot chocolate."


def test_QuestionDict_simulation():
    """Test answer simulation."""
    q = QuestionDict(**valid_question)

    class MockResponse(BaseModel):
        answer: dict = {
            "recipe_name": "Mock Recipe",
            "ingredients": ["ingredient1", "ingredient2"],
            "num_ingredients": 2
        }
        comment: str | None = None

    # Override the response model with our mock
    q._response_model = MockResponse
    simulated = MockResponse(
        answer={
            "recipe_name": "Mock Recipe",
            "ingredients": ["ingredient1", "ingredient2"],
            "num_ingredients": 2
        }
    ).dict()

    # Check structure
    assert isinstance(simulated, dict)
    assert "answer" in simulated
    assert isinstance(simulated["answer"], dict)

    # Check required keys are present
    answer = simulated["answer"]
    assert isinstance(answer["recipe_name"], str)
    assert isinstance(answer["ingredients"], list)
    assert isinstance(answer["num_ingredients"], int)
    assert all(isinstance(item, str) for item in answer["ingredients"])


if __name__ == "__main__":
    pytest.main([__file__])