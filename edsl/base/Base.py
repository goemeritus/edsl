"""Base class for all classes in the package. It provides rich printing and persistence of objects."""

from abc import ABC, abstractmethod, ABCMeta
import gzip
import io
import json
from typing import Any, Optional, Union
from uuid import UUID
import yaml

from edsl.base.RichPrintingMixin import RichPrintingMixin
from edsl.base.PersistenceMixin import PersistenceMixin


class RegisterSubclassesMeta(ABCMeta):
    """Metaclass for registering subclasses."""

    _registry = {}

    def __init__(cls, name, bases, nmspc):
        """Register the class in the registry upon creation."""
        super(RegisterSubclassesMeta, cls).__init__(name, bases, nmspc)
        if cls.__name__ != "Base":
            RegisterSubclassesMeta._registry[cls.__name__] = cls

    @staticmethod
    def get_registry():
        """Return the registry of subclasses."""
        return dict(RegisterSubclassesMeta._registry)


class DiffMethodsMixin:
    def __sub__(self, other):
        """Return the difference between two objects."""
        from edsl.base.BaseDiff import BaseDiff

        return BaseDiff(self, other)


class Base(
    RichPrintingMixin,
    PersistenceMixin,
    DiffMethodsMixin,
    ABC,
    metaclass=RegisterSubclassesMeta,
):
    """Base class for all classes in the package."""

    # def __getitem__(self, key):
    #     return getattr(self, key)

    # @abstractmethod
    # def _repr_html_(self) -> str:
    #     raise NotImplementedError("This method is not implemented yet.")

    # @abstractmethod
    # def _repr_(self) -> str:
    #     raise NotImplementedError("This method is not implemented yet.")

    def keys(self):
        """Return the keys of the object."""
        _keys = list(self.to_dict().keys())
        if "edsl_version" in _keys:
            _keys.remove("edsl_version")
        if "edsl_class_name" in _keys:
            _keys.remove("edsl_class_name")
        return _keys

    def values(self):
        """Return the values of the object."""
        data = self.to_dict()
        keys = self.keys()
        return {data[key] for key in keys}

    def _repr_html_(self):
        from edsl.utilities.utilities import data_to_html

        return data_to_html(self.to_dict())

    def __eq__(self, other):
        """Return whether two objects are equal."""
        import inspect

        if not isinstance(other, self.__class__):
            return False
        if "sort" in inspect.signature(self.to_dict).parameters:
            return self.to_dict(sort=True) == other.to_dict(sort=True)
        else:
            return self.to_dict() == other.to_dict()

    @abstractmethod
    def example():
        """This method should be implemented by subclasses."""
        raise NotImplementedError("This method is not implemented yet.")

    @abstractmethod
    def rich_print():
        """This method should be implemented by subclasses."""
        raise NotImplementedError("This method is not implemented yet.")

    @abstractmethod
    def to_dict():
        """This method should be implemented by subclasses."""
        raise NotImplementedError("This method is not implemented yet.")

    @abstractmethod
    def from_dict():
        """This method should be implemented by subclasses."""
        raise NotImplementedError("This method is not implemented yet.")

    @abstractmethod
    def code():
        """This method should be implemented by subclasses."""
        raise NotImplementedError("This method is not implemented yet.")

    def show_methods(self, show_docstrings=True):
        """Show the methods of the object."""
        public_methods_with_docstrings = [
            (method, getattr(self, method).__doc__)
            for method in dir(self)
            if callable(getattr(self, method)) and not method.startswith("_")
        ]
        if show_docstrings:
            for method, documentation in public_methods_with_docstrings:
                print(f"{method}: {documentation}")
        else:
            return [x[0] for x in public_methods_with_docstrings]
