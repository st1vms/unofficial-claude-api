"""Client module"""

from os import path as ospath
from re import sub, search
from typing import TypeVar, Annotated
from dataclasses import dataclass
from ipaddress import IPv4Address
from json import dumps, loads
from uuid import uuid4
from mimetypes import guess_type
from zlib import decompress as zlib_decompress
from zlib import MAX_WBITS
from brotli import decompress as br_decompress
from tzlocal import get_localzone
from requests import post as requests_post
from curl_cffi.requests import get as http_get
from curl_cffi.requests import post as http_post
from curl_cffi.requests import delete as http_delete
from .session import SessionData
from .errors import ClaudeAPIError, MessageRateLimitError, OverloadError


@dataclass(frozen=True)
class SendMessageResponse:
    """
    Response class returned from `send_message`
    """

    answer: str
    """
    The response string, if None check the `status_code` and `raw_answer` fields for errors
    """
    status_code: int
    """
    Response status code integer
    """
    raw_answer: bytes
    """
    Raw response bytes returned from send_message POST request, useful for error inspections
    """


@dataclass
class ClaudeProxy:
    """Base class for Claude proxies"""

    proxy_ip: str = None
    proxy_port: int = None

    def __post_init__(self):
        if self.proxy_ip is None or self.proxy_port is None:
            raise ValueError("Both proxy_ip and proxy_port must be set")

        # Check if it is a valid port number
        if not 0 <= self.proxy_port <= 65535:
            raise ValueError(f"Invalid proxy port number: {self.proxy_port}")

        # Check if it is a valid ipv4 proxy
        IPv4Address(self.proxy_ip)


ClaudeProxyT = TypeVar("ClaudeProxyT", bound=Annotated[dataclass, ClaudeProxy])


@dataclass
class HTTPProxy(ClaudeProxy):
    """
    Dataclass holding http/s proxy informations:

    `ip` -> Proxy IP

    `port` -> Proxy port

    `use_ssl` -> Boolean flag to indicate if this proxy uses https schema

    NOTE: This proxy must not require user/passwd authentication!
    """

    use_ssl: bool = False


@dataclass
class SOCKSProxy(ClaudeProxy):
    """
    Dataclass holding SOCKS proxy informations:

    `ip` -> Proxy IP

    `port` -> Proxy port

    `version_num` -> integer flag indicating which SOCKS proxy version to use,
    defaults to 4.

    NOTE: This proxy must not require user/passwd authentication!
    """

    version_num: int = 4

    def __post_init__(self):
        super().__post_init__()
        if self.version_num not in {4, 5}:
            raise ValueError(
                f"Not a valid SOCKS version number, must be 4 or 5, got {self.version_num}"
            )


