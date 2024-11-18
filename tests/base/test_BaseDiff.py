import pytest
from edsl.base.BaseDiff import (
    BaseDiff,
    BaseDiffCollection,
)  # Adjust the import path as necessary


@pytest.fixture
def example_questions():
    from edsl import Question

    q_ft = Question.example("free_text")
    q_mc = Question.example("multiple_choice")
    return q_ft, q_mc


def test_diff_apply(example_questions):
    q_ft, q_mc = example_questions

    diff1 = BaseDiff(q_ft, q_mc)
    new_q_mc = diff1.apply(q_ft)

    assert new_q_mc == q_mc


def test_diff_chain_apply():
    from edsl import Question

    q0 = Question.example("free_text")
    q1 = q0.copy()
    q1.question_text = "Why is Buzzard's Bay so named?"
    diff1 = BaseDiff(q0, q1)

    q2 = q1.copy()
    q2.question_name = "buzzard_bay"
    diff2 = BaseDiff(q1, q2)

    diff_chain = diff1.add_diff(diff2)
    new_q2 = diff_chain.apply(q0)

    assert new_q2 == q2


def test_add_diff(example_questions):
    q_ft, q_mc = example_questions

    diff1 = BaseDiff(q_ft, q_mc)
    diff_collection = BaseDiffCollection([diff1])

    assert len(diff_collection) == 1
    assert diff_collection.apply(q_ft) == q_mc


def test_diff_repr(example_questions):
    q_ft, q_mc = example_questions

    diff1 = BaseDiff(q_ft, q_mc)
    repr_str = repr(diff1)

    assert "added=" in repr_str
    assert "removed=" in repr_str
    assert "modified=" in repr_str
