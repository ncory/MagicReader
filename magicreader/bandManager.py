import json
import random
import re

class BandManager:

    def __init__(self):
        self.bands = {}


######### Band Access #########
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
        if isinstance(band_id, str) and band_id in self.bands:
            print("Found band id", flush=True)
            BandManager.addBandSequenceNamesToList(self.bands, band_id, found_seq_names)
        # Alternatively, is it a Disney MagicBand id?
        if len(found_seq_names) < 1 and BandManager.isIdDisneyBand(band_id) and 'disney' in self.bands:
            print("Band has a Disney ID - using 'disney'", flush=True)
            BandManager.addBandSequenceNamesToList(self.bands, 'disney', found_seq_names)
        # Last fallback: use sequences for "unknown"
        if len(found_seq_names) < 1 and 'unknown' in self.bands:
            print("Did not find band id - using 'unknown'", flush=True)
            BandManager.addBandSequenceNamesToList(self.bands, 'unknown', found_seq_names)
        # Now return a random item from found_seq_names (or None)
        if len(found_seq_names) > 0:
            print("Making random choice of names", flush=True)
            return random.choice(found_seq_names)
        else:
            print("No sequence name found", flush=True)
            return None
    
    @staticmethod
    def addBandSequenceNamesToList(source: dict, key: str, dest: list):
        found = source.get(key)
        if isinstance(found, list):
            for item in found:
                BandManager.bandsAppendFoundSeqName(item, dest)
        elif isinstance(found, dict):
            BandManager.bandsAppendFoundSeqName(found, dest)

    def getKnownBandsList(self):
        # Create list of bands and sequence IDs
        list = []
        # Iterate bands
        for key, value in self.bands.items():
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


######### Add/Edit #########

    def updateBand(self, band_id, name, sequence_id):
        """Updates or adds a band. Will overwrite existing values."""
        self.bands[band_id] = {
            'name': name,
            'sequence': sequence_id
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
        try:
            # Load json file
            with open('bands.json', 'r') as file:
                data = json.load(file)
                # Validate loaded object
                if data is not None and isinstance(data, dict):
                    # Cache as our bands dict
                    self.bands = data
                    return True
        except:
            print("ERROR loading bands.json", flush=True)
        # If we got here we failed
        return False

    def saveToFile(self):
        try:
            # Save as json to file
            with open('bands.json', 'w') as file:
                json.dump(self.bands, file)
                return True
        except:
            print("ERROR saving bands.json", flush=True)
            pass
        # If we got here we failed
        return False
    

    ######### Is Disney Band #########

    REGEX_MAGICBAND = re.compile("5841[0-9]+")
    #REGEX_MAGICBAND = re.compile("04[0-9a-zA-Z]+80")
    REGEX_MAGICBAND_PLUS = re.compile("04[0-9a-zA-Z]+90")

    @staticmethod
    def isIdDisneyBand(id: str) -> bool:
        if not isinstance(id, str):
            id = str(id)
        if BandManager.isIdMagicBandOrMagicBand2(id):
            return True
        elif BandManager.isIdMagicBandOrMagicBand2(id):
            return True
        return False
    
    @staticmethod
    def isIdMagicBandOrMagicBand2(id: str) -> bool:
        if not isinstance(id, str):
            id = str(id)
        # Run RegEx on id
        if BandManager.REGEX_MAGICBAND.match(id):
            return True
        return False
    
    @staticmethod
    def isIdMagicBandPlus(id: str) -> bool:
        if not isinstance(id, str):
            id = str(id)
        # Run RegEx on id
        if BandManager.REGEX_MAGICBAND_PLUS.match(id):
            return True
        return False

    