import os
import re
import json
import uuid
import shutil
import platform
import requests
import screeninfo
import mimetypes
import selenium
from time import time
from datetime import datetime
from tzlocal import get_localzone
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from dataclasses import dataclass

# Selenium module


def __cleanup_resources():
    if platform.system() == "Windows":
        folder_path = os.path.join(os.environ["LOCALAPPDATA"], "Temp")
    elif platform.system() == "Linux":
        folder_path = "/tmp"
    else:
        return

    for filename in os.listdir(folder_path):
        full_path = os.path.join(folder_path, filename)
        if os.path.isdir(full_path):
            for dirPrefix in ["tmp", "rust_mozpr"]:
                if filename.startswith(dirPrefix):
                    shutil.rmtree(full_path)
                    break


def __get_firefox_options(
    firefox_profile: str = "", headless: bool = False, private_mode: bool = False
) -> selenium.webdriver.firefox.options.Options:
    """Returns chrome options instance with given configuration set"""
    options = FirefoxOptions()
    options.profile = (
        __get_default_firefox_profile() if not firefox_profile else firefox_profile
    )

    if headless:
        monitor = screeninfo.get_monitors()[0]
        options.add_argument("--headless")
        options.add_argument(f"--window-size={monitor.width},{monitor.height}")
        options.add_argument("--start-maximized")
        options.set_preference("media.volume_scale", "0.0")

        # Opt
        options.set_preference("browser.cache.disk.enable", False)
        options.set_preference("browser.cache.memory.enable", False)
        options.set_preference("browser.cache.offline.enable", False)
        options.set_preference("network.http.use-cache", False)

    if private_mode:
        options.set_preference(
            "browser.privatebrowsing.autostart", True
        )  # Start in private mode

    return options


def __get_firefox_webdriver(
    *args, use_selwire: bool = False, **kwargs
) -> selenium.webdriver:
    """Constructor wrapper for Firefox webdriver"""

    if platform.system() == "Windows":
        # Check if firefox is in PATH
        DEFAULT_WINDWOS_FIREFOX_PATH = "C:\\Program Files\\Mozilla Firefox"
        if (
            not shutil.which("firefox")
            and os.environ["PATH"].find(DEFAULT_WINDWOS_FIREFOX_PATH) == -1
        ):
            os.environ["PATH"] += f";{DEFAULT_WINDWOS_FIREFOX_PATH}"

    if use_selwire:
        from seleniumwire import webdriver

        return webdriver.Firefox(*args, **kwargs)
    return selenium.webdriver.Firefox(*args, **kwargs)


def __linux_default_firefox_profile_path() -> str:
    profile_path = os.path.expanduser("~/.mozilla/firefox")

    if not os.path.exists(profile_path):
        raise RuntimeError(f"\nUnable to retrieve {profile_path} directory")

    for entry in os.listdir(profile_path):
        if entry.endswith(".default-release"):
            return os.path.join(profile_path, entry)
    return None


def __win_default_firefox_profile_path() -> str:
    profile_path = os.path.join(os.getenv("APPDATA"), "Mozilla\Firefox\Profiles")
    for entry in os.listdir(profile_path):
        if entry.endswith(".default-release"):
            return os.path.join(profile_path, entry)
    return None


def __get_default_firefox_profile() -> str:
    if platform.system() == "Windows":
        return __win_default_firefox_profile_path()
    elif platform.system() == "Linux":
        return __linux_default_firefox_profile_path()
    return ""


# Claude client module


@dataclass(frozen=True)
class SessionData:
    """
    This session class will be passed to ClaudeAPIClient instance,
    it can be auto generated using a working login in Firefox,
    and by having geckodriver installed, calling get_session_data()
    will use the default firefox profile to fill this structure.
    """

    cookie: str
    """
    The entire Cookie header string value
    """
    user_agent: str
    """
    Browser User agent
    """


