"""A NotebookToPaper converts an edsl Notebook into various paper formats."""

from __future__ import annotations
import os
import shutil
from typing import Optional
from nbconvert import LatexExporter
import nbformat
from traitlets.config import Config


class NotebookToPaper:
    """
    A utility class that converts edsl Notebooks into various paper formats.
    Currently supports LaTeX output with customizable templates.
    """
    
    DEFAULT_TEMPLATE = 'latex'
    
    def __init__(self, notebook):
        """
        Initialize with a Notebook instance.
        
        Args:
            notebook: An edsl Notebook instance to convert
        """
        self.notebook = notebook
        
    @property
    def available_templates(self) -> list[str]:
        """
        List available built-in LaTeX templates.
        
        Returns:
            list[str]: Names of available templates
        """
        # Currently nbconvert provides 'latex' and 'base' templates
        return ['latex', 'base']
    
    def make_latex(
        self,
        output_dir: Optional[str] = None,
        template_name: str = DEFAULT_TEMPLATE
    ) -> str:
        """
        Convert the notebook to LaTeX and create a zip file containing all necessary files.
        
        Args:
            output_dir: Directory to store output files. Defaults to current working directory.
            template_name: Name of template to use or path to custom template.
                Default is 'latex'. Built-in options are:
                - 'latex' (default)
                - 'base'
                Or provide path to custom template file
        
        Returns:
            str: Path to the created zip file
            
        Example:
            >>> from edsl import Notebook
            >>> nb = Notebook.example()
            >>> converter = NotebookToPaper(nb)
            >>> zip_path = converter.make_latex()  # uses latex template
        """
        # Set up the output directory
        if output_dir is None:
            output_dir = os.getcwd()
            
        # Create temporary directory
        temp_dir = os.path.join(output_dir, f"{self.notebook.name}_latex_temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # Configure the LaTeX export
            c = Config()
            if os.path.exists(template_name):
                # If template_name is a path to a file, use that
                c.LatexExporter.template_file = template_name
            else:
                # Otherwise assume it's a built-in template name
                if template_name not in self.available_templates:
                    raise ValueError(
                        f"Template '{template_name}' not found. "
                        f"Available built-in templates: {self.available_templates}"
                    )
                c.LatexExporter.template_name = template_name
                
            c.LatexExporter.exclude_input_prompt = True
            c.LatexExporter.exclude_output_prompt = True
            
            # Create the LaTeX exporter with our config
            latex_exporter = LatexExporter(config=c)
            
            # Convert to LaTeX
            notebook = nbformat.from_dict(self.notebook.data)
            (latex_body, resources) = latex_exporter.from_notebook_node(notebook)
            
            # Write the main LaTeX file
            latex_file_path = os.path.join(temp_dir, f"{self.notebook.name}.tex")
            with open(latex_file_path, 'w', encoding='utf-8') as f:
                f.write(latex_body)
            
            # Write any additional resources (like images)
            if resources.get('outputs'):
                for filename, data in resources['outputs'].items():
                    output_file_path = os.path.join(temp_dir, filename)
                    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
                    with open(output_file_path, 'wb') as f:
                        f.write(data)
            
            # Create zip file
            zip_path = os.path.join(output_dir, f"{self.notebook.name}_latex.zip")
            shutil.make_archive(os.path.splitext(zip_path)[0], 'zip', temp_dir)
            
            return zip_path
            
        except Exception as e:
            raise Exception(f"Failed to convert notebook to LaTeX: {str(e)}")
        
        finally:
            # Clean up temporary directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
    
    def make_pdf(
        self,
        output_dir: Optional[str] = None,
        template_name: str = DEFAULT_TEMPLATE,
        keep_latex: bool = False
    ) -> str:
        """
        Convert the notebook to PDF via LaTeX.
        Not yet implemented.
        """
        raise NotImplementedError("PDF conversion not yet implemented")

    @classmethod
    def example(cls) -> NotebookToPaper:
        """
        Create an example NotebookToPaper instance using an example Notebook.
        
        Returns:
            NotebookToPaper: An instance using an example Notebook
        """
        from edsl import Notebook
        return cls(Notebook.example())


if __name__ == "__main__":
    # Example usage and test
    from edsl import Notebook
    
    #notebook = Notebook.example()
    
    
    notebook = Notebook.pull("55641402-f0e9-4aa5-9803-bb85e61d0d6b")
    converter = NotebookToPaper(notebook)
    
    # Show available templates
    print("Available templates:", converter.available_templates)
    
    # Convert using default template
    latex_path = converter.make_latex(output_dir = "bu_paper")
    print(f"Created LaTeX zip at: {latex_path}")