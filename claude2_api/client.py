import os
import re
import json
import uuid
import requests
import mimetypes
from time import time
from datetime import datetime
from tzlocal import get_localzone
from dataclasses import dataclass
from .session import SessionData

# Claude client module


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
    error_response: dict
    """
    Error response json dictionary, useful for inspections
    """


class MessageRateLimitError(Exception):
    def __init__(self, resetTimestamp: int, *args: object) -> None:
        super().__init__(*args)
        self.resetTimestamp: int = resetTimestamp
        """
        The timestamp in seconds when the message rate limit will be reset
        """
        self.resetDate: str = datetime.fromtimestamp(resetTimestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        """
        Date formatted timestamp in the format %Y-%m-%d %H:%M:%S
        """

    @property
    def sleep_sec(self) -> int:
        """
        The amount of seconds to wait before reaching the resetTimestamp
        """
        return int(abs(time() - self.resetTimestamp)) + 1


class ClaudeAPIClient:
    __BASE_URL = "https://claude.ai"

    def __init__(self, session: SessionData) -> None:
        """
        Constructs a `ClaudeAPIClient` instance using provided `SessionData`,
        automatically retrieving organization_id and local timezone.

        Raises `ValueError` in case of failure
        """
        self.__session = session
        if (
            not self.__session
            or not self.__session.cookie
            or not self.__session.user_agent
        ):
            raise ValueError("Invalid SessionData argument!")

        self.session_key = self.__get_session_key_from_cookie()

        self.organization_id = self.__get_organization_id()

        # Retrieve timezone string
        self.__timezone = get_localzone().key

    def __get_session_key_from_cookie(self):
        cookies = self.__session.cookie.split("; ")
        for cookie in cookies:
            if "=" in cookie:
                name, value = cookie.split("=", maxsplit=1)
                if name == "sessionKey":
                    return f"{name}={value}"
        raise RuntimeError(
            "Cannot retrieve session cookie!\nCheck Claude login in Firefox profile..."
        )

    def __get_organization_id(self) -> str:
        url = f"{self.__BASE_URL}/api/organizations"

        headers = {
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Type": "application/json",
            "Referer": f"{self.__BASE_URL}/chats",
            "Cookie": self.session_key,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "User-Agent": self.__session.user_agent,
        }

        response = requests.get(url, headers=headers)
        if response.status_code == 200 and response.text:
            res = json.loads(response.text)
            if res and "uuid" in res[0]:
                return res[0]["uuid"]
        raise RuntimeError(f"Cannot retrieve Organization ID!\n{response.text}")

    def __prepare_text_file_attachment(self, file_path: str) -> dict:
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            file_content = file.read()

        return {
            "extracted_content": file_content,
            "file_name": file_name,
            "file_size": f"{file_size}",
            "file_type": "text/plain",
        }

    def __get_content_type(self, fpath: str):
        extension = os.path.splitext(fpath)[1].lower()
        mime_type, _ = mimetypes.guess_type(f"file.{extension}")
        return mime_type or "application/octet-stream"

    def __prepare_file_attachment(self, fpath: str) -> dict | None:
        content_type = self.__get_content_type(fpath)
        if content_type == "text/plain":
            return self.__prepare_text_file_attachment(fpath)

        url = f"{self.__BASE_URL}/api/convert_document"

        headers = {
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Length": f"{os.path.getsize(fpath)}",
            "Host": "claude.ai",
            "Origin": self.__BASE_URL,
            "Referer": f"{self.__BASE_URL}/chats",
            "Cookie": self.__session.cookie,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "TE": "trailers",
            "User-Agent": self.__session.user_agent,
        }

        with open(fpath, "rb") as fp:
            files = {
                "file": (os.path.basename(fpath), fp, content_type),
                "orgUuid": (None, self.organization_id),
            }

            response = requests.post(url, headers=headers, files=files)
            if response.status_code == 200:
                return response.json()
        print(
            f"\n[{response.status_code}] Unable to prepare file attachment -> {fpath}"
        )
        return None

    def __check_file_attachments_paths(self, path_list: list[str]):
        __FILESIZE_LIMIT = 20971520  # 20 MB
        if not path_list:
            return

        if len(path_list) > 5:  # No more than 5 attachments
            raise ValueError("Cannot attach more than 5 files!")

        for path in path_list:
            # Check if file exists
            if not os.path.exists(path) or not os.path.isfile(path):
                raise ValueError(f"Attachment file does not exists -> {path}")

            # Check file size
            _size = os.path.getsize(path)
            if _size > __FILESIZE_LIMIT:
                raise ValueError(
                    f"Attachment file exceed file size limit by {_size-__FILESIZE_LIMIT} out of 20MB -> {path}"
                )

    def create_chat(self) -> str | None:
        """
        Create new chat and return chat UUID string if successfull
        """
        url = f"{self.__BASE_URL}/api/organizations/{self.organization_id}/chat_conversations"
        new_uuid = str(uuid.uuid4())

        payload = json.dumps({"uuid": new_uuid, "name": ""})
        headers = {
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Type": "application/json",
            "Origin": self.__BASE_URL,
            "Referer": f"{self.__BASE_URL}/chats",
            "Cookie": self.session_key,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "TE": "trailers",
            "User-Agent": self.__session.user_agent,
        }

        response = requests.post(url, headers=headers, data=payload)
        if response and response.status_code == 201:
            j = response.json()
            if j and "uuid" in j:
                return j["uuid"]
        return None

    def delete_chat(self, chat_id: str) -> bool:
        """
        Delete chat by its UUID string, returns True if successfull, False otherwise
        """
        url = f"https://claude.ai/api/organizations/{self.organization_id}/chat_conversations/{chat_id}"

        payload = json.dumps(chat_id)
        headers = {
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Type": "application/json",
            "Content-Length": f"{len(payload)}",
            "Origin": self.__BASE_URL,
            "Referer": f"{self.__BASE_URL}/chats",
            "Cookie": self.session_key,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "TE": "trailers",
            "User-Agent": self.__session.user_agent,
        }

        response = requests.delete(url, headers=headers, data=payload)
        return response.status_code == 204

    def get_all_chat_ids(self) -> list[str]:
        """
        Retrieve a list with all created chat UUID strings, empty list if no chat is found.
        """
        url = f"{self.__BASE_URL}/api/organizations/{self.organization_id}/chat_conversations"

        headers = {
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Type": "application/json",
            "Referer": f"{self.__BASE_URL}/chats",
            "Cookie": self.session_key,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "User-Agent": self.__session.user_agent,
        }

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            j = response.json()
            return [chat["uuid"] for chat in j if "uuid" in chat]

        return []

    def get_chat_data(self, chat_id: str) -> dict:
        """
        Print JSON response from calling `/api/organizations/{organization_id}/chat_conversations/{chat_id}`
        """
        url = f"{self.__BASE_URL}/api/organizations/{self.organization_id}/chat_conversations/{chat_id}"

        headers = {
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": f"{self.__BASE_URL}/chats/{chat_id}",
            "Cookie": self.session_key,
            "Content-Type": "application/json",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "User-Agent": self.__session.user_agent,
        }

        return requests.get(url, headers=headers).json()

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
        timeout: int = 240,
    ) -> SendMessageResponse:
        """
        Send message to `chat_id` using specified `prompt` string.

        You can omitt or provide an attachments path list using `attachment_paths`

        Set a different request timeout using `timeout` argument

        Returns a `SendMessageResponse` instance, having:
        - `answer` string field,
        - `status_code` integer field,
        - `error_response` dictionary field, which will be filled in case of errors for inspections purposes.
        """

        self.__check_file_attachments_paths(attachment_paths)

        attachments = []
        if attachment_paths:
            attachments = [
                a
                for a in [
                    self.__prepare_file_attachment(path) for path in attachment_paths
                ]
                if a
            ]

        url = f"{self.__BASE_URL}/api/append_message"

        payload = json.dumps(
            {
                "attachments": attachments,
                "completion": {
                    "model": "claude-2",
                    "prompt": prompt,
                    "timezone": f"{self.__timezone}",
                },
                "conversation_uuid": chat_id,
                "organization_uuid": f"{self.organization_id}",
                "text": prompt,
            }
        )

        headers = {
            "Accept": "text/event-stream, text/event-stream",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/json",
            "Content-Length": f"{len(payload)}",
            "Origin": self.__BASE_URL,
            "Referer": f"{self.__BASE_URL}/chat/{chat_id}",
            "Cookie": self.__session.cookie,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "TE": "trailers",
            "User-Agent": self.__session.user_agent,
        }

        response = requests.post(url, headers=headers, data=payload, timeout=timeout)

        answer = None
        if response.status_code == 200 and response.content:
            decoded_data = response.content.decode("utf-8")
            decoded_data = re.sub("\n+", "\n", decoded_data).strip()
            data_strings = decoded_data.split("\n")
            completions = []
            for data_string in data_strings:
                json_str = data_string.lstrip("data:").lstrip().rstrip()
                data = json.loads(json_str)
                if data and "completion" in data:
                    completions.append(data["completion"])

            answer = "".join(completions).lstrip().rstrip()
        elif response.status_code == 429 and response.content:
            decoded_data = response.content.decode("utf-8")
            data = json.loads(decoded_data)
            if data and "error" in data and "resets_at" in data["error"]:
                raise MessageRateLimitError(int(data["error"]["resets_at"]))

        err = {}
        if not answer:
            try:
                err = json.loads(response.content.decode("utf-8"))
            except UnicodeDecodeError:
                try:
                    err = json.loads(response.content.decode("utf-8", errors='ignore'))
                except:
                    err = {}
        
        return SendMessageResponse(answer, response.status_code, err)
