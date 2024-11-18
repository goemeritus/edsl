"""A Notebook is a utility class that allows you to easily share/pull ipynbs from Coop."""

from __future__ import annotations
import json
from typing import Dict, List, Optional, Union
from uuid import uuid4

from edsl.base.Base import Base
from edsl.utilities.decorators import add_edsl_version, remove_edsl_version


class Notebook(Base):
    """
    A Notebook is a utility class that allows you to easily share/pull ipynbs from Coop.
    """

    default_name = "notebook"

    def __init__(
        self,
        data: Optional[Dict] = None,
        path: Optional[str] = None,
        name: Optional[str] = None,
    ):
        """
        Initialize a new Notebook.

        :param data: A dictionary representing the notebook data.
        This dictionary must conform to the official Jupyter Notebook format, as defined by nbformat.
        :param path: A filepath from which to load the notebook.
        If no path is provided, assume this code is run in a notebook and try to load the current notebook from file.
        :param name: A name for the Notebook.
        """
        import nbformat

        # Load current notebook path as fallback (VS Code only)
        path = path or globals().get("__vsc_ipynb_file__")
        if data is not None:
            nbformat.validate(data)
            self.data = data
        elif path is not None:
            with open(path, mode="r", encoding="utf-8") as f:
                data = nbformat.read(f, as_version=4)
            self.data = json.loads(json.dumps(data))
        else:
            # TODO: Support for IDEs other than VSCode
            raise NotImplementedError(
                "Cannot create a notebook from within itself in this development environment"
            )

        # TODO: perhaps add sanity check function
        # 1. could check if the notebook is a valid notebook
        # 2. could check notebook uses EDSL
        # ....

        self.name = name or self.default_name

    @classmethod
    def from_script(cls, path: str, name: Optional[str] = None) -> "Notebook":
        import nbformat

        # Read the script file
        with open(path, "r") as script_file:
            script_content = script_file.read()

        # Create a new Jupyter notebook
        nb = nbformat.v4.new_notebook()

        # Add the script content to the first cell
        first_cell = nbformat.v4.new_code_cell(script_content)
        nb.cells.append(first_cell)

        # Create a Notebook instance with the notebook data
        notebook_instance = cls(nb)

        return notebook_instance

    @classmethod
    def from_current_script(cls) -> "Notebook":
        import inspect
        import os

        # Get the path to the current file
        current_frame = inspect.currentframe()
        caller_frame = inspect.getouterframes(current_frame, 2)
        current_file_path = os.path.abspath(caller_frame[1].filename)

        # Use from_script to create the notebook
        return cls.from_script(current_file_path)

    def __eq__(self, other):
        """
        Check if two Notebooks are equal.
        This only checks the notebook data.
        """
        return self.data == other.data

    def __hash__(self) -> int:
        """
        Allow the model to be used as a key in a dictionary.
        """
        from edsl.utilities.utilities import dict_hash

        return dict_hash(self.data["cells"])

    def to_dict(self, add_edsl_version=False) -> dict:
        """
        Serialize to a dictionary.
        """
        d = {"name": self.name, "data": self.data}
        if add_edsl_version:
            from edsl import __version__

            d["edsl_version"] = __version__
            d["edsl_class_name"] = self.__class__.__name__
        return d

    @classmethod
    @remove_edsl_version
    def from_dict(cls, d: Dict) -> "Notebook":
        """
        Convert a dictionary representation of a Notebook to a Notebook object.
        """
        return cls(data=d["data"], name=d["name"])

    def to_file(self, path: str):
        """
        Save the notebook at the specified filepath.
        """
        import nbformat

        nbformat.write(nbformat.from_dict(self.data), fp=path)

    def print(self):
        """
        Print the notebook.
        """
        from rich import print_json
        import json

        print_json(json.dumps(self.to_dict()))

    def __repr__(self):
        """
        Return representation of Notebook.
        """
        return f'Notebook(data={self.data}, name="""{self.name}""")'

    def _repr_html_(self):
        """
        Return HTML representation of Notebook.
        """
        from nbconvert import HTMLExporter
        import nbformat

        notebook = nbformat.from_dict(self.data)
        html_exporter = HTMLExporter(template_name="basic")
        (body, _) = html_exporter.from_notebook_node(notebook)
        return body

    def _table(self) -> tuple[dict, list]:
        """
        Prepare generic table data.
        """
        table_data = []

        notebook_preview = ""
        for cell in self.data["cells"]:
            if "source" in cell:
                notebook_preview += f"{cell['source']}\n"
            if len(notebook_preview) > 1000:
                notebook_preview = f"{notebook_preview[:1000]} [...]"
                break
        notebook_preview = notebook_preview.rstrip()

        table_data.append(
            {
                "Attribute": "name",
                "Value": repr(self.name),
            }
        )
        table_data.append(
            {
                "Attribute": "notebook_preview",
                "Value": notebook_preview,
            }
        )

        column_names = ["Attribute", "Value"]
        return table_data, column_names

    def rich_print(self) -> "Table":
        """
        Display a Notebook as a rich table.
        """
        from rich.table import Table

        table_data, column_names = self._table()
        table = Table(title=f"{self.__class__.__name__} Attributes")
        for column in column_names:
            table.add_column(column, style="bold")

        for row in table_data:
            row_data = [row[column] for column in column_names]
            table.add_row(*row_data)

        return table

    @classmethod
    def example(cls, randomize: bool = False) -> Notebook:
        """
        Returns an example Notebook instance.

        :param randomize: If True, adds a random string one of the cells' output.
        """
        addition = "" if not randomize else str(uuid4())
        cells = [
            {
                "cell_type": "markdown",
                "metadata": dict(),
                "source": "# Test notebook",
            },
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": dict(),
                "outputs": [
                    {
                        "name": "stdout",
                        "output_type": "stream",
                        "text": f"Hello world!\n{addition}",
                    }
                ],
                "source": 'print("Hello world!")',
            },
        ]
        data = {
            "metadata": dict(),
            "nbformat": 4,
            "nbformat_minor": 4,
            "cells": cells,
        }
        return cls(data=data)

    def code(self) -> List[str]:
        """
        Return the code that could be used to create this Notebook.
        """
        lines = []
        lines.append("from edsl import Notebook")
        lines.append(f'nb = Notebook(data={self.data}, name="""{self.name}""")')
        return lines


if __name__ == "__main__":
    from edsl import Notebook

    notebook = Notebook.example()
    assert notebook == notebook.from_dict(notebook.to_dict())
