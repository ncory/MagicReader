#!/usr/bin/env python
from flask import Flask, jsonify, request, render_template
from magicreader import MagicBand
import platform
import os
#import requests
#from flask_restful import Api, Resource


def RunMagicApi(magicreader: MagicBand, port=8000):
    # Create app
    app = Flask("MagicReaderApi")

    @app.route('/')
    def index():
        hostname = platform.node()
        host_url = f"http://{hostname}:{port}/"
        return render_template("index.html", host_address=host_url)

    @app.route("/status")
    def status():
        statusDict = {
            "state": magicreader.state.value,
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
    
    @app.route('/control/sequence/<sequence_name>')
    def control_sequence(sequence_name):
        success = False
        # Get matching sequence
        sequence = magicreader.lookupSequence(sequence_name)
        # Play sequence
        if sequence is not None:
            magicreader.api_playSequence(sequence_name)
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
        os.system("sudo shutdown now")
        return {"result": "ok"}

    @app.route('/control/reboot')
    def control_reboot():
        os.system("sudo reboot")
        return {"result": "ok"}
    

    ###### Sequences ######

    @app.route('/sequences')
    def get_sequences():
        # Get list of sequences from app
        sequences = magicreader.api_getSequencesList()
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
                result = app.band_manager.updateBand(band_id, name, seq_id)
                if result:
                    # Done - now save to file
                    if not app.band_manager.saveToFile():
                        # Error saving - get updated band list but return error
                        result = get_bands()
                        result['result'] = "error"
                        return result
                    else:
                        # Success - return updated band list
                        return get_bands()
        except:
            pass
        # If we got here we failed
        return {"result": "error"}

    @app.route('/band/<band_id>', methods=['DELETE'])
    def delete_band(band_id):
        # Delete from band manager
        result = app.band_manager.deleteBand(band_id)
        if result:
            # Done - now save to file
            if not app.band_manager.saveToFile():
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
        (id, isMagicBand, isMagicBandPlus) = magicreader.api_read_single_rfid()
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
                    "isMagicBand": isMagicBand,
                    "isMagicBandPlus": isMagicBandPlus
                }
            }

    

    # Run Flask app
    app.run(host="0.0.0.0", port=port)
