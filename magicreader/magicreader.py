#!/usr/bin/env python
import binascii
import logging
import struct
import time
import json
import os.path
from os import path
import random 
import sys
import os
from json import dumps
from httplib2 import Http
from mfrc522 import SimpleMFRC522
import RPi.GPIO as GPIO
import signal
import threading
import queue
import datetime
import socket
from functools import total_ordering
from helpers import State, AppEvent, AppEventType, CancelReadException
from bandManager import BandManager
from rfid import RfidRead, RfidReader
from rfid_mfrc522 import RfidMfrc522
from rfid_weigand import RfidWeigand

print("Starting...", flush=True)

# Import PyGame for sound playback and hide prompts
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

# Check Python version
if sys.version_info.major < 3:
    sys.exit("This script requires Python 3")

# Read config file
with open('settings.json', 'r') as file:
    data = json.load(file)
config = data
settings = config['settings']
tap_in_presets = config['tapInPresets']
print_band_id = bool(settings['print_band_id'])
#bands = config['bands']
sequences = config['sequences']

# Setup logging
log = logging.getLogger('main')
log.setLevel(logging.CRITICAL)

print("Starting PyGame", flush=True)
# Setup PyGame (Pre init helps to get rid of sound lag)
pygame.mixer.pre_init(44100, -16, 1, 4096 )
pygame.mixer.init()
pygame.init()

print("Finished Config Loading", flush=True)



######### Class #########

