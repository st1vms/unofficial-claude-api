"""Client module"""

from os import path as ospath
from re import sub
from typing import Optional
from dataclasses import dataclass
from json import dumps, loads, JSONDecodeError
from uuid import uuid4
from time import time
from datetime import datetime
from mimetypes import guess_type
from zlib import decompress as zlib_decompress
from zlib import MAX_WBITS
from requests import Request, Session
from curl_cffi.requests import Response
from curl_cffi.requests import get as http_get
from curl_cffi.requests import post as http_post
from curl_cffi.requests import delete as http_delete
from tzlocal import get_localzone
from brotli import decompress as br_decompress
from .session import SessionData


@dataclass(frozen=True)
class SendMessageResponse:
    """
    Response class returned from `send_message`
    """

    answer: str
    """
    The response string or None, in case of errors check the `status_code` and `error_response` fields
    """
    status_code: int
    """
    Response status code integer
    """
    error_response: str
    """
    Error response string, useful for inspections
    """


class MessageRateLimitError(Exception):
    """Exception for MessageRateLimit
    Will hold three variables:

    - `reset_timestamp`: Timestamp in seconds at which the rate limit expires.

    - `reset_date`: Formatted datetime string (%Y-%m-%d %H:%M:%S) at which the rate limit expires.

    - `sleep_sec`: Amount of seconds to wait before reaching the expiration timestamp
    (Auto calculated based on reset_timestamp)"""

    def __init__(self, reset_timestamp: int, *args: object) -> None:
        super().__init__(*args)
        self.reset_timestamp: int = reset_timestamp
        """
        The timestamp in seconds when the message rate limit will be reset
        """
        self.reset_date: str = datetime.fromtimestamp(reset_timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        """
        Formatted datetime string of expiration timestamp in the format %Y-%m-%d %H:%M:%S
        """

    @property
    def sleep_sec(self) -> int:
        """
        The amount of seconds to wait before reaching the reset_timestamp
        """
        return int(abs(time() - self.reset_timestamp)) + 1


@dataclass
class HTTPProxy:
    """
    Dataclass holding http/s proxy informations:

    `ip` -> Proxy IP

    `port` -> Proxy port

    `use_ssl` -> Boolean flag to indicate if proxy uses https schema

    NOTE: This proxy must not require user/passwd authentication!
    """

    proxy_ip: str
    proxy_port: int
    use_ssl: Optional[bool] = False


class ClaudeAPIClient:
    """Base client class to interact with claude

    Requires:

    - `session`: SessionData class holding session cookie and UserAgent.
    - `proxy` (Optional): HTTPProxy class holding the proxy IP:port configuration.
    - `timeout`(Optional): Timeout in seconds to wait for each request to complete. Defaults to 240 seconds.
    """

    __BASE_URL = "https://claude.ai"

    def __init__(
        self, session: SessionData, proxy: HTTPProxy = None, timeout: float = 240
    ) -> None:
        """
        Constructs a `ClaudeAPIClient` instance using provided `SessionData`,
        automatically retrieving organization_id and local timezone.

        `proxy` argument is an optional `HTTPProxy` instance,
        holding proxy informations ( ip, port )

        Raises `ValueError` in case of failure

        """
        self.timeout = timeout
        self.proxy = proxy
        self.__session = session
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
        self.timezone = get_localzone().key

    def __get_proxy(self) -> dict[str, str] | None:
        if not self.proxy or not self.proxy.proxy_ip or not self.proxy.proxy_port:
            return None

        return {
            "http": f"{'https' if self.proxy.use_ssl else 'http'}://{self.proxy.proxy_ip}:{self.proxy.proxy_port}",
            "https": f"{'https' if self.proxy.use_ssl else 'http'}://{self.proxy.proxy_ip}:{self.proxy.proxy_port}",
        }

    def __decode_response(
        self, response: Response, return_json: bool = False
    ) -> str | bytes:
        """Decompress encoded response

        Returns `Response.json()` if `return_json==True`,
        `Response.content` otherwise.
        """

        if return_json:
            try:
                return response.json()
            except (JSONDecodeError, TypeError):
                pass

        if "Content-Encoding" not in response.headers:
            return response.content

        try:
            return response.content
        except (UnicodeDecodeError, UnicodeError):
            pass

        if response.headers["Content-Encoding"] == "gzip":
            # Content is gzip-encoded, decode it using zlib
            res = zlib_decompress(response.content, MAX_WBITS | 16)
            return loads(res.decode("utf-8")) if return_json else res
        elif response.headers["Content-Encoding"] == "deflate":
            # Content is deflate-encoded, decode it using zlib
            res = zlib_decompress(response.content, -MAX_WBITS)
            return loads(res.decode("utf-8")) if return_json else res
        elif response.headers["Content-Encoding"] == "br":
            # Content is Brotli-encoded, decode it using the brotli library
            res = br_decompress(response.content)
            return loads(res.decode("utf-8")) if return_json else res
        # Content is either not encoded or with a non supported encoding.
        return response.content if not return_json else response.json()

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
            res = self.__decode_response(response, return_json=True)
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

    def __prepare_file_attachment(self, fpath: str) -> dict | None:
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

        with open(fpath, "rb") as fp:
            files = {
                "file": (ospath.basename(fpath), fp, content_type),
                "orgUuid": (None, self.__session.organization_id),
            }

            s = Session()
            req = s.prepare_request(Request("POST", url, headers=headers, files=files))
            response = s.send(
                req,
                proxies=self.__get_proxy(),
                timeout=self.timeout,
            )
            if response.status_code == 200:
                return response.json()
        print(
            f"\n[{response.status_code}] Unable to prepare file attachment -> {fpath}\n"
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
                    f"Attachment file exceed file size limit by {_size-__filesize_limit} out of 10MB -> {path}"
                )

    def create_chat(self) -> str | None:
        """
        Create new chat and return chat UUID string if successfull
        """
        url = f"{self.__BASE_URL}/api/organizations/{self.__session.organization_id}/chat_conversations"
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
        url = f"https://claude.ai/api/organizations/{self.__session.organization_id}/chat_conversations/{chat_id}"

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
        url = f"{self.__BASE_URL}/api/organizations/{self.__session.organization_id}/chat_conversations"

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
        Print JSON response from calling `/api/organizations/{organization_id}/chat_conversations/{chat_id}`
        """
        url = f"{self.__BASE_URL}/api/organizations/{self.__session.organization_id}/chat_conversations/{chat_id}"

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
                    self.__prepare_file_attachment(path)
                    for path in attachment_paths
                ]
                if a
            ]

        url = f"{self.__BASE_URL}/api/append_message"

        payload = dumps(
            {
                "completion": {
                    "prompt": prompt,
                    "timezone": self.timezone,
                    "model": "claude-2.1",
                },
                "organization_uuid": self.__session.organization_id,
                "conversation_uuid": chat_id,
                "text": prompt,
                "attachments": attachments,
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

        if response.status_code == 200 and response.content:
            # Parse response as UTF-8 text
            res = self.__decode_response(response)
            decoded_data = res.decode("utf-8")
            decoded_data = sub("\n+", "\n", decoded_data).strip()
            data_strings = decoded_data.split("\n")
            completions = []
            for data_string in data_strings:
                json_str = data_string.lstrip("data:").lstrip().rstrip()
                # Json conversion
                data = loads(json_str)
                if data and "completion" in data:
                    completions.append(data["completion"])
            return SendMessageResponse("".join(completions).lstrip().rstrip(), 200, {})
        elif response.status_code == 429 and response.content:
            # Rate limit error
            res = self.__decode_response(response)
            data = loads(res.decode("utf-8"))
            if data and "error" in data and "resets_at" in data["error"]:
                # Wrap the rate limit into exception
                raise MessageRateLimitError(int(data["error"]["resets_at"]))

        return SendMessageResponse(None, response.status_code, response.text)
