def is_notebook() -> bool:
    """Check if the code is running in a Jupyter notebook."""
    try:
        shell = get_ipython().__class__.__name__
        if shell == "ZMQInteractiveShell":
            return True  # Jupyter notebook or qtconsole
        elif shell == "TerminalInteractiveShell":
            return False  # Terminal running IPython
        else:
            return False  # Other type (e.g., IDLE, PyCharm, etc.)
    except NameError:
        return False  # Probably standard Python interpreter
