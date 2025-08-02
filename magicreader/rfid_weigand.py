import rfid
from helpers import AppEvent, AppEventType, CancelReadException
import serial

class RfidWeigand(rfid.RfidReader):

    def __init__(self, app, port:str = None):
        super().__init__(app, port)
        self.serial_port = None
        # Do we have a port name to use?
        if self.port is None:
            self.port = '/dev/ttyUSB0'
    
    def start(self) -> bool:
        # Try creating serial port first
        try:
            self.serial_port = serial.Serial(self.port, baudrate=9600)
            print(f"Opened serial port: {self.serial_port.name}", flush=True)
        except Exception as e:
            print(f"Error opening serial port {self.port}: {e}")
            return False
        return super().start()
    
    def runReaderThread(self):
        print("Starting RFID read thread", flush=True)
        while self.app.is_active and self.serial_port is not None:
            # Perform RFID read
            print("RFID:: Waiting for RFID....", flush=True)
            id = None
            try:
                # Read to next line
                line = self.serial_port.readline()
                if len(line) < 1:
                    continue
                # Convert to string
                id = line.decode('ascii').strip()
                print(f"RFID:: Read RFID: {id}", flush=True)
                # Pass to event queue
                read = rfid.RfidRead(id, self.isDisneyBand(id))
                event = AppEvent(AppEventType.ReadRfid, read)
                print(f"RFID:: isDisneyBand: {read.isDisney}", flush=True)
                self.app.event_queue.put((5, event))
            except CancelReadException:
                print("RFID:: Got CancelReadException!!", flush=True)
                return
            except Exception as e:
                if not self.app.is_active:
                    return
                print("RFID:: Error reading RFID", flush=True)
                print (e, flush=True)

    def stop(self):
        # Close serial port
        if self.serial_port is not None:
            self.serial_port.close()
            self.serial_port = None
        print("Closed serial port", flush=True)

    def isDisneyBand(self, id:str) -> bool:
        # Convert string to int
        try:
            wiegand_number = int(id)
        except ValueError:
            print(f"RFID:: Error converting to int: {id}", flush=True)
            False
        try:
            # Decode Wiegand number to Facility and Card
            bin_str = f'{wiegand_number:032b}'
            facility_code = int(bin_str[:16], 2)
            card_number = int(bin_str[16:], 2)
            # Try building fake UID by combining Facility + Card
            # Facility: 2 bytes, Card: 2 bytes
            facility_bytes = facility_code.to_bytes(2, 'big')
            card_bytes = card_number.to_bytes(2, 'big')
            # Concatenate
            fake_uid = facility_bytes + card_bytes
            fake_uid_hex = fake_uid.hex().upper()
            return fake_uid_hex.endswith("04")
        except:
            return False
