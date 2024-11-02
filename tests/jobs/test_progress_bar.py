import pytest

import time
from edsl import Agent, Scenario
from edsl.questions import QuestionYesNo


def test_slow_progress_bar():
    """Just makes sure that the progress bar doesn't throw an error."""

    from edsl import Model

    m = Model("test", canned_response="Yes")
    m.rpm = 2

    s = [Scenario({"number": number}) for number in range(20)]
    q = QuestionYesNo(
        question_text="Is this number prime: {{ number }}?", question_name="is_prime"
    )

    from edsl.data.Cache import Cache

    results = (
        q.by(s)
        .by(m)
        .run(progress_bar=True, cache=Cache(), disable_remote_inference=True)
    )

    results.select("number", "is_prime").print()


def test_progress_bar():
    """Just makes sure that the progress bar doesn't throw an error."""

    def is_prime(self, question, scenario):
        time.sleep(0.1)
        number = scenario["number"]
        if number < 2:
            return "Yes"
        for i in range(2, number):
            if number % i == 0:
                return "No"
        return "Yes"

    a = Agent(name="prime_knower")
    a.add_direct_question_answering_method(method=is_prime)

    s = [Scenario({"number": number}) for number in range(20)]
    q = QuestionYesNo(
        question_text="Is this number prime: {{ number }}?", question_name="is_prime"
    )

    from edsl.data.Cache import Cache

    results = (
        q.by(s)
        .by(a)
        .run(progress_bar=True, cache=Cache(), disable_remote_inference=True)
    )

    results.select("number", "is_prime").print()


if __name__ == "__main__":
    test_slow_progress_bar()
