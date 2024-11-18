import gzip
import json
from typing import Optional, Union, Any

from uuid import UUID


class PersistenceMixin:
    """Mixin for saving and loading objects to and from files."""

    def push(
        self,
        description: Optional[str] = None,
        visibility: Optional[str] = "unlisted",
    ):
        """Post the object to coop."""
        from edsl.coop import Coop

        c = Coop()
        return c.create(self, description, visibility)

    @classmethod
    def pull(cls, id_or_url: Union[str, UUID], exec_profile=None):
        """Pull the object from coop."""
        from edsl.coop import Coop

        if id_or_url.startswith("http"):
            uuid_value = id_or_url.split("/")[-1]
        else:
            uuid_value = id_or_url

        c = Coop()

        return c._get_base(cls, uuid_value, exec_profile=exec_profile)

    @classmethod
    def delete(cls, id_or_url: Union[str, UUID]):
        """Delete the object from coop."""
        from edsl.coop import Coop

        c = Coop()
        return c._delete_base(cls, id_or_url)

    @classmethod
    def patch(
        cls,
        id_or_url: Union[str, UUID],
        description: Optional[str] = None,
        value: Optional[Any] = None,
        visibility: Optional[str] = None,
    ):
        """
        Patch an uploaded objects attributes.
        - `description` changes the description of the object on Coop
        - `value` changes the value of the object on Coop. **has to be an EDSL object**
        - `visibility` changes the visibility of the object on Coop
        """
        from edsl.coop import Coop

        c = Coop()
        return c._patch_base(cls, id_or_url, description, value, visibility)

    @classmethod
    def search(cls, query):
        """Search for objects on coop."""
        from edsl.coop import Coop

        c = Coop()
        return c.search(cls, query)

    def save(self, filename, compress=True):
        """Save the object to a file as zippped JSON.

        >>> obj.save("obj.json.gz")

        """
        if filename.endswith("json.gz"):
            import warnings

            warnings.warn(
                "Do not apply the file extensions. The filename should not end with 'json.gz'."
            )
            filename = filename[:-7]
        if filename.endswith("json"):
            filename = filename[:-4]
            warnings.warn(
                "Do not apply the file extensions. The filename should not end with 'json'."
            )

        if compress:
            with gzip.open(filename + ".json.gz", "wb") as f:
                f.write(json.dumps(self.to_dict()).encode("utf-8"))
        else:
            with open(filename + ".json", "w") as f:
                f.write(json.dumps(self.to_dict()))

    @staticmethod
    def open_compressed_file(filename):
        with gzip.open(filename, "rb") as f:
            file_contents = f.read()
            file_contents_decoded = file_contents.decode("utf-8")
            d = json.loads(file_contents_decoded)
        return d

    @staticmethod
    def open_regular_file(filename):
        with open(filename, "r") as f:
            d = json.loads(f.read())
        return d

    @classmethod
    def load(cls, filename):
        """Load the object from a file.

        >>> obj = cls.load("obj.json.gz")

        """

        if filename.endswith("json.gz"):
            d = cls.open_compressed_file(filename)
        elif filename.endswith("json"):
            d = cls.open_regular_file(filename)
        else:
            try:
                d = cls.open_compressed_file(filename)
            except:
                d = cls.open_regular_file(filename)
            finally:
                raise ValueError("File must be a json or json.gz file")

        return cls.from_dict(d)
