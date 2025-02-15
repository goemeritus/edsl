class CoopFunctionsMixin:
    def better_names(self, existing_names):
        from edsl import QuestionList, Scenario

        s = Scenario({"existing_names": existing_names})
        q = QuestionList(
            question_text="""The following column names are already in use: {{ existing_names }} 
                         Please provide new column names.
                         They should be short (one or two words) and unique valid Python idenifiers (i.e., use underscores instead of spaces). 
                         """,
            question_name="better_names",
        )
        results = q.by(s).run(verbose=False)
        return results.select("answer.better_names").first()
