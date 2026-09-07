import time
import RPi.GPIO as GPIO


class GPIOManager:
    PIN_MODE = GPIO.BOARD
    TRIGGER_HIGH = "HIGH"
    TRIGGER_LOW = "LOW"

    # BOARD pin numbers that are actual GPIO on a 40-pin header. The rest are
    # 3.3V (1, 17), 5V (2, 4), ground (6, 9, 14, 20, 25, 30, 34, 39) or the HAT
    # ID EEPROM (27, 28). Driving a power or ground pin as an output shorts the
    # supply through the pin driver, so these must never be configurable.
    GPIO_PINS = frozenset({
        3, 5, 7, 8, 10, 11, 12, 13, 15, 16, 18, 19, 21, 22,
        23, 24, 26, 29, 31, 32, 33, 35, 36, 37, 38, 40
    })

    # Pins this app already owns. SPI0 drives the MFRC522 (MOSI 19, MISO 21,
    # SCLK 23, CE0 24, CE1 26) and pin 22 is its reset line - see
    # RfidMfrc522.RESET_PIN, which magicreader.py cross-checks against this set
    # at startup. Handing any of these to a sequence would break the reader.
    RESERVED_PINS = frozenset({19, 21, 22, 23, 24, 26})

    @staticmethod
    def describeInvalidPin(pin):
        """Returns why this BOARD pin cannot be an output, or None if it is usable."""
        try:
            pin = int(pin)
        except Exception:
            return "pin must be a number"
        if pin < 1 or pin > 40:
            return f"pin {pin} is outside the 40-pin header"
        if pin in GPIOManager.RESERVED_PINS:
            return f"pin {pin} is reserved for the MFRC522 RFID reader (SPI and reset)"
        if pin not in GPIOManager.GPIO_PINS:
            return f"pin {pin} is a power, ground or reserved EEPROM pin, not a GPIO"
        return None

    @staticmethod
    def isUsablePin(pin) -> bool:
        return GPIOManager.describeInvalidPin(pin) is None

    @staticmethod
    def getUsablePins() -> list:
        return sorted(GPIOManager.GPIO_PINS - GPIOManager.RESERVED_PINS)

    def __init__(self, outputs=None):
        self.outputs = {}
        self.configureOutputs(outputs)

    @staticmethod
    def normalizeOutputs(outputs):
        normalized = []
        if not isinstance(outputs, list):
            return normalized
        found_ids = set()
        for output in outputs:
            if not isinstance(output, dict):
                continue
            output_id = output.get("id")
            if not isinstance(output_id, str):
                continue
            output_id = output_id.strip()
            if output_id == '' or output_id in found_ids:
                continue
            try:
                pin = int(output.get("pin"))
            except Exception:
                print(f"Skipping GPIO output '{output_id}': pin must be a number", flush=True)
                continue
            invalid_reason = GPIOManager.describeInvalidPin(pin)
            if invalid_reason is not None:
                print(f"Skipping GPIO output '{output_id}': {invalid_reason}", flush=True)
                continue
            name = output.get("name")
            if not isinstance(name, str) or name.strip() == '':
                name = output_id
            trigger_state = output.get("trigger_state", GPIOManager.TRIGGER_LOW)
            if isinstance(trigger_state, str):
                trigger_state = trigger_state.strip().upper()
            if trigger_state not in [GPIOManager.TRIGGER_HIGH, GPIOManager.TRIGGER_LOW]:
                trigger_state = GPIOManager.TRIGGER_LOW
            try:
                pulse_seconds = float(output.get("pulse_seconds", 0.5))
            except Exception:
                pulse_seconds = 0.5
            if pulse_seconds < 0:
                pulse_seconds = 0
            normalized_output = {
                "id": output_id,
                "name": name.strip(),
                "pin": pin,
                "trigger_state": trigger_state,
                "pulse_seconds": pulse_seconds
            }
            normalized.append(normalized_output)
            found_ids.add(output_id)
        return normalized

    def configureOutputs(self, outputs):
        self.outputs = {}
        normalized_outputs = GPIOManager.normalizeOutputs(outputs)
        if len(normalized_outputs) < 1:
            return
        self.configurePinMode()
        for output in normalized_outputs:
            self.outputs[output["id"]] = output
            self.setupOutput(output)

    def configurePinMode(self):
        current_mode = GPIO.getmode()
        if current_mode is None:
            GPIO.setmode(self.PIN_MODE)
            return
        if current_mode != self.PIN_MODE:
            print("GPIO pin mode already differs from BOARD numbering", flush=True)

    def setupOutput(self, output):
        pin = output.get("pin")
        rest_state = self.getRestState(output)
        try:
            GPIO.setup(pin, GPIO.OUT, initial=rest_state)
        except Exception as e:
            print(f"Error configuring GPIO pin {pin}: {e}", flush=True)

    def getOutputNamesList(self):
        return [
            {
                "id": output["id"],
                "name": output["name"],
                "pin": output["pin"],
                "trigger_state": output["trigger_state"],
                "pulse_seconds": output["pulse_seconds"]
            }
            for output in self.outputs.values()
        ]

    def getTriggerState(self, output):
        return GPIO.HIGH if output.get("trigger_state") == self.TRIGGER_HIGH else GPIO.LOW

    def getRestState(self, output):
        return GPIO.LOW if output.get("trigger_state") == self.TRIGGER_HIGH else GPIO.HIGH

    def triggerOutput(self, output_id: str, cancel_event=None):
        if output_id not in self.outputs:
            print(f"Unknown GPIO output: {output_id}", flush=True)
            return False
        output = self.outputs[output_id]
        pin = output["pin"]
        trigger_state = self.getTriggerState(output)
        rest_state = self.getRestState(output)
        pulse_seconds = output.get("pulse_seconds", 0.5)
        print(f"Triggering GPIO output {output_id} on pin {pin}", flush=True)
        try:
            GPIO.output(pin, trigger_state)
            if pulse_seconds > 0:
                if cancel_event is not None:
                    if cancel_event.wait(pulse_seconds):
                        print(f"GPIO output cancelled during pulse: {output_id}", flush=True)
                        return False
                else:
                    time.sleep(pulse_seconds)
            return True
        except Exception as e:
            print(f"Error triggering GPIO output {output_id}: {e}", flush=True)
            return False
        finally:
            try:
                GPIO.output(pin, rest_state)
            except Exception as e:
                print(f"Error resetting GPIO output {output_id}: {e}", flush=True)

    def cleanup(self):
        for output in self.outputs.values():
            try:
                GPIO.output(output["pin"], self.getRestState(output))
            except Exception as e:
                print(f"Error resetting GPIO output {output['id']}: {e}", flush=True)
