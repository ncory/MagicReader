import os
from os import path
import shutil
# Import PyGame for sound playback and hide prompts
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame


class SoundManager:
    SOUND_DIR = 'Sounds'
    SOUND_EXTENSIONS = {'.aac', '.flac', '.m4a', '.mp3', '.ogg', '.wav'}

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
        if filename is None or not isinstance(filename, str) or filename == '':
            self.clearSound(soundName)
            return True
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

    def clearSound(self, soundName: str):
        """Removes a named sound from the preloaded cache."""
        if soundName in self.sounds:
            self.sounds.pop(soundName)


######### Playback #########

    def playSound(self, soundName: str, loadIfNeeded: bool = True):
        """Plays the specified sound by name."""
        if soundName is None or not isinstance(soundName, str) or soundName == '':
            print("Invalid sound name provided", flush=True)
            return
        if soundName not in self.sounds:
            print(f"Sound '{soundName}' not found in sound manager", flush=True)
            if loadIfNeeded:
                # Attempt to load the sound file with the same name
                sound = self.loadSound(soundName)
                if sound is not None:
                    self.sounds[soundName] = sound
                else:
                    print(f"Failed to load sound '{soundName}'", flush=True)
                    return
            else:
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

    def playMusic(self, filename: str, stopCurrent: bool = True):
        """Plays the specified file as PyGame music"""
        # Append 'Sounds/' to filename
        if filename is None or not isinstance(filename, str) or filename == '':
            return None
        if not filename.startswith('Sounds/'):
            filename = 'Sounds/' + filename
        # Check if file exists
        if not path.exists(filename):
            print("Missing music file :" + filename, flush=True)
            return
        # Try playing as music
        try:
            pygame.mixer.music.load(filename)
            if stopCurrent:
                pygame.mixer.music.stop()
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
        sound_dir = self.SOUND_DIR
        if not path.exists(sound_dir):
            print("Sounds directory does not exist", flush=True)
            return []
        # List all files in the Sounds directory
        return sorted([
            f for f in os.listdir(sound_dir)
            if os.path.isfile(os.path.join(sound_dir, f)) and self.isValidSoundFilename(f)
        ], key=str.lower)

    def getSoundsDirectory(self):
        """Returns the absolute path to the Sounds directory."""
        return path.abspath(self.SOUND_DIR)

    def normalizeSoundFilename(self, filename: str):
        """Returns a direct Sounds filename, or None if the name is unsafe."""
        if filename is None or not isinstance(filename, str):
            return None
        filename = filename.strip()
        if filename.startswith(self.SOUND_DIR + '/'):
            filename = filename[len(self.SOUND_DIR) + 1:]
        if filename == '' or filename in ['.', '..'] or filename.startswith('.'):
            return None
        if '/' in filename or '\\' in filename or path.isabs(filename):
            return None
        return filename

    def isValidSoundFilename(self, filename: str):
        """Returns true if filename is safe and has a supported audio extension."""
        filename = self.normalizeSoundFilename(filename)
        if filename is None:
            return False
        ext = path.splitext(filename)[1].lower()
        return ext in self.SOUND_EXTENSIONS

    def getSoundFilePath(self, filename: str):
        """Returns the absolute path to a sound file, or None if invalid."""
        filename = self.normalizeSoundFilename(filename)
        if filename is None or not self.isValidSoundFilename(filename):
            return None
        return path.join(self.getSoundsDirectory(), filename)

    def getSoundFileInfo(self, filename: str):
        """Returns browser-friendly metadata for a sound file."""
        filename = self.normalizeSoundFilename(filename)
        file_path = self.getSoundFilePath(filename)
        if file_path is None or not path.exists(file_path) or not path.isfile(file_path):
            return None
        stat = os.stat(file_path)
        return {
            "filename": filename,
            "size": stat.st_size,
            "modified": stat.st_mtime,
        }

    def getSoundFilesList(self):
        """Returns metadata for all sound files in the Sounds directory."""
        sounds = []
        for filename in self.listAllSoundFiles():
            info = self.getSoundFileInfo(filename)
            if info is not None:
                sounds.append(info)
        return sounds

    def getSoundDiskUsage(self):
        """Returns disk usage for the filesystem that stores sound files."""
        sound_dir = self.getSoundsDirectory()
        usage_path = sound_dir if path.exists(sound_dir) else path.abspath('.')
        usage = shutil.disk_usage(usage_path)
        used = usage.total - usage.free
        return {
            "path": sound_dir,
            "total": usage.total,
            "used": used,
            "free": usage.free,
            "percent_used": round((used / usage.total) * 100, 1) if usage.total > 0 else 0
        }

    def removeSoundFromCache(self, filename: str):
        """Removes cached PyGame sound objects for a filename."""
        filename = self.normalizeSoundFilename(filename)
        if filename is None:
            return
        for soundName in [filename, self.SOUND_DIR + '/' + filename]:
            if soundName in self.sounds:
                self.sounds.pop(soundName)
    
    def deleteSoundFile(self, filename: str) -> bool:
        """Deletes the specified sound file from the Sounds directory."""
        filename = self.normalizeSoundFilename(filename)
        file_path = self.getSoundFilePath(filename)
        if file_path is None:
            print("Invalid filename provided", flush=True)
            return False
        if not path.exists(file_path):
            print(f"Sound file '{file_path}' does not exist", flush=True)
            # Task failed successfully
            return True
        # Try to remove file
        try:
            os.remove(file_path)
            self.removeSoundFromCache(filename)
            # Success
            return True
        except Exception as e:
            # Failed
            print(f"Error deleting sound file '{file_path}': {e}", flush=True)
            return False

    def renameSoundFile(self, filename: str, newFilename: str) -> bool:
        """Renames the specified sound file inside the Sounds directory."""
        filename = self.normalizeSoundFilename(filename)
        newFilename = self.normalizeSoundFilename(newFilename)
        old_path = self.getSoundFilePath(filename)
        new_path = self.getSoundFilePath(newFilename)
        if old_path is None or new_path is None:
            print("Invalid sound filename provided", flush=True)
            return False
        if not path.exists(old_path) or not path.isfile(old_path):
            print(f"Sound file '{old_path}' does not exist", flush=True)
            return False
        if path.exists(new_path):
            print(f"Sound file '{new_path}' already exists", flush=True)
            return False
        try:
            os.rename(old_path, new_path)
            self.removeSoundFromCache(filename)
            self.removeSoundFromCache(newFilename)
            return True
        except Exception as e:
            print(f"Error renaming sound file '{old_path}': {e}", flush=True)
            return False

    def saveSoundFile(self, file, filename: str = None) -> bool:
        """Saves an uploaded sound file into the Sounds directory."""
        if file is None:
            print("No sound file provided", flush=True)
            return False
        if filename is None or filename == '':
            filename = file.filename
        if isinstance(filename, str):
            filename = path.basename(filename.replace('\\', '/')).strip()
        filename = self.normalizeSoundFilename(filename)
        file_path = self.getSoundFilePath(filename)
        if file_path is None:
            print("Invalid upload filename provided", flush=True)
            return False
        if path.exists(file_path):
            print(f"Sound file '{file_path}' already exists", flush=True)
            return False
        try:
            os.makedirs(self.getSoundsDirectory(), exist_ok=True)
            file.save(file_path)
            self.removeSoundFromCache(filename)
            return True
        except Exception as e:
            print(f"Error saving sound file '{file_path}': {e}", flush=True)
            return False
