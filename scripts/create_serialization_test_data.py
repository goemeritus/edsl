import itertools
import logging
import json
import os
from edsl import __version__ as edsl_version
from edsl.base.Base import RegisterSubclassesMeta
from edsl.coop.utils import ObjectRegistry, Study
from edsl.questions import *
from tests.serialization.cases.RegisterSerializationCasesMeta import (
    RegisterSerializationCasesMeta,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s\t%(message)s")


def create_serialization_test_data():
    if ".dev" in edsl_version:
        version = edsl_version.split(".dev")[0]
    else:
        version = edsl_version

    data = []
    path = f"tests/serialization/data/{version}.json"

    # A. check if the file already exists
    if os.path.exists(path):
        logging.info(f"`{path}` already exists.")
        return

    # B. Study data needs to go up here; otherwise, there is a namespace error
    with Study(name="example_study", verbose=False) as study:
        from edsl import QuestionFreeText

        q = QuestionFreeText.example()

    data.append(
        {
            "class_name": "Study",
            "class": Study,
            "example": study,
            "dict": study.to_dict(),
        }
    )

    # C. Collect all registered classes
    subclass_registry = RegisterSubclassesMeta.get_registry()
    questions_registry = RegisterQuestionsMeta.get_registered_classes()
    object_registry = ObjectRegistry.get_registry(
        subclass_registry=subclass_registry, exclude_classes=["QuestionBase", "Study"]
    )

    combined_items = itertools.chain(
        subclass_registry.items(),
        questions_registry.items(),
        object_registry.items(),
    )

    for subclass_name, subclass in combined_items:
        example = subclass.example()
        data.append(
            {
                "class_name": subclass_name,
                "class": subclass,
                "example": example,
                "dict": example.to_dict(),
            }
        )

    logging.info(f"Found {len(data)} registered classes")
    # check if all registered have edsl_version in the dict
    for item in data:
        if "edsl_version" not in item["dict"]:
            logging.warning(
                f"Class: {item['class_name']} does not have edsl_version in the dict"
            )

    # D. Create custom / more complex examples
    RegisterSerializationCasesMeta.generate_custom_example_data(container=data)

    # E. Write data to the file
    data_to_write = [
        {"class_name": item["class_name"], "dict": item["dict"]} for item in data
    ]
    with open(path, "w") as f:
        json.dump(data_to_write, f)
    logging.info(f"Serialization test data written to `{path}`.")
    logging.info("!!! DO NOT FORGET TO FORCE PUSH IT TO THE REPO !!!")


if __name__ == "__main__":
    create_serialization_test_data()
