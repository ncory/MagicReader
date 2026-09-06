import time
import RPi.GPIO as GPIO


class GPIOManager:
    PIN_MODE = GPIO.BOARD
    TRIGGER_HIGH = "HIGH"
    TRIGGER_LOW = "LOW"

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
                continue
            if pin < 1 or pin > 40:
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
