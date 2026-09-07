#!/usr/bin/env python
import logging
import time
import json
import sys
import traceback
import RPi.GPIO as GPIO
import threading
import queue
from helpers import State, AppEvent, AppEventType, SettingValueError
from bandManager import BandManager
from sequenceManager import SequenceManager
from soundManager import SoundManager
from rfid import RfidRead
from rfid_mfrc522 import RfidMfrc522
from sequence import Sequence
from wled import WLEDManager
from rest import RestQueue
from gpioManager import GPIOManager
import jsonStore

print("Starting...", flush=True)

# Check Python version
if sys.version_info.major < 3:
    sys.exit("This script requires Python 3")

# Read config file. Seed it from the shipped default first, since the runtime
# data files are not tracked in git.
SETTINGS_FILENAME = 'settings.json'
SETTINGS_FILE = jsonStore.dataPath(SETTINGS_FILENAME)
jsonStore.seedDataFileFromDefault(SETTINGS_FILENAME)
data = jsonStore.loadJson(SETTINGS_FILE)
if data is None or not isinstance(data, dict) or 'settings' not in data:
    sys.exit(f"FATAL: Could not read settings from {SETTINGS_FILE}")
config = data
settings = config['settings']
print_band_id = bool(settings['print_band_id'])
SETTINGS_SCHEMA = [
    {
        "key": "print_band_id",
        "label": "Print Band IDs",
        "type": "boolean",
        "section": "RFID"
    },
    {
        "key": "wled_address",
        "label": "WLED Address",
        "type": "text",
        "section": "WLED"
    },
    {
        "key": "wled_preset_black",
        "label": "Blackout Preset",
        "type": "number",
        "section": "WLED",
        "min": 0
    },
    {
        "key": "wled_preset_startup",
        "label": "Startup Preset",
        "type": "number",
        "section": "WLED",
        "min": 0
    },
    {
        "key": "wled_preset_waiting",
        "label": "Waiting Preset",
        "type": "number",
        "section": "WLED",
        "min": 0
    },
    {
        "key": "wled_preset_error",
        "label": "Error Preset",
        "type": "number",
        "section": "WLED",
        "min": 0
    },
    {
        "key": "sound_startup",
        "label": "Startup Sound",
        "type": "sound",
        "section": "Sounds",
        "nullable": True
    },
    {
        "key": "sound_waiting",
        "label": "Waiting Sound",
        "type": "sound",
        "section": "Sounds",
        "nullable": True
    },
    {
        "key": "sound_error",
        "label": "Error Sound",
        "type": "sound",
        "section": "Sounds",
        "nullable": True
    },
    {
        "key": "startup_read_delay",
        "label": "Startup Read Delay",
        "type": "number",
        "section": "Timing",
        "min": 0,
        "unit": "seconds"
    },
    {
        "key": "error_read_delay",
        "label": "Error Read Delay",
        "type": "number",
        "section": "Timing",
        "min": 0,
        "unit": "seconds"
    },
    {
        "key": "inactivity_timeout",
        "label": "Inactivity Timeout",
        "type": "number",
        "section": "Timing",
        "min": 0,
        "unit": "seconds"
    },
    {
        "key": "gpio_outputs",
        "label": "GPIO Outputs",
        "type": "gpioOutputs",
        "section": "GPIO"
    }
]

# The RFID reader's reset pin is defined in rfid_mfrc522 but has to be excluded
# from the pins offered as GPIO outputs. Catch the two drifting apart here
# rather than discovering it when a sequence kills the reader.
if RfidMfrc522.RESET_PIN not in GPIOManager.RESERVED_PINS:
    print(
        f"WARNING: MFRC522 reset pin {RfidMfrc522.RESET_PIN} is not in "
        f"GPIOManager.RESERVED_PINS {sorted(GPIOManager.RESERVED_PINS)} - "
        "it could be assigned as a GPIO output and break the reader",
        flush=True
    )

# Setup logging
log = logging.getLogger('main')
log.setLevel(logging.CRITICAL)

