import datetime
import threading


class RfidRead():
    def __init__(self, id:str, isDisney:bool):
        self.id = id
        self.isDisney = isDisney
        self.time = datetime.datetime.now()


class RfidReader:
    def __init__(self, app, port:str = None):
        self.app = app
        self.port = port
        self.reader_thread = None
        self.lastReadTime = datetime.datetime.now()
        self.timeDelta = datetime.timedelta(seconds=3)

    def start(self) -> bool:
        # Create RFID thread and start it
        self.reader_thread = threading.Thread(target=self.runReaderThread, daemon=True)
        self.reader_thread.start()
        return True

    def stop(self):
        pass

    def runReaderThread(self):
        pass

    def isDisneyBand(self, id:str) -> bool:
        return False