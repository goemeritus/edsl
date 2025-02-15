import os
from edsl.exceptions.general import MissingAPIKeyError


class JobsChecks:
    def __init__(self, jobs):
        """Checks a Jobs object for missing API keys and other requirements."""
        self.jobs = jobs

    def check_api_keys(self) -> None:
        from edsl.language_models.model import Model

        if len(self.jobs.models) == 0:
            models = [Model()]
        else:
            models = self.jobs.models

        for model in models:  # + [Model()]:
            if not model.has_valid_api_key():
                raise MissingAPIKeyError(
                    model_name=str(model.model),
                    inference_service=model._inference_service_,
                )

    def get_missing_api_keys(self) -> set:
        """
        Returns a list of the API keys that a user needs to run this job, but does not currently have in their .env file.
        """
        missing_api_keys = set()

        from edsl.language_models.model import Model
        from edsl.enums import service_to_api_keyname

        for model in self.jobs.models: # + [Model()]:
            if not model.has_valid_api_key():
                key_name = service_to_api_keyname.get(
                    model._inference_service_, "NOT FOUND"
                )
                missing_api_keys.add(key_name)

        return missing_api_keys

    def user_has_ep_api_key(self) -> bool:
        """
        Returns True if the user has an EXPECTED_PARROT_API_KEY in their env.

        Otherwise, returns False.
        """

        coop_api_key = os.getenv("EXPECTED_PARROT_API_KEY")

        if coop_api_key is not None:
            return True
        else:
            return False

    def user_has_all_model_keys(self):
        """
        Returns True if the user has all model keys required to run their job.

        Otherwise, returns False.
        """

        try:
            self.check_api_keys()
            return True
        except MissingAPIKeyError:
            return False
        except Exception:
            raise

    def needs_external_llms(self) -> bool:
        """
        Returns True if the job needs external LLMs to run.

        Otherwise, returns False.
        """
        # These cases are necessary to skip the API key check during doctests

        # Accounts for Results.example()
        all_agents_answer_questions_directly = len(self.jobs.agents) > 0 and all(
            [hasattr(a, "answer_question_directly") for a in self.jobs.agents]
        )

        # Accounts for InterviewExceptionEntry.example()
        only_model_is_test = set([m.model for m in self.jobs.models]) == set(["test"])

        # Accounts for Survey.__call__
        all_questions_are_functional = set(
            [q.question_type for q in self.jobs.survey.questions]
        ) == set(["functional"])

        if (
            all_agents_answer_questions_directly
            or only_model_is_test
            or all_questions_are_functional
        ):
            return False
        else:
            return True

    def needs_key_process(self):
        """
        A User needs the key process when:
        1. They don't have all the model keys
        2. They don't have the EP API
        3. They need external LLMs to run the job
        """
        return (
            not self.user_has_all_model_keys()
            and not self.user_has_ep_api_key()
            and self.needs_external_llms()
        )

    def status(self) -> dict:
        """
        Returns a dictionary with the status of the job checks.
        """
        return {
            "user_has_ep_api_key": self.user_has_ep_api_key(),
            "user_has_all_model_keys": self.user_has_all_model_keys(),
            "needs_external_llms": self.needs_external_llms(),
            "needs_key_process": self.needs_key_process(),
        }

    def key_process(self):
        import secrets
        from dotenv import load_dotenv
        from edsl.config import CONFIG
        from edsl.coop.coop import Coop
        from edsl.utilities.utilities import write_api_key_to_env

        missing_api_keys = self.get_missing_api_keys()

        edsl_auth_token = secrets.token_urlsafe(16)

        print("\nThe following keys are needed to run this survey: \n")
        for api_key in missing_api_keys:
            print(f"🔑 {api_key}")
        print(
            """
            \nYou can provide your own keys for language models or use an Expected Parrot key to access all available models.
            \nClick the link below to create an account and run your survey with your Expected Parrot key:
            """
        )
    
        coop = Coop()
        coop._display_login_url(
            edsl_auth_token=edsl_auth_token,
            # link_description="",
        )

        api_key = coop._poll_for_api_key(edsl_auth_token)

        if api_key is None:
            print("\nTimed out waiting for login. Please try again.")
            return

        path_to_env = write_api_key_to_env(api_key)
        print(f"\n✨ Your Expected Parrot key has been stored at the following path: {path_to_env}\n")

        # Retrieve API key so we can continue running the job
        load_dotenv()


if __name__ == "__main__":
    import doctest

    doctest.testmod()