print("Finished Config Loading", flush=True)


######### Class #########

class MagicBand():
    def __init__(self):
        # Create managers
        self.band_manager = BandManager()
        self.sequence_manager = SequenceManager()
        self.soundManager = SoundManager()
        self.wledManager = WLEDManager(settings['wled_address'])
        # Set flags and status
        self.state = State.Uknown
        self.allowRead = False
        self.setState(State.Starting)
        self.is_active = False
        self.inactive_timer = None
        self.wait_mode_timer = None
        self.read_delay_timer = None
        self.read_once_enabled = False
        self.read_once_result = None
        self.sequence_thread = None
        self.sequence_cancel_event = None
        self.sequence_lock = threading.Lock()
        self.active_sequence = None
        self.active_sequence_id = None
        self.pending_rfid_after_sequence_cancel = None
        # Create queue
        self.event_queue = queue.PriorityQueue()
        self.event_thread = None
        # Create RFID reader and fix logging level
        print("Creating RFID reader object", flush=True)
        if RfidMfrc522.waitForMfrc522Hardware():
            self.reader = RfidMfrc522(self)
        else:
            self.reader = None
        self.gpioManager = GPIOManager(settings.get('gpio_outputs', []))
        # Pre-load sound files
        self.loadConfiguredSounds()
    
    def run(self):
        """Starts the application"""
        # Load bands from file
        if not self.band_manager.loadFromFile():
            print("ERROR: Failed to load bands from file", flush=True)
            return False
        # Load sequences from file
        if not self.sequence_manager.loadFromFile():
            print("ERROR: Failed to load sequences from file", flush=True)
            return False
        self.sequence_manager.preCacheSoundFiles(self.soundManager)
        # Set active flag
        self.is_active = True
        # Start RFID reader
        if self.reader is None:
            return False
        if self.reader.start() is False:
            return False
        # Play startup lights and sound
        self.setState(State.Welcome)
        self.triggerStartup()
        # Create and start event thread
        self.event_thread = threading.Thread(target=self.runEventQueue, daemon=True)
        self.event_thread.start()
        # Start first read
        self.startWaitModeTimer(settings['startup_read_delay'])
        # Reset inactivity timer
        self.resetInactiveTimer()
        # Success
        return True
        
    def shutdown(self):
        # Set state
        self.setState(State.Shutdown, "Shutting down")
        # Add event to queue
        self.event_queue.put((1, AppEvent(AppEventType.Shutdown)))

    def waitForShutdown(self, timeout: float = 10.0) -> bool:
        """Blocks until the event thread has finished cleanup(). Returns True if it did."""
        if self.event_thread is None:
            # Never started - run cleanup inline so we still reset hardware.
            self.cleanup()
            return True
        self.event_thread.join(timeout)
        if self.event_thread.is_alive():
            print("WARNING: Timed out waiting for cleanup to finish", flush=True)
            return False
        return True

    def cleanup(self):
        print("Cleanup starting...", flush=True)
        # Clear active flags
        self.is_active = False
        self.allowRead = False
        self.cancelActiveSequence()
        # Reset configured GPIO outputs before the RFID library clears GPIO state.
        self.gpioManager.cleanup()
        # Stop RIFD reader
        if self.reader is not None:
            self.reader.stop()
        # Trigger blackout on LEDs. Must be queued BEFORE the REST queue is
        # stopped, otherwise the call is never sent and the LEDs stay lit.
        self.wledManager.callLedPreset(settings['wled_preset_black'])
        # Stop REST queue (drains the blackout call above before exiting)
        RestQueue().shutdown()
        # Stop all sound
        self.soundManager.stopAllSounds()
        # Cleanup GPIO
        GPIO.cleanup()
        print("Cleanup finished", flush=True)

    def onError(self, message: str = None):
        # Status
        self.setState(State.Error, message, True)
        # Trigger error lights & sound
        self.triggerError()
        # Setup next band read
        self.startWaitModeTimer(settings['error_read_delay'])


    ######### Status Functions #########

    def setState(self, state: State, message: str = None, isError: bool = False):
        self.state = state
        self.status = message
        self.isError = isError


    ######### Settings Functions #########

    def getSettings(self):
        current_settings = dict(settings)
        if "gpio_outputs" not in current_settings:
            current_settings["gpio_outputs"] = []
        return current_settings

    def getSettingsSchema(self):
        return SETTINGS_SCHEMA

    def loadConfiguredSounds(self):
        self.soundManager.preLoadSound("startup", settings.get('sound_startup'))
        self.soundManager.preLoadSound("waiting", settings.get('sound_waiting'))
        self.soundManager.preLoadSound("error", settings.get('sound_error'))

    def coerceSettingValue(self, field: dict, value):
        key = field.get("key")
        field_type = field.get("type")
        nullable = bool(field.get("nullable", False))
        if value == '' and nullable:
            return True, None
        if value is None:
            return (True, None) if nullable else (False, None)
        if field_type == "boolean":
            if isinstance(value, bool):
                return True, value
            return False, None
        if field_type == "number":
            if isinstance(value, bool):
                return False, None
            try:
                number_value = int(value)
            except Exception:
                return False, None
            if "min" in field and number_value < field["min"]:
                return False, None
            return True, number_value
        if field_type == "select":
            allowed_values = [option.get("value") for option in field.get("options", [])]
            if value in allowed_values:
                return True, value
            return False, None
        if field_type == "sound":
            if not isinstance(value, str):
                return False, None
            value = self.soundManager.normalizeSoundFilename(value)
            if value is None:
                return (True, None) if nullable else (False, None)
            if not self.soundManager.isValidSoundFilename(value):
                return False, None
            return True, value
        if field_type == "text":
            if not isinstance(value, str):
                return False, None
            value = value.strip()
            if value == '':
                return (True, None) if nullable else (False, None)
            return True, value
        if field_type == "gpioOutputs":
            if value is None:
                return True, []
            if not isinstance(value, list):
                return False, None
            normalized_outputs = GPIOManager.normalizeOutputs(value)
            seen_ids = set()
            for output in value:
                if not isinstance(output, dict):
                    return False, None
                output_id = output.get("id")
                if not isinstance(output_id, str) or output_id.strip() == '' or output_id.strip() in seen_ids:
                    return False, None
                seen_ids.add(output_id.strip())
                pin = output.get("pin")
                # Reject power, ground, EEPROM and RFID-reader pins outright -
                # driving a supply rail as an output is a short, and taking an
                # SPI or reset pin would break the MFRC522.
                invalid_reason = GPIOManager.describeInvalidPin(pin)
                if invalid_reason is not None:
                    raise SettingValueError(f"GPIO output '{output_id.strip()}': {invalid_reason}")
                pin = int(pin)
                trigger_state = output.get("trigger_state")
                if not isinstance(trigger_state, str) or trigger_state.strip().upper() not in ["HIGH", "LOW"]:
                    return False, None
                try:
                    pulse_seconds = float(output.get("pulse_seconds"))
                except Exception:
                    return False, None
                if pulse_seconds < 0:
                    return False, None
            return True, normalized_outputs
        print(f"Unknown setting type for {key}: {field_type}", flush=True)
        return False, None

    def updateSettings(self, request_settings: dict):
        """Validates and persists settings. Returns (success, restart_required, message)."""
        if request_settings is None or not isinstance(request_settings, dict):
            return False, False, "No settings provided"
        global settings, print_band_id
        old_settings = dict(settings)
        updated_settings = {}
        restart_required = False
        for field in SETTINGS_SCHEMA:
            key = field.get("key")
            if key in request_settings:
                try:
                    valid, value = self.coerceSettingValue(field, request_settings.get(key))
                except SettingValueError as e:
                    print(f"Invalid setting value for {key}: {e}", flush=True)
                    return False, False, str(e)
                if not valid:
                    print(f"Invalid setting value for {key}: {request_settings.get(key)}", flush=True)
                    return False, False, f"Invalid value for {field.get('label', key)}"
                updated_settings[key] = value
            elif key in settings:
                updated_settings[key] = settings[key]
            if updated_settings.get(key) != old_settings.get(key) and field.get("restart_required") is True:
                restart_required = True
        for key, value in settings.items():
            if key not in updated_settings:
                updated_settings[key] = value
        if not jsonStore.saveJsonAtomic(SETTINGS_FILE, {"settings": updated_settings}):
            return False, False, "Could not save settings to disk"
        # Rebind rather than clear()+update(). Mutating in place left a window
        # where the dict was empty, so a reader on the event or sequence thread
        # could hit a KeyError mid-save. Rebinding is a single atomic name
        # swap: every reader sees either the old dict or the new one.
        settings = updated_settings
        config['settings'] = settings
        print_band_id = bool(settings.get('print_band_id'))
        self.wledManager.address = settings.get('wled_address')
        self.loadConfiguredSounds()
        self.gpioManager.configureOutputs(settings.get('gpio_outputs', []))
        if self.is_active:
            self.resetInactiveTimer()
        return True, restart_required, None


    ######### Inactivity Timer #########

    def resetInactiveTimer(self):
        if self.inactive_timer is not None:
            # Cancel existing timer
            self.inactive_timer.cancel()
        # Create new timer
        self.inactive_timer = threading.Timer(settings['inactivity_timeout'], self.inactiveTimerFired)
        self.inactive_timer.start()

    def inactiveTimerFired(self):
        print("Timed out due to inactivity - entering blackout mode (Taps still allowed)", flush=True)
        # Add blackout event to queue
        self.event_queue.put((2, AppEvent(AppEventType.Blackout, False)))


    ######### Wait Mode Timer #########

    def stopWaitModeTimer(self):
        if self.wait_mode_timer is not None:
            # Cancel existing timer
            self.wait_mode_timer.cancel()
            self.wait_mode_timer = None

    def startWaitModeTimer(self, seconds: int, allowReadAfter: int = -1):
        if self.wait_mode_timer is not None:
            # Cancel existing timer
            self.wait_mode_timer.cancel()
            self.wait_mode_timer = None
        # Is there a wait?
        if seconds < 1:
            # Nope, just queue the event now
            self.event_queue.put((2, AppEvent(AppEventType.EnterWaitMode)))
        else:
            # Yes, let's start the timer
            # Make sure reads are disabled now
            self.allowRead = False
            # Are we setting a separate read timer?
            if allowReadAfter > 0:
                # Start read delay timer
                self.startReadDelayTimer(allowReadAfter)
            # Create new wait mode timer
            self.wait_mode_timer = threading.Timer(seconds, self.waitModeTimerFired)
            self.wait_mode_timer.start()

    def waitModeTimerFired(self):
        print("Wait mode timer finished - entering wait mode", flush=True)
        # Add wait mode event to queue
        self.event_queue.put((2, AppEvent(AppEventType.EnterWaitMode)))
        # Reset inactivity timer
        self.resetInactiveTimer()


    ######### Read Timer #########

    def stopReadDelayTimer(self):
        if self.read_delay_timer is not None:
            # Cancel existing timer
            self.read_delay_timer.cancel()
            self.read_delay_timer = None

    def startReadDelayTimer(self, seconds: int):
        if self.read_delay_timer is not None:
            # Cancel existing timer
            self.read_delay_timer.cancel()
            self.read_delay_timer = None
        # Is there a wait?
        if seconds < 1:
            # Nope, just allow it now
            self.allowRead = True
        else:
            # Yes, let's start the timer
            self.read_delay_timer = threading.Timer(seconds, self.readDelayTimerFired)
            self.read_delay_timer.start()

    def readDelayTimerFired(self):
        print("Read delay timer finished - allowing RFID reads", flush=True)
        self.allowRead = True


    ######### Queue/Thread Functions #########

    def runEventQueue(self):
        while self.is_active:
            # Get next event (will block!)
            priority, event = self.event_queue.get()
            # Reset inactivity timer
            self.resetInactiveTimer()
            try:
                # What type of event?
                if event.type == AppEventType.ReadRfid:
                    # READ RFID
                    # Are we looking for a read once?
                    if self.read_once_enabled:
                        # Accept this as our result
                        self.read_once_enabled = False
                        self.read_once_result = event.data
                        continue
                    active_sequence = self.getActiveSequence()
                    if active_sequence is not None:
                        if active_sequence.cancel_allowed:
                            print("RFID tap received - cancelling active sequence", flush=True)
                            if self.pending_rfid_after_sequence_cancel is None:
                                self.pending_rfid_after_sequence_cancel = event.data
                            else:
                                print("RFID tap ignored - sequence cancellation already pending", flush=True)
                            self.allowRead = False
                            self.cancelActiveSequence()
                        else:
                            print("RFID tap ignored - active sequence cannot be cancelled", flush=True)
                        continue
                    # Are we looking for an ID?
                    if self.allowRead:
                        id = event.data.id
                        print(f"Accepted RFID read: {id}   isDisney: {event.data.isDisney}", flush=True)
                        # Stop more reads
                        self.allowRead = False
                        # Handle read
                        self.onReadMagicBand(id, event.data.isDisney)
                elif event.type == AppEventType.EnterWaitMode:
                    # ENTER WAIT MODE
                    if self.isSequenceActive():
                        self.cancelActiveSequence()
                        continue
                    # Allow reads
                    self.allowRead = True
                    # Set state
                    self.setState(State.WaitingForTap)
                    # Trigger lights and sound
                    self.triggerWaiting()
                elif event.type == AppEventType.PlaySequence:
                    # PLAY SEQUENCE
                    if not self.playSequence(event.data):
                        self.onError("Failed to start sequence")
                elif event.type == AppEventType.StopSequence:
                    # STOP SEQUENCE
                    sequence_was_active = self.cancelActiveSequence()
                    # Stop timers
                    self.stopReadDelayTimer()
                    self.stopWaitModeTimer()
                    if not sequence_was_active:
                        # Stop any current sounds and return to wait mode.
                        self.soundManager.stopAllSounds()
                        self.event_queue.put((1, AppEvent(AppEventType.EnterWaitMode)))
                elif event.type == AppEventType.SequenceFinished:
                    # SEQUENCE FINISHED
                    self.sequenceFinished(event.data)
                elif event.type == AppEventType.Blackout:
                    # BLACKOUT
                    self.cancelActiveSequence()
                    # Cancel reads?
                    if isinstance(event.data, bool) and event.data is True:
                        self.allowRead = False
                    # Set state
                    self.setState(State.Blackout)
                    # Trigger blackout lights/sounds
                    self.triggerBlackout()
                elif event.type == AppEventType.Shutdown:
                    # SHUTDOWN
                    self.cancelActiveSequence()
                    # Run cleanup routine
                    self.cleanup()
                    # End this thread
                    return
            except Exception as e:
                # A raise here used to kill the event thread outright: the app
                # would keep reporting a healthy state over the API while
                # silently ignoring every tap. Log it and stay alive instead.
                print(f"ERROR handling event {getattr(event, 'type', None)}: {e}", flush=True)
                traceback.print_exc()
                # A failed shutdown still has to end the thread, otherwise
                # waitForShutdown() blocks until its timeout.
                if getattr(event, 'type', None) == AppEventType.Shutdown:
                    return
                try:
                    self.onError("Internal error")
                except Exception as inner:
                    print(f"ERROR while reporting event failure: {inner}", flush=True)

    ######### MagicBand Functions #########

    def onReadMagicBand(self, band_id:str, isDisney:bool):
        """Looks up the band ID, and runs a matching sequence."""
        # Set state
        self.setState(State.Checking)
        # Stop any music playback
        self.soundManager.stopMusic()
        # Convert band_id to str
        if not isinstance(band_id, str):
            print("Converting to string", flush=True)
            band_id = str(band_id)
        if print_band_id == True:
            print(f"Read MagicBand ID: {band_id}", flush=True)
        # Lookup sequence name for band id
        print("Looking up band id", flush=True)
        seq_id = self.band_manager.lookupBandId(band_id, isDisney)
        # Get matching sequence
        print("Looking up sequence", flush=True)
        sequence = self.sequence_manager.getSequenceById(seq_id)
        if sequence is None:
            print("ERROR: found no sequnce to run!", flush=True)
            self.onError("Found no sequence to run!")
            return
        # Run sequence
        if not self.playSequence(seq_id):
            # Error!
            self.onError("Failed to playback sequence")
    

    ######### Trigger Functions for LEDs and sounds #########

    def triggerStartup(self):
        """Triggers 'Startup' LED sequence and sound. Called when app first launches."""
        # Play sound
        if settings.get('sound_startup') is not None:
            self.soundManager.playSound("startup")
        # Trigger LED sequence
        self.wledManager.callLedPreset(settings['wled_preset_startup'])

    def triggerWaiting(self):
        """Triggers 'Waiting' LED sequence and sound. Called when app enters read loop and is waiting for an RFID read."""
        # Play sound
        if settings.get('sound_waiting') is not None:
            self.soundManager.playSound("waiting")
        # Trigger LED sequence
        self.wledManager.callLedPreset(settings['wled_preset_waiting'])
        
    def triggerError(self):
        """Triggers 'Error' LED sequence and sound."""
        # Play sound
        if settings.get('sound_error') is not None:
            self.soundManager.playSound("error")
        # Trigger LED sequence
        self.wledManager.callLedPreset(settings['wled_preset_error'])
    
    def triggerBlackout(self):
        """Turns off LEDs, stops all sounds, and cancels any pending RFID read actions"""
        if self.read_once_enabled:
            self.read_once_enabled = False
            self.read_once_result = None
        # Stop all sound
        self.soundManager.stopAllSounds()
        # Recall black LED preset
        self.wledManager.callLedPreset(settings['wled_preset_black'])


    ######### Sequence functions #########

    def isSequenceActive(self):
        with self.sequence_lock:
            return self.active_sequence is not None

    def getActiveSequence(self):
        with self.sequence_lock:
            return self.active_sequence

    def getActiveSequenceId(self):
        with self.sequence_lock:
            return self.active_sequence_id

    def cancelActiveSequence(self):
        with self.sequence_lock:
            cancel_event = self.sequence_cancel_event
            sequence_id = self.active_sequence_id
            if self.active_sequence is None or cancel_event is None:
                return False
        print(f"Cancelling sequence: {sequence_id}", flush=True)
        cancel_event.set()
        self.soundManager.stopAllSounds()
        return True

    def playSequence(self, id: str):
        """Starts playback for the selected sequence in a background thread."""
        # Get sequence from sequence manager
        sequence = self.sequence_manager.getSequenceById(id)
        if sequence is None or not isinstance(sequence, Sequence):
            print("Invalid sequence", flush=True)
            return False
        with self.sequence_lock:
            if self.active_sequence is not None:
                print("Cannot start sequence - another sequence is already active", flush=True)
                return False
            cancel_event = threading.Event()
            thread = threading.Thread(
                target=self.runSequence,
                args=(id, sequence, cancel_event),
                daemon=True
            )
            self.active_sequence = sequence
            self.active_sequence_id = id
            self.sequence_cancel_event = cancel_event
            self.sequence_thread = thread
        # Allow RFID reads during cancellable sequences so taps can cancel playback.
        self.allowRead = sequence.cancel_allowed
        # Stop all music
        self.soundManager.stopMusic()
        # Set status
        self.setState(State.PlayingSequence, sequence.name)
        # Actually play the sequence in the worker thread.
        thread.start()
        return True

    def runSequence(self, id: str, sequence: Sequence, cancel_event: threading.Event):
        success = False
        try:
            success = sequence.play(self.wledManager, self.soundManager, self.gpioManager, cancel_event)
        except Exception as e:
            print(f"Error playing sequence {id}: {e}", flush=True)
            success = False
        cancelled = cancel_event.is_set()
        self.event_queue.put((1, AppEvent(AppEventType.SequenceFinished, {
            "id": id,
            "success": success,
            "cancelled": cancelled
        })))

    def sequenceFinished(self, result: dict):
        if not isinstance(result, dict):
            result = {}
        sequence_id = result.get("id", None)
        success = result.get("success", False)
        cancelled = result.get("cancelled", False)
        should_return_to_wait = self.state == State.PlayingSequence
        with self.sequence_lock:
            if self.active_sequence_id is not None and sequence_id != self.active_sequence_id:
                print(f"Ignoring stale sequence completion for: {sequence_id}", flush=True)
                return
            self.active_sequence = None
            self.active_sequence_id = None
            self.sequence_cancel_event = None
            self.sequence_thread = None
        pending_rfid = self.pending_rfid_after_sequence_cancel
        self.pending_rfid_after_sequence_cancel = None
        self.allowRead = False
        if cancelled:
            print(f"Sequence cancelled: {sequence_id}", flush=True)
            if pending_rfid is not None and isinstance(pending_rfid, RfidRead):
                print("Processing RFID tap after sequence cancellation", flush=True)
                self.onReadMagicBand(pending_rfid.id, pending_rfid.isDisney)
                return
        elif not success:
            print(f"Sequence failed: {sequence_id}", flush=True)
            self.onError("Failed to playback sequence")
            return
        else:
            print(f"Sequence finished: {sequence_id}", flush=True)
        if should_return_to_wait:
            self.startWaitModeTimer(0)


    ######### Web Api Calls #########

    def api_blackout(self):
        # Push event
        self.event_queue.put((2, AppEvent(AppEventType.Blackout, True)))
        
    def api_waitForTap(self):
        # Stop music
        self.soundManager.stopMusic()
        # Push event
        self.event_queue.put((2, AppEvent(AppEventType.EnterWaitMode)))
    
    def api_allowRead(self):
        # Allow RFID reads (by 'starting' and thus cancelling the read time)
        self.startReadDelayTimer(0)
    
    def api_disableRead(self):
        # Disable RFID reads
        self.allowRead = False
    
    def api_playSequence(self, seq_id: str):
        # Push event
        self.event_queue.put((2, AppEvent(AppEventType.PlaySequence, seq_id)))
    
    def api_stopSequence(self):
        # Push event
        self.event_queue.put((2, AppEvent(AppEventType.StopSequence)))
        
    def api_read_single_rfid(self) -> tuple[str, bool] | None:
        # Temporarily disable reading
        previous_read = self.allowRead
        self.allowRead = False
        # Enable read-once flag
        self.read_once_enabled = True
        # Wait for a successful read
        wait_start = time.perf_counter()
        result = None
        while True:
            # How long have we waited?
            wait_now = time.perf_counter()
            if wait_now - wait_start > 30:
                # Over 30 seconds - fail
                print("Timed out reading single RFID", flush=True)
                break
            # Check for result
            if self.read_once_result is not None and isinstance(self.read_once_result, RfidRead):
                # Success!
                # Check if ID is a MagicBand and setup result
                id = str(self.read_once_result.id)
                isDisney = self.read_once_result.isDisney
                result = (id, isDisney)
                print(f"Success reading single RFID: {result}   isDisney: {isDisney}", flush=True)
                break
            # Nope, wait one second
            time.sleep(1)
        # Reset read once values
        self.read_once_result = None
        self.read_once_enabled = False
        # Restore read state
        if previous_read:
            # Set read timer for 5 seconds
            self.startReadDelayTimer(5)
        # Return what we found
        return result