def get_session_data(profile: str = "", quiet: bool = False) -> SessionData | None:
    """
    Retrieve Claude session data using existing Firefox profile.
    This function requires geckodriver installed!
    The default Firefox profile will be used, if the profile argument was not overwrited.
    """

    __BASE_CHAT_URL = "https://claude.ai/chats"
    if not profile:
        profile = __get_default_firefox_profile()

    if not quiet:
        print(f"\nRetrieving {__BASE_CHAT_URL} session cookie from {profile}")

    __cleanup_resources()
    opts = __get_firefox_options(firefox_profile=profile, headless=True)
    driver = __get_firefox_webdriver(options=opts)
    try:
        driver.get(__BASE_CHAT_URL)
        user_agent = driver.execute_script("return navigator.userAgent")
        if not user_agent:
            raise RuntimeError("\nCannot retrieve UserAgent...")

        cookies = driver.get_cookies()

        cookie_string = "; ".join(
            [f"{cookie['name']}={cookie['value']}" for cookie in cookies]
        )
        return SessionData(cookie_string, user_agent)
    finally:
        driver.quit()
        __cleanup_resources()


class MessageRateLimitHit(Exception):
    def __init__(self, resetTimestamp: int, *args: object) -> None:
        super().__init__(*args)
        self.resetTimestamp: int = resetTimestamp
        self.resetDate: str = datetime.fromtimestamp(resetTimestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    @property
    def sleep_sec(self) -> int:
        """
        The amount of seconds to wait before reaching the resetTimestamp
        """
        return int(abs(time() - self.resetTimestamp)) + 1


class ClaudeAPIClient:
    __BASE_URL = "https://claude.ai"

    def __init__(self, session: SessionData) -> None:
        self.__session = session
        if (
            not self.__session
            or not self.__session.cookie
            or not self.__session.user_agent
        ):
            raise ValueError("Invalid SessionData argument!")

        self.organization_id = self.__get_organization_id()

        # Retrieve timezone string
        self.__timezone = get_localzone().key

    def __get_organization_id(self) -> str:
        url = f"{self.__BASE_URL}/api/organizations"

        headers = {
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Type": "application/json",
            "Referer": f"{self.__BASE_URL}/chats",
            "Cookie": self.__session.cookie,
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
        raise RuntimeError("Cannot retrieve Organization ID!")

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

    def __prepare_file_attachment(self, fpath: str) -> dict:
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
            return {}

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
            "Cookie": self.__session.cookie,
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
            "Cookie": self.__session.cookie,
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
        url = f"{self.__BASE_URL}/api/organizations/{self.organization_id}/chat_conversations"

        headers = {
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Type": "application/json",
            "Referer": f"{self.__BASE_URL}/chats",
            "Cookie": self.__session.cookie,
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
        Print JSON response from calling /api/organizations/{organization_id}/chat_conversations/{chat_id}
        """
        url = f"{self.__BASE_URL}/api/organizations/{self.organization_id}/chat_conversations/{chat_id}"

        headers = {
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": f"{self.__BASE_URL}/chats/{chat_id}",
            "Cookie": self.__session.cookie,
            "Content-Type": "application/json",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "User-Agent": self.__session.user_agent,
        }

        return requests.get(url, headers=headers).json()

    def send_message(
        self,
        chat_id: str,
        prompt: str,
        attachment_path: str = "",
        timeout: int = 240,
        quiet: bool = False,
    ) -> str | None:
        """
        Send message to chat_id using specified prompt, loading attachment if present.
        Returns answer string if successfull, None otherwise.

        For text files use send_text_message(), for any other file type, use this function instead
        """
        if attachment_path and (
            not os.path.exists(attachment_path) or not os.path.isfile(attachment_path)
        ):
            raise ValueError(f"\nInvalid attachment path -> {attachment_path}")

        attachment = []
        if attachment_path:
            attachment = [self.__prepare_file_attachment(attachment_path)]

        url = f"{self.__BASE_URL}/api/append_message"

        payload = json.dumps(
            {
                "attachments": attachment,
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
                raise MessageRateLimitHit(int(data["error"]["resets_at"]))
        elif not quiet:
            print(
                f"\nGot unexpected status code -> {response.status_code}\nResponse: {response.content.decode('utf-8')}"
            )
        return answer
