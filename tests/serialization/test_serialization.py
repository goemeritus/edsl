import itertools
import json
import os
from edsl import __version__ as edsl_version
from edsl.Base import RegisterSubclassesMeta
from edsl.coop.utils import ObjectRegistry, Study
from edsl.questions import RegisterQuestionsMeta


def test_serialization():
    # get all filenames in tests/serialization/data -- just use full path
    path = "tests/serialization/data"
    files = os.listdir(path)

    # if no file starts with edsl_version, throw an error
    version = edsl_version.split(".dev")[0] if ".dev" in edsl_version else edsl_version
    assert any(
        [f.startswith(version) for f in files]
    ), f"No serialization data found for the current EDSL version ({version}). Please run `make test-data`."

    # get all EDSL classes that you'd like to test
    combined_items = itertools.chain(
        RegisterSubclassesMeta.get_registry().items(),
        RegisterQuestionsMeta.get_registered_classes().items(),
    )
    classes = []
    for subclass_name, subclass in combined_items:
        classes.append(
            {
                "class_name": subclass_name,
                "class": subclass,
            }
        )

    classes.append(
        {
            "class_name": "Study",
            "class": Study,
        }
    )

    for file in files:
        print("\n\n")
        print(f"Testing compatibility of {version} with {file}")
        with open(os.path.join(path, file), "r") as f:
            data = json.load(f)
        for item in data:
            class_name = item["class_name"]
            if class_name == "QuestionFunctional":
                continue
            print(f"- Testing {class_name}")
            try:
                cls = next(c for c in classes if c["class_name"] == class_name)
            except StopIteration:
                raise ValueError(f"Class {class_name} not found in classes")
            try:
                cls["class"].from_dict
            except:
                raise ValueError(f"Class {class_name} does not have from_dict method")
            try:
                _ = cls["class"].from_dict(item["dict"])
            except Exception as e:
                print("The data is:", item["dict"])
                raise ValueError(f"Error in class {class_name}: {e}")


def test_serialization_coverage():
    """
    This test will fail if the current EDSL version does not include tests
    for all EDSL objects.
    """

    def to_camel_case(s: str):
        words = s.split("_")
        capitalized_words = [word.title() for word in words]
        return "".join(capitalized_words)

    objects_dct = {}
    for object in ObjectRegistry.objects:
        camel_case_name = to_camel_case(object["object_type"])
        objects_dct[camel_case_name] = object["edsl_class"]

    combined_items = itertools.chain(
        RegisterSubclassesMeta.get_registry().items(),
        RegisterQuestionsMeta.get_registered_classes().items(),
        objects_dct.items(),
    )

    classes = {}
    for subclass_name, subclass in combined_items:
        classes[subclass_name] = subclass

    current_version = (
        edsl_version.split(".dev")[0] if ".dev" in edsl_version else edsl_version
    )

    file = f"tests/serialization/data/{current_version}.json"

    print(f"Testing coverage of {current_version} with {file}")
    with open(file, "r") as f:
        data = json.load(f)
    data_classes = set()
    for item in data:
        class_name = item["class_name"]
        data_classes.add(class_name)

    classes_to_cover = set(classes.keys())

    classes_not_covered = (classes_to_cover - data_classes) - set(["Question"])

    assert (
        len(classes_not_covered) == 0
    ), f"No serialization data for the following classes: {classes_not_covered}"
