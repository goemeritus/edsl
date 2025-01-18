from edsl import QuestionFreeText, Survey


q1 = QuestionFreeText(
    question_name="q1", question_text="What is your favorite primary color 1?"
)
q2 = QuestionFreeText(
    question_name="q2",
    question_text="What is your favorite primary programming language?",
)

q3 = QuestionFreeText(
    question_name="q3", question_text="What is your favorite primary color 2?"
)
q4 = QuestionFreeText(
    question_name="q4",
    question_text="What is your favorite primary programming language 2?",
)
from edsl import Model

m = Model("test")
s = Survey(questions=[q1, q2, q3, q4])
res = s.by(m).run(disable_remote_inference=True, cache=False, stop_on_exception=True)
res.select("answer.*")
