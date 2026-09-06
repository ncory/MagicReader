#!/usr/bin/env python
from flask import Flask, jsonify, request, render_template, send_file, send_from_directory
from magicreader import MagicBand
from sequenceManager import SequenceManager
from sequence import Sequence
from werkzeug.datastructures import FileStorage
import platform
import os
import subprocess
import logging
import datetime
import io
import json
import shutil
import zipfile
#import requests
#from flask_restful import Api, Resource


def RunMagicApi(magicreader: MagicBand, port=8000):
    # Create app
    app = Flask("MagicReaderApi")
    # Supress logging all the damn requests
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)

    backup_labels = {
        "bands": "Bands",
        "sequences": "Sequences",
        "settings": "Settings",
        "sounds": "Sounds"
    }

    def get_backup_timestamp():
        return datetime.datetime.now().strftime("%Y-%m-%d %H%M")

    def get_backup_filename(backup_type, extension):
        label = backup_labels.get(backup_type, backup_type.title())
        return f"MagicReader {label} Backup {get_backup_timestamp()}.{extension}"

    def format_backup_file_size(bytes_value):
        if not isinstance(bytes_value, int) and not isinstance(bytes_value, float):
            return ""
        if bytes_value < 0:
            return ""
        if bytes_value < 1024:
            return f"{int(bytes_value)} B"
        units = ["KB", "MB", "GB"]
        value = bytes_value / 1024
        for index, unit in enumerate(units):
            if value < 1024 or index == len(units) - 1:
                decimals = 1 if value < 10 else 0
                return f"{value:.{decimals}f} {unit}"
            value = value / 1024
        return f"{int(bytes_value)} B"

    def load_json_file(filename):
        with open(filename, 'r') as file:
            return json.load(file)

    def make_json_backup_response(backup_type, data):
        json_data = json.dumps(data, indent=4)
        return app.response_class(
            json_data,
            mimetype='application/json',
            headers={
                "Content-Disposition": f"attachment; filename=\"{get_backup_filename(backup_type, 'json')}\""
            }
        )

    def normalize_band_backup(data):
        if not isinstance(data, dict):
            return None
        normalized = {}
        for band_id, band_data in data.items():
            if not isinstance(band_id, str) or band_id == '' or not isinstance(band_data, dict):
                continue
            if isinstance(band_data.get("actions"), list):
                continue
            name = band_data.get("name")
            if name is not None and not isinstance(name, str):
                name = None
            sequences = []
            sequence_data = band_data.get("sequences")
            if isinstance(sequence_data, list):
                sequences = [seq_id for seq_id in sequence_data if isinstance(seq_id, str) and seq_id != '']
            else:
                sequence_id = band_data.get("sequence")
                if isinstance(sequence_id, str) and sequence_id != '':
                    sequences = [sequence_id]
            normalized[band_id] = {
                "name": name,
                "sequences": sequences
            }
        return normalized

    def normalize_sequence_backup(data):
        if not isinstance(data, dict):
            return None
        normalized = {}
        for seq_id, sequence_data in data.items():
            if not isinstance(seq_id, str) or seq_id == '' or not isinstance(sequence_data, dict):
                continue
            if not isinstance(sequence_data.get("actions"), list):
                continue
            sequence = Sequence.createFromDict(sequence_data, seq_id)
            if sequence is not None:
                normalized[seq_id] = sequence
        return normalized

    def normalize_settings_backup(data):
        if not isinstance(data, dict):
            return None
        settings_data = data.get("settings") if isinstance(data.get("settings"), dict) else data
        if not isinstance(settings_data, dict):
            return None
        normalized = {}
        for key, value in settings_data.items():
            if isinstance(key, str):
                normalized[key] = value
        return normalized

    def get_safe_sound_zip_entries(zip_file):
        entries = []
        seen = set()
        for info in zip_file.infolist():
            if info.is_dir():
                continue
            filename = os.path.basename(info.filename.replace('\\', '/')).strip()
            filename = magicreader.soundManager.normalizeSoundFilename(filename)
            if filename is None or filename in seen or not magicreader.soundManager.isValidSoundFilename(filename):
                continue
            entries.append((info, filename))
            seen.add(filename)
        return entries

    def detect_restore_file(upload: FileStorage, index: int):
        filename = upload.filename or f"File {index + 1}"
        content = upload.read()
        upload.seek(0)
        detected = {
            "index": index,
            "filename": filename,
            "type": "unknown",
            "label": "Unknown",
            "valid": False,
            "summary": "Unsupported backup file."
        }
        if filename.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content), 'r') as zip_file:
                    entries = get_safe_sound_zip_entries(zip_file)
                    total_size = sum(info.file_size for info, _ in entries)
                    detected.update({
                        "type": "sounds",
                        "label": backup_labels["sounds"],
                        "valid": len(entries) > 0,
                        "summary": f"{len(entries)} sound file{'s' if len(entries) != 1 else ''}, {format_backup_file_size(total_size)}"
                    })
            except Exception as e:
                detected["summary"] = f"Invalid ZIP file: {e}"
            return detected
        if not filename.lower().endswith(".json"):
            return detected
        try:
            data = json.loads(content.decode('utf-8'))
        except Exception as e:
            detected["summary"] = f"Invalid JSON file: {e}"
            return detected
        settings_data = normalize_settings_backup(data)
        sequences_data = normalize_sequence_backup(data)
        bands_data = normalize_band_backup(data)
        lower_filename = filename.lower()
        if "settings" in lower_filename and settings_data is not None:
            detected.update({
                "type": "settings",
                "label": backup_labels["settings"],
                "valid": len(settings_data) > 0,
                "summary": f"{len(settings_data)} setting{'s' if len(settings_data) != 1 else ''}"
            })
        elif "sequence" in lower_filename and sequences_data is not None:
            detected.update({
                "type": "sequences",
                "label": backup_labels["sequences"],
                "valid": len(sequences_data) > 0,
                "summary": f"{len(sequences_data)} sequence{'s' if len(sequences_data) != 1 else ''}"
            })
        elif "band" in lower_filename and bands_data is not None:
            detected.update({
                "type": "bands",
                "label": backup_labels["bands"],
                "valid": len(bands_data) > 0,
                "summary": f"{len(bands_data)} band{'s' if len(bands_data) != 1 else ''}"
            })
        elif settings_data is not None and "settings" in data:
            detected.update({
                "type": "settings",
                "label": backup_labels["settings"],
                "valid": len(settings_data) > 0,
                "summary": f"{len(settings_data)} setting{'s' if len(settings_data) != 1 else ''}"
            })
        elif sequences_data is not None and len(sequences_data) > 0:
            detected.update({
                "type": "sequences",
                "label": backup_labels["sequences"],
                "valid": True,
                "summary": f"{len(sequences_data)} sequence{'s' if len(sequences_data) != 1 else ''}"
            })
        elif bands_data is not None and len(bands_data) > 0:
            detected.update({
                "type": "bands",
                "label": backup_labels["bands"],
                "valid": True,
                "summary": f"{len(bands_data)} band{'s' if len(bands_data) != 1 else ''}"
            })
        return detected

    def restore_json_file(upload):
        content = upload.read()
        upload.seek(0)
        return json.loads(content.decode('utf-8'))

    def restore_bands(upload, mode):
        backup_bands = normalize_band_backup(restore_json_file(upload))
        if backup_bands is None:
            return None
        if mode == "overwrite":
            magicreader.band_manager.bands = backup_bands
        else:
            merged = dict(magicreader.band_manager.bands)
            merged.update(backup_bands)
            magicreader.band_manager.bands = merged
        if not magicreader.band_manager.saveToFile():
            return None
        return len(backup_bands)

    def restore_sequences(upload, mode):
        backup_sequences = normalize_sequence_backup(restore_json_file(upload))
        if backup_sequences is None:
            return None
        if mode == "overwrite":
            magicreader.sequence_manager.sequences = backup_sequences
        else:
            magicreader.sequence_manager.sequences.update(backup_sequences)
        if not magicreader.sequence_manager.saveToFile():
            return None
        magicreader.sequence_manager.preCacheSoundFiles(magicreader.soundManager)
        return len(backup_sequences)

    def restore_settings(upload, mode):
        backup_settings = normalize_settings_backup(restore_json_file(upload))
        if backup_settings is None:
            return None
        settings_to_apply = backup_settings
        if mode != "overwrite":
            settings_to_apply = magicreader.getSettings()
            settings_to_apply.update(backup_settings)
        success, _ = magicreader.updateSettings(settings_to_apply)
        return len(backup_settings) if success else None

    def restore_sounds(upload, mode):
        content = upload.read()
        upload.seek(0)
        restored_count = 0
        with zipfile.ZipFile(io.BytesIO(content), 'r') as zip_file:
            entries = get_safe_sound_zip_entries(zip_file)
            if mode == "overwrite":
                for filename in magicreader.soundManager.listAllSoundFiles():
                    magicreader.soundManager.deleteSoundFile(filename)
            os.makedirs(magicreader.soundManager.getSoundsDirectory(), exist_ok=True)
            for info, filename in entries:
                file_path = magicreader.soundManager.getSoundFilePath(filename)
                if file_path is None:
                    continue
                if mode != "overwrite" and os.path.exists(file_path):
                    continue
                with zip_file.open(info) as source:
                    with open(file_path, 'wb') as dest:
                        shutil.copyfileobj(source, dest)
                magicreader.soundManager.removeSoundFromCache(filename)
                restored_count += 1
        magicreader.loadConfiguredSounds()
        magicreader.sequence_manager.preCacheSoundFiles(magicreader.soundManager)
        return restored_count


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

    @app.route('/backup.html')
    def page_backup():
        hostname = platform.node()
        host_url = f"http://{hostname}:{port}/"
        return render_template("backup.html", host_address=host_url)


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


    ###### Backup / Restore ######

    @app.route('/backup/bands')
    def backup_bands():
        return make_json_backup_response("bands", load_json_file('data/bands.json'))

    @app.route('/backup/sequences')
    def backup_sequences():
        return make_json_backup_response("sequences", load_json_file('data/sequences.json'))

    @app.route('/backup/settings')
    def backup_settings():
        return make_json_backup_response("settings", load_json_file('data/settings.json'))

    @app.route('/backup/sounds')
    def backup_sounds():
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for filename in magicreader.soundManager.listAllSoundFiles():
                file_path = magicreader.soundManager.getSoundFilePath(filename)
                if file_path is not None and os.path.exists(file_path):
                    zip_file.write(file_path, arcname=filename)
        zip_buffer.seek(0)
        response = send_file(
            zip_buffer,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=get_backup_filename("sounds", "zip")
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.route('/restore/preview', methods=['POST'])
    def restore_preview():
        uploads = request.files.getlist('files')
        previews = [detect_restore_file(upload, index) for index, upload in enumerate(uploads)]
        return {
            "result": "ok",
            "data": {
                "files": previews
            }
        }

    @app.route('/restore', methods=['POST'])
    def restore_files():
        mode = request.form.get('mode', 'merge')
        if mode not in ["merge", "overwrite"]:
            mode = "merge"
        try:
            selected_indexes = json.loads(request.form.get('selected_indexes', '[]'))
        except Exception:
            selected_indexes = []
        selected_indexes = [index for index in selected_indexes if isinstance(index, int)]
        selected_lookup = set(selected_indexes)
        uploads = request.files.getlist('files')
        results = []
        for index, upload in enumerate(uploads):
            if index not in selected_lookup:
                continue
            detected = detect_restore_file(upload, index)
            if not detected.get("valid"):
                results.append({
                    "filename": upload.filename,
                    "type": detected.get("type"),
                    "result": "error",
                    "summary": detected.get("summary")
                })
                continue
            restored_count = None
            if detected.get("type") == "bands":
                restored_count = restore_bands(upload, mode)
            elif detected.get("type") == "sequences":
                restored_count = restore_sequences(upload, mode)
            elif detected.get("type") == "settings":
                restored_count = restore_settings(upload, mode)
            elif detected.get("type") == "sounds":
                restored_count = restore_sounds(upload, mode)
            results.append({
                "filename": upload.filename,
                "type": detected.get("type"),
                "label": detected.get("label"),
                "result": "ok" if restored_count is not None else "error",
                "count": restored_count
            })
        if len(results) < 1:
            return {"result": "error", "data": {"message": "No valid backup files selected."}}
        if any(result.get("result") == "error" for result in results):
            return {"result": "error", "data": {"files": results}}
        return {"result": "ok", "data": {"files": results}}
    

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
