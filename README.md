<a href="https://www.buymeacoffee.com/st1vms"><img src="https://img.buymeacoffee.com/button-api/?text=1 Pizza Margherita&emoji=🍕&slug=st1vms&button_colour=0fa913&font_colour=ffffff&font_family=Bree&outline_colour=ffffff&coffee_colour=FFDD00" width="200" height="50" style="max-width:100%;"/></a>

# unofficial-claude2-api

Claude2 unofficial API supporting direct HTTP chat creation/deletion/retrieval,
message attachments and auto session gathering using Firefox with geckodriver.

## How to install

```
pip install unofficial-claude2-api
```

## Uninstallation
```
pip uninstall unofficial-claude2-api
```

## Requirements
#### These requirements are needed to auto retrieve session cookie and UserAgent using selenium
 - Firefox installed, and with at least one profile logged into [Claude](https://claude.ai/chats).

 - [geckodriver](https://github.com/mozilla/geckodriver/releases) installed inside a folder registered in PATH environment variable.

_______

## Example Usage

```python
from claude2_api.client import (
    ClaudeAPIClient,
    get_session_data,
    MessageRateLimitHit,
)

FILEPATH = "test.txt"

# This function will automatically retrieve a SessionData instance using selenium
# Omitting profile argument will use default Firefox profile
data = get_session_data()

# Initialize a client instance using a session
client = ClaudeAPIClient(data)

# Create a new chat and cache the chat_id
chat_id = client.create_chat()
if not chat_id:
    # This will not throw MessageRateLimitHit
    # But it still means that account has no more messages left.
    print(f"\nMessage limit hit, cannot create chat...")
    quit()

try:
    # Used for sending message with or without attachment
    answer = client.send_message(
        chat_id, "Hello!", attachment_path=FILEPATH, timeout=240
    )
    # May return None, in that case, delay a bit and retry
    print(answer)
except MessageRateLimitHit as e:
    # The exception will hold these informations about the rate limit:
    print(f"\nMessage limit hit, resets at {e.resetDate}")
    print(f"\n{e.sleep_sec} seconds left until -> {e.resetTimestamp}")
    quit()
finally:
    # Perform chat deletion for cleanup
    client.delete_chat(chat_id)

# Get a list of all chats ids
all_chat_ids = client.get_all_chat_ids()
# Delete all chats
for chat in all_chat_ids:
    client.delete_chat(chat)
```

______

## TROUBLESHOOTING

This api will sometimes throw 403 error on `send_message`, when this happens it is recommeded to look for these things:
- Check if your IP location is allowed, should be in US/UK, other locations may work sporadically.

- Don't try to send the same prompt/file over and over again, instead wait for some time, and change input.

- For now the only way to know if 403/500 error happened, is to check if answer object is None.

## DISCLAIMER

This repository provides an unofficial API for automating free accounts on [claude.ai](https://claude.ai/chats).
Please note that this API is not endorsed, supported, or maintained by Anthropic. Use it at your own discretion and risk. Anthropic may make changes to their official product or APIs at any time, which could affect the functionality of this unofficial API. We do not guarantee the accuracy, reliability, or security of the information and data retrieved using this API. By using this repository, you agree that the maintainers are not responsible for any damages, issues, or consequences that may arise from its usage. Always refer to Anthropic's official documentation and terms of use. This project is maintained independently by contributors who are not affiliated with Anthropic.
