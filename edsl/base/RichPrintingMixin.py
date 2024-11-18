class RichPrintingMixin:
    """Mixin for rich printing and persistence of objects."""

    def _for_console(self):
        """Return a string representation of the object for console printing."""
        from rich.console import Console

        with io.StringIO() as buf:
            console = Console(file=buf, record=True)
            table = self.rich_print()
            console.print(table)
            return console.export_text()

    def __str__(self):
        """Return a string representation of the object for console printing."""
        # return self._for_console()
        return yaml.dump(self.to_dict(add_edsl_version=False))

    def print(self):
        """Print the object to the console."""
        from edsl.utilities.utilities import is_notebook
        from IPython.display import display

        if is_notebook():
            display(self.rich_print())
        else:
            from rich.console import Console

            console = Console()
            console.print(self.rich_print())
