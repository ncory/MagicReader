#!/usr/bin/env python
from flask import Flask, jsonify, request, render_template
from magicreader import MagicBand
from sequenceManager import SequenceManager
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


    ###### Status ######

    @app.route("/status")
    def status():
        statusDict = {
            "state": magicreader.state.value,
            "lastTapInPreset": magicreader.lastTapInPreset,
            "status": magicreader.status,
            "isError": magicreader.isError,
            "allowRead": magicreader.allowRead
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
    
    @app.route('/control/tapInPreset/<id>')
    def control_tapInPreset(id):
        success = False
        # Play tap-in preset
        if id is not None:
            magicreader.api_playPlayTapInPreset(id)
            return {"result": "ok"}
        # Failed if we got here
        return {"result": "error"}
    
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
    

    ###### Tap-In Presets ######

    @app.route('/tapInPresets')
    def get_tapInPresets():
        # Get list of sequences from app
        presets = magicreader.api_getTapInPresetsList()
        # Return data
        return {
            "result": "ok",
            "data": presets
        }
    

    ###### Sequences ######

    @app.route('/sequences')
    def get_sequences():
        # Get list of sequences from app
        sequences = magicreader.sequence_manager.getSequenceNamesList()
        # Return data
        return {
            "result": "ok",
            "data": sequences
        }
    

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
                seq_id = None
                if 'sequence' in request_data:
                    seq_id = request_data.get('sequence')
                    if not isinstance(seq_id, str):
                        seq_id = None
                # Process with band manager
                result = magicreader.band_manager.updateBand(band_id, name, seq_id)
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
