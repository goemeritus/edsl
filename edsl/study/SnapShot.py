import inspect
from typing import Generator, List, Optional


class SnapShot:
    def __init__(self, namespace, exclude: Optional[List] = None):
        self.namespace = namespace
        self.exclude = exclude or []
        self.edsl_objects = dict(self._get_edsl_objects(namespace=self.namespace))
        self.edsl_classes = dict(self._get_edsl_classes(namespace=self.namespace))

    def _all_object_keys(self):
        return self.namespace.keys()

    def __repr__(self):
        return f"SnapShot(edsl_objects={self.edsl_objects}, edsl_classes={self.edsl_objects})"

    def _get_edsl_classes(
        self, namespace: dict
    ) -> Generator[tuple[str, type], None, None]:
        """Get all EDSL classes in the namespace.

        :param namespace: The namespace to search for EDSL classes. The default is the global namespace.

        >>> sn = SnapShot(namespace = {})
        >>> sn.edsl_classes
        {}

        >>> from edsl.data.Cache import Cache
        >>> sn = SnapShot(namespace = globals())
        >>> sn.edsl_classes
        {'Cache': <class 'edsl.data.Cache.Cache'>}
        """
        from edsl.base.Base import RegisterSubclassesMeta
        from edsl import QuestionBase

        all_edsl_objects = RegisterSubclassesMeta.get_registry()

        for name, value in namespace.items():
            if (
                inspect.isclass(value)
                and name in all_edsl_objects
                and value != RegisterSubclassesMeta
            ):
                yield name, value
            if inspect.isclass(value) and issubclass(value, QuestionBase):
                yield name, value

    def _get_edsl_objects(self, namespace) -> Generator[tuple[str, type], None, None]:
        """Get all EDSL objects in the global namespace.

        >>> sn = SnapShot(namespace = globals())
        >>> sn.edsl_objects
        {}

        """
        from edsl.base.Base import Base
        from edsl.study.Study import Study

        def is_edsl_object(obj):
            package_name = "edsl"
            cls = obj.__class__
            module_name = cls.__module__
            return module_name.startswith(package_name)

        for name, value in namespace.items():
            # TODO check this code logic (if there are other objects with to_dict method that are not from edsl)
            if (
                is_edsl_object(value)
                and hasattr(value, "to_dict")
                and not inspect.isclass(value)
                and value.__class__ not in [o.__class__ for o in self.exclude]
            ):
                yield name, value


if __name__ == "__main__":
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)
