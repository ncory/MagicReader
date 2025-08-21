from httplib2 import Http

class RestHelpers:
    _http_obj = Http()

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
