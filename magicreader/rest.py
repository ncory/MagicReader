from httplib2 import Http
import queue
import threading
import time
from urllib.parse import urlsplit


class UnreachableHosts:
    """Remembers hosts that just failed, so the next cue does not wait on them.

    A host that does not resolve is expensive out of all proportion to the
    cue it serves: an unresolvable mDNS name costs a flat 5 s on a Pi, paid
    again on every single call, because mDNS has no negative answer to cache -
    absence of a reply is the only "no", and you wait out the timeout to hear
    it. The REST queue is serial, so one dead WLED board delays every light
    cue behind it; a BrightSign address resolves inline on the sequence
    thread, which stalls the sequence itself, sounds included.

    So the first failure is paid, and calls to that host are then skipped
    until the cooldown expires. The trade is deliberate: for up to COOLDOWN
    seconds after a device comes back, its cues are dropped. That beats every
    cue arriving seconds late while it is away.

    Shared by the HTTP and UDP paths, and safe to call from any thread.
    """

    COOLDOWN = 15.0

    _failures = {}
    _lock = threading.Lock()

    @staticmethod
    def hostOf(target):
        """Returns the host for a URL or a bare address, or None."""
        if not isinstance(target, str) or not target.strip():
            return None
        target = target.strip()
        if "//" in target:
            host = urlsplit(target).hostname
        else:
            # A bare address, as the UDP actions carry it
            host = target.split("/")[0].split(":")[0]
        return host.lower() if host else None

    @staticmethod
    def shouldSkip(target):
        """True if this host failed recently and is still in its cooldown."""
        host = UnreachableHosts.hostOf(target)
        if host is None:
            return False
        with UnreachableHosts._lock:
            entry = UnreachableHosts._failures.get(host)
            if entry is None:
                return False
            if time.monotonic() - entry["at"] >= UnreachableHosts.COOLDOWN:
                # Cooldown is up. Let this one through to probe the host -
                # success clears the entry, another failure restarts it
                return False
            entry["skipped"] += 1
            return True

    @staticmethod
    def recordFailure(target, error = None):
        host = UnreachableHosts.hostOf(target)
        if host is None:
            return
        with UnreachableHosts._lock:
            entry = UnreachableHosts._failures.get(host)
            if entry is None or time.monotonic() - entry["at"] >= UnreachableHosts.COOLDOWN:
                # Announce only when the host enters a cooldown, not on every
                # failure, or a dead device fills the log
                print(f"Host {host} unreachable ({error}) - skipping calls to it "
                      f"for {UnreachableHosts.COOLDOWN:.0f}s", flush=True)
            UnreachableHosts._failures[host] = {"at": time.monotonic(), "skipped": 0}

    @staticmethod
    def recordSuccess(target):
        host = UnreachableHosts.hostOf(target)
        if host is None:
            return
        with UnreachableHosts._lock:
            entry = UnreachableHosts._failures.pop(host, None)
        if entry is not None:
            print(f"Host {host} is answering again "
                  f"({entry['skipped']} call(s) skipped while it was away)", flush=True)

    @staticmethod
    def reset():
        """Forgets every recorded failure. For tests."""
        with UnreachableHosts._lock:
            UnreachableHosts._failures.clear()

class RestQueue:
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # Double-checked locking so concurrent callers share one instance
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # __init__ runs on every RestQueue() call, even though __new__ returns
        # the shared instance. Only build the queue and worker thread once,
        # otherwise each call orphans the previous queue and leaks its thread.
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        # Create queue
        self.is_active = True
        self.queue = queue.PriorityQueue()
        # Create and start event thread
        self.thread = threading.Thread(target=self.runQueue, daemon=True)
        self.thread.start()
    
    def runQueue(self):
        while self.is_active:
            # Get next event (will block!)
            priority, event = self.queue.get()
            # Shutdown event?
            if event is False:
                # SHUTDOWN - end thread
                self.is_active = False
                return
            # Otherwise, do we have a tuple?
            if isinstance(event, tuple) and len(event) == 5:
                # Make REST call
                url, method, payload, isJson, isUrlEncoding = event
                RestHelpers.makeRestCall(url, method, payload, isJson, isUrlEncoding)
                #print(f"REST call completed: {method}: {url}", flush=True)
            else:
                print(f"Unknown event in REST queue: {event}", flush=True)
                continue

    def shutdown(self, timeout: float = 5.0):
        """Drains any queued calls, then stops the worker thread."""
        # Priority 99 so calls already queued (priority 10) still go out first -
        # the shutdown blackout preset has to reach WLED before we stop.
        self.queue.put((99, False))
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout)
            if self.thread.is_alive():
                print("WARNING: REST queue did not drain before timeout", flush=True)
    
    def makeRestCallAsync(self, url, method = 'GET', payload = None, isJson = False, isUrlEncoded = False):
        """Queues a REST call to be made later."""
        #print(f"Queueing REST Call: {method}: {url}", flush=True)
        self.queue.put((10,(url, method, payload, isJson, isUrlEncoded)))


class RestHelpers:
    _http_obj = Http(timeout=0.5)

    @staticmethod
    def makeRestCall(url, method = 'GET', payload = None, isJson = False, isUrlEncoded = False):
        """Makes the specified HTTP call with an optional paylod and JSON content type."""
        # A host that just failed is skipped rather than waited on again. The
        # queue is serial, so the wait is not paid by this cue alone
        if UnreachableHosts.shouldSkip(url):
            return False
        print(f"REST Call: {method}: {url}", flush=True)
        try:
            # Body content
            if isJson:
                message_headers = {'Content-Type': 'application/json; charset=UTF-8'}
                body = payload
            elif isUrlEncoded:
                message_headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
                body = payload
            else:
                message_headers = {}
                body = None
            # Make HTTP call
            response = RestHelpers._http_obj.request(
                uri = url,
                method = method,
                body = body,
                headers = message_headers
            )
            #print(response, flush=True)
            # A 404 or 500 is the host answering, not a host that is down, so
            # only a transport-level failure counts against it
            UnreachableHosts.recordSuccess(url)
            return True
        except Exception as e:
            print(f"Error making REST call: {e}", flush=True)
            UnreachableHosts.recordFailure(url, e)
            return False
