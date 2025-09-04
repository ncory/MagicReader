from httplib2 import Http
import queue
import threading

class RestQueue:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
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
            if isinstance(event, tuple) and len(event) == 4:
                # Make REST call
                url, method, playload, isJson = event
                RestHelpers.makeRestCall(url, method, playload, isJson)
                #print(f"REST call completed: {method}: {url}", flush=True)
            else:
                print(f"Unknown event in REST queue: {event}", flush=True)
                continue

    def shutdown(self):
        # Add 'False' to queue - means shutdown
        self.queue.put((0, False))
    
    def makeRestCallAsync(self, url, method = 'GET', playload = None, isJson = False):
        """Queues a REST call to be made later."""
        #print(f"Queueing REST Call: {method}: {url}", flush=True)
        self.queue.put((10,(url, method, playload, isJson)))


class RestHelpers:
    _http_obj = Http(timeout=0.5)

    @staticmethod
    def makeRestCall(url, method = 'GET', playload = None, isJson = False):
        """Makes the specified HTTP call with an optional playlod and JSON content type."""
        print(f"REST Call: {method}: {url}", flush=True)
        try:
            # Use JSON content-type?
            if isJson:
                message_headers = {'Content-Type': 'application/json; charset=UTF-8'}
            else:
                message_headers = {}
            # Make HTTP call
            response = RestHelpers._http_obj.request(
                uri = url,
                method = method,
                headers = message_headers
            )
            #print(response, flush=True
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
