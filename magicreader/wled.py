from rest import RestHelpers

class WLEDManager:
    """Manager for WLED operations."""
    
    def __init__(self, address):
        self.address = address

    def callLedPreset(self, preset: int):
        """Makes a REST call to the internal WLED instance to recall a preset."""
        # Chec input
        if preset is None or not isinstance(preset, int):
            return
        # Construct URL to call
        url = f"http://{self.address}/win&PL={preset}"
        print(f"Calling LED preset: {url}", flush=True)
        # Make REST call
        RestHelpers.makeRestCall(url, 'GET')
