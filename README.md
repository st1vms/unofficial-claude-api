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
