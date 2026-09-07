import jsonStore
import random

class BandManager:
    FILENAME = 'bands.json'

    def __init__(self):
        self.bands = {}


######### Band Access #########
    @staticmethod
    def appendBandSequenceNames(band_dict, found_seq_names):
        if not isinstance(band_dict, dict):
            return
        sequences = band_dict.get('sequences')
        if isinstance(sequences, list):
            for seq_name in sequences:
                if isinstance(seq_name, str) and seq_name != '':
                    found_seq_names.append(seq_name)
        seq_name = band_dict.get('sequence')
        if isinstance(seq_name, str) and seq_name != '':
            found_seq_names.append(seq_name)

    def lookupBandId(self, band_id:str, isDisney:bool) -> str:
        """Looks up sequence name for band id"""
        found_seq_names = []
        # Look for band_id
        if isinstance(band_id, str) and band_id in self.bands:
            print("Found band id", flush=True)
            BandManager.addBandSequenceNamesToList(self.bands, band_id, found_seq_names)
        # Alternatively, is it a Disney MagicBand id?
        if len(found_seq_names) < 1 and isDisney and 'disney' in self.bands:
            print("Band has a Disney ID - using 'disney'", flush=True)
            BandManager.addBandSequenceNamesToList(self.bands, 'disney', found_seq_names)
        # Last fallback: use sequences for "unknown"
        if len(found_seq_names) < 1 and 'unknown' in self.bands:
            print("Did not find band id - using 'unknown'", flush=True)
            BandManager.addBandSequenceNamesToList(self.bands, 'unknown', found_seq_names)
        # Now return a random item from found_seq_names (or None)
        chosenSeq = None
        if len(found_seq_names) > 0:
            print("Making random choice of sequence names", flush=True)
            chosenSeq = random.choice(found_seq_names)
        else:
            print("No sequence name found", flush=True)
            chosenSeq = None
        return chosenSeq
    
    @staticmethod
    def addBandSequenceNamesToList(source: dict, key: str, dest: list):
        found = source.get(key)
        if isinstance(found, list):
            for item in found:
                BandManager.appendBandSequenceNames(item, dest)
        elif isinstance(found, dict):
            BandManager.appendBandSequenceNames(found, dest)

    def getKnownBandsList(self):
        # Create list of bands and sequence IDs
        found = []
        # Iterate bands
        for key, value in self.bands.items():
            if value is not None and isinstance(value, dict):
                name = None
                if 'name' in value:
                    name = value.get('name')
                    if name is not None and not isinstance(name, str):
                        name = None
                sequences = []
                BandManager.appendBandSequenceNames(value, sequences)
                found.append({"band_id": key, "name": name, "sequences": sequences})
        # Return
        return found


######### Add/Edit #########

    def updateBand(self, band_id, name, sequence_ids: list = None):
        """Updates or adds a band. Will overwrite existing values."""
        sequences = []
        if isinstance(sequence_ids, list):
            for sequence_id in sequence_ids:
                if isinstance(sequence_id, str) and sequence_id != '':
                    sequences.append(sequence_id)
        elif isinstance(sequence_ids, str) and sequence_ids != '':
            sequences.append(sequence_ids)
        self.bands[band_id] = {
            'name': name,
            'sequences': sequences
        }
        return True
    
    def deleteBand(self, band_id):
        """Deletes band. Returns True if band was removed or already wasn't in list."""
        if band_id is None:
            return False
        if band_id in self.bands:
            # Remove
            self.bands.pop(band_id)
        return True


######### File Access #########

    def loadFromFile(self):
        # Create the runtime file from the shipped default if this is a fresh install
        jsonStore.seedDataFileFromDefault(BandManager.FILENAME)
        # Load json file (falls back to the .bak copy if the main file is corrupt)
        data = jsonStore.loadJson(jsonStore.dataPath(BandManager.FILENAME))
        # Validate loaded object
        if data is not None and isinstance(data, dict):
            # Cache as our bands dict
            self.bands = data
            return True
        print("ERROR loading bands.json", flush=True)
        # If we got here we failed
        return False

    def saveToFile(self):
        return jsonStore.saveJsonAtomic(jsonStore.dataPath(BandManager.FILENAME), self.bands)
    

