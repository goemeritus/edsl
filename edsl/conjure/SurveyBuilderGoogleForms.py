import textwrap
from typing import Dict
import json

import pandas as pd

from edsl.conjure.SurveyBuilder import SurveyBuilder
from edsl.conjure.utilities import RCodeSnippet


class SurveyBuilderGoogleForms(SurveyBuilder):
    
    def get_responses(self) -> Dict:
        """Returns a dataframe of responses by reading the datafile_name.
        
        The structure should be a dictionary, where the keys are the question codes,
        and the values are the responses.

        For example, {"Q1": [1, 2, 3], "Q2": [4, 5, 6]}
        """
        df = pd.read_csv(self.datafile_name)
        # df = self.get_responses_r_code(self.datafile_name)
        df.fillna("", inplace=True)
        df = df.astype(str)
        data_dict = df.to_dict(orient="list")
        return {k.lower(): v for k, v in data_dict.items()}

    def get_question_name_to_text(self) -> Dict:
        """
        Get the question name to text mapping.
        """
        d = {}
        df = pd.read_csv(self.datafile_name)
        for col in df.columns:
            if col in self.lookup_dict():
                d[col] = self.lookup_dict()[col]
            else:
                d[col] = col

        return d

    def get_question_name_to_answer_book(self):
        """Returns a dictionary mapping question codes to a dictionary mapping answer codes to answer text.

        e.g., {'q1': {1: 'yes', 2:'no'}}
        """
        d = self.get_question_name_to_text()
        return {k: {} for k, v in d.items()}


if __name__ == "__main__":
    google_form_builder = SurveyBuilderGoogleForms("responses.csv", 100)