class ClaudeAPIClient:
    """Base client class to interact with claude

    Requires:

    - `session`: SessionData class holding session cookie and UserAgent.
    - `proxy` (Optional): HTTPProxy class holding the proxy IP:port configuration.
    - `timeout`(Optional): Timeout in seconds to wait for each request to complete.
    Defaults to 240 seconds.
    """

    __BASE_URL = "https://claude.ai"

    def __init__(
        self,
        session: SessionData,
        proxy: ClaudeProxyT = None,
        model_name: str = "claude-2.1",
        timeout: float = 240,
    ) -> None:
        """
        Constructs a `ClaudeAPIClient` instance using provided `SessionData`,
        automatically retrieving organization_id and local timezone.

        `proxy` argument is an optional `HTTPProxy` instance,
        holding proxy informations ( ip, port )

        Raises `ValueError` in case of failure

        """
        if model_name not in {"claude-2.0", "claude-2.1"}:
            raise ValueError(
                "model_name must be either one of 'claude-2.0' or 'claude-2.1' strings"
            )

        self.model_name: str = model_name
        self.timeout: float = timeout
        self.proxy: ClaudeProxyT = proxy
        self.__session: SessionData = session
        if (
            not self.__session
            or not self.__session.cookie
            or not self.__session.user_agent
        ):
            raise ValueError("Invalid SessionData argument!")

        if self.__session.organization_id is None:
            print("\nRetrieving organization ID...")
            self.__session.organization_id = self.__get_organization_id()

        # Retrieve timezone string
        self.timezone: str = get_localzone().key

    def __get_proxy(self) -> dict[str, str] | None:

        if self.proxy is None or not issubclass(self.proxy.__class__, ClaudeProxy):
            return None

        ip, port = self.proxy.proxy_ip, self.proxy.proxy_port

        if isinstance(self.proxy, HTTPProxy):
            # Return HTTP proxy
            return {
                "http": f"{'https' if self.proxy.use_ssl else 'http'}://{ip}:{port}",
                "https": f"{'https' if self.proxy.use_ssl else 'http'}://{ip}:{port}",
            }
        if isinstance(self.proxy, SOCKSProxy):
            # Return SOCKS proxy
            return {
                "http": f"socks{self.proxy.version_num}://{ip}:{port}",
                "https": f"socks{self.proxy.version_num}://{ip}:{port}",
            }

        return None

    def __get_organization_id(self) -> str:
        url = f"{self.__BASE_URL}/api/organizations"

        headers = {
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Cookie": self.__session.cookie,
            "Host": "claude.ai",
            "DNT": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__session.user_agent,
        }

        response = http_get(
            url,
            headers=headers,
            proxies=self.__get_proxy(),
            timeout=self.timeout,
            impersonate="chrome110",
        )
        if response.status_code == 200 and response.content:
            res = response.json()
            if res and "uuid" in res[0]:
                return res[0]["uuid"]
        raise RuntimeError(f"Cannot retrieve Organization ID!\n{response.text}")

    def __prepare_text_file_attachment(self, file_path: str) -> dict:
        file_name = ospath.basename(file_path)
        file_size = ospath.getsize(file_path)

        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            file_content = file.read()

        return {
            "extracted_content": file_content,
            "file_name": file_name,
            "file_size": f"{file_size}",
            "file_type": "text/plain",
        }

    def __get_content_type(self, fpath: str):
        extension = ospath.splitext(fpath)[1].lower()
        mime_type, _ = guess_type(f"file.{extension}")
        return mime_type or "application/octet-stream"

    def __prepare_file_attachment(self, fpath: str, chat_id: str) -> dict | None:
        content_type = self.__get_content_type(fpath)
        if content_type == "text/plain":
            return self.__prepare_text_file_attachment(fpath)

        url = f"{self.__BASE_URL}/api/convert_document"

        headers = {
            "Host": "claude.ai",
            "User-Agent": self.__session.user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": f"{self.__BASE_URL}/chat/{chat_id}",
            "Origin": self.__BASE_URL,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "Cookie": self.__session.cookie,
            "TE": "trailers",
        }

        with open(fpath, "rb") as fp:
            files = {
                "file": (ospath.basename(fpath), fp, content_type),
                "orgUuid": (None, self.__session.organization_id),
            }

            response = requests_post(
                url,
                headers=headers,
                files=files,
                timeout=self.timeout,
                proxies=self.__get_proxy(),
            )
            if response.status_code == 200:
                return response.json()
        print(
            f"\n[{response.status_code}] Unable to prepare file attachment -> {fpath}\n"
            f"\nReason: {response.text}\n\n"
        )
        return None

    def __check_file_attachments_paths(self, path_list: list[str]):
        __filesize_limit = 10485760  # 10 MB
        if not path_list:
            return

        if len(path_list) > 5:  # No more than 5 attachments
            raise ValueError("Cannot attach more than 5 files!")

        for path in path_list:
            # Check if file exists
            if not ospath.exists(path) or not ospath.isfile(path):
                raise ValueError(f"Attachment file does not exists -> {path}")

            # Check file size
            _size = ospath.getsize(path)
            if _size > __filesize_limit:
                raise ValueError(
                    f"Attachment file exceed file size limit by {_size-__filesize_limit}"
                    "out of 10MB -> {path}"
                )

    def create_chat(self) -> str | None:
        """
        Create new chat and return chat UUID string if successfull
        """
        url = (
            f"{self.__BASE_URL}/api/organizations/"
            f"{self.__session.organization_id}/chat_conversations"
        )

        new_uuid = str(uuid4())

        payload = dumps(
            {"name": "", "uuid": new_uuid}, indent=None, separators=(",", ":")
        )
        headers = {
            "Host": "claude.ai",
            "User-Agent": self.__session.user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/json",
            "Content-Length": f"{len(payload)}",
            "Referer": f"{self.__BASE_URL}/chats",
            "Origin": self.__BASE_URL,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "Cookie": self.__session.cookie,
            "TE": "trailers",
        }

        response = http_post(
            url,
            headers=headers,
            data=payload,
            proxies=self.__get_proxy(),
            timeout=self.timeout,
            impersonate="chrome110",
        )
        if response and response.status_code == 201:
            j = response.json()
            if j and "uuid" in j:
                return j["uuid"]
        return None

    def delete_chat(self, chat_id: str) -> bool:
        """
        Delete chat by its UUID string, returns True if successfull, False otherwise
        """
        url = (
            f"https://claude.ai/api/organizations/"
            f"{self.__session.organization_id}/chat_conversations/{chat_id}"
        )

        payload = f'"{chat_id}"'
        headers = {
            "Host": "claude.ai",
            "User-Agent": self.__session.user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/json",
            "Content-Length": f"{len(payload)}",
            "Referer": f"{self.__BASE_URL}/chat/{chat_id}",
            "Origin": self.__BASE_URL,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "Cookie": self.__session.cookie,
            "TE": "trailers",
        }

        response = http_delete(
            url,
            headers=headers,
            data=payload,
            proxies=self.__get_proxy(),
            timeout=self.timeout,
            impersonate="chrome110",
        )
        return response.status_code == 204

    def get_all_chat_ids(self) -> list[str]:
        """
        Retrieve a list with all created chat UUID strings, empty list if no chat is found.
        """
        url = (
            f"{self.__BASE_URL}/api/organizations/"
            f"{self.__session.organization_id}/chat_conversations"
        )

        headers = {
            "Host": "claude.ai",
            "User-Agent": self.__session.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Connection": "keep-alive",
            "Cookie": self.__session.cookie,
        }

        response = http_get(
            url,
            headers=headers,
            proxies=self.__get_proxy(),
            timeout=self.timeout,
            impersonate="chrome110",
        )
        if response.status_code == 200:
            j = response.json()
            return [chat["uuid"] for chat in j if "uuid" in chat]

        return []

    def get_chat_data(self, chat_id: str) -> dict:
        """
        Print JSON response from calling
        `/api/organizations/{organization_id}/chat_conversations/{chat_id}`
        """

        url = (
            f"{self.__BASE_URL}/api/organizations/"
            f"{self.__session.organization_id}/chat_conversations/{chat_id}"
        )

        headers = {
            "Host": "claude.ai",
            "User-Agent": self.__session.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Connection": "keep-alive",
            "Cookie": self.__session.cookie,
        }

        return http_get(
            url,
            headers=headers,
            proxies=self.__get_proxy(),
            timeout=self.timeout,
            impersonate="chrome110",
        ).json()

    def delete_all_chats(self) -> bool:
        """
        Deleted all chats associated with this session

        Returns True on success, False in case at least one chat was not deleted.
        """
        chats = self.get_all_chat_ids()
        return all([self.delete_chat(chat_id) for chat_id in chats])

    def __decode_response(self, buffer: bytes, encoding_header: str) -> bytes:
        """Return decoded response bytes"""

        if encoding_header == "gzip":
            # Content is gzip-encoded, decode it using zlib
            return zlib_decompress(buffer, MAX_WBITS | 16)
        elif encoding_header == "deflate":
            # Content is deflate-encoded, decode it using zlib
            return zlib_decompress(buffer, -MAX_WBITS)
        elif encoding_header == "br":
            # Content is Brotli-encoded, decode it using the brotli library
            return br_decompress(buffer)

        # Content is either not encoded or with a non supported encoding.
        return buffer

    def __parse_send_message_response(self, data_bytes: bytes) -> str | None:
        """Return a tuple consisting of (answer, error_string)"""

        # Parse json string lines from raw response string
        res = data_bytes.decode("utf-8").strip()

        # Removes extre newline separators
        res = sub("\n+", "\n", res).strip()

        # Get json data lines
        data_lines = []
        for r in res.splitlines():
            s = search(r"\{.*\}", r)
            if s is not None:
                data_lines.append(s.group(0))

        if not data_lines:
            # Unable to parse data
            return None

        completions = []

        for line in data_lines:
            data_dict: dict = loads(line)

            if "error" in data_dict:
                if "resets_at" in data_dict["error"]:
                    # Wrap the rate limit into exception
                    raise MessageRateLimitError(int(data_dict["error"]["resets_at"]))

                # Get the error type and message
                error_d = data_dict.get("error", {})
                error_type = error_d.get("type", "")
                error_msg = error_d.get("message", "")

                if "overloaded" in error_type:
                    # Wrap Overload error
                    raise OverloadError(
                        f"Claude returned error ({error_msg}): "
                        "Wait some time for before subsequent requests!"
                    )
                # Raise generic error
                raise ClaudeAPIError(f"Unkown Claude error ({error_type}): {error_msg}")

            # Add the completion string to the answer
            if "completion" in data_dict:
                completions.append(data_dict["completion"])

        # Return all of the completion strings joined togheter
        return "".join(completions).strip()

    def send_message(
        self,
        chat_id: str,
        prompt: str,
        attachment_paths: list[str] = None,
    ) -> SendMessageResponse:
        """
        Send message to `chat_id` using specified `prompt` string.

        You can omitt or provide an attachments path list using `attachment_paths`

        Returns a `SendMessageResponse` instance, having:
        - `answer` string field,
        - `status_code` integer field,
        - `error_response` string field, which will be None in case of no errors.
        """

        self.__check_file_attachments_paths(attachment_paths)

        attachments = []
        if attachment_paths:
            attachments = [
                a
                for a in [
                    self.__prepare_file_attachment(path, chat_id)
                    for path in attachment_paths
                ]
                if a
            ]

        url = (
            f"{self.__BASE_URL}/api/organizations/"
            + f"{self.__session.organization_id}/chat_conversations/"
            + f"{chat_id}/completion"
        )

        payload = dumps(
            {
                "attachments": attachments,
                "files": [],
                "model": self.model_name,
                "prompt": prompt,
                "timezone": self.timezone,
            },
            indent=None,
            separators=(",", ":"),
        )

        headers = {
            "Host": "claude.ai",
            "User-Agent": self.__session.user_agent,
            "Accept": "text/event-stream, text/event-stream",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/json",
            "Content-Length": f"{len(payload)}",
            "Referer": f"{self.__BASE_URL}/chat/{chat_id}",
            "Origin": self.__BASE_URL,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "Cookie": self.__session.cookie,
            "TE": "trailers",
        }

        response = http_post(
            url,
            headers=headers,
            data=payload,
            timeout=self.timeout,
            proxies=self.__get_proxy(),
            impersonate="chrome110",
        )

        enc = None
        if "Content-Encoding" in response.headers:
            enc = response.headers["Content-Encoding"]

        # Decrypt encoded response
        dec = self.__decode_response(response.content, enc)

        return SendMessageResponse(
            self.__parse_send_message_response(dec),
            response.status_code,
            response.content,
        )
