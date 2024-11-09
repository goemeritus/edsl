from edsl import Model
from edsl.jobs.Jobs import Jobs
from edsl.questions import QuestionFreeText
from edsl.surveys import Survey

price_lookup = {
    ("test", "test"): {
        "input": {
            "service": "test",
            "model": "test",
            "mode": "regular",
            "token_type": "input",
            "service_stated_token_qty": 1,
            "service_stated_token_price": 1,
            "one_usd_buys": 1,
        },
        "output": {
            "service": "test",
            "model": "test",
            "mode": "regular",
            "token_type": "output",
            "service_stated_token_qty": 1,
            "service_stated_token_price": 1,
            "one_usd_buys": 1,
        },
    }
}


def test_prompt_cost_estimation():
    estimated_cost_dct = Jobs.estimate_prompt_cost(
        system_prompt="",
        user_prompt="What is your favorite month?",
        price_lookup=price_lookup,
        inference_service="test",
        model="test",
    )

    assert estimated_cost_dct["input_tokens"] == 7
    assert estimated_cost_dct["output_tokens"] == 6
    assert estimated_cost_dct["cost_usd"] == 13

    estimated_cost_dct = Jobs.estimate_prompt_cost(
        system_prompt="",
        user_prompt="Why is that your favorite month?",
        price_lookup=price_lookup,
        inference_service="test",
        model="test",
    )

    assert estimated_cost_dct["input_tokens"] == 8
    assert estimated_cost_dct["output_tokens"] == 6
    assert estimated_cost_dct["cost_usd"] == 14


def test_prompt_cost_estimation_with_piping():
    estimated_cost_dct = Jobs.estimate_prompt_cost(
        system_prompt="",
        user_prompt="Why is {{ answer }} your favorite month?",
        price_lookup=price_lookup,
        inference_service="test",
        model="test",
    )

    assert estimated_cost_dct["input_tokens"] == 20
    assert estimated_cost_dct["output_tokens"] == 15
    assert estimated_cost_dct["cost_usd"] == 35


def test_job_cost_estimation():
    q0 = QuestionFreeText(
        question_name="q0", question_text="What is your favorite month?"
    )
    q1 = QuestionFreeText(
        question_name="q1", question_text="Why is that your favorite month?"
    )
    m = Model("test", canned_response="SPAM!")
    s = Survey(questions=[q0, q1])
    j = Jobs(survey=s, models=[m])
    estimated_cost_dct = Jobs.estimate_job_cost_from_external_prices(j, price_lookup)

    input_tokens = estimated_cost_dct["estimated_total_input_tokens"]
    assert input_tokens == 15

    output_tokens = estimated_cost_dct["estimated_total_output_tokens"]
    assert output_tokens == 12

    cost = estimated_cost_dct["estimated_total_cost_usd"]
    assert cost == 27


def test_job_cost_estimation_with_iterations():
    q0 = QuestionFreeText(
        question_name="q0", question_text="What is your favorite month?"
    )
    q1 = QuestionFreeText(
        question_name="q1", question_text="Why is that your favorite month?"
    )
    m = Model("test", canned_response="SPAM!")
    s = Survey(questions=[q0, q1])
    j = Jobs(survey=s, models=[m])
    estimated_cost_dct = Jobs.estimate_job_cost_from_external_prices(
        j, price_lookup, iterations=2
    )

    input_tokens = estimated_cost_dct["estimated_total_input_tokens"]
    assert input_tokens == 30

    output_tokens = estimated_cost_dct["estimated_total_output_tokens"]
    assert output_tokens == 24

    cost = estimated_cost_dct["estimated_total_cost_usd"]
    assert cost == 54


def test_job_cost_estimation_with_piping():
    q0 = QuestionFreeText(
        question_name="q0", question_text="What is your favorite month?"
    )
    q1 = QuestionFreeText(
        question_name="q1", question_text="Why is {{ q0.answer }} your favorite month?"
    )
    m = Model("test", canned_response="SPAM!")
    s = Survey(questions=[q0, q1])
    j = Jobs(survey=s, models=[m])
    estimated_cost_dct = Jobs.estimate_job_cost_from_external_prices(j, price_lookup)

    # Test to make sure that the piping multiplier has taken effect
    input_tokens = estimated_cost_dct["estimated_total_input_tokens"]
    assert input_tokens == 27  # 7 from q0 + 20 from q1

    output_tokens = estimated_cost_dct["estimated_total_output_tokens"]
    assert output_tokens == 21  # 6 from q0 + 15 from q1

    cost = estimated_cost_dct["estimated_total_cost_usd"]
    assert cost == 48  # 7 + 20 + 6 + 15


def test_job_cost_estimation_with_piping_and_iterations():
    q0 = QuestionFreeText(
        question_name="q0", question_text="What is your favorite month?"
    )
    q1 = QuestionFreeText(
        question_name="q1", question_text="Why is {{ q0.answer }} your favorite month?"
    )
    m = Model("test", canned_response="SPAM!")
    s = Survey(questions=[q0, q1])
    j = Jobs(survey=s, models=[m])
    estimated_cost_dct = Jobs.estimate_job_cost_from_external_prices(
        j, price_lookup, iterations=2
    )

    # Test to make sure that the piping multiplier has taken effect
    input_tokens = estimated_cost_dct["estimated_total_input_tokens"]
    assert input_tokens == 54

    output_tokens = estimated_cost_dct["estimated_total_output_tokens"]
    assert output_tokens == 42

    cost = estimated_cost_dct["estimated_total_cost_usd"]
    assert cost == 96
