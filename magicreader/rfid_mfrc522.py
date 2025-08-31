import rfid
from helpers import AppEvent, AppEventType, CancelReadException
from mfrc522 import SimpleMFRC522
import re
import datetime

class RfidMfrc522(rfid.RfidReader):

    def __init__(self, app, port:str = None):
        super().__init__(app, port)
        # Create RFID reader and fix logging level
        self.reader = SimpleMFRC522()
        self.reader.READER.logger.setLevel('CRITICAL')

    def runReaderThread(self):
        print("Starting RFID read thread", flush=True)
        while self.app.is_active:
            # Perform RFID read
            print("RFID:: Waiting for RFID....", flush=True)
            id = None
            try:
                id = self.reader.read_id()
                if id is None:
                    continue
                # How long since last read?
                now = datetime.datetime.now()
                diff = now - self.lastReadTime
                if (diff > self.timeDelta):
                    # Enough time has passed, allow read
                    print(f"RFID:: Read RFID: {id}", flush=True)
                    # Pass to event queue
                    read = rfid.RfidRead(id, self.isDisneyBand(id))
                    event = AppEvent(AppEventType.ReadRfid, read)
                    self.app.event_queue.put((5, event))
                    # Update last read time
                    self.lastReadTime = now
            except CancelReadException:
                print("RFID:: Got CancelReadException!!", flush=True)
                return
            except Exception as e:
                if not self.app.is_active:
                    return
                print("RFID:: Error reading RFID", flush=True)
                print (e, flush=True)
    
    def stop(self):
        self.reader.READER.Close_MFRC522()
    
    REGEX_MAGICBAND = re.compile("5841[0-9]+")
    #REGEX_MAGICBAND = re.compile("04[0-9a-zA-Z]+80")
    REGEX_MAGICBAND_PLUS = re.compile("04[0-9a-zA-Z]+90")

    def isDisneyBand(self, id:str) -> bool:
        if not isinstance(id, str):
            id = str(id)
        if RfidMfrc522.isIdMagicBandOrMagicBand2(id):
            return True
        elif RfidMfrc522.isIdMagicBandOrMagicBand2(id):
            return True
        return False

    @staticmethod
    def isIdMagicBandOrMagicBand2(id: str) -> bool:
        if not isinstance(id, str):
            id = str(id)
        # Run RegEx on id
        if RfidMfrc522.REGEX_MAGICBAND.match(id):
            return True
        return False
    
    @staticmethod
    def isIdMagicBandPlus(id: str) -> bool:
        if not isinstance(id, str):
            id = str(id)
        # Run RegEx on id
        if RfidMfrc522.REGEX_MAGICBAND_PLUS.match(id):
            return True
        return False
