import os
from os import path
# Import PyGame for sound playback and hide prompts
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame


class SoundManager:

    def __init__(self):
        print("Creating Sound Manager", flush=True)
        print("Starting PyGame", flush=True)
        # Setup PyGame (Pre init helps to get rid of sound lag)
        pygame.mixer.pre_init(44100, -16, 1, 4096 )
        pygame.mixer.init()
        pygame.init()
        # Dictionary to hold sound objects
        self.sounds = {}


######### Loading #########
    
    def preLoadSounds(self, soundList):
        """Preloads a list of sounds into the sound manager."""
        for sound in soundList:
            try:
                self.sounds[sound] = pygame.mixer.Sound(sound)
            except pygame.error as e:
                print(f"Error loading sound {sound}: {e}", flush=True)
    
    def preLoadSound(self, soundName: str, filename: str) -> bool:
        # Load sound file
        sound = self.loadSound(filename)
        if sound is not None:
            # Store in dictionary
            self.sounds[soundName] = sound
            return True
        else:
            print(f"Failed to load sound: {filename}", flush=True)
            return False

    def loadSound(self, filename: str) -> pygame.mixer.Sound:
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


######### Playback #########

    def playSound(self, soundName: str):
        """Plays the specified sound by name."""
        if soundName is None or not isinstance(soundName, str) or soundName == '':
            print("Invalid sound name provided", flush=True)
            return
        if soundName not in self.sounds:
            print(f"Sound '{soundName}' not found in sound manager", flush=True)
            return
        sound = self.sounds[soundName]
        if sound is None:
            print(f"Sound '{soundName}' is not loaded", flush=True)
            return
        # Play the sound object
        self.playSoundObject(sound)
    
    def playSoundFile(self, filename: str):
        # Load sound file
        sound = self.loadSound(filename)
        if sound is not None:
            # Play the sound object
            self.playSoundObject(sound)
        else:
            print(f"Failed to load sound file: {filename}", flush=True)

    def playSoundObject(self, sound: pygame.mixer.Sound):
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
        # Append 'Sounds/' to filename
        if filename is None or not isinstance(filename, str) or filename == '':
            return None
        if not filename.startswith('Sounds/'):
            filename = 'Sounds/' + filename
        # Check if file exists
        if not path.exists(filename):
            print("Missing msuic file :" + filename, flush=True)
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

    def stopAllSounds(self):
        """Stops all currently playing sounds."""
        pygame.mixer.stop()
        pygame.mixer.music.stop()


######### File Access #########

    def listAllSoundFiles(self):
        """Returns a list of all sound files in the Sounds directory."""
        sound_dir = 'Sounds'
        if not path.exists(sound_dir):
            print("Sounds directory does not exist", flush=True)
            return []
        # List all files in the Sounds directory
        return [f for f in os.listdir(sound_dir) if os.path.isfile(os.path.join(sound_dir, f))]
    
    def deleteSoundFile(self, filename: str) -> bool:
        """Deletes the specified sound file from the Sounds directory."""
        # Check filename and append 'Sounds/' if needed
        if filename is None or not isinstance(filename, str) or filename == '':
            print("Invalid filename provided", flush=True)
            return False
        if not filename.startswith('Sounds/'):
            filename = 'Sounds/' + filename
        if not path.exists(filename):
            print(f"Sound file '{filename}' does not exist", flush=True)
            # Task failed successfully
            return True
        # Try to remove file
        try:
            os.remove(filename)
            # Also remove from loaded sounds if present
            soundName = filename.split('/')[-1]
            if soundName in self.sounds:
                self.sounds.pop(soundName)
            # Success
            return True
        except Exception as e:
            # Failed
            print(f"Error deleting sound file '{filename}': {e}", flush=True)
            return False
