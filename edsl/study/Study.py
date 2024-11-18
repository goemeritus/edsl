import copy
import inspect
import json
import os
import platform
import socket
from datetime import datetime
from typing import Dict, Optional, Union
from uuid import UUID, uuid4
from edsl import Cache, set_session_cache, unset_session_cache
from edsl.utilities.utilities import dict_hash
from edsl.study.ObjectEntry import ObjectEntry
from edsl.study.ProofOfWork import ProofOfWork
from edsl.study.SnapShot import SnapShot


class Study:
    """A study organizes a series of EDSL objects.

    ```python
    with Study(name = "cool_study") as study:
        q = QuestionFreeText.example()
        results = q.run()
    ```

    The `study` object is a context manager.
    It lets you group a series of events and objects together.

    >>> with Study(name = "cool_study", verbose = False) as study:
    ...     from edsl import QuestionFreeText
    ...     q = QuestionFreeText.example()
    >>> len(study.objects)
    1
    >>> _ = os.system("rm cool_study.json")


    It records all the edsl objects that are created during the study.
    On exit, is saves them to a study file.

    """

    def __init__(
        self,
        name: Optional[str] = None,
        filename: Optional[str] = None,
        description: Optional[str] = None,
        objects: Optional[Dict[str, ObjectEntry]] = None,
        cache: Optional[Cache] = None,
        coop: bool = False,
        use_study_cache=True,
        overwrite_on_change=True,
        proof_of_work=None,
        proof_of_work_difficulty: int = None,
        namespace: Optional[dict] = None,
        verbose: Optional[bool] = True,
    ):
        """
        :param name: The name of the study.
        :param description: A description of the study.
        :param objects: A dictionary of objects to add to the study.
        :param cache: A cache object to (potentially) use for the study.
        :param filename: The path to the study file.
        :param coop: Whether to push the study to coop.
        :param use_study_cache: Whether to use the study cache.
        :param overwrite_on_change: Whether to overwrite the study file if it has changed.

        >>> s = Study()
        Traceback (most recent call last):
        ...
        ValueError: You must provide a name or a filename for the study.

        """
        self.verbose = verbose

        if name is None and filename is None:
            raise ValueError("You must provide a name or a filename for the study.")

        if filename is None:
            self.filename = name
        else:
            self.filename = filename

        if (
            self.filename
            and os.path.exists(self.filename + ".json")
            and os.path.getsize(self.filename + ".json") > 0
        ):
            if self.verbose:
                print(f"Using existing study file {self.filename}.json")
            self._load_from_file()
        else:
            self.name = name
            self.description = description
            self.objects = objects or {}
            self.cache = cache or Cache()
            self.proof_of_work = proof_of_work or ProofOfWork()

        # These always overwrite the saved study
        self.coop = coop
        self.use_study_cache = use_study_cache
        self.overwrite_on_change = overwrite_on_change
        self.proof_of_work_difficulty = proof_of_work_difficulty

        self.starting_objects = copy.deepcopy(self.objects)

        if namespace:
            self._namespace = namespace
        else:
            self._namespace = None

        self._create_mapping_dicts()

    @property
    def namespace(self):
        return self._find_stack()

    def _find_stack(self) -> dict:
        "Finds the frame with the Study context"
        # if self.verbose:
        #    self.explore_stacks()
        frame = inspect.currentframe()
        candidate_frames = []
        while frame:
            if "Study" in frame.f_globals:
                candidate_frames.append(frame)

            frame = frame.f_back

        found_variables_dict = {}
        for frame in candidate_frames:
            found_variables_dict.update(frame.f_globals)
            found_variables_dict.update(frame.f_locals)

        return found_variables_dict

    def explore_stacks(self):
        frame = inspect.currentframe()
        count = 0
        d = {}
        while frame:
            d[count] = "Study" in frame.f_globals.keys()
            count += 1
            from rich import print as rprint

            print("Globals:")
            rprint(frame.f_globals["__name__"])
            rprint(frame.f_globals.keys())
            print("Locals:")
            rprint(frame.f_locals.keys())
            print("\n")
            frame = frame.f_back
        return d

    def _create_mapping_dicts(self):
        self._name_to_object = {}
        self._hash_to_name = {}
        self._name_to_oe = {}
        name_counts = {}
        for hash, obj in self.objects.items():
            new_name = obj.variable_name
            if obj.variable_name in name_counts:
                name_counts[obj.variable_name] += 1
                new_name = obj.variable_name + "_" + str(name_counts[obj.variable_name])
            else:
                name_counts[obj.variable_name] = 1
            self._name_to_object[new_name] = obj.object
            self._hash_to_name[hash] = new_name

    def __len__(self):
        return len(self.objects)

    def __eq__(self, other):
        return self.objects.keys() == other.objects.keys()

    @property
    def name_to_object(self):
        """
        >>> s = Study.example()
        >>> s.name_to_object
        {'q': Question('free_text', question_name = \"""how_are_you\""", question_text = \"""How are you?\""")}
        """
        self._create_mapping_dicts()
        return self._name_to_object

    @property
    def hash_to_name(self):
        self._create_mapping_dicts()
        return self._hash_to_name

    def __getattr__(self, name):
        return self.name_to_object[name]

    @classmethod
    def from_file(cls, filename: str):
        """Load a study from a file."""
        if filename.endswith(".json"):
            filename = filename[:-5]
        return cls(filename=filename)

    def _load_from_file(self):
        """Load the study from a file.

        >>> import tempfile
        >>> filename = tempfile.NamedTemporaryFile(delete=False)
        >>> study = Study(name = "poo", filename = filename.name)
        >>> study.save()
        Saving study to ...
        >>> study2 = Study(filename = filename.name)
        Using existing study file ...
        >>> study2.name
        'poo'
        """
        with open(self.filename + ".json", "r") as f:
            d = json.load(f)
            d["cache"] = Cache.from_dict(d["cache"])
            d["proof_of_work"] = ProofOfWork.from_dict(d["proof_of_work"])
            d["objects"] = {
                hash: ObjectEntry.from_dict(obj_dict)
                for hash, obj_dict in d["objects"].items()
            }
            self.__dict__.update(d)

    def __enter__(self):
        """
        >>> s = Study(name = "temp", use_study_cache = True, verbose = False)
        >>> _ = s.__enter__()
        >>> from edsl.config import CONFIG
        >>> hasattr(CONFIG, "EDSL_SESSION_CACHE")
        True
        >>> _ = s.__exit__(None, None, None)
        >>> len(s.objects)
        0
        >>> os.remove("temp.json")

        """
        if self.verbose:
            print("Existing objects in study:")
            self.print()
        snapshot = SnapShot(self.namespace, exclude=[self])
        if self.use_study_cache:
            if self.verbose:
                print("Using study cache.")
            set_session_cache(self.cache)

        if snapshot.edsl_objects:
            raise ValueError(
                "You have EDSL objects in the global namespace.",
                "Please remove them before starting a study or put under the 'Study' context manager."
                "Objects found:",
                snapshot.edsl_objects,
            )
        return self

    def __hash__(self) -> int:
        return dict_hash(list(self.objects.keys()))

    def study_diff(self):
        ## Need to also report missing.
        from edsl.base.BaseDiff import BaseDiff

        raise NotImplementedError("Need to implement this.")

    def print(self):
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Study")
        table.add_column("Original Name")
        table.add_column("Study Name")
        table.add_column("Class")
        table.add_column("Description")
        table.add_column("Hash")
        table.add_column("Coop info")
        table.add_column("Created")

        for obj_hash, obj in self.objects.items():
            url = (
                ""
                if not hasattr(obj, "coop_info") or obj.coop_info is None
                else obj.coop_info.get("url", "")
            )
            table.add_row(
                obj.variable_name,
                self.hash_to_name[obj_hash],
                obj.edsl_class_name,
                obj.description,
                obj.hash,
                url,
                datetime.fromtimestamp(obj.created_at).strftime("%Y-%m-%d %H:%M:%S"),
            )
        # Add cache at the end
        table.add_row(
            "N/A - Study Cache",
            "cache",
            "Cache",
            f"Cache of study, entries: {len(self.cache)}",
            str(hash(self.cache)),
            "N/A",
            "N/A",
        )
        console.print(table)

    def __exit__(self, exc_type, exc_val, exc_tb):
        snapshot = SnapShot(namespace=self.namespace, exclude=[self])
        # print("Frame objects are:", snapshot.namespace.keys())
        # breakpoint()
        if self.use_study_cache:
            unset_session_cache()

        for variable_name, object in snapshot.edsl_objects.items():
            self._add_edsl_object(object=object, variable_name=variable_name)

        if not self.starting_objects:
            if self.verbose:
                print(f"New study saved to {self.filename}.json")
            self.save()

        if self.starting_objects and list(self.starting_objects.keys()) == list(
            self.objects.keys()
        ):
            if self.verbose:
                print("Study perfectly replicated.")
        else:
            if self.verbose:
                print("Starting hashes:", self.starting_objects.keys())
                print("Current hashes:", self.objects.keys())
            if self.starting_objects:
                missing = set(self.starting_objects.keys()) - set(self.objects.keys())
                added = set(self.objects.keys()) - set(self.starting_objects.keys())
                # breakpoint()
                print("Study did not perfectly replicate.")
                for hash in missing:
                    print(f"Missing object: {self.starting_objects[hash]}")
                for hash in added:
                    print(f"Added object: {self.objects[hash]}")
                if self.overwrite_on_change:
                    print("Overwriting study file.")
                    self.save()
                else:
                    print(
                        "Please save the study file with a new name or call study iwth 'overwrite_on_change=True' to overwrite the existing study file."
                    )

        if self.coop:
            self.push()
            if self.overwrite_on_change:
                self.save()
            else:
                raise ValueError(
                    "If you want to push to coop, you must save the study file with a new name or call study iwth 'overwrite_on_change=True' to overwrite the existing study file."
                )

        if self.verbose:
            print("Objects in study now:")
            self.print()

        if self.proof_of_work_difficulty:
            print("Adding proof of work to study...")
            from edsl.study.ProofOfWork import ProofOfWork

            # TODO: Need to check if hashes are the same.
            if not self.proof_of_work.input_data:
                self.proof_of_work.add_input_data(str(self.__hash__()))
            self.proof_of_work.add_proof(self.proof_of_work_difficulty)
            print(
                "Proof of work added to study with difficulty ",
                self.proof_of_work_difficulty,
            )
            print(self.proof_of_work)
            self.save()

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "objects": {hash: obj.to_dict() for hash, obj in self.objects.items()},
            "filename": self.filename,
            "cache": self.cache.to_dict(),
            "use_study_cache": self.use_study_cache,
            "overwrite_on_change": self.overwrite_on_change,
            "proof_of_work": self.proof_of_work.to_dict(),
        }

    def versions(self):
        """Return a dictionary of objects grouped by variable name."""
        d = {}
        for _, obj_entry in self.objects.items():
            if obj_entry.variable_name not in d:
                d[obj_entry.variable_name] = [obj_entry]
            else:
                d[obj_entry.variable_name].append(obj_entry)

        return d

    def diff(self, variable_name: str, index1: int, index2: int):
        """Return the difference between the versions of an object."""
        versions = self.versions()[variable_name]
        diff = versions[index2].object - versions[index1].object
        return diff

    @classmethod
    def example(cls, verbose=False, randomize=False):
        import tempfile

        study_file = tempfile.NamedTemporaryFile()
        with cls(filename=study_file.name, verbose=verbose) as study:
            from edsl import QuestionFreeText

            q = QuestionFreeText.example(randomize=randomize)
        return study

    @classmethod
    def from_dict(cls, d):
        d["cache"] = Cache.from_dict(d["cache"])
        d["objects"] = {
            str(object_hash): ObjectEntry.from_dict(obj_dict)
            for object_hash, obj_dict in d["objects"].items()
        }
        d["proof_of_work"] = ProofOfWork.from_dict(d["proof_of_work"])
        return cls(**d)

    def save(self):
        if self.verbose:
            print(f"Saving study to {self.filename}.json")
        with open(self.filename + ".json", "w") as f:
            json.dump(self.to_dict(), f, indent=4)

    def _get_system_info(self):
        return {
            "platform": platform.platform(),
            "system": platform.system(),
            "processor": platform.processor(),
            "hostname": socket.gethostname(),
        }

    @staticmethod
    def _get_description(object):
        text = ""
        if hasattr(object, "__len__"):
            text += f"Num. entries: {len(object)}"
        if hasattr(object, "question_name"):
            text += f"Question name: {object.question_name}"
        return text

    def _add_edsl_object(self, object, variable_name, description=None) -> None:
        """
        >>> s = Study.example()
        >>> from edsl import QuestionLinearScale
        >>> s._add_edsl_object(QuestionLinearScale.example(), 'q')
        >>> len(s)
        2
        """
        if description is None:
            description = self._get_description(object)
        oe = ObjectEntry(
            variable_name=variable_name, object=object, description=description
        )
        if oe.hash in self.objects:
            return
        else:
            self.objects[oe.hash] = oe

    def push(self) -> dict:
        """Push the objects to coop."""

        from edsl import Coop

        coop = Coop()
        return coop.create(self, description=self.description)

    def delete_object(self, identifier: Union[str, UUID]):
        """
        Delete an EDSL object from the study.

        :param identifier: Either the variable name or the hash of the object to delete
        :raises ValueError: If the object is not found in the study
        """
        if isinstance(identifier, str):
            # If identifier is a variable name or a string representation of UUID
            for hash, obj_entry in list(self.objects.items()):
                if obj_entry.variable_name == identifier or hash == identifier:
                    del self.objects[hash]
                    self._create_mapping_dicts()  # Update internal mappings
                    if self.verbose:
                        print(f"Deleted object with identifier: {identifier}")
                    return
            raise ValueError(f"No object found with identifier: {identifier}")
        elif isinstance(identifier, UUID):
            # If identifier is a UUID object
            hash_str = str(identifier)
            if hash_str in self.objects:
                del self.objects[hash_str]
                self._create_mapping_dicts()  # Update internal mappings
                if self.verbose:
                    print(f"Deleted object with hash: {hash_str}")
                return
            raise ValueError(f"No object found with hash: {hash_str}")
        else:
            raise TypeError(
                "Identifier must be either a string (variable name or hash) or a UUID object"
            )

    @classmethod
    def pull(cls, uuid: Optional[Union[str, UUID]] = None, url: Optional[str] = None):
        """Pull the object from coop."""
        from edsl.coop import Coop

        coop = Coop()
        return coop.get(uuid, url, "study")

    def __repr__(self):
        return f"""Study(name = "{self.name}", description = "{self.description}", objects = {self.objects}, cache = {self.cache}, filename = "{self.filename}", coop = {self.coop}, use_study_cache = {self.use_study_cache}, overwrite_on_change = {self.overwrite_on_change})"""


if __name__ == "__main__":
    import doctest

    doctest.testmod(optionflags=doctest.ELLIPSIS)

    # with Study(name = "cool_study") as study:
    #      from edsl import QuestionFreeText
    #      q = QuestionFreeText.example()

    # assert len(study.objects) == 1

    # print(study.versions())
    # {'q': [ObjectEntry(variable_name='q', object=Question('free_text', question_name = """how_are_you""", question_text = """How are you?"""), description='Question name: how_are_you', coop_info=None, created_at=1720276402.561273, edsl_class_name='QuestionFreeText')]}
