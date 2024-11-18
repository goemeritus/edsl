import functools
import asyncio
import nest_asyncio

nest_asyncio.apply()


def add_edsl_version(func):
    """
    Decorator for EDSL objects' `to_dict` method.
    - Adds the EDSL version and class name to the dictionary.

    """
    from edsl import __version__ as edsl_version

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        d = func(*args, **kwargs)
        d["edsl_version"] = edsl_version
        d["edsl_class_name"] = func.__qualname__.split(".")[0]
        return d

    return wrapper


def remove_edsl_version(func):
    """
    Decorator for the EDSL objects' `from_dict` method.
    - Removes the EDSL version and class name from the dictionary.
    - Ensures backwards compatibility with older versions of EDSL.
    """

    @functools.wraps(func)
    def wrapper(cls, data, *args, **kwargs):
        data_copy = dict(data)
        edsl_version = data_copy.pop("edsl_version", None)
        edsl_classname = data_copy.pop("edsl_class_name", None)

        # Version- and class-specific logic here
        if edsl_classname == "Survey":
            if edsl_version is None or edsl_version <= "0.1.20":
                data_copy["question_groups"] = {}

        return func(cls, data_copy, *args, **kwargs)

    return wrapper


def jupyter_nb_handler(func):
    """Decorator to run an async function in the event loop if it's running, or synchronously otherwise."""

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        # This is an async wrapper to await the coroutine
        return await func(*args, **kwargs)

    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If the loop is running, schedule the coroutine and wait for the result
            future = asyncio.ensure_future(async_wrapper(*args, **kwargs))
            return loop.run_until_complete(future)
        else:
            # If the loop is not running, run the coroutine to completion
            return asyncio.run(async_wrapper(*args, **kwargs))

    return wrapper


def sync_wrapper(async_func):
    """Decorator to create a synchronous wrapper for an asynchronous function."""

    @functools.wraps(async_func)
    def wrapper(*args, **kwargs):
        return asyncio.run(async_func(*args, **kwargs))

    return wrapper
