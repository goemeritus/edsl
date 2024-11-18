from typing import Optional
from collections import UserList
from edsl import Model

from edsl.language_models import LanguageModel
from edsl.base.Base import Base
from edsl.utilities.decorators import add_edsl_version, remove_edsl_version
from edsl.utilities.utilities import is_valid_variable_name
from edsl.utilities.utilities import dict_hash


class ModelList(Base, UserList):
    def __init__(self, data: Optional[list] = None):
        """Initialize the ScenarioList class.

        >>> from edsl import Model
        >>> m = ModelList(Model.available())

        """
        if data is not None:
            super().__init__(data)
        else:
            super().__init__([])

    @property
    def names(self):
        """

        >>> ModelList.example().names
        {'...'}
        """
        return set([model.model for model in self])

    def rich_print(self):
        pass

    def __repr__(self):
        return f"ModelList({super().__repr__()})"

    def __hash__(self):
        """Return a hash of the ModelList. This is used for comparison of ModelLists.

        >>> isinstance(hash(Model()), int)
        True

        """
        from edsl.utilities.utilities import dict_hash

        return dict_hash(self.to_dict(sort=True, add_edsl_version=False))

    def to_dict(self, sort=False, add_edsl_version=True):
        if sort:
            model_list = sorted([model for model in self], key=lambda x: hash(x))
            d = {
                "models": [
                    model.to_dict(add_edsl_version=add_edsl_version)
                    for model in model_list
                ]
            }
        else:
            d = {
                "models": [
                    model.to_dict(add_edsl_version=add_edsl_version) for model in self
                ]
            }
        if add_edsl_version:
            from edsl import __version__

            d["edsl_version"] = __version__
            d["edsl_class_name"] = "ModelList"

        return d

    @classmethod
    def from_names(self, *args, **kwargs):
        """A a model list from a list of names"""
        if len(args) == 1 and isinstance(args[0], list):
            args = args[0]
        return ModelList([Model(model_name, **kwargs) for model_name in args])

    @classmethod
    @remove_edsl_version
    def from_dict(cls, data):
        """
        Create a ModelList from a dictionary.

        >>> newm = ModelList.from_dict(ModelList.example().to_dict())
        >>> assert ModelList.example() == newm
        """
        return cls(data=[LanguageModel.from_dict(model) for model in data["models"]])

    def code(self):
        pass

    @classmethod
    def example(cls, randomize: bool = False) -> "ModelList":
        """
        Returns an example ModelList instance.

        :param randomize: If True, uses Model's randomize method.
        """

        return cls([Model.example(randomize) for _ in range(3)])


if __name__ == "__main__":
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
