from httplib2 import Http
import queue
import threading

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
        except Exception as e:
            print(f"Error making REST call: {e}", flush=True)



'''
import requests

class RestHelpers:

    @staticmethod
    def makeRestCall(url, method = 'GET', playload = None, isJson = False, timeout: float = 0.001):
        """Makes the specified HTTP call with an optional playlod and JSON content type."""
        print(f"REST Call: {method}: {url}", flush=True)
        try:
            # Use JSON content-type?
            if isJson:
                message_headers = {'Content-Type': 'application/json; charset=UTF-8'}
            else:
                message_headers = {}
            # Which flavor of request?
            if method == 'GET':
                response = requests.get(url, headers=message_headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, headers=message_headers, json=playload, timeout=timeout)
            elif method == 'PUT':
                response = requests.put(url, headers=message_headers, json=playload, timeout=timeout)
            elif method == 'DELETE':
                response = requests.delete(url, headers=message_headers, timeout=timeout)
            else:
                print(f"Unsupported HTTP method: {method}", flush=True)
                return
            #print(response, flush=True
        except Exception as e:
            print(f"Error making REST call: {e}", flush=True)
'''
