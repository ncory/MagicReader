#!/usr/bin/env python
from api import RunMagicApi
from magicreader import MagicBand
import threading
import time
import sys
import signal

# Configure SIGTERM handler
def signal_term_handler(sigNum, frame):
    # on receiving a signal initiate a normal exit
    raise SystemExit('Got SIGTERM')

# Register the SIGTERM handler
signal.signal(signal.SIGTERM, signal_term_handler)

# Run MagicBand app
print("Running MagicBand app...", flush=True)
app = MagicBand()
if not app.run():
    print("Fatal error while starting app", flush=True)
    sys.exit(-1)
#app_thread = threading.Thread(target=app.run, daemon=True)
#app_thread.start()

# Run API
api_thread = threading.Thread(target=RunMagicApi, args=[app], daemon=True)
api_thread.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Caught KeyboardInterrupt", flush=True)
except SystemExit:
    print("Caught SIGTERM exception", flush=True)
except Exception as e:
    print("exception")
    print(e)
finally:
    # Stop app thread + cleanup
    print("Exiting app...", flush=True)
    app.shutdown()
    # Kill API thread
    #api_thread.kill()
    # Exit
    sys.exit(0)

