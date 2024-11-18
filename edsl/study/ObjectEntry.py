import time
import webbrowser
from typing import Any, Dict, Optional, Type
from edsl import QuestionBase
from edsl.base.Base import RegisterSubclassesMeta


class ObjectEntry:
    def __init__(
        self,
        variable_name: str,
        object: Any,
        description: str,
        coop_info: Optional[Dict[str, Any]] = None,
        created_at: Optional[float] = None,
        edsl_class_name: Optional[str] = None,
    ):
        """
        Initialize an ObjectEntry instance.

        :param variable_name: The name of the variable.
        :param object: The object being wrapped.
        :param description: A description of the object.
        :param coop_info: Optional Coop information dictionary.
        :param created_at: Optional creation timestamp. Defaults to current time.
        :param edsl_class_name: Optional EDSL class name. Defaults to object's class name.
        """
        self.created_at = created_at or time.time()
        self.variable_name = variable_name
        self.object = object
        self.edsl_class_name = edsl_class_name or object.__class__.__name__
        self.description = description
        self.coop_info = coop_info

    @classmethod
    def _get_class(cls, object_dict: Dict[str, Any]) -> Type:
        """
        Get the class of an object from its dictionary representation.

        :param object_dict: The dictionary representation of the object.
        :return: The class of the object.
        """
        class_name = object_dict["edsl_class_name"]
        if class_name == "QuestionBase":
            return QuestionBase
        else:
            return RegisterSubclassesMeta._registry[class_name]

    def __repr__(self) -> str:
        """
        Return a string representation of the ObjectEntry instance.

        :return: A string representation of the ObjectEntry instance.
        """
        return f"ObjectEntry(variable_name='{self.variable_name}', object={self.object!r}, description='{self.description}', coop_info={self.coop_info}, created_at={self.created_at}, edsl_class_name='{self.edsl_class_name}')"

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the ObjectEntry instance to a dictionary.

        :return: A dictionary representation of the ObjectEntry instance.
        """
        return {
            "created_at": self.created_at,
            "variable_name": self.variable_name,
            "object": self.object.to_dict(),
            "edsl_class_name": self.edsl_class_name,
            "description": self.description,
            "coop_info": self.coop_info,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ObjectEntry":
        """
        Create an ObjectEntry instance from a dictionary.

        :param d: The dictionary representation of the ObjectEntry instance.
        :return: An ObjectEntry instance.
        """
        d["object"] = cls._get_class(d["object"]).from_dict(d["object"])
        return cls(**d)

    @property
    def hash(self) -> str:
        """
        Compute the hash of the object.

        :return: The hash of the object as a string.
        """
        return str(hash(self.object))

    def add_to_namespace(self) -> None:
        """
        Add the object to the global namespace using its variable name.
        """
        globals()[self.variable_name] = self.object

    @property
    def coop_info(self) -> Optional[Dict[str, Any]]:
        """
        Get the Coop information for the object.

        :return: The Coop information dictionary, if available.
        """
        return self._coop_info

    @coop_info.setter
    def coop_info(self, coop_info: Optional[Dict[str, Any]]) -> None:
        """
        Set the Coop information for the object.

        :param coop_info: The Coop information dictionary.
        """
        self._coop_info = coop_info

    def view_on_coop(self) -> None:
        """
        Open the object's Coop URL in a web browser.
        """
        if self.coop_info is None:
            print("Object not pushed to coop")
            return
        url = self.coop_info.get("url")
        webbrowser.open(url)

    def push(self, refresh: Optional[bool] = False) -> Dict[str, Any]:
        """
        Push the object to the Coop.

        :param refresh: Whether to refresh the Coop entry for the object.
        :return: The Coop info dictionary.
        """
        if self.coop_info is None or refresh:
            self.coop_info = self.object.push(description=self.description)
            print(
                f"Object {self.variable_name} pushed to coop with info: {self._coop_info}"
            )
        else:
            print(
                f"Object {self.variable_name} already pushed to coop with info: {self._coop_info}"
            )

    def __eq__(self, other: "ObjectEntry") -> bool:
        """
        Check if two ObjectEntry instances are equal.

        :param other: The other ObjectEntry instance.
        :return: True if the two instances are equal, False otherwise.
        """
        # if the other item is not "ObjectEntry" type, return False
        if not isinstance(other, ObjectEntry):
            return False

        return (
            self.variable_name == other.variable_name
            and self.object == other.object
            and self.description == other.description
            and self.coop_info == other.coop_info
            and self.created_at == other.created_at
            and self.edsl_class_name == other.edsl_class_name
        )


if __name__ == "__main__":
    from edsl import QuestionFreeText
    from edsl.study import ObjectEntry

    q = QuestionFreeText.example()

    oe = ObjectEntry("q", q, "This is a question")
    d = oe.to_dict()
    new_oe = ObjectEntry.from_dict(d)
    new_oe == oe
