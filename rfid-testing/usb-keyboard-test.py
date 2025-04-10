import asyncio
import time
from sshkeyboard import listen_keyboard

def press(key):
    print(f"'{key}' pressed")
    time.sleep(3)
    print(f"'{key}' press slept")

def release(key):
    return
    print(f"'{key}' relased")
    time.sleep(3)
    print(f"'{key}' release slept")

print("Now listening...")

listen_keyboard(
    on_press=press,
    on_release=release,
    sequential=True,
    debug=True
)

print("Done listening")
