"""
The Results object is the result of running a survey. 
It is not typically instantiated directly, but is returned by the run method of a `Job` object.
"""

from __future__ import annotations
import json
import random
from collections import UserList, defaultdict
from typing import Optional, Callable, Any, Type, Union, List, TYPE_CHECKING

if TYPE_CHECKING:
    from edsl import Survey, Cache, AgentList, ModelList, ScenarioList
    from edsl.results.Result import Result
    from edsl.jobs.tasks.TaskHistory import TaskHistory

from simpleeval import EvalWithCompoundTypes

from edsl.exceptions.results import (
    ResultsError,
    ResultsBadMutationstringError,
    ResultsColumnNotFoundError,
    ResultsInvalidNameError,
    ResultsMutateError,
    ResultsFilterError,
    ResultsDeserializationError,
)

from edsl.results.ResultsExportMixin import ResultsExportMixin
from edsl.results.ResultsToolsMixin import ResultsToolsMixin
from edsl.results.ResultsDBMixin import ResultsDBMixin
from edsl.results.ResultsGGMixin import ResultsGGMixin
from edsl.results.ResultsFetchMixin import ResultsFetchMixin

from edsl.utilities.decorators import add_edsl_version, remove_edsl_version
from edsl.utilities.utilities import dict_hash


from edsl.base.Base import Base


class Mixins(
    ResultsExportMixin,
    ResultsDBMixin,
    ResultsFetchMixin,
    ResultsGGMixin,
    ResultsToolsMixin,
):
    def print_long(self, max_rows: int = None) -> None:
        """Print the results in long format.

        >>> from edsl.results import Results
        >>> r = Results.example()
        >>> r.select('how_feeling').print_long(max_rows = 2)
        ┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━┓
        ┃ Result index ┃ Key         ┃ Value ┃
        ┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━┩
        │ 0            │ how_feeling │ OK    │
        │ 1            │ how_feeling │ Great │
        └──────────────┴─────────────┴───────┘
        """
        from edsl.utilities.interface import print_results_long

        print_results_long(self, max_rows=max_rows)