class MagicBand():
    def __init__(self):
        # Create managers
        self.band_manager = BandManager()
        # Set flags and status
        self.state = State.Uknown
        self.allowRead = False
        self.setState(State.Starting)
        self.lastTapInPreset = None
        self.is_active = False
        self.should_cancel_read = False
        self.thread = None
        self.inactive_timer = None
        self.wait_mode_timer = None
        self.read_delay_timer = None
        self.read_once_enabled = False
        self.read_once_result = None
        # Create http object to use later
        self.http_obj = Http()
        # Create queue
        self.event_queue = queue.PriorityQueue()
        self.event_thread = None
        # Create RFID reader and fix logging level
        print("Creating RFID reader object", flush=True)
        if (settings['rfid_mode'] == 'weigand-serial'):
            self.reader = RfidWeigand(self, settings.get('rfid_port'))
        elif (settings['rfid_mode'] == 'mfrc522'):
            self.reader = RfidMfrc522(self)
        else:
            self.reader = None
        # Pre-load all sound files
        self.loadAllSounds()
    
    def run(self):
        """Starts the application"""
        # Load bands from file
        if not self.band_manager.loadFromFile():
            return False
        # Set active flag
        self.is_active = True
        # Start RFID reader
        if self.reader is None:
            return False
        if self.reader.start() is False:
            return False
        # Install signal handler
        #signal.signal(signal.SIGUSR1, MagicBand.on_signusr1)
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

    def cleanup(self):
        # Clear active flags
        self.is_active = False
        self.allowRead = False
        # Stop RIFD reader
        self.reader.stop()
        # Trigger blackout on LEDs
        self.callLedPreset(settings['wled_preset_black'])
        # Stop all sound
        pygame.mixer.stop()
        pygame.mixer.music.stop()
        # Cleanup GPIO
        GPIO.cleanup()

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
            # What type of event?
            if event.type == AppEventType.ReadRfid:
                # READ RFID
                # Are we looking for a read once?
                if self.read_once_enabled:
                    # Accept this as our result
                    self.read_once_enabled = False
                    self.read_once_result = event.data
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
                # Allow reads
                self.allowRead = True
                # Set state
                self.setState(State.WaitingForTap)
                # Trigger lights and sound
                self.triggerWaiting()
            elif event.type == AppEventType.PlayTapInPreset:
                # PLAY TAP-IN PRESET
                # Disable reads
                self.allowRead = False
                # Play preset
                self.setState(State.PlayingTapIn)
                self.playTapInPreset(event.data)
                # Return to waiting
                self.event_queue.put((2, AppEvent(AppEventType.EnterWaitMode)))
            elif event.type == AppEventType.PlaySequence:
                # PLAY SEQUENCE
                # Lookup sequence
                sequence = self.lookupSequence(event.data)
                # Play sequence
                self.playSequence(sequence, event.data)
            elif event.type == AppEventType.StopSequence:
                # STOP SEQUENCE
                # Stop music
                self.stopMusic()
                # Stop timers
                self.stopReadDelayTimer()
                self.stopWaitModeTimer()
                # Push event for wait mode
                self.event_queue.put((1, AppEvent(AppEventType.EnterWaitMode)))
            elif event.type == AppEventType.Blackout:
                # BLACKOUT
                # Cancel reads?
                if isinstance(event.data, bool) and event.data is True:
                    self.allowRead = False
                # Set state
                self.setState(State.Blackout)
                # Trigger blackout lights/sounds
                self.triggerBlackout()
            elif event.type == AppEventType.Shutdown:
                # SHUTDOWN
                # Run cleanup routine
                self.cleanup()
                # End this thread
                return
    '''
    ######### RFID Functions #########

    def runReaderThread(self):
        print("Starting RFID read thread", flush=True)
        while self.is_active:
            # Perform RFID read
            print("RFID:: Waiting for RFID....", flush=True)
            id = None
            try:
                id = self.reader.read_id()
                if id is None:
                    continue
                print(f"RFID:: Read RFID: {id}", flush=True)
                # Pass to event queue
                read = RfidRead(id)
                event = AppEvent(AppEventType.ReadRfid, read)
                self.event_queue.put((5, event))
            except CancelReadException:
                print("RFID:: Got CancelReadException!!", flush=True)
                return
            except Exception as e:
                if not self.is_active:
                    return
                print("RFID:: Error reading RFID", flush=True)
                print (e, flush=True)
    

    ######### MagicBand Functions #########

    def startRfidRead(self, read_delay):
        return
        """Starts an RFID lookup after the specified delay."""
        if not self.is_active:
            return
        print(f"Waiting {read_delay} seconds")
        # Wait for delay
        time.sleep(read_delay)
        # Trigger lights and sound
        self.triggerWaiting()
        # Perform RFID read
        self.setStatus("Waiting for MagicBand tap...")
        print("Waiting for RFID....")
        id = None
        try:
            id, text = self.reader.read()
            print(f"Read RFID: {id}")
        except CancelReadException:
            print("Got CancelReadException!!")
            self.setStatus("Standby")
            return
        except Exception as e:
            if not self.is_active:
                return
            print("Error reading RFID")
            print (e)
            self.onError("Error reading RFID")
        # Did we get an ID?
        if not self.is_active:
            return
        if id is not None:
            self.onReadMagicBand(id)
        else:
            print("Error reading RFID")
            self.onError("Error reading RFID")
    
    def cancelRead(self):
        """Sends the SIGUSR1 signal to interrupt any pending RFID reads."""
        # Set flag to tell ourself what we're doing
        self.should_cancel_read = True
        # Kill read thread
        #if self.thread is not None:
            #signal.pthread_kill(self.thread.ident, signal.SIGTSTP)
        #print("Sent kill signal")
        # Send signal
        #signal.raise_signal(signal.SIGUSR1)
    
    def on_signusr1(sig, frame):
        raise CancelReadException()

'''
    def cancelRead(self):
        """Sends the SIGUSR1 signal to interrupt any pending RFID reads."""
        # Set flag to tell ourself what we're doing
        self.should_cancel_read = True
        # Kill read thread
        #if self.thread is not None:
            #signal.pthread_kill(self.thread.ident, signal.SIGTSTP)
        #print("Sent kill signal")
        # Send signal
        #signal.raise_signal(signal.SIGUSR1)

    ######### MagicBand Functions #########

    def onReadMagicBand(self, band_id:str, isDisney:bool):
        """Looks up the band ID, and runs a matching sequence."""
        # Set state
        self.setState(State.Checking)
        # Stop any music playback
        self.stopMusic()
        # Convert band_id to str
        if not isinstance(band_id, str):
            print("Converting to string", flush=True)
            band_id = str(band_id)
        if print_band_id == True:
            print(f"Read MagicBand ID: {band_id}", flush=True)
        # Lookup sequence name for band id
        print("Looking up band id", flush=True)
        name = self.band_manager.lookupBandId(band_id, isDisney)
        # Get matching sequence
        print("Looking up sequence", flush=True)
        sequence = self.lookupSequence(name)
        if sequence is None:
            print("ERROR: found no sequnce to run!", flush=True)
            self.onError("Found no sequence to run!")
            return
        # Play a random tap-in preset
        self.setState(State.PlayingTapIn)
        self.playTapInPreset(self.getRandomTapInPreset())
        '''
        # Trigger success lights and sound
        self.setState(State.TapSuccess)
        self.triggerReadSuccess()
        # Wait
        time.sleep(settings['success_action_delay'])
        '''
        # Run sequence
        if not self.playSequence(sequence, name):
            # Error!
            self.onError("Failed to playback sequence")
    
    '''
    @staticmethod
    def bandsAppendFoundSeqName(band_dict, found_seq_names):
        if isinstance(band_dict, dict) and 'sequence' in band_dict:
            seq_name = band_dict.get('sequence')
            if seq_name is not None and isinstance(seq_name, str):
                found_seq_names.append(seq_name)

    def lookupBandId(self, band_id):
        """Looks up sequence name for band id"""
        found_seq_names = []     
        # Look for band_id
        if isinstance(band_id, str) and band_id in bands:
            print("Found band id", flush=True)
            found = bands.get(band_id)
            if isinstance(found, list):
                for item in found:
                    MagicBand.bandsAppendFoundSeqName(item, found_seq_names)
            elif isinstance(found, dict):
                MagicBand.bandsAppendFoundSeqName(found, found_seq_names)
        # Otherwise, use sequences for "unknown"
        if len(found_seq_names) < 1 and 'unknown' in bands:
            print("Did not find band id - using 'unknown'", flush=True)
            found = bands.get('unknown')
            if isinstance(found, list):
                for item in found:
                    MagicBand.bandsAppendFoundSeqName(item, found_seq_names)
            elif isinstance(found, dict):
                MagicBand.bandsAppendFoundSeqName(found, found_seq_names)
        # Now return a random item from found_seq_names (or None)
        if len(found_seq_names) > 0:
            print("Making random choice of names", flush=True)
            return random.choice(found_seq_names)
        else:
            print("No sequence name found", flush=True)
            return None
    '''

    def lookupSequence(self, name):
        """Looks up sequence for specified name"""
        found_sequences = []
        # Look for name
        if name is not None and isinstance(name, str):
            if name in sequences:
                found = sequences.get(name)
                if isinstance(found, dict):
                    return found
        # If we got here, we didn't find it
        return None


    ######### Trigger Functions for LEDs and sounds #########

    def triggerStartup(self):
        """Triggers 'Startup' LED sequence and sound. Called when app first launches."""
        # Play sound
        self.playSound(self.sound_startup)
        # Trigger LED sequence
        self.callLedPreset(settings['wled_preset_startup'])

    def triggerWaiting(self):
        """Triggers 'Waiting' LED sequence and sound. Called when app enters read loop and is waiting for an RFID read."""
        # Play sound
        self.playSound(self.sound_waiting)
        # Trigger LED sequence
        self.callLedPreset(settings['wled_preset_waiting'])

    def triggerReadSuccess(self):
        """Triggers 'Success' LED sequence and sound. Called after successful ID lookup."""
        # Play sound
        self.playSound(self.sound_success)
        # Trigger LED sequence
        self.callLedPreset(settings['wled_preset_success'])
        
    def triggerError(self):
        """Triggers 'Error' LED sequence and sound."""
        # Play sound
        self.playSound(self.sound_error)
        # Trigger LED sequence
        self.callLedPreset(settings['wled_preset_error'])
    
    def triggerBlackout(self):
        """Turns off LEDs, stops all sounds, and cancels any pending RFID read actions"""
        # Stop RFID reading
        #self.cancelRead()
        if self.read_once_enabled:
            self.read_once_enabled = False
            self.read_once_result = None
        # Stop all sound
        pygame.mixer.stop()
        pygame.mixer.music.stop()
        # Recall black LED preset
        self.callLedPreset(settings['wled_preset_black'])
    

    ######### Sound functions #########

    def loadAllSounds(self):
        """Loads all preset sound files"""
        self.sound_startup = self.loadSound(settings['sound_startup'])
        self.sound_waiting = self.loadSound(settings['sound_waiting'])
        self.sound_success = self.loadSound(settings['sound_success'])
        self.sound_error = self.loadSound(settings['sound_error'])

    def loadSound(self, filename: str):
        """Pre-loads the specified file as a PyGame sound object"""
        # Append 'Sounds/' to filename
        if filename is None or not isinstance(filename, str) or filename == '':
            return None
        if not filename.startswith('Sounds/'):
            filename = 'Sounds/' + filename
        # Check if file exists
        if not path.exists(filename):
            print("Missing sound file :" + filename, flush=True)
            return None
        # Load file into memory as a PyGame Sound instance
        try:
            return pygame.mixer.Sound(filename)
        except Exception as e:
            print("Error loading sound", flush=True)
            print(e, flush=True)
            return None

    def playSound(self, sound):
        """Plays the specified sound object."""
        print("Playing sound", flush=True)
        if sound is not None:
            try:
                pygame.mixer.Sound.play(sound)
            except Exception as e:
                print("Error playing sound", flush=True)
                print(e, flush=True)
    
    def playMusic(self, filename: str):
        """Plays the specified file as PyGame music"""
        # Check file
        if filename is None or not isinstance(filename, str) or filename == '':
            return
        if not path.exists(filename):
            print(f"Missing music file: {filename}", flush=True)
            return
        # Try playing as music
        try:
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
        except Exception as e:
            print(f"Error playing music file: {filename}", flush=True)
            print(e, flush=True)
    
    def stopMusic(self):
        """Stops any current music playback"""
        pygame.mixer.music.stop()
    
    
    ######### LED functions #########

    def callLedPreset(self, preset: int):
        """Makes a REST call to the internal WLED instance to recall a preset."""
        # Chec input
        if preset is None or not isinstance(preset, int):
            return
        # Construct URL to call
        url = f"http://{settings['wled_address']}/win&PL={preset}"
        print(f"Calling LED preset: {url}", flush=True)
        # Make REST call
        self.makeRestCall(url, 'GET')


    ######### Tap-In Preset functions #########

    def getRandomTapInPreset(self):
        """Returns a random tap-in preset id from the list"""
        if tap_in_presets is not None and isinstance(tap_in_presets, dict) and len(tap_in_presets) > 0:
            return random.choice(list(tap_in_presets.keys()))
        return None

    def playTapInPreset(self, id: str):
        # Find preset from list
        if id in tap_in_presets:
            preset = tap_in_presets.get(id)
            if isinstance(preset, dict):
                # Run tap-in preset
                self.lastTapInPreset = id
                # Call WLED
                if 'wled_preset' in preset and isinstance(preset['wled_preset'], int):
                    self.callLedPreset(preset['wled_preset'])
                # Play sound
                if 'sound' in preset and isinstance(preset['sound'], str):
                    sound = self.loadSound(preset['sound'])
                    if sound is not None:
                        self.playSound(sound)
                # Delay for duration of sound
                if 'duration' in preset and (isinstance(preset['duration'], int) or isinstance(preset['duration'], float)):
                    duration = preset['duration']
                    if duration > 0:
                        print(f"Waiting {duration} seconds for sound to finish", flush=True)
                        time.sleep(duration)
                # Done!
                return True
        return False

    ######### Sequence functions #########

    def playSequence(self, sequence, sequence_name: str = None):
        """Play the selected sequence"""        
        if sequence is None or not isinstance(sequence, dict):
            print("Invalid sequence", flush=True)
            return False
        # Disable further reads
        self.allowRead = False
        # Stop all music
        self.stopMusic()
        # Set status
        self.setState(State.PlayingSequence, sequence_name)
        # Log sequence with name
        if 'name' in sequence and isinstance(sequence['name'], str):
            print(f"Playing sequence: {sequence['name']} ({sequence_name})")
        # Is there an LED preset to recall?
        if 'wled_action' in sequence:
            self.callLedPreset(sequence.get('wled_action'))
        # Play music
        if 'music' in sequence:
            self.playMusic(sequence.get('music'))
        # Iterate actions
        if 'actions' in sequence:
            actions = sequence.get('actions')
            if isinstance(actions, list):
                for action in actions:
                    if not self.performAction(action):
                        return False
        # Done playing sequence
        # Setup next read
        delay = 0
        allow_read = True
        if 'wait_delay' in sequence and isinstance(sequence['wait_delay'], int):
            delay = sequence['wait_delay']
        if 'cancel_allowed' in sequence and isinstance(sequence['cancel_allowed'], bool):
            allow_read = sequence['cancel_allowed']
        if allow_read:
            read_delay = 2
        else:
            read_delay = -1
        self.startWaitModeTimer(delay, read_delay)
        return True


    ######### Action functions #########

    def performAction(self, action):
        """Performs the action based on type (URL, Brightsign)"""
        # Check for valid action dictionary
        if action is None or not isinstance(action, dict):
            print("Invalid action", flush=True)
            return False
        # Check type
        type = None
        if 'type' in action:
            type = action.get('type')
        if type is None or not isinstance(type, str):
            print("Invalid action type", flush=True)
            return False
        # Check for delay
        delay = 0
        if 'delay' in action:
            delay = action.get('delay')
            if not isinstance(delay, int):
                delay = 0
        if delay > 0:
            # Sleep
            time.sleep(delay)
        # Now actually do something...
        # URL type
        if type == 'url':
            print("URL Action", flush=True)
            # Get values
            url = None
            if 'url' in action:
                url = action.get('url')
            if url is None or not isinstance(url, str):
                print("Invalid URL", flush=True)
                return False
            method = None
            if 'method' in action:
                method = action.get('method')
            if method is None or not isinstance(method, str):
                method = "GET"
            # Perform REST call
            self.makeRestCall(url, method)
            # Done
            return True
        # Brightsign type
        elif type == 'brightsign':
            print("BrightSign Action", flush=True)
            # Get values
            address = None
            if 'address' in action:
                address = action.get('address')
            if address is None or not isinstance(address, str):
                print("Invalid BightSign player address", flush=True)
                return False
            port = None
            if 'port' in action:
                port = action.get('port')
            if port is None or not isinstance(port, int):
                print("Invalid BrightSign player port", flush=True)
                return False
            command = None
            if 'command' in action:
                command = action.get('command')
            if command is None or not isinstance(command, str):
                print("Invalid BrightSign player command")
                return False
            # Make UDP call to BrightSign player
            MagicBand.sendBrightSignCommand(address, port, command)
            return True
        elif type == 'chromateq':
            print("Chromateq Action", flush=True)
            # Get values
            address = None
            if 'address' in action:
                address = action.get('address')
            if address is None or not isinstance(address, str):
                print("Invalid Chromateq address", flush=True)
                return False
            port = None
            if 'port' in action:
                port = action.get('port')
            if port is None or not isinstance(port, int):
                print("Invalid Chromateq port", flush=True)
                return False
            scene_id = None
            if 'scene_id' in action:
                scene_id = action.get('scene_id')
            if scene_id is None or not isinstance(scene_id, int) or scene_id < 0:
                print("Invalid Chromateq scene_id")
                return False
            area = 0
            if 'area' in action:
                area = action.get('area')
                if area is None or not isinstance(area, int) or area < 0:
                    area = 0
            status = True
            if 'status' in action:
                status = action.get('status')
                if status is None or not isinstance(area, bool):
                    status = True
            # Make UDP call to Chromateq software
            MagicBand.sendChromateqSceneCommand(address, port, scene_id, area, status)
            return True
        # Unknown type
        else:
            print(f"Unknown action type: {type}", flush=True)
            return False
    

    ######### Web Hook Functions #########

    def makeRestCall(self, url, method = 'GET', playload = None, isJson = False):
        """Makes the specified HTTP call with an optional playlod and JSON content type."""
        print(f"REST Call: {method}: {url}", flush=True)
        try:
            # Use JSON content-type?
            if isJson:
                message_headers = {'Content-Type': 'application/json; charset=UTF-8'}
            else:
                message_headers = {}
            # Make HTTP call
            response = self.http_obj.request(
                uri = url,
                method = method,
                headers = message_headers
            )
            #print(response, flush=True
        except Exception as e:
            print("Error making REST call", flush=True)
            print(e, flush=True)
    

    ######### BrightSign Functions #########

    def sendBrightSignCommand(address: str, port: int, command: str):
        # Validate input
        if address is None or not isinstance(address, str):
            return
        if port is None or not isinstance(port, int) or port <= 0 or port > 65535:
            return
        if command is None or not isinstance(command, str):
            return
        print(f"Sending '{command}' to {address}:{port}")
        # Encode string to bytes
        data = command.encode("utf-8")
        #print(f"Message as bytes: {data}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(data, (address, port))
        print("Finished sending UDP")
    

    ######### Chromateq Functions #########

    def sendChromateqSceneCommand(address: str, port: int, scene_id: int, area: int, status: bool):
        # Validate input
        if address is None or not isinstance(address, str):
            return
        if port is None or not isinstance(port, int) or port <= 0 or port > 65535:
            return
        if scene_id is None or not isinstance(scene_id, int) or scene_id < 0:
            return
        if status is None or not isinstance(status, bool):
            return
        print(f"Sending Chromateq scene command -  scene_id:{scene_id}, area: {area}, status: {status}  to {address}:{port}")
        # Compose message as dict
        message = {
            "id": scene_id,
            "a": area,
            "s": status
        }
        # Encode as JSON
        json_str = json.dumps(message)
        # Encode JSN to bytes
        data = json_str.encode("utf-8")
        #print(f"Message as bytes: {data}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(data, (address, port))
        print("Finished sending UDP")
    

    ######### Web Api Calls #########
    
    def api_blackout(self):
        # Push event
        self.event_queue.put((2, AppEvent(AppEventType.Blackout, True)))
        
    def api_waitForTap(self):
        # Stop music
        self.stopMusic()
        # Push event
        self.event_queue.put((2, AppEvent(AppEventType.EnterWaitMode)))
    
    def api_allowRead(self):
        # Allow RFID reads (by 'starting' and thus cancelling the read time)
        self.startReadDelayTimer(0)
    
    def api_disableRead(self):
        # Disable RFID reads
        self.allowRead = False
    
    def api_playSequence(self, name):
        # Push event
        self.event_queue.put((2, AppEvent(AppEventType.PlaySequence, name)))
    
    def api_stopSequence(self):
        # Push event
        self.event_queue.put((2, AppEvent(AppEventType.StopSequence)))
    
    def api_getTapInPresetsList(self):
        # Create list of tap-in presets and names
        list = []
        # Iterate presets
        for key, value in tap_in_presets.items():
            if 'name' in value:
                list.append({"id": key, "name": value.get('name')})
            else:
                list.append({"id": key})
        # Return
        return list
    
    def api_playPlayTapInPreset(self, id: str):
        # Push event
        self.event_queue.put((2, AppEvent(AppEventType.PlayTapInPreset, id)))
    
    def api_getSequencesList(self):
        # Create list of sequences and names
        list = []
        # Iterate sequences
        for key, value in sequences.items():
            if 'name' in value:
                list.append({"id": key, "name": value.get('name')})
            else:
                list.append({"id": key})
        # Return
        return list
    
    '''
    def api_getKnownBandsList(self):
        # Create list of bands and sequence IDs
        list = []
        # Iterate bands
        for key, value in bands.items():
            if value is not None and isinstance(value, dict):
                name = None
                sequence = None
                if 'name' in value:
                    name = value.get('name')
                    if name is not None and not isinstance(name, str):
                        name = None
                if 'sequence' in value:
                    sequence = value.get('sequence')
                    if sequence is not None and not isinstance(sequence, str):
                        sequence = None
                list.append({"band_id": key, "name": name, "sequence": sequence})
        # Return
        return list
    '''
    
    def api_read_single_rfid(self) -> tuple[str, bool, bool]:
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

