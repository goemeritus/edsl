from typing import List, Dict, Any, Optional, TYPE_CHECKING, Callable
from dataclasses import dataclass
from contextlib import AbstractContextManager
from collections import UserList
from logging import Logger, getLogger
import logging
from edsl.logging_config import setup_logging

if TYPE_CHECKING:
    from .Cache import Cache
    from edsl.coop.coop import Coop
    from .CacheEntry import CacheEntry


class CacheKeyList(UserList):
    def __init__(self, data: List[str]):
        super().__init__(data)
        self.data = data

    def __repr__(self):
        import reprlib

        keys_repr = reprlib.repr(self.data)
        return f"CacheKeyList({keys_repr})"


class CacheEntriesList(UserList):
    def __init__(self, data: List["CacheEntry"]):
        super().__init__(data)
        self.data = data

    def __repr__(self):
        import reprlib

        entries_repr = reprlib.repr(self.data)
        return f"CacheEntries({entries_repr})"

    def to_cache(self) -> "Cache":
        from edsl.data.Cache import Cache

        return Cache({entry.key: entry for entry in self.data})


@dataclass
class CacheDifference:
    client_missing_entries: CacheEntriesList
    server_missing_keys: List[str]

    def __repr__(self):
        """Returns a string representation of the CacheDifference object."""
        import reprlib

        missing_entries_repr = reprlib.repr(self.client_missing_entries)
        missing_keys_repr = reprlib.repr(self.server_missing_keys)
        return f"CacheDifference(client_missing_entries={missing_entries_repr}, server_missing_keys={missing_keys_repr})"


class RemoteCacheSync(AbstractContextManager):
    """Synchronizes a local cache with a remote cache.

    Handles bidirectional synchronization:
    - Downloads missing entries from remote to local cache
    - Uploads new local entries to remote cache
    """

    def __init__(
        self,
        coop: "Coop",
        cache: "Cache",
        output_func: Callable,
        remote_cache: bool = True,
        remote_cache_description: str = "",
        logger: Optional[Logger] = None,
    ):
        """
        Initializes a RemoteCacheSync object.

        :param coop: Coop object for interacting with the remote cache
        :param cache: Cache object for local cache
        :param output_func: Function for outputting messages
        :param remote_cache: Whether to enable remote cache synchronization
        :param remote_cache_description: Description for remote cache entries
        :param logger: Optional logger instance. If not provided, creates a new one
        """
        self.coop = coop
        self.cache = cache
        self._output = output_func
        self.remote_cache_enabled = remote_cache
        self.remote_cache_description = remote_cache_description
        self.initial_cache_keys = []
        self.logger = logger or getLogger(__name__)
        self.logger.info(
            f"RemoteCacheSync initialized with cache size: {len(self.cache.keys())}"
        )

    def __enter__(self) -> "RemoteCacheSync":
        if self.remote_cache_enabled:
            self._sync_from_remote()
            self.initial_cache_keys = list(self.cache.keys())
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.remote_cache_enabled:
            self._sync_to_remote()
        return False  # Propagate exceptions

    def _get_cache_difference(self) -> CacheDifference:
        """Retrieves differences between local and remote caches."""
        diff = self.coop.remote_cache_get_diff(self.cache.keys())
        return CacheDifference(
            client_missing_entries=diff.get("client_missing_cacheentries", []),
            server_missing_keys=diff.get("server_missing_cacheentry_keys", []),
        )

    def _sync_from_remote(self) -> None:
        """Downloads missing entries from remote cache to local cache."""
        diff: CacheDifference = self._get_cache_difference()
        missing_count = len(diff.client_missing_entries)

        if missing_count == 0:
            self.logger.debug("No new entries to add to local cache.")
            return

        self.logger.info(
            f"Updating local cache with {missing_count:,} new "
            f"{'entry' if missing_count == 1 else 'entries'} from remote..."
        )

        self.cache.add_from_dict(
            {entry.key: entry for entry in diff.client_missing_entries}
        )
        self.logger.info("Local cache updated!")

    def _get_entries_to_upload(self, diff: CacheDifference) -> CacheEntriesList:
        """Determines which entries need to be uploaded to remote cache."""
        # Get entries for keys missing from server
        server_missing_entries = CacheEntriesList(
            [
                entry
                for key in diff.server_missing_keys
                if (entry := self.cache.data.get(key)) is not None
            ]
        )

        # Get newly added entries since sync started
        new_entries = CacheEntriesList(
            [
                entry
                for entry in self.cache.values()
                if entry.key not in self.initial_cache_keys
            ]
        )

        return server_missing_entries + new_entries

    def _sync_to_remote(self) -> None:
        """Uploads new local entries to remote cache."""
        diff: CacheDifference = self._get_cache_difference()
        entries_to_upload: CacheEntriesList = self._get_entries_to_upload(diff)
        upload_count = len(entries_to_upload)

        if upload_count > 0:
            self.logger.info(
                f"Updating remote cache with {upload_count:,} new "
                f"{'entry' if upload_count == 1 else 'entries'}..."
            )

            self.coop.remote_cache_create_many(
                entries_to_upload,
                visibility="private",
                description=self.remote_cache_description,
            )
            self.logger.info("Remote cache updated!")
        else:
            self.logger.debug("No new entries to add to remote cache.")

        self.logger.info(
            f"There are {len(self.cache.keys()):,} entries in the local cache."
        )


if __name__ == "__main__":
    import doctest

    doctest.testmod()

    setup_logging()  # Use default settings
    # Or customize: setup_logging(log_dir="custom_logs", console_level=logging.DEBUG)

    from edsl.coop.coop import Coop
    from edsl.data.Cache import Cache
    from edsl.data.CacheEntry import CacheEntry

    r = RemoteCacheSync(Coop(), Cache(), print)
    diff = r._get_cache_difference()
