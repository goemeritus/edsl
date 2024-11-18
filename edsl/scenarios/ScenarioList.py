"""A list of Scenarios to be used in a survey."""

from __future__ import annotations
from typing import Any, Optional, Union, List, Callable
import csv
import random
from collections import UserList, Counter
from collections.abc import Iterable
import urllib.parse
import urllib.request
from io import StringIO
from collections import defaultdict
import inspect

from simpleeval import EvalWithCompoundTypes

from edsl.base.Base import Base
from edsl.utilities.decorators import add_edsl_version, remove_edsl_version
from edsl.scenarios.Scenario import Scenario
from edsl.scenarios.ScenarioListPdfMixin import ScenarioListPdfMixin
from edsl.scenarios.ScenarioListExportMixin import ScenarioListExportMixin

from edsl.utilities.naming_utilities import sanitize_string
from edsl.utilities.utilities import is_valid_variable_name


class ScenarioListMixin(ScenarioListPdfMixin, ScenarioListExportMixin):
    pass


class ScenarioList(Base, UserList, ScenarioListMixin):
    """Class for creating a list of scenarios to be used in a survey."""

    def __init__(self, data: Optional[list] = None, codebook: Optional[dict] = None):
        """Initialize the ScenarioList class."""
        if data is not None:
            super().__init__(data)
        else:
            super().__init__([])
        self.codebook = codebook or {}

    def unique(self) -> ScenarioList:
        """Return a list of unique scenarios.

        >>> s = ScenarioList([Scenario({'a': 1}), Scenario({'a': 1}), Scenario({'a': 2})])
        >>> s.unique()
        ScenarioList([Scenario({'a': 1}), Scenario({'a': 2})])
        """
        return ScenarioList(list(set(self)))

    @property
    def has_jinja_braces(self) -> bool:
        """Check if the ScenarioList has Jinja braces."""
        return any([scenario.has_jinja_braces for scenario in self])

    def convert_jinja_braces(self) -> ScenarioList:
        """Convert Jinja braces to Python braces."""
        return ScenarioList([scenario.convert_jinja_braces() for scenario in self])

    def give_valid_names(self) -> ScenarioList:
        """Give valid names to the scenario keys.

        >>> s = ScenarioList([Scenario({'a': 1, 'b': 2}), Scenario({'a': 1, 'b': 1})])
        >>> s.give_valid_names()
        ScenarioList([Scenario({'a': 1, 'b': 2}), Scenario({'a': 1, 'b': 1})])
        >>> s = ScenarioList([Scenario({'are you there John?': 1, 'b': 2}), Scenario({'a': 1, 'b': 1})])
        >>> s.give_valid_names()
        ScenarioList([Scenario({'john': 1, 'b': 2}), Scenario({'a': 1, 'b': 1})])
        """
        codebook = {}
        new_scenaerios = []
        for scenario in self:
            new_scenario = {}
            for key in scenario:
                if not is_valid_variable_name(key):
                    if key in codebook:
                        new_key = codebook[key]
                    else:
                        new_key = sanitize_string(key)
                        if not is_valid_variable_name(new_key):
                            new_key = f"var_{len(codebook)}"
                        codebook[key] = new_key
                    new_scenario[new_key] = scenario[key]
                else:
                    new_scenario[key] = scenario[key]
            new_scenaerios.append(Scenario(new_scenario))
        return ScenarioList(new_scenaerios, codebook)

    def unpivot(self, id_vars=None, value_vars=None):
        """
        Unpivot the ScenarioList, allowing for id variables to be specified.

        Parameters:
        id_vars (list): Fields to use as identifier variables (kept in each entry)
        value_vars (list): Fields to unpivot. If None, all fields not in id_vars will be used.

        Example:
        >>> s = ScenarioList([
        ...     Scenario({'id': 1, 'year': 2020, 'a': 10, 'b': 20}),
        ...     Scenario({'id': 2, 'year': 2021, 'a': 15, 'b': 25})
        ... ])
        >>> s.unpivot(id_vars=['id', 'year'], value_vars=['a', 'b'])
        ScenarioList([Scenario({'id': 1, 'year': 2020, 'variable': 'a', 'value': 10}), Scenario({'id': 1, 'year': 2020, 'variable': 'b', 'value': 20}), Scenario({'id': 2, 'year': 2021, 'variable': 'a', 'value': 15}), Scenario({'id': 2, 'year': 2021, 'variable': 'b', 'value': 25})])
        """
        if id_vars is None:
            id_vars = []
        if value_vars is None:
            value_vars = [field for field in self[0].keys() if field not in id_vars]

        new_scenarios = []
        for scenario in self:
            for var in value_vars:
                new_scenario = {id_var: scenario[id_var] for id_var in id_vars}
                new_scenario["variable"] = var
                new_scenario["value"] = scenario[var]
                new_scenarios.append(Scenario(new_scenario))

        return ScenarioList(new_scenarios)

    def pivot(self, id_vars, var_name="variable", value_name="value"):
        """
        Pivot the ScenarioList from long to wide format.

        Parameters:
        id_vars (list): Fields to use as identifier variables
        var_name (str): Name of the variable column (default: 'variable')
        value_name (str): Name of the value column (default: 'value')

        Example:
        >>> s = ScenarioList([
        ...     Scenario({'id': 1, 'year': 2020, 'variable': 'a', 'value': 10}),
        ...     Scenario({'id': 1, 'year': 2020, 'variable': 'b', 'value': 20}),
        ...     Scenario({'id': 2, 'year': 2021, 'variable': 'a', 'value': 15}),
        ...     Scenario({'id': 2, 'year': 2021, 'variable': 'b', 'value': 25})
        ... ])
        >>> s.pivot(id_vars=['id', 'year'])
        ScenarioList([Scenario({'id': 1, 'year': 2020, 'a': 10, 'b': 20}), Scenario({'id': 2, 'year': 2021, 'a': 15, 'b': 25})])
        """
        pivoted_dict = {}

        for scenario in self:
            # Create a tuple of id values to use as a key
            id_key = tuple(scenario[id_var] for id_var in id_vars)

            # If this combination of id values hasn't been seen before, initialize it
            if id_key not in pivoted_dict:
                pivoted_dict[id_key] = {id_var: scenario[id_var] for id_var in id_vars}

            # Add the variable-value pair to the dict
            variable = scenario[var_name]
            value = scenario[value_name]
            pivoted_dict[id_key][variable] = value

        # Convert the dict of dicts to a list of Scenarios
        pivoted_scenarios = [
            Scenario(dict(zip(id_vars, id_key), **values))
            for id_key, values in pivoted_dict.items()
        ]

        return ScenarioList(pivoted_scenarios)

    def group_by(self, id_vars, variables, func):
        """
        Group the ScenarioList by id_vars and apply a function to the specified variables.

        Parameters:
        id_vars (list): Fields to use as identifier variables for grouping
        variables (list): Fields to pass to the aggregation function
        func (callable): Function to apply to the grouped variables.
                        Should accept lists of values for each variable.

        Returns:
        ScenarioList: A new ScenarioList with the grouped and aggregated results

        Example:
        >>> def avg_sum(a, b):
        ...     return {'avg_a': sum(a) / len(a), 'sum_b': sum(b)}
        >>> s = ScenarioList([
        ...     Scenario({'group': 'A', 'year': 2020, 'a': 10, 'b': 20}),
        ...     Scenario({'group': 'A', 'year': 2021, 'a': 15, 'b': 25}),
        ...     Scenario({'group': 'B', 'year': 2020, 'a': 12, 'b': 22}),
        ...     Scenario({'group': 'B', 'year': 2021, 'a': 17, 'b': 27})
        ... ])
        >>> s.group_by(id_vars=['group'], variables=['a', 'b'], func=avg_sum)
        ScenarioList([Scenario({'group': 'A', 'avg_a': 12.5, 'sum_b': 45}), Scenario({'group': 'B', 'avg_a': 14.5, 'sum_b': 49})])
        """
        # Check if the function is compatible with the specified variables
        func_params = inspect.signature(func).parameters
        if len(func_params) != len(variables):
            raise ValueError(
                f"Function {func.__name__} expects {len(func_params)} arguments, but {len(variables)} variables were provided"
            )

        # Group the scenarios
        grouped = defaultdict(lambda: defaultdict(list))
        for scenario in self:
            key = tuple(scenario[id_var] for id_var in id_vars)
            for var in variables:
                grouped[key][var].append(scenario[var])

        # Apply the function to each group
        result = []
        for key, group in grouped.items():
            try:
                aggregated = func(*[group[var] for var in variables])
            except Exception as e:
                raise ValueError(f"Error applying function to group {key}: {str(e)}")

            if not isinstance(aggregated, dict):
                raise ValueError(f"Function {func.__name__} must return a dictionary")

            new_scenario = dict(zip(id_vars, key))
            new_scenario.update(aggregated)
            result.append(Scenario(new_scenario))

        return ScenarioList(result)

    @property
    def parameters(self) -> set:
        """Return the set of parameters in the ScenarioList

        Example:

        >>> s = ScenarioList([Scenario({'a': 1}), Scenario({'b': 2})])
        >>> s.parameters == {'a', 'b'}
        True
        """
        if len(self) == 0:
            return set()

        return set.union(*[set(s.keys()) for s in self])

    def __hash__(self) -> int:
        """Return the hash of the ScenarioList.

        >>> s = ScenarioList.example()
        >>> hash(s)
        1262252885757976162
        """
        from edsl.utilities.utilities import dict_hash

        return dict_hash(self.to_dict(sort=True, add_edsl_version=False))

    def __repr__(self):
        return f"ScenarioList({self.data})"

    def __mul__(self, other: ScenarioList) -> ScenarioList:
        """Takes the cross product of two ScenarioLists.

        >>> s1 = ScenarioList.from_list("a", [1, 2])
        >>> s2 = ScenarioList.from_list("b", [3, 4])
        >>> s1 * s2
        ScenarioList([Scenario({'a': 1, 'b': 3}), Scenario({'a': 1, 'b': 4}), Scenario({'a': 2, 'b': 3}), Scenario({'a': 2, 'b': 4})])
        """
        from itertools import product

        new_sl = []
        for s1, s2 in list(product(self, other)):
            new_sl.append(s1 + s2)
        return ScenarioList(new_sl)

    def times(self, other: ScenarioList) -> ScenarioList:
        """Takes the cross product of two ScenarioLists.

        Example:

        >>> s1 = ScenarioList([Scenario({'a': 1}), Scenario({'a': 2})])
        >>> s2 = ScenarioList([Scenario({'b': 1}), Scenario({'b': 2})])
        >>> s1.times(s2)
        ScenarioList([Scenario({'a': 1, 'b': 1}), Scenario({'a': 1, 'b': 2}), Scenario({'a': 2, 'b': 1}), Scenario({'a': 2, 'b': 2})])
        """
        return self.__mul__(other)

    def shuffle(self, seed: Optional[str] = "edsl") -> ScenarioList:
        """Shuffle the ScenarioList.

        >>> s = ScenarioList.from_list("a", [1,2,3,4])
        >>> s.shuffle()
        ScenarioList([Scenario({'a': 3}), Scenario({'a': 4}), Scenario({'a': 1}), Scenario({'a': 2})])
        """
        random.seed(seed)
        random.shuffle(self.data)
        return self

    def _repr_html_(self) -> str:
        from edsl.utilities.utilities import data_to_html

        data = self.to_dict()
        _ = data.pop("edsl_version")
        _ = data.pop("edsl_class_name")
        for s in data["scenarios"]:
            _ = s.pop("edsl_version")
            _ = s.pop("edsl_class_name")
        for scenario in data["scenarios"]:
            for key, value in scenario.items():
                if hasattr(value, "to_dict"):
                    data[key] = value.to_dict()
        return data_to_html(data)

    def tally(self, field) -> dict:
        """Return a tally of the values in the field.

        Example:

        >>> s = ScenarioList([Scenario({'a': 1, 'b': 1}), Scenario({'a': 1, 'b': 2})])
        >>> s.tally('b')
        {1: 1, 2: 1}
        """
        return dict(Counter([scenario[field] for scenario in self]))

    def sample(self, n: int, seed="edsl") -> ScenarioList:
        """Return a random sample from the ScenarioList

        >>> s = ScenarioList.from_list("a", [1,2,3,4,5,6])
        >>> s.sample(3)
        ScenarioList([Scenario({'a': 2}), Scenario({'a': 1}), Scenario({'a': 3})])
        """

        random.seed(seed)

        return ScenarioList(random.sample(self.data, n))

    def expand(self, expand_field: str, number_field=False) -> ScenarioList:
        """Expand the ScenarioList by a field.

        Example:

        >>> s = ScenarioList( [ Scenario({'a':1, 'b':[1,2]}) ] )
        >>> s.expand('b')
        ScenarioList([Scenario({'a': 1, 'b': 1}), Scenario({'a': 1, 'b': 2})])
        """
        new_scenarios = []
        for scenario in self:
            values = scenario[expand_field]
            if not isinstance(values, Iterable) or isinstance(values, str):
                values = [values]
            for index, value in enumerate(values):
                new_scenario = scenario.copy()
                new_scenario[expand_field] = value
                if number_field:
                    new_scenario[expand_field + "_number"] = index + 1
                new_scenarios.append(new_scenario)
        return ScenarioList(new_scenarios)

    def concatenate(self, fields: List[str], separator: str = ";") -> "ScenarioList":
        """Concatenate specified fields into a single field.

        Args:
            fields (List[str]): List of field names to concatenate.
            separator (str, optional): Separator to use between field values. Defaults to ";".

        Returns:
            ScenarioList: A new ScenarioList with concatenated fields.

        Example:
            >>> s = ScenarioList([Scenario({'a': 1, 'b': 2, 'c': 3}), Scenario({'a': 4, 'b': 5, 'c': 6})])
            >>> s.concatenate(['a', 'b', 'c'])
            ScenarioList([Scenario({'concat_a_b_c': '1;2;3'}), Scenario({'concat_a_b_c': '4;5;6'})])
        """
        new_scenarios = []
        for scenario in self:
            new_scenario = scenario.copy()
            concat_values = []
            for field in fields:
                if field in new_scenario:
                    concat_values.append(str(new_scenario[field]))
                    del new_scenario[field]

            new_field_name = f"concat_{'_'.join(fields)}"
            new_scenario[new_field_name] = separator.join(concat_values)
            new_scenarios.append(new_scenario)

        return ScenarioList(new_scenarios)

    def unpack_dict(
        self, field: str, prefix: Optional[str] = None, drop_field: bool = False
    ) -> ScenarioList:
        """Unpack a dictionary field into separate fields.

        Example:

        >>> s = ScenarioList([Scenario({'a': 1, 'b': {'c': 2, 'd': 3}})])
        >>> s.unpack_dict('b')
        ScenarioList([Scenario({'a': 1, 'b': {'c': 2, 'd': 3}, 'c': 2, 'd': 3})])
        """
        new_scenarios = []
        for scenario in self:
            new_scenario = scenario.copy()
            for key, value in scenario[field].items():
                if prefix:
                    new_scenario[prefix + key] = value
                else:
                    new_scenario[key] = value
            if drop_field:
                new_scenario.pop(field)
            new_scenarios.append(new_scenario)
        return ScenarioList(new_scenarios)

    def transform(
        self, field: str, func: Callable, new_name: Optional[str] = None
    ) -> ScenarioList:
        """Transform a field using a function."""
        new_scenarios = []
        for scenario in self:
            new_scenario = scenario.copy()
            new_scenario[new_name or field] = func(scenario[field])
            new_scenarios.append(new_scenario)
        return ScenarioList(new_scenarios)

    def mutate(
        self, new_var_string: str, functions_dict: Optional[dict[str, Callable]] = None
    ) -> ScenarioList:
        """
        Return a new ScenarioList with a new variable added.

        Example:

        >>> s = ScenarioList([Scenario({'a': 1, 'b': 2}), Scenario({'a': 1, 'b': 1})])
        >>> s.mutate("c = a + b")
        ScenarioList([Scenario({'a': 1, 'b': 2, 'c': 3}), Scenario({'a': 1, 'b': 1, 'c': 2})])

        """
        if "=" not in new_var_string:
            raise Exception(
                f"Mutate requires an '=' in the string, but '{new_var_string}' doesn't have one."
            )
        raw_var_name, expression = new_var_string.split("=", 1)
        var_name = raw_var_name.strip()
        from edsl.utilities.utilities import is_valid_variable_name

        if not is_valid_variable_name(var_name):
            raise Exception(f"{var_name} is not a valid variable name.")

        # create the evaluator
        functions_dict = functions_dict or {}

        def create_evaluator(scenario) -> EvalWithCompoundTypes:
            return EvalWithCompoundTypes(names=scenario, functions=functions_dict)

        def new_scenario(old_scenario: Scenario, var_name: str) -> Scenario:
            evaluator = create_evaluator(old_scenario)
            value = evaluator.eval(expression)
            new_s = old_scenario.copy()
            new_s[var_name] = value
            return new_s

        try:
            new_data = [new_scenario(s, var_name) for s in self]
        except Exception as e:
            raise Exception(f"Error in mutate. Exception:{e}")

        return ScenarioList(new_data)

    def order_by(self, *fields: str, reverse: bool = False) -> ScenarioList:
        """Order the scenarios by one or more fields.

        Example:

        >>> s = ScenarioList([Scenario({'a': 1, 'b': 2}), Scenario({'a': 1, 'b': 1})])
        >>> s.order_by('b', 'a')
        ScenarioList([Scenario({'a': 1, 'b': 1}), Scenario({'a': 1, 'b': 2})])
        """

        def get_sort_key(scenario: Any) -> tuple:
            return tuple(scenario[field] for field in fields)

        return ScenarioList(sorted(self, key=get_sort_key, reverse=reverse))

    def filter(self, expression: str) -> ScenarioList:
        """
        Filter a list of scenarios based on an expression.

        Example:

        >>> s = ScenarioList([Scenario({'a': 1, 'b': 1}), Scenario({'a': 1, 'b': 2})])
        >>> s.filter("b == 2")
        ScenarioList([Scenario({'a': 1, 'b': 2})])
        """

        def create_evaluator(scenario: Scenario):
            """Create an evaluator for the given result.
            The 'combined_dict' is a mapping of all values for that Result object.
            """
            return EvalWithCompoundTypes(names=scenario)

        try:
            # iterates through all the results and evaluates the expression
            new_data = [
                scenario
                for scenario in self.data
                if create_evaluator(scenario).eval(expression)
            ]
        except Exception as e:
            print(f"Exception:{e}")
            raise Exception(f"Error in filter. Exception:{e}")

        return ScenarioList(new_data)

    def from_urls(
        self, urls: list[str], field_name: Optional[str] = "text"
    ) -> ScenarioList:
        """Create a ScenarioList from a list of URLs.

        :param urls: A list of URLs.
        :param field_name: The name of the field to store the text from the URLs.


        """
        return ScenarioList([Scenario.from_url(url, field_name) for url in urls])

    def select(self, *fields) -> ScenarioList:
        """
        Selects scenarios with only the references fields.

        Example:

        >>> s = ScenarioList([Scenario({'a': 1, 'b': 1}), Scenario({'a': 1, 'b': 2})])
        >>> s.select('a')
        ScenarioList([Scenario({'a': 1}), Scenario({'a': 1})])
        """
        if len(fields) == 1:
            fields_to_select = [list(fields)[0]]
        else:
            fields_to_select = list(fields)

        return ScenarioList(
            [scenario.select(fields_to_select) for scenario in self.data]
        )

    def drop(self, *fields) -> ScenarioList:
        """Drop fields from the scenarios.

        Example:

        >>> s = ScenarioList([Scenario({'a': 1, 'b': 1}), Scenario({'a': 1, 'b': 2})])
        >>> s.drop('a')
        ScenarioList([Scenario({'b': 1}), Scenario({'b': 2})])
        """
        return ScenarioList([scenario.drop(fields) for scenario in self.data])

    def keep(self, *fields) -> ScenarioList:
        """Keep only the specified fields in the scenarios.

        Example:

        >>> s = ScenarioList([Scenario({'a': 1, 'b': 1}), Scenario({'a': 1, 'b': 2})])
        >>> s.keep('a')
        ScenarioList([Scenario({'a': 1}), Scenario({'a': 1})])
        """
        return ScenarioList([scenario.keep(fields) for scenario in self.data])

    @classmethod
    def from_list(
        cls, name: str, values: list, func: Optional[Callable] = None
    ) -> ScenarioList:
        """Create a ScenarioList from a list of values.

        Example:

        >>> ScenarioList.from_list('name', ['Alice', 'Bob'])
        ScenarioList([Scenario({'name': 'Alice'}), Scenario({'name': 'Bob'})])
        """
        if not func:
            func = lambda x: x
        return cls([Scenario({name: func(value)}) for value in values])

    def to_dataset(self) -> "Dataset":
        """
        >>> s = ScenarioList.from_list("a", [1,2,3])
        >>> s.to_dataset()
        Dataset([{'a': [1, 2, 3]}])
        >>> s = ScenarioList.from_list("a", [1,2,3]).add_list("b", [4,5,6])
        >>> s.to_dataset()
        Dataset([{'a': [1, 2, 3]}, {'b': [4, 5, 6]}])
        """
        from edsl.results.Dataset import Dataset

        keys = self[0].keys()
        data = [{key: [scenario[key] for scenario in self.data]} for key in keys]
        return Dataset(data)

    def split(
        self, field: str, split_on: str, index: int, new_name: Optional[str] = None
    ) -> ScenarioList:
        """Split a scenario fiel in multiple fields."""
        if new_name is None:
            new_name = field + "_split_" + str(index)
        new_scenarios = []
        for scenario in self:
            new_scenario = scenario.copy()
            new_scenario[new_name] = scenario[field].split(split_on)[index]
            new_scenarios.append(new_scenario)
        return ScenarioList(new_scenarios)

    def add_list(self, name, values) -> ScenarioList:
        """Add a list of values to a ScenarioList.

        Example:

        >>> s = ScenarioList([Scenario({'name': 'Alice'}), Scenario({'name': 'Bob'})])
        >>> s.add_list('age', [30, 25])
        ScenarioList([Scenario({'name': 'Alice', 'age': 30}), Scenario({'name': 'Bob', 'age': 25})])
        """
        for i, value in enumerate(values):
            if i < len(self):
                self[i][name] = value
            else:
                self.append(Scenario({name: value}))
        return self

    def add_value(self, name: str, value: Any) -> ScenarioList:
        """Add a value to all scenarios in a ScenarioList.

        Example:

        >>> s = ScenarioList([Scenario({'name': 'Alice'}), Scenario({'name': 'Bob'})])
        >>> s.add_value('age', 30)
        ScenarioList([Scenario({'name': 'Alice', 'age': 30}), Scenario({'name': 'Bob', 'age': 30})])
        """
        for scenario in self:
            scenario[name] = value
        return self

    def rename(self, replacement_dict: dict) -> ScenarioList:
        """Rename the fields in the scenarios.

        Example:

        >>> s = ScenarioList([Scenario({'name': 'Alice', 'age': 30}), Scenario({'name': 'Bob', 'age': 25})])
        >>> s.rename({'name': 'first_name', 'age': 'years'})
        ScenarioList([Scenario({'first_name': 'Alice', 'years': 30}), Scenario({'first_name': 'Bob', 'years': 25})])

        """

        new_list = ScenarioList([])
        for obj in self:
            new_obj = obj.rename(replacement_dict)
            new_list.append(new_obj)
        return new_list

    @classmethod
    def from_sqlite(cls, filepath: str, table: str):
        import sqlite3

        with sqlite3.connect(filepath) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table}")
            columns = [description[0] for description in cursor.description]
            data = cursor.fetchall()
        return cls([Scenario(dict(zip(columns, row))) for row in data])

    @classmethod
    def from_latex(cls, tex_file_path: str):
        with open(tex_file_path, "r") as file:
            lines = file.readlines()

        processed_lines = []
        non_blank_lines = [
            (i, line.strip()) for i, line in enumerate(lines) if line.strip()
        ]

        for index, (line_no, text) in enumerate(non_blank_lines):
            entry = {
                "line_no": line_no + 1,  # Using 1-based index for line numbers
                "text": text,
                "line_before": non_blank_lines[index - 1][1] if index > 0 else None,
                "line_after": (
                    non_blank_lines[index + 1][1]
                    if index < len(non_blank_lines) - 1
                    else None
                ),
            }
            processed_lines.append(entry)

        return ScenarioList([Scenario(entry) for entry in processed_lines])

    @classmethod
    def from_google_doc(cls, url: str) -> ScenarioList:
        """Create a ScenarioList from a Google Doc.

        This method downloads the Google Doc as a Word file (.docx), saves it to a temporary file,
        and then reads it using the from_docx class method.

        Args:
            url (str): The URL to the Google Doc.

        Returns:
            ScenarioList: An instance of the ScenarioList class.

        """
        import tempfile
        import requests
        from docx import Document

        if "/edit" in url:
            doc_id = url.split("/d/")[1].split("/edit")[0]
        else:
            raise ValueError("Invalid Google Doc URL format.")

        export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=docx"

        # Download the Google Doc as a Word file (.docx)
        response = requests.get(export_url)
        response.raise_for_status()  # Ensure the request was successful

        # Save the Word file to a temporary file
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as temp_file:
            temp_file.write(response.content)
            temp_filename = temp_file.name

        # Call the from_docx class method with the temporary file
        return cls.from_docx(temp_filename)

    @classmethod
    def from_pandas(cls, df) -> ScenarioList:
        """Create a ScenarioList from a pandas DataFrame.

        Example:

        >>> import pandas as pd
        >>> df = pd.DataFrame({'name': ['Alice', 'Bob'], 'age': [30, 25], 'location': ['New York', 'Los Angeles']})
        >>> ScenarioList.from_pandas(df)
        ScenarioList([Scenario({'name': 'Alice', 'age': 30, 'location': 'New York'}), Scenario({'name': 'Bob', 'age': 25, 'location': 'Los Angeles'})])
        """
        return cls([Scenario(row) for row in df.to_dict(orient="records")])

    @classmethod
    def from_wikipedia(cls, url: str, table_index: int = 0):
        """
        Extracts a table from a Wikipedia page.

        Parameters:
            url (str): The URL of the Wikipedia page.
            table_index (int): The index of the table to extract (default is 0).

        Returns:
            pd.DataFrame: A DataFrame containing the extracted table.
        # # Example usage
        # url = "https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)"
        # df = from_wikipedia(url, 0)

        # if not df.empty:
        #     print(df.head())
        # else:
        #     print("Failed to extract table.")


        """
        import pandas as pd
        import requests
        from requests.exceptions import RequestException

        try:
            # Check if the URL is reachable
            response = requests.get(url)
            response.raise_for_status()  # Raises HTTPError for bad responses

            # Extract tables from the Wikipedia page
            tables = pd.read_html(url)

            # Ensure the requested table index is within the range of available tables
            if table_index >= len(tables) or table_index < 0:
                raise IndexError(
                    f"Table index {table_index} is out of range. This page has {len(tables)} table(s)."
                )

            # Return the requested table as a DataFrame
            # return tables[table_index]
            return cls.from_pandas(tables[table_index])

        except RequestException as e:
            print(f"Error fetching the URL: {e}")
        except ValueError as e:
            print(f"Error parsing tables: {e}")
        except IndexError as e:
            print(e)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

        # Return an empty DataFrame in case of an error
        # return cls.from_pandas(pd.DataFrame())

    def to_key_value(self, field: str, value=None) -> Union[dict, set]:
        """Return the set of values in the field.

        Example:

        >>> s = ScenarioList([Scenario({'name': 'Alice'}), Scenario({'name': 'Bob'})])
        >>> s.to_key_value('name') == {'Alice', 'Bob'}
        True
        """
        if value is None:
            return {scenario[field] for scenario in self}
        else:
            return {scenario[field]: scenario[value] for scenario in self}

    @classmethod
    def from_excel(
        cls, filename: str, sheet_name: Optional[str] = None
    ) -> ScenarioList:
        """Create a ScenarioList from an Excel file.

        If the Excel file contains multiple sheets and no sheet_name is provided,
        the method will print the available sheets and require the user to specify one.

        Example:

        >>> import tempfile
        >>> import os
        >>> import pandas as pd
        >>> with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as f:
        ...     df1 = pd.DataFrame({
        ...         'name': ['Alice', 'Bob'],
        ...         'age': [30, 25],
        ...         'location': ['New York', 'Los Angeles']
        ...     })
        ...     df2 = pd.DataFrame({
        ...         'name': ['Charlie', 'David'],
        ...         'age': [35, 40],
        ...         'location': ['Chicago', 'Boston']
        ...     })
        ...     with pd.ExcelWriter(f.name) as writer:
        ...         df1.to_excel(writer, sheet_name='Sheet1', index=False)
        ...         df2.to_excel(writer, sheet_name='Sheet2', index=False)
        ...     temp_filename = f.name
        >>> scenario_list = ScenarioList.from_excel(temp_filename, sheet_name='Sheet1')
        >>> len(scenario_list)
        2
        >>> scenario_list[0]['name']
        'Alice'
        >>> scenario_list = ScenarioList.from_excel(temp_filename)  # Should raise an error and list sheets
        Traceback (most recent call last):
        ...
        ValueError: Please provide a sheet name to load data from.
        """
        from edsl.scenarios.Scenario import Scenario
        import pandas as pd

        # Get all sheets
        all_sheets = pd.read_excel(filename, sheet_name=None)

        # If no sheet_name is provided and there is more than one sheet, print available sheets
        if sheet_name is None:
            if len(all_sheets) > 1:
                print("The Excel file contains multiple sheets:")
                for name in all_sheets.keys():
                    print(f"- {name}")
                raise ValueError("Please provide a sheet name to load data from.")
            else:
                # If there is only one sheet, use it
                sheet_name = list(all_sheets.keys())[0]

        # Load the specified or determined sheet
        df = pd.read_excel(filename, sheet_name=sheet_name)

        observations = []
        for _, row in df.iterrows():
            observations.append(Scenario(row.to_dict()))

        return cls(observations)

    @classmethod
    def from_google_sheet(cls, url: str, sheet_name: str = None) -> ScenarioList:
        """Create a ScenarioList from a Google Sheet.

        This method downloads the Google Sheet as an Excel file, saves it to a temporary file,
        and then reads it using the from_excel class method.

        Args:
            url (str): The URL to the Google Sheet.
            sheet_name (str, optional): The name of the sheet to load. If None, the method will behave
                                        the same as from_excel regarding multiple sheets.

        Returns:
            ScenarioList: An instance of the ScenarioList class.

        """
        import pandas as pd
        import tempfile
        import requests

        if "/edit" in url:
            sheet_id = url.split("/d/")[1].split("/edit")[0]
        else:
            raise ValueError("Invalid Google Sheet URL format.")

        export_url = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
        )

        # Download the Google Sheet as an Excel file
        response = requests.get(export_url)
        response.raise_for_status()  # Ensure the request was successful

        # Save the Excel file to a temporary file
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as temp_file:
            temp_file.write(response.content)
            temp_filename = temp_file.name

        # Call the from_excel class method with the temporary file
        return cls.from_excel(temp_filename, sheet_name=sheet_name)

    @classmethod
    def from_csv(cls, source: Union[str, urllib.parse.ParseResult]) -> ScenarioList:
        """Create a ScenarioList from a CSV file or URL.

        Args:
            source: A string representing either a local file path or a URL to a CSV file,
                    or a urllib.parse.ParseResult object for a URL.

        Returns:
            ScenarioList: A ScenarioList object containing the data from the CSV.

        Example:

        >>> import tempfile
        >>> import os
        >>> with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.csv') as f:
        ...     _ = f.write("name,age,location\\nAlice,30,New York\\nBob,25,Los Angeles\\n")
        ...     temp_filename = f.name
        >>> scenario_list = ScenarioList.from_csv(temp_filename)
        >>> len(scenario_list)
        2
        >>> scenario_list[0]['name']
        'Alice'
        >>> scenario_list[1]['age']
        '25'

        >>> url = "https://example.com/data.csv"
        >>> ## scenario_list_from_url = ScenarioList.from_csv(url)
        """
        from edsl.scenarios.Scenario import Scenario

        def is_url(source):
            try:
                result = urllib.parse.urlparse(source)
                return all([result.scheme, result.netloc])
            except ValueError:
                return False

        if isinstance(source, str) and is_url(source):
            with urllib.request.urlopen(source) as response:
                csv_content = response.read().decode("utf-8")
            csv_file = StringIO(csv_content)
        elif isinstance(source, urllib.parse.ParseResult):
            with urllib.request.urlopen(source.geturl()) as response:
                csv_content = response.read().decode("utf-8")
            csv_file = StringIO(csv_content)
        else:
            csv_file = open(source, "r")

        try:
            reader = csv.reader(csv_file)
            header = next(reader)
            observations = [Scenario(dict(zip(header, row))) for row in reader]
        finally:
            csv_file.close()

        return cls(observations)

    def to_dict(self, sort=False, add_edsl_version=True) -> dict:
        """
        >>> s = ScenarioList([Scenario({'food': 'wood chips'}), Scenario({'food': 'wood-fired pizza'})])
        >>> s.to_dict()
        {'scenarios': [{'food': 'wood chips', 'edsl_version': '...', 'edsl_class_name': 'Scenario'}, {'food': 'wood-fired pizza', 'edsl_version': '...', 'edsl_class_name': 'Scenario'}], 'edsl_version': '...', 'edsl_class_name': 'ScenarioList'}

        """
        if sort:
            data = sorted(self, key=lambda x: hash(x))
        else:
            data = self
        d = {"scenarios": [s.to_dict(add_edsl_version=add_edsl_version) for s in data]}
        if add_edsl_version:
            from edsl import __version__

            d["edsl_version"] = __version__
            d["edsl_class_name"] = self.__class__.__name__
        return d

    @classmethod
    def gen(cls, scenario_dicts_list: List[dict]) -> ScenarioList:
        """Create a `ScenarioList` from a list of dictionaries.

        Example:

        >>> ScenarioList.gen([{'name': 'Alice'}, {'name': 'Bob'}])
        ScenarioList([Scenario({'name': 'Alice'}), Scenario({'name': 'Bob'})])

        """
        from edsl.scenarios.Scenario import Scenario

        return cls([Scenario(s) for s in scenario_dicts_list])

    @classmethod
    @remove_edsl_version
    def from_dict(cls, data) -> ScenarioList:
        """Create a `ScenarioList` from a dictionary."""
        from edsl.scenarios.Scenario import Scenario

        return cls([Scenario.from_dict(s) for s in data["scenarios"]])

    @classmethod
    def from_nested_dict(cls, data: dict) -> ScenarioList:
        """Create a `ScenarioList` from a nested dictionary."""
        from edsl.scenarios.Scenario import Scenario

        s = ScenarioList()
        for key, value in data.items():
            s.add_list(key, value)
        return s

    def code(self) -> str:
        ## TODO: Refactor to only use the questions actually in the survey
        """Create the Python code representation of a survey."""
        header_lines = [
            "from edsl.scenarios.Scenario import Scenario",
            "from edsl.scenarios.ScenarioList import ScenarioList",
        ]
        lines = ["\n".join(header_lines)]
        names = []
        for index, scenario in enumerate(self):
            lines.append(f"scenario_{index} = " + repr(scenario))
            names.append(f"scenario_{index}")
        lines.append(f"scenarios = ScenarioList([{', '.join(names)}])")
        return lines

    @classmethod
    def example(cls, randomize: bool = False) -> ScenarioList:
        """
        Return an example ScenarioList instance.

        :params randomize: If True, use Scenario's randomize method to randomize the values.
        """
        return cls([Scenario.example(randomize), Scenario.example(randomize)])

    def rich_print(self) -> None:
        """Display an object as a table."""
        from rich.table import Table

        table = Table(title="ScenarioList")
        table.add_column("Index", style="bold")
        table.add_column("Scenario")
        for i, s in enumerate(self):
            table.add_row(str(i), s.rich_print())
        return table

    def __getitem__(self, key: Union[int, slice]) -> Any:
        """Return the item at the given index.

        Example:
        >>> s = ScenarioList([Scenario({'age': 22, 'hair': 'brown', 'height': 5.5}), Scenario({'age': 22, 'hair': 'brown', 'height': 5.5})])
        >>> s[0]
        Scenario({'age': 22, 'hair': 'brown', 'height': 5.5})

        >>> s[:1]
        ScenarioList([Scenario({'age': 22, 'hair': 'brown', 'height': 5.5})])

        """
        if isinstance(key, slice):
            return ScenarioList(super().__getitem__(key))
        elif isinstance(key, int):
            return super().__getitem__(key)
        else:
            return self.to_dict(add_edsl_version=False)[key]

    def to_agent_list(self):
        """Convert the ScenarioList to an AgentList.

        Example:

        >>> s = ScenarioList([Scenario({'age': 22, 'hair': 'brown', 'height': 5.5}), Scenario({'age': 22, 'hair': 'brown', 'height': 5.5})])
        >>> s.to_agent_list()
        AgentList([Agent(traits = {'age': 22, 'hair': 'brown', 'height': 5.5}), Agent(traits = {'age': 22, 'hair': 'brown', 'height': 5.5})])
        """
        from edsl.agents.AgentList import AgentList
        from edsl.agents.Agent import Agent

        return AgentList([Agent(traits=s.data) for s in self])

    def chunk(
        self,
        field,
        num_words: Optional[int] = None,
        num_lines: Optional[int] = None,
        include_original=False,
        hash_original=False,
    ) -> "ScenarioList":
        """Chunk the scenarios based on a field.

        Example:

        >>> s = ScenarioList([Scenario({'text': 'The quick brown fox jumps over the lazy dog.'})])
        >>> s.chunk('text', num_words=3)
        ScenarioList([Scenario({'text': 'The quick brown', 'text_chunk': 0}), Scenario({'text': 'fox jumps over', 'text_chunk': 1}), Scenario({'text': 'the lazy dog.', 'text_chunk': 2})])
        """
        new_scenarios = []
        for scenario in self:
            replacement_scenarios = scenario.chunk(
                field,
                num_words=num_words,
                num_lines=num_lines,
                include_original=include_original,
                hash_original=hash_original,
            )
            new_scenarios.extend(replacement_scenarios)
        return ScenarioList(new_scenarios)


if __name__ == "__main__":
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
