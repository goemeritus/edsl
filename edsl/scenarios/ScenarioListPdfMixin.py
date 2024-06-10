import fitz  # PyMuPDF
import os
import subprocess

from edsl import Scenario


class ScenarioListPdfMixin:
    @classmethod
    def from_pdf(cls, filename):
        scenarios = list(cls.extract_text_from_pdf(filename))
        return cls(scenarios)

    @classmethod
    def _from_pdf_to_image(cls, pdf_path, image_format="jpeg"):
        """
        Convert each page of a PDF into an image and create Scenario instances.

        :param pdf_path: Path to the PDF file.
        :param image_format: Format of the output images (default is 'jpeg').
        :return: ScenarioList instance containing the Scenario instances.
        """
        import tempfile
        from pdf2image import convert_from_path

        with tempfile.TemporaryDirectory() as output_folder:
            # Convert PDF to images
            images = convert_from_path(pdf_path)

            scenarios = []

            # Save each page as an image and create Scenario instances
            for i, image in enumerate(images):
                image_path = os.path.join(output_folder, f"page_{i+1}.{image_format}")
                image.save(image_path, image_format.upper())

                scenario = Scenario._from_filepath_image(image_path)
                scenarios.append(scenario)

            print(f"Saved {len(images)} pages as images in {output_folder}")
            return cls(scenarios)

    @staticmethod
    def extract_text_from_pdf(pdf_path):
        # Ensure the file exists
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"The file {pdf_path} does not exist.")

        # Open the PDF file
        document = fitz.open(pdf_path)

        # Get the filename from the path
        filename = os.path.basename(pdf_path)

        # Iterate through each page and extract text
        for page_num in range(len(document)):
            page = document.load_page(page_num)
            text = page.get_text()

            # Create a dictionary for the current page
            page_info = {"filename": filename, "page": page_num + 1, "text": text}
            yield Scenario(page_info)

    def create_hello_world_pdf(pdf_path):
        # LaTeX content
        latex_content = r"""
        \documentclass{article}
        \title{Hello World}
        \author{John}
        \date{\today}
        \begin{document}
        \maketitle
        \section{Hello, World!}
        This is a simple hello world example created with LaTeX and Python.
        \end{document}
        """

        # Create a .tex file
        tex_filename = pdf_path + ".tex"
        with open(tex_filename, "w") as tex_file:
            tex_file.write(latex_content)

        # Compile the .tex file to PDF
        subprocess.run(["pdflatex", tex_filename], check=True)

        # Optionally, clean up auxiliary files generated by pdflatex
        aux_files = [pdf_path + ext for ext in [".aux", ".log"]]
        for aux_file in aux_files:
            try:
                os.remove(aux_file)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    pass

    # from edsl import ScenarioList

    # class ScenarioListNew(ScenarioList, ScenaroListPdfMixin):
    #     pass

    # #ScenarioListNew.create_hello_world_pdf('hello_world')
    # #scenarios = ScenarioListNew.from_pdf('hello_world.pdf')
    # #print(scenarios)

    # from edsl import ScenarioList, QuestionFreeText
    # homo_silicus = ScenarioList.from_pdf('w31122.pdf')
    # q = QuestionFreeText(question_text = "What is the key point of the text in {{ text }}?", question_name = "key_point")
    # results = q.by(homo_silicus).run(progress_bar = True)
    # results.select('scenario.page', 'answer.key_point').order_by('page').print()
