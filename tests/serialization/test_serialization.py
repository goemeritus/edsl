import itertools
import json
import os
from edsl import __version__ as edsl_version
from edsl.base.Base import RegisterSubclassesMeta
from edsl.coop.utils import ObjectRegistry
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
    subclass_registry = RegisterSubclassesMeta.get_registry()
    questions_registry = RegisterQuestionsMeta.get_registered_classes()
    object_registry = ObjectRegistry.get_registry(
        subclass_registry=subclass_registry, exclude_classes=["QuestionBase"]
    )
    combined_items = itertools.chain(
        subclass_registry.items(),
        questions_registry.items(),
        object_registry.items(),
    )
    classes = []
    for subclass_name, subclass in combined_items:
        classes.append(
            {
                "class_name": subclass_name,
                "class": subclass,
            }
        )

    for file in files:
        print("\n\n")
        print(f"Testing compatibility of {version} with {file}")
        with open(os.path.join(path, file), "r") as f:
            data = json.load(f)
        for item in data:
            class_name = item["class_name"]
            if class_name in [
                "QuestionFunctional",
                "QuestionBudget",
                "QuestionRank",
                "QuestionTopK",
            ]:
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
    combined_items = itertools.chain(
        RegisterSubclassesMeta.get_registry().items(),
        RegisterQuestionsMeta.get_registered_classes().items(),
        ObjectRegistry.get_registry().items(),
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

    classes_not_covered = (classes_to_cover - data_classes) - set(
        # We don't need the base Question or QuestionAddTwoNumbers (a test instance of QuestionFunctional)
        [
            "QuestionBase",
            "QuestionAddTwoNumbers",
            "FileStore",
            "HTMLFileStore",
            "CSVFileStore",
            "PDFFileStore",
            "PNGFileStore",
            "SQLiteFileStore",
        ]
    )

    assert (
        len(classes_not_covered) == 0
    ), f"No serialization data for the following classes: {classes_not_covered}"