class Results(UserList, Mixins, Base):
    """
    This class is a UserList of Result objects.

    It is instantiated with a `Survey` and a list of `Result` objects.
    It can be manipulated in various ways with select, filter, mutate, etc.
    It also has a list of created_columns, which are columns that have been created with `mutate` and are not part of the original data.
    """

    known_data_types = [
        "answer",
        "scenario",
        "agent",
        "model",
        "prompt",
        "raw_model_response",
        "iteration",
        "question_text",
        "question_options",
        "question_type",
        "comment",
        "generated_tokens",
    ]

    def __init__(
        self,
        survey: Optional[Survey] = None,
        data: Optional[list[Result]] = None,
        created_columns: Optional[list[str]] = None,
        cache: Optional[Cache] = None,
        job_uuid: Optional[str] = None,
        total_results: Optional[int] = None,
        task_history: Optional[TaskHistory] = None,
    ):
        """Instantiate a `Results` object with a survey and a list of `Result` objects.

        :param survey: A Survey object.
        :param data: A list of Result objects.
        :param created_columns: A list of strings that are created columns.
        :param job_uuid: A string representing the job UUID.
        :param total_results: An integer representing the total number of results.
        """
        super().__init__(data)
        from edsl.data.Cache import Cache
        from edsl.jobs.tasks.TaskHistory import TaskHistory

        self.survey = survey
        self.created_columns = created_columns or []
        self._job_uuid = job_uuid
        self._total_results = total_results
        self.cache = cache or Cache()

        self.task_history = task_history or TaskHistory(interviews=[])

        if hasattr(self, "_add_output_functions"):
            self._add_output_functions()

    def leaves(self):
        leaves = []
        for result in self:
            leaves.extend(result.leaves())
        return leaves

    def tree(
        self,
        fold_attributes: Optional[List[str]] = None,
        drop: Optional[List[str]] = None,
        open_file=True,
    ) -> dict:
        """Return the results as a tree."""
        from edsl.results.tree_explore import FoldableHTMLTableGenerator

        if drop is None:
            drop = []

        valid_attributes = [
            "model",
            "scenario",
            "agent",
            "answer",
            "question",
            "iteration",
        ]
        if fold_attributes is None:
            fold_attributes = []

        for attribute in fold_attributes:
            if attribute not in valid_attributes:
                raise ValueError(
                    f"Invalid fold attribute: {attribute}; must be in {valid_attributes}"
                )
        data = self.leaves()
        generator = FoldableHTMLTableGenerator(data)
        tree = generator.tree(fold_attributes=fold_attributes, drop=drop)
        html_content = generator.generate_html(tree, fold_attributes)
        import tempfile
        from edsl.utilities.utilities import is_notebook

        from IPython.display import display, HTML

        if is_notebook():
            import html
            from IPython.display import display, HTML

            height = 1000
            width = 1000
            escaped_output = html.escape(html_content)
            # escaped_output = rendered_html
            iframe = f""""
            <iframe srcdoc="{ escaped_output }" style="width: {width}px; height: {height}px;"></iframe>
            """
            display(HTML(iframe))
            return None

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            f.write(html_content.encode())
            print(f"HTML file has been generated: {f.name}")

            if open_file:
                import webbrowser
                import time

                time.sleep(1)  # Wait for 1 second
                # webbrowser.open(f.name)
                import os

                filename = f.name
                webbrowser.open(f"file://{os.path.abspath(filename)}")

            else:
                return html_content

    def code(self):
        raise NotImplementedError

    def __getitem__(self, i):
        if isinstance(i, int):
            return self.data[i]

        if isinstance(i, slice):
            return self.__class__(survey=self.survey, data=self.data[i])

        if isinstance(i, str):
            return self.to_dict()[i]

        raise TypeError("Invalid argument type")

    def _update_results(self) -> None:
        from edsl import Agent, Scenario
        from edsl.language_models import LanguageModel
        from edsl.results import Result

        if self._job_uuid and len(self.data) < self._total_results:
            results = [
                Result(
                    agent=Agent.from_dict(json.loads(r.agent)),
                    scenario=Scenario.from_dict(json.loads(r.scenario)),
                    model=LanguageModel.from_dict(json.loads(r.model)),
                    iteration=1,
                    answer=json.loads(r.answer),
                )
                for r in CRUD.read_results(self._job_uuid)
            ]
            self.data = results

    def __add__(self, other: Results) -> Results:
        """Add two Results objects together.
        They must have the same survey and created columns.
        :param other: A Results object.

        Example:

        >>> r = Results.example()
        >>> r2 = Results.example()
        >>> r3 = r + r2
        """
        if self.survey != other.survey:
            raise ResultsError(
                "The surveys are not the same so the the results cannot be added together."
            )
        if self.created_columns != other.created_columns:
            raise ResultsError(
                "The created columns are not the same so they cannot be added together."
            )

        return Results(
            survey=self.survey,
            data=self.data + other.data,
            created_columns=self.created_columns,
        )

    def __repr__(self) -> str:
        import reprlib

        return f"Results(data = {reprlib.repr(self.data)}, survey = {repr(self.survey)}, created_columns = {self.created_columns})"

    def _repr_html_(self) -> str:
        # from IPython.display import HTML

        json_str = json.dumps(self.to_dict(add_edsl_version=False)["data"], indent=4)
        return f"<pre>{json_str}</pre>"

    def to_dict(self, sort=False, add_edsl_version=False) -> dict[str, Any]:
        from edsl.data.Cache import Cache

        if sort:
            data = sorted([result for result in self.data], key=lambda x: hash(x))
        else:
            data = [result for result in self.data]

        d = {
            "data": [
                result.to_dict(add_edsl_version=add_edsl_version) for result in data
            ],
            "survey": self.survey.to_dict(add_edsl_version=add_edsl_version),
            "created_columns": self.created_columns,
            "cache": (
                Cache()
                if not hasattr(self, "cache")
                else self.cache.to_dict(add_edsl_version=add_edsl_version)
            ),
            "task_history": self.task_history.to_dict(),
        }
        if add_edsl_version:
            from edsl import __version__

            d["edsl_version"] = __version__
            d["edsl_class_name"] = "Results"

        return d

    def compare(self, other_results):
        """
        Compare two Results objects and return the differences.
        """
        hashes_0 = [hash(result) for result in self]
        hashes_1 = [hash(result) for result in other_results]

        in_self_but_not_other = set(hashes_0).difference(set(hashes_1))
        in_other_but_not_self = set(hashes_1).difference(set(hashes_0))

        indicies_self = [hashes_0.index(h) for h in in_self_but_not_other]
        indices_other = [hashes_1.index(h) for h in in_other_but_not_self]
        return {
            "a_not_b": [self[i] for i in indicies_self],
            "b_not_a": [other_results[i] for i in indices_other],
        }

    @property
    def has_unfixed_exceptions(self):
        return self.task_history.has_unfixed_exceptions

    def __hash__(self) -> int:
        return dict_hash(self.to_dict(sort=True, add_edsl_version=False))

    @property
    def hashes(self) -> set:
        return set(hash(result) for result in self.data)

    def sample(self, n: int) -> Results:
        """Return a random sample of the results.

        :param n: The number of samples to return.

        >>> from edsl.results import Results
        >>> r = Results.example()
        >>> len(r.sample(2))
        2
        """
        indices = None

        for entry in self:
            key, values = list(entry.items())[0]
            if indices is None:  # gets the indices for the first time
                indices = list(range(len(values)))
                sampled_indices = random.sample(indices, n)
                if n > len(indices):
                    raise ResultsError(
                        f"Cannot sample {n} items from a list of length {len(indices)}."
                    )
            entry[key] = [values[i] for i in sampled_indices]

        return self

    @classmethod
    @remove_edsl_version
    def from_dict(cls, data: dict[str, Any]) -> Results:
        """Convert a dictionary to a Results object.

        :param data: A dictionary representation of a Results object.

        Example:

        >>> r = Results.example()
        >>> d = r.to_dict()
        >>> r2 = Results.from_dict(d)
        >>> r == r2
        True
        """
        from edsl import Survey, Cache
        from edsl.results.Result import Result
        from edsl.jobs.tasks.TaskHistory import TaskHistory

        try:
            results = cls(
                survey=Survey.from_dict(data["survey"]),
                data=[Result.from_dict(r) for r in data["data"]],
                created_columns=data.get("created_columns", None),
                cache=(
                    Cache.from_dict(data.get("cache")) if "cache" in data else Cache()
                ),
                task_history=TaskHistory.from_dict(data.get("task_history")),
            )
        except Exception as e:
            raise ResultsDeserializationError(f"Error in Results.from_dict: {e}")
        return results

    ######################
    ## Convenience methods
    ## & Report methods
    ######################
    @property
    def _key_to_data_type(self) -> dict[str, str]:
        """
        Return a mapping of keys (how_feeling, status, etc.) to strings representing data types.

        Objects such as Agent, Answer, Model, Scenario, etc.
        - Uses the key_to_data_type property of the Result class.
        - Includes any columns that the user has created with `mutate`
        """
        d: dict = {}
        for result in self.data:
            d.update(result.key_to_data_type)
        for column in self.created_columns:
            d[column] = "answer"

        return d

    @property
    def _data_type_to_keys(self) -> dict[str, str]:
        """
        Return a mapping of strings representing data types (objects such as Agent, Answer, Model, Scenario, etc.) to keys (how_feeling, status, etc.)
        - Uses the key_to_data_type property of the Result class.
        - Includes any columns that the user has created with `mutate`

        Example:

        >>> r = Results.example()
        >>> r._data_type_to_keys
        defaultdict(...
        """
        d: dict = defaultdict(set)
        for result in self.data:
            for key, value in result.key_to_data_type.items():
                d[value] = d[value].union(set({key}))
        for column in self.created_columns:
            d["answer"] = d["answer"].union(set({column}))
        return d

    @property
    def columns(self) -> list[str]:
        """Return a list of all of the columns that are in the Results.

        Example:

        >>> r = Results.example()
        >>> r.columns
        ['agent.agent_instruction', ...]
        """
        column_names = [f"{v}.{k}" for k, v in self._key_to_data_type.items()]
        return sorted(column_names)

    @property
    def answer_keys(self) -> dict[str, str]:
        """Return a mapping of answer keys to question text.

        Example:

        >>> r = Results.example()
        >>> r.answer_keys
        {'how_feeling': 'How are you this {{ period }}?', 'how_feeling_yesterday': 'How were you feeling yesterday {{ period }}?'}
        """
        from edsl.utilities.utilities import shorten_string

        if not self.survey:
            raise ResultsError("Survey is not defined so no answer keys are available.")

        answer_keys = self._data_type_to_keys["answer"]
        answer_keys = {k for k in answer_keys if "_comment" not in k}
        questions_text = [
            self.survey.get_question(k).question_text for k in answer_keys
        ]
        short_question_text = [shorten_string(q, 80) for q in questions_text]
        initial_dict = dict(zip(answer_keys, short_question_text))
        sorted_dict = {key: initial_dict[key] for key in sorted(initial_dict)}
        return sorted_dict

    @property
    def agents(self) -> AgentList:
        """Return a list of all of the agents in the Results.

        Example:

        >>> r = Results.example()
        >>> r.agents
        AgentList([Agent(traits = {'status': 'Joyful'}), Agent(traits = {'status': 'Joyful'}), Agent(traits = {'status': 'Sad'}), Agent(traits = {'status': 'Sad'})])
        """
        from edsl import AgentList

        return AgentList([r.agent for r in self.data])

    @property
    def models(self) -> ModelList:
        """Return a list of all of the models in the Results.

        Example:

        >>> r = Results.example()
        >>> r.models[0]
        Model(model_name = ...)
        """
        from edsl import ModelList

        return ModelList([r.model for r in self.data])

    @property
    def scenarios(self) -> ScenarioList:
        """Return a list of all of the scenarios in the Results.

        Example:

        >>> r = Results.example()
        >>> r.scenarios
        ScenarioList([Scenario({'period': 'morning'}), Scenario({'period': 'afternoon'}), Scenario({'period': 'morning'}), Scenario({'period': 'afternoon'})])
        """
        from edsl import ScenarioList

        return ScenarioList([r.scenario for r in self.data])

    @property
    def agent_keys(self) -> list[str]:
        """Return a set of all of the keys that are in the Agent data.

        Example:

        >>> r = Results.example()
        >>> r.agent_keys
        ['agent_instruction', 'agent_name', 'status']
        """
        return sorted(self._data_type_to_keys["agent"])

    @property
    def model_keys(self) -> list[str]:
        """Return a set of all of the keys that are in the LanguageModel data.

        >>> r = Results.example()
        >>> r.model_keys
        ['frequency_penalty', 'logprobs', 'max_tokens', 'model', 'presence_penalty', 'temperature', 'top_logprobs', 'top_p']
        """
        return sorted(self._data_type_to_keys["model"])

    @property
    def scenario_keys(self) -> list[str]:
        """Return a set of all of the keys that are in the Scenario data.

        >>> r = Results.example()
        >>> r.scenario_keys
        ['period']
        """
        return sorted(self._data_type_to_keys["scenario"])

    @property
    def question_names(self) -> list[str]:
        """Return a list of all of the question names.

        Example:

        >>> r = Results.example()
        >>> r.question_names
        ['how_feeling', 'how_feeling_yesterday']
        """
        if self.survey is None:
            return []
        return sorted(list(self.survey.question_names))

    @property
    def all_keys(self) -> list[str]:
        """Return a set of all of the keys that are in the Results.

        Example:

        >>> r = Results.example()
        >>> r.all_keys
        ['agent_instruction', 'agent_name', 'frequency_penalty', 'how_feeling', 'how_feeling_yesterday', 'logprobs', 'max_tokens', 'model', 'period', 'presence_penalty', 'status', 'temperature', 'top_logprobs', 'top_p']
        """
        answer_keys = set(self.answer_keys)
        all_keys = (
            answer_keys.union(self.agent_keys)
            .union(self.scenario_keys)
            .union(self.model_keys)
        )
        return sorted(list(all_keys))

    def first(self) -> Result:
        """Return the first observation in the results.

        Example:

        >>> r = Results.example()
        >>> r.first()
        Result(agent...
        """
        return self.data[0]

    def answer_truncate(self, column: str, top_n=5, new_var_name=None) -> Results:
        """Create a new variable that truncates the answers to the top_n.

        :param column: The column to truncate.
        :param top_n: The number of top answers to keep.
        :param new_var_name: The name of the new variable. If None, it is the original name + '_truncated'.



        """
        if new_var_name is None:
            new_var_name = column + "_truncated"
        answers = list(self.select(column).tally().keys())

        def f(x):
            if x in answers[:top_n]:
                return x
            else:
                return "Other"

        return self.recode(column, recode_function=f, new_var_name=new_var_name)

    def recode(
        self, column: str, recode_function: Optional[Callable], new_var_name=None
    ) -> Results:
        """
        Recode a column in the Results object.

        >>> r = Results.example()
        >>> r.recode('how_feeling', recode_function = lambda x: 1 if x == 'Great' else 0).select('how_feeling', 'how_feeling_recoded')
        Dataset([{'answer.how_feeling': ['OK', 'Great', 'Terrible', 'OK']}, {'answer.how_feeling_recoded': [0, 1, 0, 0]}])
        """

        if new_var_name is None:
            new_var_name = column + "_recoded"
        new_data = []
        for result in self.data:
            new_result = result.copy()
            value = new_result.get_value("answer", column)
            # breakpoint()
            new_result["answer"][new_var_name] = recode_function(value)
            new_data.append(new_result)

        # print("Created new variable", new_var_name)
        return Results(
            survey=self.survey,
            data=new_data,
            created_columns=self.created_columns + [new_var_name],
        )

    def add_column(self, column_name: str, values: list) -> Results:
        """Adds columns to Results

        >>> r = Results.example()
        >>> r.add_column('a', [1,2,3, 4]).select('a')
        Dataset([{'answer.a': [1, 2, 3, 4]}])
        """

        assert len(values) == len(
            self.data
        ), "The number of values must match the number of results."
        new_results = self.data.copy()
        for i, result in enumerate(new_results):
            result["answer"][column_name] = values[i]
        return Results(
            survey=self.survey,
            data=new_results,
            created_columns=self.created_columns + [column_name],
        )

    def add_columns_from_dict(self, columns: List[dict]) -> Results:
        """Adds columns to Results from a list of dictionaries.

        >>> r = Results.example()
        >>> r.add_columns_from_dict([{'a': 1, 'b': 2}, {'a': 3, 'b': 4}, {'a':3, 'b':2}, {'a':3, 'b':2}]).select('a', 'b')
        Dataset([{'answer.a': [1, 3, 3, 3]}, {'answer.b': [2, 4, 2, 2]}])
        """
        keys = list(columns[0].keys())
        for key in keys:
            values = [d[key] for d in columns]
            self = self.add_column(key, values)
        return self

    @staticmethod
    def _create_evaluator(
        result: Result, functions_dict: Optional[dict] = None
    ) -> EvalWithCompoundTypes:
        """Create an evaluator for the expression.

        >>> from unittest.mock import Mock
        >>> result = Mock()
        >>> result.combined_dict = {'how_feeling': 'OK'}

        >>> evaluator = Results._create_evaluator(result = result, functions_dict = {})
        >>> evaluator.eval("how_feeling == 'OK'")
        True

        >>> result.combined_dict = {'answer': {'how_feeling': 'OK'}}
        >>> evaluator = Results._create_evaluator(result = result, functions_dict = {})
        >>> evaluator.eval("answer.how_feeling== 'OK'")
        True

        Note that you need to refer to the answer dictionary in the expression.

        >>> evaluator.eval("how_feeling== 'OK'")
        Traceback (most recent call last):
        ...
        simpleeval.NameNotDefined: 'how_feeling' is not defined for expression 'how_feeling== 'OK''
        """
        if functions_dict is None:
            functions_dict = {}
        evaluator = EvalWithCompoundTypes(
            names=result.combined_dict, functions=functions_dict
        )
        evaluator.functions.update(int=int, float=float)
        return evaluator

    def mutate(
        self, new_var_string: str, functions_dict: Optional[dict] = None
    ) -> Results:
        """
        Creates a value in the Results object as if has been asked as part of the survey.

        :param new_var_string: A string that is a valid Python expression.
        :param functions_dict: A dictionary of functions that can be used in the expression. The keys are the function names and the values are the functions themselves.

        It splits the new_var_string at the "=" and uses simple_eval

        Example:

        >>> r = Results.example()
        >>> r.mutate('how_feeling_x = how_feeling + "x"').select('how_feeling_x')
        Dataset([{'answer.how_feeling_x': ...
        """
        # extract the variable name and the expression
        if "=" not in new_var_string:
            raise ResultsBadMutationstringError(
                f"Mutate requires an '=' in the string, but '{new_var_string}' doesn't have one."
            )
        raw_var_name, expression = new_var_string.split("=", 1)
        var_name = raw_var_name.strip()
        from edsl.utilities.utilities import is_valid_variable_name

        if not is_valid_variable_name(var_name):
            raise ResultsInvalidNameError(f"{var_name} is not a valid variable name.")

        # create the evaluator
        functions_dict = functions_dict or {}

        def new_result(old_result: "Result", var_name: str) -> "Result":
            evaluator = self._create_evaluator(old_result, functions_dict)
            value = evaluator.eval(expression)
            new_result = old_result.copy()
            new_result["answer"][var_name] = value
            return new_result

        try:
            new_data = [new_result(result, var_name) for result in self.data]
        except Exception as e:
            raise ResultsMutateError(f"Error in mutate. Exception:{e}")

        return Results(
            survey=self.survey,
            data=new_data,
            created_columns=self.created_columns + [var_name],
        )

    def rename(self, old_name: str, new_name: str) -> Results:
        """Rename an answer column in a Results object.

        >>> s = Results.example()
        >>> s.rename('how_feeling', 'how_feeling_new').select('how_feeling_new')
        Dataset([{'answer.how_feeling_new': ['OK', 'Great', 'Terrible', 'OK']}])

        # TODO: Should we allow renaming of scenario fields as well? Probably.

        """

        for obs in self.data:
            obs["answer"][new_name] = obs["answer"][old_name]
            del obs["answer"][old_name]

        return self

    def shuffle(self, seed: Optional[str] = "edsl") -> Results:
        """Shuffle the results.

        Example:

        >>> r = Results.example()
        >>> r.shuffle(seed = 1)[0]
        Result(...)
        """
        if seed != "edsl":
            seed = random.seed(seed)

        new_data = self.data.copy()
        random.shuffle(new_data)
        return Results(survey=self.survey, data=new_data, created_columns=None)

    def sample(
        self,
        n: Optional[int] = None,
        frac: Optional[float] = None,
        with_replacement: bool = True,
        seed: Optional[str] = "edsl",
    ) -> Results:
        """Sample the results.

        :param n: An integer representing the number of samples to take.
        :param frac: A float representing the fraction of samples to take.
        :param with_replacement: A boolean representing whether to sample with replacement.
        :param seed: An integer representing the seed for the random number generator.

        Example:

        >>> r = Results.example()
        >>> len(r.sample(2))
        2
        """
        if seed != "edsl":
            random.seed(seed)

        if n is None and frac is None:
            raise Exception("You must specify either n or frac.")

        if n is not None and frac is not None:
            raise Exception("You cannot specify both n and frac.")

        if frac is not None and n is None:
            n = int(frac * len(self.data))

        if with_replacement:
            new_data = random.choices(self.data, k=n)
        else:
            new_data = random.sample(self.data, n)

        return Results(survey=self.survey, data=new_data, created_columns=None)

    def select(self, *columns: Union[str, list[str]]) -> Results:
        """
        Select data from the results and format it.

        :param columns: A list of strings, each of which is a column name. The column name can be a single key, e.g. "how_feeling", or a dot-separated string, e.g. "answer.how_feeling".

        Example:

        >>> results = Results.example()
        >>> results.select('how_feeling')
        Dataset([{'answer.how_feeling': ['OK', 'Great', 'Terrible', 'OK']}])

        >>> results.select('how_feeling', 'model', 'how_feeling')
        Dataset([{'answer.how_feeling': ['OK', 'Great', 'Terrible', 'OK']}, {'answer.how_feeling': ['OK', 'Great', 'Terrible', 'OK']}, {'model.model': ['...', '...', '...', '...']}, {'answer.how_feeling': ['OK', 'Great', 'Terrible', 'OK']}, {'answer.how_feeling': ['OK', 'Great', 'Terrible', 'OK']}])

        >>> from edsl import Results; r = Results.example(); r.select('answer.how_feeling_y')
        Dataset([{'answer.how_feeling_yesterday': ['Great', 'Good', 'OK', 'Terrible']}])
        """

        from edsl.results.Selector import Selector

        if len(self) == 0:
            raise Exception("No data to select from---the Results object is empty.")

        selector = Selector(
            known_data_types=self.known_data_types,
            data_type_to_keys=self._data_type_to_keys,
            key_to_data_type=self._key_to_data_type,
            fetch_list_func=self._fetch_list,
            columns=self.columns,
        )
        return selector.select(*columns)

    def sort_by(self, *columns: str, reverse: bool = False) -> Results:
        import warnings

        warnings.warn(
            "sort_by is deprecated. Use order_by instead.", DeprecationWarning
        )
        return self.order_by(*columns, reverse=reverse)

    def _parse_column(self, column: str) -> tuple[str, str]:
        if "." in column:
            return column.split(".")
        return self._key_to_data_type[column], column

    def order_by(self, *columns: str, reverse: bool = False) -> Results:
        """Sort the results by one or more columns.

        :param columns: One or more column names as strings.
        :param reverse: A boolean that determines whether to sort in reverse order.

        Each column name can be a single key, e.g. "how_feeling", or a dot-separated string, e.g. "answer.how_feeling".

        Example:

        >>> r = Results.example()
        >>> r.sort_by('how_feeling', reverse=False).select('how_feeling').print()
        ┏━━━━━━━━━━━━━━┓
        ┃ answer       ┃
        ┃ .how_feeling ┃
        ┡━━━━━━━━━━━━━━┩
        │ Great        │
        ├──────────────┤
        │ OK           │
        ├──────────────┤
        │ OK           │
        ├──────────────┤
        │ Terrible     │
        └──────────────┘
        >>> r.sort_by('how_feeling', reverse=True).select('how_feeling').print()
        ┏━━━━━━━━━━━━━━┓
        ┃ answer       ┃
        ┃ .how_feeling ┃
        ┡━━━━━━━━━━━━━━┩
        │ Terrible     │
        ├──────────────┤
        │ OK           │
        ├──────────────┤
        │ OK           │
        ├──────────────┤
        │ Great        │
        └──────────────┘
        """

        def to_numeric_if_possible(v):
            try:
                return float(v)
            except:
                return v

        def sort_key(item):
            key_components = []
            for col in columns:
                data_type, key = self._parse_column(col)
                value = item.get_value(data_type, key)
                key_components.append(to_numeric_if_possible(value))
            return tuple(key_components)

        new_data = sorted(self.data, key=sort_key, reverse=reverse)
        return Results(survey=self.survey, data=new_data, created_columns=None)

    def filter(self, expression: str) -> Results:
        """
        Filter based on the given expression and returns the filtered `Results`.

        :param expression: A string expression that evaluates to a boolean. The expression is applied to each element in `Results` to determine whether it should be included in the filtered results.

        The `expression` parameter is a string that must resolve to a boolean value when evaluated against each element in `Results`.
        This expression is used to determine which elements to include in the returned `Results`.

        Example usage: Create an example `Results` instance and apply filters to it:

        >>> r = Results.example()
        >>> r.filter("how_feeling == 'Great'").select('how_feeling').print()
        ┏━━━━━━━━━━━━━━┓
        ┃ answer       ┃
        ┃ .how_feeling ┃
        ┡━━━━━━━━━━━━━━┩
        │ Great        │
        └──────────────┘

        Example usage: Using an OR operator in the filter expression.

        >>> r = Results.example().filter("how_feeling = 'Great'").select('how_feeling').print()
        Traceback (most recent call last):
        ...
        edsl.exceptions.results.ResultsFilterError: You must use '==' instead of '=' in the filter expression.
        ...

        >>> r.filter("how_feeling == 'Great' or how_feeling == 'Terrible'").select('how_feeling').print()
        ┏━━━━━━━━━━━━━━┓
        ┃ answer       ┃
        ┃ .how_feeling ┃
        ┡━━━━━━━━━━━━━━┩
        │ Great        │
        ├──────────────┤
        │ Terrible     │
        └──────────────┘
        """

        def has_single_equals(string):
            if "!=" in string:
                return False
            if "=" in string and not (
                "==" in string or "<=" in string or ">=" in string
            ):
                return True

        if has_single_equals(expression):
            raise ResultsFilterError(
                "You must use '==' instead of '=' in the filter expression."
            )

        try:
            # iterates through all the results and evaluates the expression
            new_data = []
            for result in self.data:
                evaluator = self._create_evaluator(result)
                result.check_expression(expression)  # check expression
                if evaluator.eval(expression):
                    new_data.append(result)

        except ValueError as e:
            raise ResultsFilterError(
                f"Error in filter. Exception:{e}",
                f"The expression you provided was: {expression}",
                "See https://docs.expectedparrot.com/en/latest/results.html#filtering-results for more details.",
            )
        except Exception as e:
            raise ResultsFilterError(
                f"""Error in filter. Exception:{e}.""",
                f"""The expression you provided was: {expression}.""",
                """Please make sure that the expression is a valid Python expression that evaluates to a boolean.""",
                """For example, 'how_feeling == "Great"' is a valid expression, as is 'how_feeling in ["Great", "Terrible"]'., """,
                """However, 'how_feeling = "Great"' is not a valid expression.""",
                """See https://docs.expectedparrot.com/en/latest/results.html#filtering-results for more details.""",
            )

        if len(new_data) == 0:
            import warnings

            warnings.warn("No results remain after applying the filter.")

        return Results(survey=self.survey, data=new_data, created_columns=None)

    @classmethod
    def example(cls, randomize: bool = False) -> Results:
        """Return an example `Results` object.

        Example usage:

        >>> r = Results.example()

        :param debug: if False, uses actual API calls
        """
        from edsl.jobs.Jobs import Jobs
        from edsl.data.Cache import Cache

        c = Cache()
        job = Jobs.example(randomize=randomize)
        results = job.run(
            cache=c,
            stop_on_exception=True,
            skip_retry=True,
            raise_validation_errors=True,
            disable_remote_cache=True,
            disable_remote_inference=True,
        )
        return results

    def rich_print(self):
        """Display an object as a table."""
        pass

    def __str__(self):
        data = self.to_dict()["data"]
        return json.dumps(data, indent=4)

    def show_exceptions(self, traceback=False):
        """Print the exceptions."""
        if hasattr(self, "task_history"):
            self.task_history.show_exceptions(traceback)
        else:
            print("No exceptions to show.")

    def score(self, f: Callable) -> list:
        """Score the results using in a function.

        :param f: A function that takes values from a Resul object and returns a score.

        >>> r = Results.example()
        >>> def f(status): return 1 if status == 'Joyful' else 0
        >>> r.score(f)
        [1, 1, 0, 0]
        """
        return [r.score(f) for r in self.data]


def main():  # pragma: no cover
    """Call the OpenAI API credits."""
    from edsl.results.Results import Results

    results = Results.example(debug=True)
    print(results.filter("how_feeling == 'Great'").select("how_feeling"))
    print(results.mutate("how_feeling_x = how_feeling + 'x'").select("how_feeling_x"))


if __name__ == "__main__":
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
