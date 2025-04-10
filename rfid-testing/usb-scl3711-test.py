import sys
import nfc
import time


print("Starting script")



def on_connect(tag):
    print(f"Tag found with ID: {tag.identifier.hex()}")
    return True

try:
    # Create reader object
    print("Looking for USB NFC reader...")
    with nfc.ContactlessFrontend('usb') as clf:
        print("Reader initialized. Waiting for tags...")
        # Keep looking for tags
        while True:
            # Poll for a tag
            if not clf.connect(rdwr={'on-connect': on_connect}):
                # If not tag is found, wait a bit before trying again
                time.sleep(0.5)
            else:
                # Tag as been detected and processed, wait before looking for another
                time.sleep(1)
except KeyboardInterrupt:
    print("Caught keyboard interrupt")
except Exception as e:
    print(f"An error occurred: {e}")
