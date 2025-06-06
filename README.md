
# unofficial-claude-api

## Table of Contents

- [Installation](#how-to-install)
- [Requirements](#requirements)
- [Example Usage](#example-usage)
- [Advanced Usage](#advanced-usage)
  - [Retrieving Chat History](#retrieving-chat-history)
  - [Manual Session Data (Faster Loading)](#manual-session-data)
  - [Using Proxies](#using-proxies)
  - [Customization](#customization)
    - [Changing model version](#changing-claude-model)
    - [Changing Organization](#changing-organization)
- [How to Contribute](#how-to-contribute)
- [Donating](#donating)

## What is this?

This unofficial Python API provides access to the conversational capabilities of Anthropic's Claude AI through a simple chat messaging interface.

While not officially supported by Anthropic, this library can enable interesting conversational applications.

It allows for:

- Creating chat sessions with Claude and getting chat IDs.
- Sending messages to Claude containing up to 5 attachment files (txt, pdf, csv, png, jpeg, etc...) 10 MB each, images are also supported!
- Retrieving chat message history, accessing specific chat conversations.
- Deleting old chats when they are no longer needed.
- Sending requests through proxies.

### Some of the key things you can do with Claude through this API

- Ask questions about a wide variety of topics. Claude can chat about current events, pop culture, sports,
and more.

- Get helpful explanations on complex topics. Ask Claude to explain concepts and ideas in simple terms.

- Generate summaries from long text or documents. Just give the filepath as an attachment to Claude and get back a concise summary.

- Receive thoughtful responses to open-ended prompts and ideas. Claude can brainstorm ideas, expand on concepts, and have philosophical discussions.

- Send images and let Claude analyze them for you.

## How to install

```shell
pip install unofficial-claude-api
```

## Uninstallation

```shell
pip uninstall unofficial-claude-api
```

## Requirements

### These requirements are needed to auto retrieve a SessionData object using selenium

- Python >= 3.10
- Firefox installed, and with at least one profile logged into [Claude](https://claude.ai/chats).
- [geckodriver](https://github.com/mozilla/geckodriver/releases) installed inside a folder registered in PATH environment variable.

***( scrolling through this README you'll find also a manual alternative )***

## Example Usage

```python
from sys import exit as sys_exit
from claude_api.client import (
    ClaudeAPIClient,
    SendMessageResponse,
)
from claude_api.session import SessionData, get_session_data
from claude_api.errors import ClaudeAPIError, MessageRateLimitError, OverloadError

# Wildcard import will also work the same as above
# from claude_api import *

# List of attachments filepaths, up to 5, max 10 MB each
FILEPATH_LIST = [] #["test.txt"]

# Text message to send
PROMPT = "Hello!"

# This function will automatically retrieve a SessionData instance using selenium
# It will auto gather cookie session, user agent and organization ID.
# Omitting profile argument will use default Firefox profile
session: SessionData = get_session_data()

# Initialize a client instance using a session
# Optionally change the requests timeout parameter to best fit your needs...default to 240 seconds.
client = ClaudeAPIClient(session, timeout=240)

# Create a new chat and cache the chat_id
chat_id = client.create_chat()
if not chat_id:
    # This will not throw MessageRateLimitError
    # But it still means that account has no more messages left.
    print("\nMessage limit hit, cannot create chat...")
    sys_exit(-1)

try:
    # Used for sending message with or without attachments
    # Returns a SendMessageResponse instance
    res: SendMessageResponse = client.send_message(
        chat_id, PROMPT, attachment_paths=FILEPATH_LIST
    )
    # Inspect answer
    if res.answer:
        print(res.answer)
    else:
        # Inspect response status code and raw answer bytes
        print(f"\nError code {res.status_code}, raw_answer: {res.raw_answer}")
except ClaudeAPIError as e:
    # Identify the error
    if isinstance(e, MessageRateLimitError):
        # The exception will hold these informations about the rate limit:
        print(f"\nMessage limit hit, resets at {e.reset_date}")
        print(f"\n{e.sleep_sec} seconds left until -> {e.reset_timestamp}")
    elif isinstance(e, OverloadError):
        print(f"\nOverloaded error: {e}")
    else:
        print(f"\nGot unknown Claude error: {e}")
finally:
    # Perform chat deletion for cleanup
    client.delete_chat(chat_id)

## (OPTIONAL) 

# Get a list of all chats ids
all_chat_ids = client.get_all_chat_ids()
# Delete all chats
for chat in all_chat_ids:
    client.delete_chat(chat)

# Or by using a shortcut utility
# client.delete_all_chats()
```

## Advanced Usage

### Retrieving chat history

```python
# A convenience method to access a specific chat conversation is
chat_data = client.get_chat_data(chat_id)
```

`chat_data` will be the same json dictionary returned by calling
`/api/organizations/{organization_id}/chat_conversations/{chat_id}`

Here's an example of this json:

```json
{
    "uuid": "<ConversationUUID>",
    "name": "",
    "summary": "",
    "model": null,
    "created_at": "1997-12-25T13:33:33.959409+00:00",
    "updated_at": "1997-12-25T13:33:39.487561+00:00",
    "chat_messages": [
        {
            "uuid": "<MessageUUID>",
            "text": "Who is Bugs Bunny?",
            "sender": "human",
            "index": 0,
            "created_at": "1997-12-25T13:33:39.487561+00:00",
            "updated_at": "1997-12-25T13:33:40.959409+00:00",
            "edited_at": null,
            "chat_feedback": null,
            "attachments": []
        },
        {
            "uuid": "<MessageUUID>",
            "text": "<Claude response's text>",
            "sender": "assistant",
            "index": 1,
            "created_at": "1997-12-25T13:33:40.959409+00:00",
            "updated_at": "1997-12-25T13:33:42.487561+00:00",
            "edited_at": null,
            "chat_feedback": null,
            "attachments": []
        }
    ]
}
```

__________

### Manual Session Data

If for whatever reason you'd like to avoid auto session gathering using selenium,
you just need to manually create a `SessionData` class for `ClaudeAPIClient` constructor, like so...

```python
from claude_api.session import SessionData

cookie_header_value = "The entire Cookie header value string when you visit https://claude.ai/chats"
user_agent = "User agent to use, required"

# You can retrieve this string from /api/organizations endpoint
# If omitted or None it will be auto retrieved when instantiating ClaudeAPIClient
organization_id = "<org_uuid>"

session = SessionData(cookie_header_value, user_agent, organization_id)
```

__________

### Using Proxies

#### How to set HTTP/S proxies

If you'd like to set an HTTP proxy for all requests, follow this example:

```py
from claude_api.client import HTTPProxy, ClaudeAPIClient
from claude_api.session import SessionData

# Create HTTPProxy instance
http_proxy = HTTPProxy(
    "the.proxy.ip.addr",    # Proxy IP
    8080,                   # Proxy port
    "username",             # Proxy Username (optional)
    "password",             # Proxy Password (optional)
    use_ssl=False           # Set to True if proxy uses HTTPS schema
)

session = SessionData(...)

# Give the proxy instance to ClaudeAPIClient constructor, along with session data.
client = ClaudeAPIClient(session, proxy=http_proxy)
```

#### How to set SOCKS proxies

If you want to opt for SOCKS proxies instead, the procedure is the same, but you need to import the `SOCKSProxy` class instead, configuring it with the version number.

```py
from claude_api.client import SOCKSProxy, ClaudeAPIClient
from claude_api.session import SessionData

# Create SOCKSProxy instance
socks_proxy = SOCKSProxy(
    "the.proxy.ip.addr",    # Proxy IP
    8080,                   # Proxy port
    "username",             # Proxy Username (optional)
    "password",             # Proxy Password (optional)
    version_num=5           # Either 4 or 5, defaults to 4
)

session = SessionData(...)

# Give the proxy instance to ClaudeAPIClient constructor as usual
client = ClaudeAPIClient(session, proxy=socks_proxy)
```

__________

## Customization

### Changing Claude model

In case you'd like to change the model used, or you do have accounts that are unable to migrate to latest model, you can override the `model_name` string parameter of `ClaudeAPIClient` constructor like so:

```py
from claude_api.client import ClaudeAPIClient
from claude_api.session import SessionData

session = SessionData(...)

# Defaults to None (latest Claude model)
client = ClaudeAPIClient(session, model_name="claude-2.0")
```

You can retrieve the `model_name` strings from the [official API docs](https://docs.anthropic.com/claude/docs/models-overview#model-comparison)

__________

### Changing Organization

As reported in issue [#23](https://github.com/st1vms/unofficial-claude-api/issues/23)
if you're encountering 403 errors when using Selenium to auto retrieve a `SessionData` class and your account has multiple organizations,
you may want to override the default organization retrieved.

By default `get_session_data` retrieves the last organization from the result array found [here](https://claude.ai/api/organizations).
You can override the index to fetch by using parameter `organization_index`:

```py
from claude_api.session import get_session_data

# Defaults to -1 (last entry)
session = get_session_data(organization_index=-1)
```

## How to Contribute

Contributions are welcome, please follow these guidelines to contribute:

1. **Fork the repository** and create a new branch for your feature or fix.

2. **Make your changes**. Ensure the code is clean, well-documented, and consistent with the existing style.

3. **Test your changes** before submitting. Also include unit tests in your pull request where appropriate.

5. **Create a pull request** to the latest `dev-*` branch. Include a clear description of your changes.

### Notes
- Stick to the current architecture and avoid unnecessary dependencies.
- If the change involves significant refactoring or bug fixes, open an issue first to discuss it.
- Ensure any modified or new code is covered by tests with reproducible results.

All contributions must respect the licensing terms in the repository.

## Disclaimer

This repository provides an unofficial API for automating free accounts on [claude.ai](https://claude.ai/chats).
Please note that this API is not endorsed, supported, or maintained by Anthropic. Use it at your own discretion and risk. Anthropic may make changes to their official product or APIs at any time, which could affect the functionality of this unofficial API. We do not guarantee the accuracy, reliability, or security of the information and data retrieved using this API. By using this repository, you agree that the maintainers are not responsible for any damages, issues, or consequences that may arise from its usage. Always refer to Anthropic's official documentation and terms of use. This project is maintained independently by contributors who are not affiliated with Anthropic.

## Donations

A huge thank you in advance to anyone who wants to donate :)

[![Buy Me a Pizza](https://img.buymeacoffee.com/button-api/?text=1%20Pizza%20Margherita&emoji=🍕&slug=st1vms&button_colour=0fa913&font_colour=ffffff&font_family=Bree&outline_colour=ffffff&coffee_colour=FFDD00)](https://www.buymeacoffee.com/st1vms)
