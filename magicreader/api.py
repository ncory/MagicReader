#!/usr/bin/env python
from flask import Flask, jsonify, request, render_template, send_from_directory
from magicreader import MagicBand
from sequenceManager import SequenceManager
from sequence import Sequence
import platform
import os
import subprocess
import logging
#import requests
#from flask_restful import Api, Resource


def RunMagicApi(magicreader: MagicBand, port=8000):
    # Create app
    app = Flask("MagicReaderApi")
    # Supress logging all the damn requests
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)


    ###### Pages ######

    @app.route('/')
    def index():
        hostname = platform.node()
        host_url = f"http://{hostname}:{port}/"
        return render_template("index.html", host_address=host_url)

    @app.route('/bands.html')
    def page_bands():
        hostname = platform.node()
        host_url = f"http://{hostname}:{port}/"
        return render_template("bands.html", host_address=host_url)

    @app.route('/settings.html')
    def page_settings():
        hostname = platform.node()
        host_url = f"http://{hostname}:{port}/"
        return render_template("settings.html", host_address=host_url)

    @app.route('/sequences.html')
    def page_sequences():
        hostname = platform.node()
        host_url = f"http://{hostname}:{port}/"
        return render_template("sequences.html", host_address=host_url)

    @app.route('/sounds.html')
    def page_sounds():
        hostname = platform.node()
        host_url = f"http://{hostname}:{port}/"
        return render_template("sounds.html", host_address=host_url)


    ###### Status ######

    @app.route("/status")
    def status():
        statusDict = {
            "state": magicreader.state.value,
            "status": magicreader.status,
            "isError": magicreader.isError,
            "allowRead": magicreader.allowRead,
            "sequenceActive": magicreader.isSequenceActive(),
            "activeSequenceId": magicreader.getActiveSequenceId()
        }
        return {"result": "ok", "status": statusDict}
    

    ###### Control ######

    @app.route('/control/blackout')
    def control_blackout():
        magicreader.api_blackout()
        #magicreader.triggerBlackout()
        return {"result": "ok"}
    
    @app.route('/control/wait')
    def control_wait():
        magicreader.api_waitForTap()
        #magicreader.triggerWaiting()
        return {"result": "ok"}
    
    @app.route('/control/allowRead')
    def control_allowRead():
        magicreader.api_allowRead()
        return {"result": "ok"}
    
    @app.route('/control/disableRead')
    def control_disableRead():
        magicreader.api_disableRead()
        return {"result": "ok"}
    
    @app.route('/control/sequence/<seq_id>')
    def control_sequence(seq_id):
        success = False
        # Get matching sequence
        sequence = magicreader.sequence_manager.getSequenceById(seq_id)
        # Play sequence
        if sequence is not None:
            magicreader.api_playSequence(seq_id)
            #success = magicreader.playSequence(sequence, sequence_name)
            return {"result": "ok"}
        # Failed if we got here
        return {"result": "error"}
    
    @app.route('/control/stopSequence')
    def control_stopSequence():
        magicreader.api_stopSequence()
        return {"result": "ok"}

    @app.route('/control/shutdown')
    def control_shutdown():
        os.system("nohup bash /home/pi/magicreader/soft-shutdown.sh &")
        #os.system("sudo shutdown now")
        return {"result": "ok"}

    @app.route('/control/reboot')
    def control_reboot():
        os.system("sudo systemctl start MagicReboot.service")
        #os.system("nohup bash /home/pi/magicreader/soft-reboot.sh &")
        #os.system("sudo reboot")
        return {"result": "ok"}

    @app.route('/control/magicWand')
    def control_magicWand():
        #os.system("/home/pi/magicreader/MagicWand.sh")
        os.system("sudo systemctl start MagicWand.service")
        return {"result": "ok"}


    ###### Settings ######

    @app.route('/settings')
    def get_settings():
        return {
            "result": "ok",
            "data": {
                "settings": magicreader.getSettings(),
                "schema": magicreader.getSettingsSchema(),
                "sounds": magicreader.soundManager.listAllSoundFiles()
            }
        }

    @app.route('/settings', methods=['PUT'])
    def put_settings():
        try:
            request_data = request.get_json()
            if request_data is not None and isinstance(request_data, dict):
                request_settings = request_data.get('settings', request_data)
                success, restart_required = magicreader.updateSettings(request_settings)
                if success:
                    result = get_settings()
                    result["restartRequired"] = restart_required
                    return result
        except Exception as e:
            print(f"ERROR saving settings: {e}", flush=True)
        return {"result": "error"}
    

    ###### Sequences ######

    @app.route('/sequenceNames')
    def get_sequenceNames():
        # Get list of sequences from app
        sequences = magicreader.sequence_manager.getSequenceNamesList()
        # Return data
        return {
            "result": "ok",
            "data": sequences
        }

    @app.route('/sequences')
    def get_sequences():
        # Get list of sequences from app
        sequences = magicreader.sequence_manager.getSequencesList()
        # Return data
        return {
            "result": "ok",
            "data": sequences
        }

    @app.route('/sequence/<seq_id>', methods=['PUT'])
    def put_sequence(seq_id):
        try:
            request_data = request.get_json()
            if request_data is not None and isinstance(request_data, dict):
                new_seq_id = seq_id
                if 'id' in request_data and isinstance(request_data.get('id'), str) and request_data.get('id') != '':
                    new_seq_id = request_data.get('id')
                sequence = Sequence.createFromDict(request_data, new_seq_id)
                if sequence is not None:
                    old_sequence = magicreader.sequence_manager.getSequenceById(seq_id)
                    if old_sequence is not None and seq_id != new_seq_id:
                        magicreader.sequence_manager.deleteSequence(seq_id)
                    if magicreader.sequence_manager.updateSequence(sequence):
                        if not magicreader.sequence_manager.saveToFile():
                            result = get_sequences()
                            result['result'] = "error"
                            return result
                        return get_sequences()
        except Exception as e:
            print(f"ERROR saving sequence: {e}", flush=True)
        return {"result": "error"}

    @app.route('/sequence/<seq_id>', methods=['DELETE'])
    def delete_sequence(seq_id):
        result = magicreader.sequence_manager.deleteSequence(seq_id)
        if result:
            if not magicreader.sequence_manager.saveToFile():
                result = get_sequences()
                result['result'] = "error"
                return result
            return get_sequences()
        return {"result": "error"}


    ###### Sounds ######

    @app.route('/sounds')
    def get_sounds():
        sounds = magicreader.soundManager.getSoundFilesList()
        disk = magicreader.soundManager.getSoundDiskUsage()
        return {
            "result": "ok",
            "data": {
                "sounds": sounds,
                "disk": disk
            }
        }

    @app.route('/sounds', methods=['POST'])
    def post_sound():
        upload = request.files.get('file')
        filename = request.form.get('filename')
        if magicreader.soundManager.saveSoundFile(upload, filename):
            return get_sounds()
        return {"result": "error"}

    @app.route('/sound/<path:filename>')
    def get_sound(filename):
        filename = magicreader.soundManager.normalizeSoundFilename(filename)
        if filename is None or not magicreader.soundManager.isValidSoundFilename(filename):
            return {"result": "error"}, 404
        file_info = magicreader.soundManager.getSoundFileInfo(filename)
        if file_info is None:
            return {"result": "error"}, 404
        return send_from_directory(magicreader.soundManager.getSoundsDirectory(), filename)

    @app.route('/sound/<path:filename>', methods=['PUT'])
    def put_sound(filename):
        try:
            request_data = request.get_json()
            if request_data is not None and isinstance(request_data, dict):
                new_filename = request_data.get('filename')
                if magicreader.soundManager.renameSoundFile(filename, new_filename):
                    return get_sounds()
        except Exception as e:
            print(f"ERROR renaming sound file: {e}", flush=True)
        return {"result": "error"}

    @app.route('/sound/<path:filename>', methods=['DELETE'])
    def delete_sound(filename):
        if magicreader.soundManager.deleteSoundFile(filename):
            return get_sounds()
        return {"result": "error"}
    

    ###### Bands ######

    @app.route('/bands')
    def get_bands():
        # Get list of bands from manager
        bands = magicreader.band_manager.getKnownBandsList()
        # Return data
        return {
            "result": "ok",
            "data": bands
        }
    
    @app.route('/band/<band_id>', methods=['PUT'])
    def put_band(band_id):
        try:
            # Get body as JSON data
            request_data = request.get_json()
            if request_data is not None and isinstance(request_data, dict):
                # Validate data
                name = None
                if 'name' in request_data:
                    name = request_data.get('name')
                    if not isinstance(name, str):
                        name = None
                seq_ids = []
                if 'sequences' in request_data:
                    sequences_data = request_data.get('sequences')
                    if isinstance(sequences_data, list):
                        seq_ids = [seq_id for seq_id in sequences_data if isinstance(seq_id, str)]
                elif 'sequence' in request_data:
                    seq_id = request_data.get('sequence')
                    if isinstance(seq_id, str):
                        seq_ids = [seq_id]
                # Process with band manager
                result = magicreader.band_manager.updateBand(band_id, name, seq_ids)
                if result:
                    # Done - now save to file
                    if not magicreader.band_manager.saveToFile():
                        # Error saving - get updated band list but return error
                        result = get_bands()
                        result['result'] = "error"
                        return result
                    else:
                        # Success - return updated band list
                        return get_bands()
        except Exception as e:
            pass
        # If we got here we failed
        return {"result": "error"}

    @app.route('/band/<band_id>', methods=['DELETE'])
    def delete_band(band_id):
        # Delete from band manager
        result = magicreader.band_manager.deleteBand(band_id)
        if result:
            # Done - now save to file
            if not magicreader.band_manager.saveToFile():
                # Error saving - get updated band list but return error
                result = get_bands()
                result['result'] = "error"
                return result
            else:
                # Success - return updated band list
                return get_bands()
        else:
            return {"result": "error"}
    
    @app.route('/bands/read', methods=['PUT'])
    def put_bandsRead():
        # Ask app to read a single RFID
        (id, isDisneyBand) = magicreader.api_read_single_rfid()
        # Did we get an ID?
        if id is None:
            # No - report error
            return {
                "result": "error",
                "data": None
            }
        else:
            # Yes - return ID
            return {
                "result": "ok",
                "data": {
                    "id": id,
                    "isDisneyBand": isDisneyBand
                }
            }

    

    # Run Flask app
    app.run(host="0.0.0.0", port=port, debug=False)
