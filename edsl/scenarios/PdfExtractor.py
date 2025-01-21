import os


class PdfExtractor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        #self.constructor = parent_object.__class__

    def get_pdf_dict(self) -> dict:
        # Ensure the file exists
        import fitz

        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"The file {self.pdf_path} does not exist.")

        # Open the PDF file
        document = fitz.open(self.pdf_path)

        # Get the filename from the path
        filename = os.path.basename(self.pdf_path)

        # Iterate through each page and extract text
        text = ""
        for page_num in range(len(document)):
            page = document.load_page(page_num)
            blocks = page.get_text("blocks")  # Extract text blocks

            # Sort blocks by their vertical position (y0) to maintain reading order
            blocks.sort(key=lambda b: (b[1], b[0]))  # Sort by y0 first, then x0

            # Combine the text blocks in order
            for block in blocks:
                text += block[4] + "\n"

        # Create a dictionary for the combined text
        page_info = {"filename": filename, "text": text}
        return page_info
