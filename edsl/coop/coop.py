import aiohttp
import json
import requests

from typing import Any, Optional, Union, Literal, TypedDict
from uuid import UUID

import edsl

from edsl.config import CONFIG
from edsl.data.CacheEntry import CacheEntry
from edsl.jobs.Jobs import Jobs
from edsl.surveys.Survey import Survey

from edsl.exceptions.coop import (
    CoopInvalidURLError,
    CoopNoUUIDError,
    CoopServerResponseError,
)
from edsl.coop.utils import (
    EDSLObject,
    ObjectRegistry,
    ObjectType,
    RemoteJobStatus,
    VisibilityType,
)

from edsl.coop.CoopFunctionsMixin import CoopFunctionsMixin
from edsl.coop.ExpectedParrotKeyHandler import ExpectedParrotKeyHandler

from edsl.inference_services.data_structures import ServiceToModelsMapping


class RemoteInferenceResponse(TypedDict):
    job_uuid: str
    results_uuid: str
    results_url: str
    latest_error_report_uuid: str
    latest_error_report_url: str
    status: str
    reason: str
    credits_consumed: float
    version: str


class RemoteInferenceCreationInfo(TypedDict):
    uuid: str
    description: str
    status: str
    iterations: int
    visibility: str
    version: str


class Coop(CoopFunctionsMixin):
    """
    Client for the Expected Parrot API.
    """

    def __init__(
        self, api_key: Optional[str] = None, url: Optional[str] = None
    ) -> None:
        """
        Initialize the client.
        - Provide an API key directly, or through an env variable.
        - Provide a URL directly, or use the default one.
        """
        self.ep_key_handler = ExpectedParrotKeyHandler()
        self.api_key = api_key or self.ep_key_handler.get_ep_api_key()

        self.url = url or CONFIG.EXPECTED_PARROT_URL
        if self.url.endswith("/"):
            self.url = self.url[:-1]
        if "chick.expectedparrot" in self.url:
            self.api_url = "https://chickapi.expectedparrot.com"
        elif "expectedparrot" in self.url:
            self.api_url = "https://api.expectedparrot.com"
        elif "localhost:1234" in self.url:
            self.api_url = "http://localhost:8000"
        else:
            self.api_url = self.url
        self._edsl_version = edsl.__version__

    def get_progress_bar_url(self):
        return f"{CONFIG.EXPECTED_PARROT_URL}"

    ################
    # BASIC METHODS
    ################
    @property
    def headers(self) -> dict:
        """
        Return the headers for the request.
        """
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            headers["Authorization"] = f"Bearer None"
        return headers

    def _send_server_request(
        self,
        uri: str,
        method: str,
        payload: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = 5,
    ) -> requests.Response:
        """
        Send a request to the server and return the response.
        """
        url = f"{self.api_url}/{uri}"
        method = method.upper()
        if payload is None:
            timeout = 40
        elif (
            method.upper() == "POST"
            and "json_string" in payload
            and payload.get("json_string") is not None
        ):
            timeout = max(40, (len(payload.get("json_string", "")) // (1024 * 1024)))
        try:
            if method in ["GET", "DELETE"]:
                response = requests.request(
                    method, url, params=params, headers=self.headers, timeout=timeout
                )
            elif method in ["POST", "PATCH"]:
                response = requests.request(
                    method,
                    url,
                    params=params,
                    json=payload,
                    headers=self.headers,
                    timeout=timeout,
                )
            else:
                raise Exception(f"Invalid {method=}.")
        except requests.ConnectionError:
            raise requests.ConnectionError(f"Could not connect to the server at {url}.")

        return response

    def _get_latest_stable_version(self, version: str) -> str:
        """
        Extract the latest stable PyPI version from a version string.

        Examples:
        - Decrement the patch number of a dev version: "0.1.38.dev1" -> "0.1.37"
        - Return a stable version as is: "0.1.37" -> "0.1.37"
        """
        if "dev" not in version:
            return version
        else:
            # For 0.1.38.dev1, split into ["0", "1", "38", "dev1"]
            major, minor, patch = version.split(".")[:3]

            current_patch = int(patch)
            latest_patch = current_patch - 1
            return f"{major}.{minor}.{latest_patch}"

    def _user_version_is_outdated(
        self, user_version_str: str, server_version_str: str
    ) -> bool:
        """
        Check if the user's EDSL version is outdated compared to the server's.
        """
        server_stable_version_str = self._get_latest_stable_version(server_version_str)
        user_stable_version_str = self._get_latest_stable_version(user_version_str)

        # Turn the version strings into tuples of ints for comparison
        user_stable_version = tuple(map(int, user_stable_version_str.split(".")))
        server_stable_version = tuple(map(int, server_stable_version_str.split(".")))

        return user_stable_version < server_stable_version

    def _resolve_server_response(
        self, response: requests.Response, check_api_key: bool = True
    ) -> None:
        """
        Check the response from the server and raise errors as appropriate.
        """
        # Get EDSL version from header
        # breakpoint()
        server_edsl_version = response.headers.get("X-EDSL-Version")

        if server_edsl_version:
            if self._user_version_is_outdated(
                user_version_str=self._edsl_version,
                server_version_str=server_edsl_version,
            ):
                print(
                    "Please upgrade your EDSL version to access our latest features. Open your terminal and run `pip install --upgrade edsl`"
                )

        if response.status_code >= 400:
            try:
                message = response.json().get("detail")
            except json.JSONDecodeError:
                raise CoopServerResponseError(
                    f"Server returned status code {response.status_code}."
                    "JSON response could not be decoded.",
                    "The server response was: " + response.text,
                )
            # print(response.text)
            if "The API key you provided is invalid" in message and check_api_key:
                import secrets
                from edsl.utilities.utilities import write_api_key_to_env

                edsl_auth_token = secrets.token_urlsafe(16)

                print("Your Expected Parrot API key is invalid.")
                self._display_login_url(
                    edsl_auth_token=edsl_auth_token,
                    link_description="\n🔗 Use the link below to log in to your account and automatically update your API key.",
                )
                api_key = self._poll_for_api_key(edsl_auth_token)

                if api_key is None:
                    print("\nTimed out waiting for login. Please try again.")
                    return

                print("\n✨ API key retrieved.")

                if stored_in_user_space := self.ep_key_handler.ask_to_store(api_key):
                    pass
                else:
                    path_to_env = write_api_key_to_env(api_key)
                    print(
                        "\n✨ API key retrieved and written to .env file at the following path:"
                    )
                    print(f"    {path_to_env}")
                    print("Rerun your code to try again with a valid API key.")
                return

            elif "Authorization" in message:
                print(message)
                message = "Please provide an Expected Parrot API key."

            raise CoopServerResponseError(message)

    def _poll_for_api_key(
        self, edsl_auth_token: str, timeout: int = 120
    ) -> Union[str, None]:
        """
        Allows the user to retrieve their Expected Parrot API key by logging in with an EDSL auth token.

        :param edsl_auth_token: The EDSL auth token to use for login
        :param timeout: Maximum time to wait for login, in seconds (default: 120)
        """
        import time
        from datetime import datetime

        start_poll_time = time.time()
        waiting_for_login = True
        while waiting_for_login:
            elapsed_time = time.time() - start_poll_time
            if elapsed_time > timeout:
                # Timed out waiting for the user to log in
                print("\r" + " " * 80 + "\r", end="")
                return None

            api_key = self._get_api_key(edsl_auth_token)
            if api_key is not None:
                print("\r" + " " * 80 + "\r", end="")
                return api_key
            else:
                duration = 5
                time_checked = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
                frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                start_time = time.time()
                i = 0
                while time.time() - start_time < duration:
                    print(
                        f"\r{frames[i % len(frames)]} Waiting for login. Last checked: {time_checked}",
                        end="",
                        flush=True,
                    )
                    time.sleep(0.1)
                    i += 1

    def _json_handle_none(self, value: Any) -> Any:
        """
        Handle None values during JSON serialization.
        - Return "null" if the value is None. Otherwise, don't return anything.
        """
        if value is None:
            return "null"

    def _resolve_uuid_or_alias(
        self, uuid: Union[str, UUID] = None, url: str = None
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Resolve the uuid or alias information from a uuid or a url.
        Returns a tuple of (uuid, owner_username, alias)
        - For content/<uuid> URLs: returns (uuid, None, None)
        - For content/<username>/<alias> URLs: returns (None, username, alias)
        """
        if not url and not uuid:
            raise CoopNoUUIDError("No uuid or url provided for the object.")

        if not uuid and url:
            parts = (
                url.replace("http://", "")
                .replace("https://", "")
                .rstrip("/")
                .split("/")
            )

            # Remove domain
            parts = parts[1:]

            if len(parts) < 2 or parts[0] != "content":
                raise CoopInvalidURLError(
                    f"Invalid URL format. The URL must end with /content/<uuid> or /content/<username>/<alias>: {url}"
                )

            if len(parts) == 2:
                obj_uuid = parts[1]
                return obj_uuid, None, None
            elif len(parts) == 3:
                username, alias = parts[1], parts[2]
                return None, username, alias
            else:
                raise CoopInvalidURLError(
                    f"Invalid URL format. The URL must end with /content/<uuid> or /content/<username>/<alias>: {url}"
                )

        return str(uuid), None, None

    @property
    def edsl_settings(self) -> dict:
        """
        Retrieve and return the EDSL settings stored on Coop.
        If no response is received within 5 seconds, return an empty dict.
        """
        from requests.exceptions import Timeout

        try:
            response = self._send_server_request(
                uri="api/v0/edsl-settings", method="GET", timeout=20
            )
            self._resolve_server_response(response, check_api_key=False)
            return response.json()
        except Timeout:
            return {}

    ################
    # Objects
    ################
    def create(
        self,
        object: EDSLObject,
        description: Optional[str] = None,
        alias: Optional[str] = None,
        visibility: Optional[VisibilityType] = "unlisted",
    ) -> dict:
        """
        Create an EDSL object in the Coop server.
        """
        object_type = ObjectRegistry.get_object_type_by_edsl_class(object)
        response = self._send_server_request(
            uri=f"api/v0/object",
            method="POST",
            payload={
                "description": description,
                "alias": alias,
                "json_string": json.dumps(
                    object.to_dict(),
                    default=self._json_handle_none,
                ),
                "object_type": object_type,
                "visibility": visibility,
                "version": self._edsl_version,
            },
        )
        self._resolve_server_response(response)
        response_json = response.json()
        return {
            "description": response_json.get("description"),
            "object_type": object_type,
            "url": f"{self.url}/content/{response_json.get('uuid')}",
            "uuid": response_json.get("uuid"),
            "version": self._edsl_version,
            "visibility": response_json.get("visibility"),
        }

    def get(
        self,
        uuid: Union[str, UUID] = None,
        url: str = None,
        expected_object_type: Optional[ObjectType] = None,
    ) -> EDSLObject:
        """
        Retrieve an EDSL object by its uuid/url or by owner username and alias.
        - If the object's visibility is private, the user must be the owner.
        - Optionally, check if the retrieved object is of a certain type.

        :param uuid: the uuid of the object either in str or UUID format.
        :param url: the url of the object (can be content/uuid or content/username/alias format).
        :param expected_object_type: the expected type of the object.

        :return: the object instance.
        """
        obj_uuid, owner_username, alias = self._resolve_uuid_or_alias(uuid, url)

        if obj_uuid:
            response = self._send_server_request(
                uri=f"api/v0/object",
                method="GET",
                params={"uuid": obj_uuid},
            )
        else:
            response = self._send_server_request(
                uri=f"api/v0/object/alias",
                method="GET",
                params={"owner_username": owner_username, "alias": alias},
            )

        self._resolve_server_response(response)
        json_string = response.json().get("json_string")
        object_type = response.json().get("object_type")
        if expected_object_type and object_type != expected_object_type:
            raise Exception(f"Expected {expected_object_type=} but got {object_type=}")
        edsl_class = ObjectRegistry.object_type_to_edsl_class.get(object_type)
        object = edsl_class.from_dict(json.loads(json_string))
        return object

    def get_all(self, object_type: ObjectType) -> list[dict[str, Any]]:
        """
        Retrieve all objects of a certain type associated with the user.
        """
        edsl_class = ObjectRegistry.object_type_to_edsl_class.get(object_type)
        response = self._send_server_request(
            uri=f"api/v0/objects",
            method="GET",
            params={"type": object_type},
        )
        self._resolve_server_response(response)
        objects = [
            {
                "object": edsl_class.from_dict(json.loads(o.get("json_string"))),
                "uuid": o.get("uuid"),
                "version": o.get("version"),
                "description": o.get("description"),
                "visibility": o.get("visibility"),
                "url": f"{self.url}/content/{o.get('uuid')}",
            }
            for o in response.json()
        ]
        return objects

    def delete(self, uuid: Union[str, UUID] = None, url: str = None) -> dict:
        """
        Delete an object from the server.
        """
        obj_uuid, _, _ = self._resolve_uuid_or_alias(uuid, url)
        response = self._send_server_request(
            uri=f"api/v0/object",
            method="DELETE",
            params={"uuid": obj_uuid},
        )

        self._resolve_server_response(response)
        return response.json()

    def patch(
        self,
        uuid: Union[str, UUID] = None,
        url: str = None,
        description: Optional[str] = None,
        alias: Optional[str] = None,
        value: Optional[EDSLObject] = None,
        visibility: Optional[VisibilityType] = None,
    ) -> dict:
        """
        Change the attributes of an uploaded object
        - Only supports visibility for now
        """
        if description is None and visibility is None and value is None:
            raise Exception("Nothing to patch.")
        obj_uuid, _, _ = self._resolve_uuid_or_alias(uuid, url)
        response = self._send_server_request(
            uri=f"api/v0/object",
            method="PATCH",
            params={"uuid": obj_uuid},
            payload={
                "description": description,
                "alias": alias,
                "json_string": (
                    json.dumps(
                        value.to_dict(),
                        default=self._json_handle_none,
                    )
                    if value
                    else None
                ),
                "visibility": visibility,
            },
        )
        self._resolve_server_response(response)
        return response.json()

    ################
    # Remote Cache
    ################
    def remote_cache_create(
        self,
        cache_entry: CacheEntry,
        visibility: VisibilityType = "private",
        description: Optional[str] = None,
    ) -> dict:
        """
        Create a single remote cache entry.
        If an entry with the same key already exists in the database, update it instead.

        :param cache_entry: The cache entry to send to the server.
        :param visibility: The visibility of the cache entry.
        :param optional description: A description for this entry in the remote cache.

        >>> entry = CacheEntry.example()
        >>> coop.remote_cache_create(cache_entry=entry)
        {'status': 'success', 'created_entry_count': 1, 'updated_entry_count': 0}
        """
        response = self._send_server_request(
            uri="api/v0/remote-cache",
            method="POST",
            payload={
                "json_string": json.dumps(cache_entry.to_dict()),
                "version": self._edsl_version,
                "visibility": visibility,
                "description": description,
            },
        )
        self._resolve_server_response(response)
        response_json = response.json()
        created_entry_count = response_json.get("created_entry_count", 0)
        if created_entry_count > 0:
            self.remote_cache_create_log(
                response,
                description="Upload new cache entries to server",
                cache_entry_count=created_entry_count,
            )
        return response.json()

    def remote_cache_create_many(
        self,
        cache_entries: list[CacheEntry],
        visibility: VisibilityType = "private",
        description: Optional[str] = None,
    ) -> dict:
        """
        Create many remote cache entries.
        If an entry with the same key already exists in the database, update it instead.

        :param cache_entries: The list of cache entries to send to the server.
        :param visibility: The visibility of the cache entries.
        :param optional description: A description for these entries in the remote cache.

        >>> entries = [CacheEntry.example(randomize=True) for _ in range(10)]
        >>> coop.remote_cache_create_many(cache_entries=entries)
        {'status': 'success', 'created_entry_count': 10, 'updated_entry_count': 0}
        """
        payload = [
            {
                "json_string": json.dumps(c.to_dict()),
                "version": self._edsl_version,
                "visibility": visibility,
                "description": description,
            }
            for c in cache_entries
        ]
        response = self._send_server_request(
            uri="api/v0/remote-cache/many",
            method="POST",
            payload=payload,
            timeout=40,
        )
        self._resolve_server_response(response)
        response_json = response.json()
        created_entry_count = response_json.get("created_entry_count", 0)
        if created_entry_count > 0:
            self.remote_cache_create_log(
                response,
                description="Upload new cache entries to server",
                cache_entry_count=created_entry_count,
            )
        return response.json()

    def remote_cache_get(
        self,
        exclude_keys: Optional[list[str]] = None,
        select_keys: Optional[list[str]] = None,
    ) -> list[CacheEntry]:
        """
        Get all remote cache entries.

        :param optional exclude_keys: Exclude CacheEntry objects with these keys.

        >>> coop.remote_cache_get()
        [CacheEntry(...), CacheEntry(...), ...]
        """
        if exclude_keys is None:
            exclude_keys = []
        if select_keys is None:
            select_keys = []
        response = self._send_server_request(
            uri="api/v0/remote-cache/get-many",
            method="POST",
            payload={"keys": exclude_keys, "selected_keys": select_keys},
            timeout=40,
        )
        self._resolve_server_response(response)
        return [
            CacheEntry.from_dict(json.loads(v.get("json_string")))
            for v in response.json()
        ]

    def remote_cache_get_diff(
        self,
        client_cacheentry_keys: list[str],
    ) -> dict:
        """
        Get the difference between local and remote cache entries for a user.
        """
        response = self._send_server_request(
            uri="api/v0/remote-cache/get-diff",
            method="POST",
            payload={"keys": client_cacheentry_keys},
            timeout=40,
        )
        self._resolve_server_response(response)
        response_json = response.json()
        response_dict = {
            "client_missing_cacheentries": [
                CacheEntry.from_dict(json.loads(c.get("json_string")))
                for c in response_json.get("client_missing_cacheentries", [])
            ],
            "server_missing_cacheentry_keys": response_json.get(
                "server_missing_cacheentry_keys", []
            ),
        }
        downloaded_entry_count = len(response_dict["client_missing_cacheentries"])
        if downloaded_entry_count > 0:
            self.remote_cache_create_log(
                response,
                description="Download missing cache entries to client",
                cache_entry_count=downloaded_entry_count,
            )
        return response_dict

    def remote_cache_clear(self) -> dict:
        """
        Clear all remote cache entries.

        >>> entries = [CacheEntry.example(randomize=True) for _ in range(10)]
        >>> coop.remote_cache_create_many(cache_entries=entries)
        >>> coop.remote_cache_clear()
        {'status': 'success', 'deleted_entry_count': 10}
        """
        response = self._send_server_request(
            uri="api/v0/remote-cache/delete-all",
            method="DELETE",
        )
        self._resolve_server_response(response)
        response_json = response.json()
        deleted_entry_count = response_json.get("deleted_entry_count", 0)
        if deleted_entry_count > 0:
            self.remote_cache_create_log(
                response,
                description="Clear cache entries",
                cache_entry_count=deleted_entry_count,
            )
        return response.json()

    def remote_cache_create_log(
        self, response: requests.Response, description: str, cache_entry_count: int
    ) -> Union[dict, None]:
        """
        If a remote cache action has been completed successfully,
        log the action.
        """
        if 200 <= response.status_code < 300:
            log_response = self._send_server_request(
                uri="api/v0/remote-cache-log",
                method="POST",
                payload={
                    "description": description,
                    "cache_entry_count": cache_entry_count,
                },
            )
            self._resolve_server_response(log_response)
            return response.json()

    def remote_cache_clear_log(self) -> dict:
        """
        Clear all remote cache log entries.

        >>> coop.remote_cache_clear_log()
        {'status': 'success'}
        """
        response = self._send_server_request(
            uri="api/v0/remote-cache-log/delete-all",
            method="DELETE",
        )
        self._resolve_server_response(response)
        return response.json()

    def remote_inference_create(
        self,
        job: Jobs,
        description: Optional[str] = None,
        status: RemoteJobStatus = "queued",
        visibility: Optional[VisibilityType] = "unlisted",
        initial_results_visibility: Optional[VisibilityType] = "unlisted",
        iterations: Optional[int] = 1,
    ) -> RemoteInferenceCreationInfo:
        """
        Send a remote inference job to the server.

        :param job: The EDSL job to send to the server.
        :param optional description: A description for this entry in the remote cache.
        :param status: The status of the job. Should be 'queued', unless you are debugging.
        :param visibility: The visibility of the cache entry.
        :param iterations: The number of times to run each interview.

        >>> job = Jobs.example()
        >>> coop.remote_inference_create(job=job, description="My job")
        {'uuid': '9f8484ee-b407-40e4-9652-4133a7236c9c', 'description': 'My job', 'status': 'queued', 'iterations': None, 'visibility': 'unlisted', 'version': '0.1.38.dev1'}
        """
        response = self._send_server_request(
            uri="api/v0/remote-inference",
            method="POST",
            payload={
                "json_string": json.dumps(
                    job.to_dict(),
                    default=self._json_handle_none,
                ),
                "description": description,
                "status": status,
                "iterations": iterations,
                "visibility": visibility,
                "version": self._edsl_version,
                "initial_results_visibility": initial_results_visibility,
            },
        )
        self._resolve_server_response(response)
        response_json = response.json()

        return RemoteInferenceCreationInfo(
            **{
                "uuid": response_json.get("job_uuid"),
                "description": response_json.get("description"),
                "status": response_json.get("status"),
                "iterations": response_json.get("iterations"),
                "visibility": response_json.get("visibility"),
                "version": self._edsl_version,
            }
        )

    def remote_inference_get(
        self, job_uuid: Optional[str] = None, results_uuid: Optional[str] = None
    ) -> RemoteInferenceResponse:
        """
        Get the details of a remote inference job.
        You can pass either the job uuid or the results uuid as a parameter.
        If you pass both, the job uuid will be prioritized.

        :param job_uuid: The UUID of the EDSL job.
        :param results_uuid: The UUID of the results associated with the EDSL job.

        >>> coop.remote_inference_get("9f8484ee-b407-40e4-9652-4133a7236c9c")
        {'job_uuid': '9f8484ee-b407-40e4-9652-4133a7236c9c', 'results_uuid': 'dd708234-31bf-4fe1-8747-6e232625e026', 'results_url': 'https://www.expectedparrot.com/content/dd708234-31bf-4fe1-8747-6e232625e026', 'latest_error_report_uuid': None, 'latest_error_report_url': None, 'status': 'completed', 'reason': None, 'credits_consumed': 0.35, 'version': '0.1.38.dev1'}
        """
        if job_uuid is None and results_uuid is None:
            raise ValueError("Either job_uuid or results_uuid must be provided.")
        elif job_uuid is not None:
            params = {"job_uuid": job_uuid}
        else:
            params = {"results_uuid": results_uuid}

        response = self._send_server_request(
            uri="api/v0/remote-inference",
            method="GET",
            params=params,
        )
        self._resolve_server_response(response)
        data = response.json()

        results_uuid = data.get("results_uuid")
        latest_error_report_uuid = data.get("latest_error_report_uuid")

        if results_uuid is None:
            results_url = None
        else:
            results_url = f"{self.url}/content/{results_uuid}"

        if latest_error_report_uuid is None:
            latest_error_report_url = None
        else:
            latest_error_report_url = (
                f"{self.url}/home/remote-inference/error/{latest_error_report_uuid}"
            )

        return RemoteInferenceResponse(
            **{
                "job_uuid": data.get("job_uuid"),
                "results_uuid": results_uuid,
                "results_url": results_url,
                "latest_error_report_uuid": latest_error_report_uuid,
                "latest_error_report_url": latest_error_report_url,
                "status": data.get("status"),
                "reason": data.get("reason"),
                "credits_consumed": data.get("price"),
                "version": data.get("version"),
            }
        )

    def get_running_jobs(self) -> list[str]:
        """
        Get a list of currently running job IDs.

        Returns:
            list[str]: List of running job UUIDs
        """
        response = self._send_server_request(uri="jobs/status", method="GET")
        self._resolve_server_response(response)
        return response.json().get("running_jobs", [])

    def remote_inference_cost(
        self, input: Union[Jobs, Survey], iterations: int = 1
    ) -> int:
        """
        Get the cost of a remote inference job.

        :param input: The EDSL job to send to the server.

        >>> job = Jobs.example()
        >>> coop.remote_inference_cost(input=job)
        {'credits': 0.77, 'usd': 0.0076950000000000005}
        """
        if isinstance(input, Jobs):
            job = input
        elif isinstance(input, Survey):
            job = Jobs(survey=input)
        else:
            raise TypeError("Input must be either a Job or a Survey.")

        response = self._send_server_request(
            uri="api/v0/remote-inference/cost",
            method="POST",
            payload={
                "json_string": json.dumps(
                    job.to_dict(),
                    default=self._json_handle_none,
                ),
                "iterations": iterations,
            },
        )
        self._resolve_server_response(response)
        response_json = response.json()
        return {
            "credits": response_json.get("cost_in_credits"),
            "usd": response_json.get("cost_in_usd"),
        }

    ################
    # PROJECTS
    ################
    def create_project(
        self,
        survey: Survey,
        project_name: str = "Project",
        survey_description: Optional[str] = None,
        survey_alias: Optional[str] = None,
        survey_visibility: Optional[VisibilityType] = "unlisted",
    ):
        """
        Create a survey object on Coop, then create a project from the survey.
        """
        survey_details = self.create(
            object=survey,
            description=survey_description,
            alias=survey_alias,
            visibility=survey_visibility,
        )
        survey_uuid = survey_details.get("uuid")
        response = self._send_server_request(
            uri=f"api/v0/projects/create-from-survey",
            method="POST",
            payload={"project_name": project_name, "survey_uuid": str(survey_uuid)},
        )
        self._resolve_server_response(response)
        response_json = response.json()
        return {
            "name": response_json.get("project_name"),
            "uuid": response_json.get("uuid"),
            "admin_url": f"{self.url}/home/projects/{response_json.get('uuid')}",
            "respondent_url": f"{self.url}/respond/{response_json.get('uuid')}",
        }

    ################
    # DUNDER METHODS
    ################
    def __repr__(self):
        """Return a string representation of the client."""
        return f"Client(api_key='{self.api_key}', url='{self.url}')"

    ################
    # EXPERIMENTAL
    ################
    async def remote_async_execute_model_call(
        self, model_dict: dict, user_prompt: str, system_prompt: str
    ) -> dict:
        url = self.api_url + "/inference/"
        # print("Now using url: ", url)
        data = {
            "model_dict": model_dict,
            "user_prompt": user_prompt,
            "system_prompt": system_prompt,
        }
        # Use aiohttp to send a POST request asynchronously
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                response_data = await response.json()
        return response_data

    def web(
        self,
        survey: dict,
        platform: Literal[
            "google_forms", "lime_survey", "survey_monkey"
        ] = "lime_survey",
        email=None,
    ):
        url = f"{self.api_url}/api/v0/export_to_{platform}"
        if email:
            data = {"json_string": json.dumps({"survey": survey, "email": email})}
        else:
            data = {"json_string": json.dumps({"survey": survey, "email": ""})}

        response_json = requests.post(url, headers=self.headers, data=json.dumps(data))

        return response_json

    def fetch_prices(self) -> dict:
        """
        Fetch model prices from Coop. If the request fails, return an empty dict.
        """

        from edsl.coop.PriceFetcher import PriceFetcher

        from edsl.config import CONFIG

        if CONFIG.get("EDSL_FETCH_TOKEN_PRICES") == "True":
            price_fetcher = PriceFetcher()
            return price_fetcher.fetch_prices()
        elif CONFIG.get("EDSL_FETCH_TOKEN_PRICES") == "False":
            return {}
        else:
            raise ValueError(
                "Invalid EDSL_FETCH_TOKEN_PRICES value---should be 'True' or 'False'."
            )

    def fetch_models(self) -> ServiceToModelsMapping:
        """
        Fetch a dict of available models from Coop.

        Each key in the dict is an inference service, and each value is a list of models from that service.
        """
        response = self._send_server_request(uri="api/v0/models", method="GET")
        self._resolve_server_response(response)
        data = response.json()
        return ServiceToModelsMapping(data)

    def fetch_working_models(self) -> list[dict]:
        """
        Fetch a list of working models from Coop.

        Example output:

        [
            {
                "service": "openai",
                "model": "gpt-4o",
                "works_with_text": True,
                "works_with_images": True,
                "usd_per_1M_input_tokens": 2.5,
                "usd_per_1M_output_tokens": 10.0,
            }
        ]
        """
        response = self._send_server_request(uri="api/v0/working-models", method="GET")
        self._resolve_server_response(response)
        data = response.json()
        return [
            {
                "service": record.get("service"),
                "model": record.get("model"),
                "works_with_text": record.get("works_with_text"),
                "works_with_images": record.get("works_with_images"),
                "usd_per_1M_input_tokens": record.get("input_price_per_1M_tokens"),
                "usd_per_1M_output_tokens": record.get("output_price_per_1M_tokens"),
            }
            for record in data
        ]

    def fetch_rate_limit_config_vars(self) -> dict:
        """
        Fetch a dict of rate limit config vars from Coop.

        The dict keys are RPM and TPM variables like EDSL_SERVICE_RPM_OPENAI.
        """
        response = self._send_server_request(
            uri="api/v0/config-vars",
            method="GET",
        )
        self._resolve_server_response(response)
        data = response.json()
        return data

    def _display_login_url(
        self, edsl_auth_token: str, link_description: Optional[str] = None
    ):
        """
        Uses rich.print to display a login URL.

        - We need this function because URL detection with print() does not work alongside animations in VSCode.
        """
        from rich import print as rich_print
        from rich.console import Console

        console = Console()

        url = f"{CONFIG.EXPECTED_PARROT_URL}/login?edsl_auth_token={edsl_auth_token}"

        if console.is_terminal:
            # Running in a standard terminal, show the full URL
            if link_description:
                rich_print("{link_description}\n[#38bdf8][link={url}]{url}[/link][/#38bdf8]")
            else:
                rich_print(f"[#38bdf8][link={url}]{url}[/link][/#38bdf8]")
        else:
            # Running in an interactive environment (e.g., Jupyter Notebook), hide the URL
            if link_description:
                rich_print(f"{link_description}\n[#38bdf8][link={url}][underline]Log in and automatically store key[/underline][/link][/#38bdf8]")
            else:
                rich_print(f"[#38bdf8][link={url}][underline]Log in and automatically store key[/underline][/link][/#38bdf8]")





    def _get_api_key(self, edsl_auth_token: str):
        """
        Given an EDSL auth token, find the corresponding user's API key.
        """

        response = self._send_server_request(
            uri="api/v0/get-api-key",
            method="POST",
            payload={
                "edsl_auth_token": edsl_auth_token,
            },
        )
        data = response.json()
        api_key = data.get("api_key")
        return api_key

    def login(self):
        """
        Starts the EDSL auth token login flow.
        """
        import secrets
        from dotenv import load_dotenv
        from edsl.utilities.utilities import write_api_key_to_env

        edsl_auth_token = secrets.token_urlsafe(16)

        self._display_login_url(
            edsl_auth_token=edsl_auth_token,
            link_description="\n🔗 Use the link below to log in to Expected Parrot so we can automatically update your API key.",
        )
        api_key = self._poll_for_api_key(edsl_auth_token)

        if api_key is None:
            raise Exception("Timed out waiting for login. Please try again.")

        path_to_env = write_api_key_to_env(api_key)
        print("\n✨ API key retrieved and written to .env file at the following path:")
        print(f"    {path_to_env}")

        # Add API key to environment
        load_dotenv()


def main():
    """
    A simple example for the coop client
    """
    from uuid import uuid4
    from edsl import (
        Agent,
        AgentList,
        Cache,
        Notebook,
        QuestionFreeText,
        QuestionMultipleChoice,
        Results,
        Scenario,
        ScenarioList,
        Survey,
    )
    from edsl.coop import Coop
    from edsl.data.CacheEntry import CacheEntry
    from edsl.jobs import Jobs

    # init & basics
    API_KEY = "b"
    coop = Coop(api_key=API_KEY)
    coop
    coop.edsl_settings

    ##############
    # A. A simple example
    ##############
    # .. create and manipulate an object through the Coop client
    response = coop.create(QuestionMultipleChoice.example())
    coop.get(uuid=response.get("uuid"))
    coop.get(uuid=response.get("uuid"), expected_object_type="question")
    coop.get(url=response.get("url"))
    coop.create(QuestionMultipleChoice.example())
    coop.get_all("question")
    coop.patch(uuid=response.get("uuid"), visibility="private")
    coop.patch(uuid=response.get("uuid"), description="hey")
    coop.patch(uuid=response.get("uuid"), value=QuestionFreeText.example())
    # coop.patch(uuid=response.get("uuid"), value=Survey.example()) - should throw error
    coop.get(uuid=response.get("uuid"))
    coop.delete(uuid=response.get("uuid"))

    # .. create and manipulate an object through the class
    response = QuestionMultipleChoice.example().push()
    QuestionMultipleChoice.pull(uuid=response.get("uuid"))
    QuestionMultipleChoice.pull(url=response.get("url"))
    QuestionMultipleChoice.patch(uuid=response.get("uuid"), visibility="private")
    QuestionMultipleChoice.patch(uuid=response.get("uuid"), description="hey")
    QuestionMultipleChoice.patch(
        uuid=response.get("uuid"), value=QuestionFreeText.example()
    )
    QuestionMultipleChoice.pull(response.get("uuid"))
    QuestionMultipleChoice.delete(response.get("uuid"))

    ##############
    # B. Examples with all objects
    ##############
    OBJECTS = [
        ("agent", Agent),
        ("agent_list", AgentList),
        ("cache", Cache),
        ("notebook", Notebook),
        ("question", QuestionMultipleChoice),
        ("results", Results),
        ("scenario", Scenario),
        ("scenario_list", ScenarioList),
        ("survey", Survey),
    ]
    for object_type, cls in OBJECTS:
        print(f"Testing {object_type} objects")
        # 1. Delete existing objects
        existing_objects = coop.get_all(object_type)
        for item in existing_objects:
            coop.delete(uuid=item.get("uuid"))
        # 2. Create new objects
        example = cls.example()
        response_1 = coop.create(example)
        response_2 = coop.create(cls.example(), visibility="private")
        response_3 = coop.create(cls.example(), visibility="public")
        response_4 = coop.create(
            cls.example(), visibility="unlisted", description="hey"
        )
        # 3. Retrieve all objects
        objects = coop.get_all(object_type)
        assert len(objects) == 4
        # 4. Try to retrieve an item that does not exist
        try:
            coop.get(uuid=uuid4())
        except Exception as e:
            print(e)
        # 5. Try to retrieve all test objects by their uuids
        for response in [response_1, response_2, response_3, response_4]:
            coop.get(uuid=response.get("uuid"))
        # 6. Change visibility of all objects
        for item in objects:
            coop.patch(uuid=item.get("uuid"), visibility="private")
        # 6. Change description of all objects
        for item in objects:
            coop.patch(uuid=item.get("uuid"), description="hey")
        # 7. Delete all objects
        for item in objects:
            coop.delete(uuid=item.get("uuid"))
        assert len(coop.get_all(object_type)) == 0

    ##############
    # C. Remote Cache
    ##############
    # clear
    coop.remote_cache_clear()
    assert coop.remote_cache_get() == []
    # create one remote cache entry
    cache_entry = CacheEntry.example()
    cache_entry.to_dict()
    coop.remote_cache_create(cache_entry)
    # create many remote cache entries
    cache_entries = [CacheEntry.example(randomize=True) for _ in range(10)]
    coop.remote_cache_create_many(cache_entries)
    # get all remote cache entries
    coop.remote_cache_get()
    coop.remote_cache_get(exclude_keys=[])
    coop.remote_cache_get(exclude_keys=["a"])
    exclude_keys = [cache_entry.key for cache_entry in cache_entries]
    coop.remote_cache_get(exclude_keys)
    # clear
    coop.remote_cache_clear()
    coop.remote_cache_get()

    ##############
    # D. Remote Inference
    ##############
    job = Jobs.example()
    coop.remote_inference_cost(job)
    job_coop_object = coop.remote_inference_create(job)
    job_coop_results = coop.remote_inference_get(job_coop_object.get("uuid"))
    coop.get(uuid=job_coop_results.get("results_uuid"))
