
/////// Global Variables ///////
var tapInPresets = null;
var sequences = null;
var bands = null;
var statusCache = null;


/*
function isString(val) {
    if (typeof val === 'string'
        || val instanceof String) {
            return true;
    }
    return false;
}
*/
const isString = v => v !== undefined && v !== null & (typeof v === 'string' || v instanceof String)
const isDict = v => v !== undefined && v !== null & (typeof v === 'object' || v instanceof Object)
const isBool = v => v !== undefined && v !== null & (typeof v === 'boolean' || v instanceof Boolean)

function getDataFromSuccessfulApiResponse(response, success="ok") {
    if ('result' in response) {
        if (isString(response.result)) {
            if (response.result === success) {
                // Success
                if ('data' in response) {
                    return response.data
                }
            }
        }
    }
    return null;
}

function getStringFromDict(dict, key) {
    if (dict.hasOwnProperty(key)) {
        let val = dict[key];
        return isString(val) ? val : null;
    }
    return null;
}

function getBoolFromDict(dict, key, returnFalseNotNull = true) {
    if (dict.hasOwnProperty(key)) {
        let val = dict[key];
        return isBool(val) ? val : returnFalseNotNull ? false : null;
    }
    return returnFalseNotNull ? false : null;
}


/////// Root Functions ///////

$(function() {
    // Initial updates
    updateStatus();
    getTapInPresetsList();
    getSequenceList();
    // Regular status updates
    setInterval(updateStatus, 1000);
});

function onLoadMainPage() {
    displaySequences();
    displayTapInPresets();
}

function onLoadBandsPage() {
    // Show bands table
    displayBands();
    // Refresh bands
    getKnownBandsList();
    // Update sequences in selects
    updateSequencesInSelect($('#newBandSequence'));
    updateSequencesInSelect($('#editBandSequence'));
}


/////// API Functions ///////

function makeApiCall(endpoint, method='GET', callback_success=null, callback_error=null, data=null) {
    url = endpoint
    $.ajax({
        url: url,
        method: method,
        success: callback_success,
        error: callback_error,
        contentType: 'application/json',
        data: data ? JSON.stringify(data) : null,
    });
}


/////// Control Functions ///////

function controlBlackout() {
    makeApiCall('/control/blackout');
}

function controlWait() {
    makeApiCall('/control/wait');
}

function controlStopSequence() {
    makeApiCall('/control/stopSequence');
}

function controlAllowRead() {
    makeApiCall('/control/allowRead');
}

function controlDisableRead() {
    makeApiCall('/control/disableRead');
}

function controlShutdown() {
    makeApiCall('/control/shutdown');
}

function controlReboot() {
    makeApiCall('/control/reboot');
}

function controlMagicWand() {
    makeApiCall('/control/magicWand');
}

function playTapInPreset(element) {
    // Get preset id from data-id
    let id = element.dataset.id
    console.debug('playing tap-in: ' + id);
    // Call API
    makeApiCall('/control/tapInPreset/' + id);
    console.debug('done with tap-in API call');
}

function playSequence(element) {
    // Get sequence name from data-sequence
    let sequence = element.dataset.sequence
    console.debug('sequence: ' + sequence);
    // Call API
    makeApiCall('/control/sequence/' + sequence);
}


/////// Status Functions ///////

function updateStatus() {
    // API Call
    makeApiCall('/status', 'GET',
        function(data, textStatus, jqXHR) {
            // Success
            statusCache = data.status;
            displayStatus();
        },
        function(jqXHR, textStatus, errorThrown) {
            // ERROR
            console.debug("ERROR loading status:" + errorThrown);
            statusCache = null;
            displayStatus();
        });
}

function displayStatus() {
    // Is there a status?
    if (statusCache != null && statusCache instanceof Object) {
        /// SUCCESS
        let statusDiv = $("#status-message");
        let allowReadDiv = $("#status-readAllowed");
        // Switch status
        switch (statusCache.state) {
            case "starting":
                statusDiv.text("Starting up...");
                break
            case "welcome":
                statusDiv.text("Playing welcome message");
                break;
            case "waitingForTap":
                statusDiv.text("Waiting for MagicBand tap");
                break;
            case "checking":
                statusDiv.text("Read ID - Checking");
                break;
            case "success":
                statusDiv.text("Read ID - Success!");
                break;
            case "playingTapIn":
                // Do we have a tap-in preset id?
                if (statusCache.lastTapInPreset != null && statusCache.lastTapInPreset != '') {
                    statusDiv.text("Playing Tap-In: " + getTapInName(statusCache.lastTapInPreset));
                }
                else {
                    statusDiv.text("Playing Tap-In");
                }
                break;
            case "playingSequence":
                // Do we have a sequence name?
                if (statusCache.status != null && statusCache.status != '') {
                    statusDiv.text("Playing Sequence: " + getSequenceName(statusCache.status));
                }
                else {
                    statusDiv.text("Playing Sequence");
                }
                break;
            case "blackout":
                statusDiv.text("Blackout");
                break;
            case "error":
                // Do we have a message?
                if (statusCache.status != null && statusCache.status != '') {
                    statusDiv.text("ERROR: " + statusCache.status);
                }
                else {
                    statusDiv.text("ERROR");
                }
                break;
                case "shutdown":
                statusDiv.text("Shutting down...");
                break;
            default:
                statusDiv.text("Unknown");
                break;
        }
        // Is error?
        statusDiv.toggleClass('bg-danger', statusCache.isError);
        // Fetch allwo read button
        let allowReadButton = $("#button-allowRead");
        allowReadButton.off('click')
        // Read allowed?
        if (statusCache.allowRead) {
            allowReadDiv.text("RFID Read Allowed");
            allowReadButton.text("Disable RFID Read")
            allowReadButton.on('click', controlDisableRead)
        } else {
            allowReadDiv.text("Ignoring RFID");
            allowReadButton.text("Enable RFID Read")
            allowReadButton.on('click', controlAllowRead)
        }
} else {
        /// ERROR
        $("#status-message").text("<< ERROR Loading Status >>").toggleClass('bg-danger', true);
        $("#status-readAllowed").text("");
    }
}


/////// Tap-In Functions ///////

function getTapInPresetsList() {
    // API Call
    makeApiCall('/tapInPresets', 'GET',
        function(response, textStatus, jqXHR) {
            // Success
            // Cache tap-in presets list
            tapInPresets = response.data;
            // Display tap-in presets buttons
            displayTapInPresets();
        },
        function(jqXHR, textStatus, errorThrown) {
            // ERROR
            console.debug("ERROR loading tap-in presets:" + errorThrown);
            tapInPresets = null;
            // Display tap-in presets buttons
            displayTapInPresets();
        });
}

function getTapInName(id) {
    if (tapInPresets != null && tapInPresets instanceof Array) {
        var foundName = id;
        tapInPresets.forEach((preset) => {
            if("id" in preset) {
                if (id == preset.id && "name" in preset) {
                    foundName = preset.name;
                }
            }
        });
        return foundName;
    }
    return id;
}

function displayTapInPresets() {
    // Remove all existing tap-in buttons
    let presetsDiv = $('#tapInPresets');
    presetsDiv.empty();
    // Do we have available presets?
    if (tapInPresets != null && tapInPresets instanceof Array) {
        /// Success
        tapInPresets.forEach((preset) => {
            // Is this a valid object?
            if (preset instanceof Object) {
                // Get ID
                if("id" in preset) {
                    let id = preset.id;
                    let presetName;
                    // Name or use id?
                    if ("name" in preset) {
                        presetName = preset.name;
                    } else {
                        presetName = id;
                    }
                    // Add button
                    addTapInPresetButton(presetsDiv, id, presetName);
                }
            }
        });
    } else {
        /// ERROR - Do nothing
    }
}

function addTapInPresetButton(div, id, name) {
    // Create button
    let newButton = $('<button type="button" class="sequence-button btn btn-primary" onclick="playTapInPreset(this)"></button>');
    // Set id
    newButton.attr("data-id", id);
    // Set name
    newButton.text(name);
    // Add to parent div
    div.append(newButton);
}


/////// Sequence Functions ///////

function getSequenceList() {
    // API Call
    makeApiCall('/sequences', 'GET',
        function(response, textStatus, jqXHR) {
            // Success
            // Cache sequences list
            sequences = response.data;
            // Display sequence buttons
            displaySequences();
            // Update in selects
            updateSequencesInSelect($('#newBandSequence'));
            updateSequencesInSelect($('#editBandSequence'));
        },
        function(jqXHR, textStatus, errorThrown) {
            // ERROR
            console.debug("ERROR loading sequences:" + errorThrown);
            sequences = null;
            // Display sequence buttons
            displaySequences();
            // Update in selects
            updateSequencesInSelect($('#newBandSequence'));
            updateSequencesInSelect($('#editBandSequence'));
        });
}

function displaySequences() {
    // Remove all existing sequence buttons
    let sequencesDiv = $('#sequences');
    sequencesDiv.empty();
    // Do we have available sequences?
    if (sequences != null && sequences instanceof Array) {
        /// Success
        sequences.forEach((seq) => {
            // Is this a valid object?
            if (seq instanceof Object) {
                // Get ID
                if("id" in seq) {
                    let id = seq.id;
                    let seqName;
                    // Name or use id?
                    if ("name" in seq) {
                        seqName = seq.name;
                    } else {
                        seqName = id;
                    }
                    // Add button
                    addSequenceButton(sequencesDiv, id, seqName);
                }
            }
        });
    } else {
        /// ERROR - Do nothing
    }
}

function addSequenceButton(div, id, name) {
    // Create button
    let newButton = $('<button type="button" class="sequence-button btn btn-primary" onclick="playSequence(this)"></button>');
    // Set id
    newButton.attr("data-sequence", id);
    // Set name
    newButton.text('Play "' + name + '"');
    // Add to parent div
    div.append(newButton);
}

function updateSequencesInSelect(sequencesSelect) {
    // Remove all existing sequence buttons
    sequencesSelect.empty();
    // Add empty/none option
    sequencesSelect.append($('<option selected value="">None</option>'));
    // Do we have available sequences?
    if (sequences != null && sequences instanceof Array) {
        /// Success
        sequences.forEach((seq) => {
            // Is this a valid object?
            if (seq instanceof Object) {
                // Get ID
                if("id" in seq && "name" in seq) {
                    let id = seq.id;
                    let seqName = seq.name;
                    // Add option
                    addSequenceSelectOption(sequencesSelect, id, seqName);
                }
            }
        });
    } else {
        /// ERROR - Do nothing
    }
}

function addSequenceSelectOption(select, id, name) {
    // Create button
    let newOption = $('<option>' + name + '</option>');
    // Set id
    newOption.attr("value", id);
    // Add to parent select
    select.append(newOption);
}

function getSequenceName(id) {
    if (sequences != null && sequences instanceof Array) {
        var foundName = id;
        sequences.forEach((seq) => {
            if("id" in seq) {
                if (id == seq.id && "name" in seq) {
                    foundName = seq.name;
                }
            }
        });
    }
    return foundName;
}



/////// Band Functions ///////

function getKnownBandsList() {
    // API Call
    makeApiCall('/bands', 'GET',
        function(response, textStatus, jqXHR) {
            // Cache bands list
            bands = getDataFromSuccessfulApiResponse(response);
            displayBands();
        },
        function(jqXHR, textStatus, errorThrown) {
            // ERROR
            console.debug("ERROR loading bands:" + errorThrown);
            bands = null;
            displayBands();
        });
}

function displayBands() {
    // Remove all existing bands frm table
    let bandsTableBody = $('#bandsTable_body');
    bandsTableBody.empty();
    // Do we have available bands?
    if (bands != null && bands instanceof Array) {
        /// Success
        bands.forEach((band) => {
            // Is this a valid object?
            if (band instanceof Object) {
                // Get ID
                if("band_id" in band) {
                    let band_id = band.band_id;
                    // Get name
                    let band_name = null;
                    if("name" in band) {
                        band_name = band.name;
                    }
                    if(band_name == null || !isString(band_name)) {
                        band_name = "";
                    }
                    // Get sequence name
                    let seq_name = null;
                    if ("sequence" in band) {
                        seq_name = getSequenceName(band.sequence);
                    }
                    if(seq_name == null || !isString(seq_name)) {
                        seq_name = "";
                    }
                    // Add rw
                    addBandToTable(bandsTableBody, band_id, band_name, seq_name);
                }
            }
        });
    } else {
        /// ERROR - Do nothing
    }
}

function addBandToTable(bandsTableBody, band_id, band_name, seq_name) {
    // Create row
    let tr = $("<tr>");
    // Add id
    let td_id = $('<td>').text(band_id);
    tr.append(td_id);
    // Add band name
    let td_name = $('<td>').text(band_name);
    tr.append(td_name);
    // Add sequence name
    let td_seq_name = $('<td>').text(seq_name);
    tr.append(td_seq_name);
    // Add buttons
    let td_buttons = $('<td>');
    let div_buttons = $('<div role="group">').addClass('btn-group');
    td_buttons.append(div_buttons);
    tr.append(td_buttons);
    // Button - Edit
    div_buttons.append($('<button type="button" class="btn btn-secondary" onclick="buttonBandEdit(this)">Edit</button>')
        .attr("data-sequence", band_id));
    // Button - Delete
    div_buttons.append($('<button type="button" class="btn btn-danger" onclick="buttonBandDelete(this)">Delete</button>')
        .attr("data-sequence", band_id));
    // Add row to table
    bandsTableBody.append(tr);
}

function buttonReadNewBand() {
    // Disable button and show spinner
    $('#button-readNewBand').attr("disabled", "disabled");
    $('#button-readerNewBand-spinner').toggleClass('d-none', false);
    $('#button-readNewBand-text').text("Reading New Band");
    $('#readNewBand-result').text("Waiting for RFID tap...");
    // API Call
    makeApiCall('/bands/read', 'PUT',
        function(response, textStatus, jqXHR) {
            // Success
            data = getDataFromSuccessfulApiResponse(response);
            // Did we get a returned ID?
            if (!isDict(data)) {
                // Nope
                $('#readNewBand-result').text("FAILED reading RFID. Server returned empty result.");
                enableReadNewBandButton();
                return;
            }
            // Get values
            let id = getStringFromDict(data, 'id');
            let isMagicBand = getBoolFromDict(data, 'isDisneyBand');
            // Yes
            let str = "Success! Read RFID:  " + id;
            if (isMagicBand) str = str + " (MagicBand)";
            $('#readNewBand-result').text(str);
            enableReadNewBandButton();
            // Show new band form and fill out id
            clearAddNewBandForm();
            $('#newBandBandId').val(id);
            $('#addNewBandDiv').toggleClass('d-none', false);
        },
        function(jqXHR, textStatus, errorThrown) {
            // ERROR
            console.debug("ERROR reading new band:" + errorThrown);
            $('#readNewBand-result').text("FAILED reading RFID. Error contacting server.");
            enableReadNewBandButton();
        });
}

function buttonAddNewBand() {
    // Clear form
    clearAddNewBandForm();
    // Show form
    $('#addNewBandDiv').toggleClass('d-none', false);
}

function buttonAddNewBandCancel() {
    // Hide form
    $('#addNewBandDiv').toggleClass('d-none', true);
    // Clear form
    clearAddNewBandForm();
}

function clearAddNewBandForm() {
    // Clear form
    $('#newBandBandId').val('');
    $('#newBandNickname').val('');
    $('#newBandSequence').val('');
}

function enableReadNewBandButton() {
    $('#button-readNewBand').removeAttr("disabled");
    $('#button-readerNewBand-spinner').toggleClass('d-none', true);
    $('#button-readNewBand-text').text("Read New Band");
}

function buttonAddNewBandSave() {
    // Get values
    let bandId = $('#newBandBandId').val();
    let bandNickname = $('#newBandNickname').val();
    let bandSequence = $('#newBandSequence').val();
    // Validate
    if (!isString(bandId) || bandId.length < 1) {
        alert("Please enter a valid Band ID.");
        return;
    }
    // API Call
    makeApiCall('/band/' + bandId, 'PUT',
        function(response, textStatus, jqXHR) {
            // Success
            data = getDataFromSuccessfulApiResponse(response);
            if (data != null && isDict(data)) {
                // Success - Add to table
                getKnownBandsList();
                buttonAddNewBandCancel();
            } else {
                alert("Failed to add new band. Server returned empty result.");
            }
        },
        function(jqXHR, textStatus, errorThrown) {
            // ERROR
            console.debug("ERROR adding new band:" + errorThrown);
            alert("Failed to add new band. Error contacting server.");
        },
        {id: bandId, name: bandNickname, sequence: bandSequence});
}

function getBandFromCache(band_id) {
    // Check if bands are cached
    if (bands != null && bands instanceof Array) {
        // Loop through bands
        for (let i = 0; i < bands.length; i++) {
            let band = bands[i];
            // Check if band_id matches
            if (band instanceof Object && 'band_id' in band && band.band_id === band_id) {
                // Found band
                return band;
            }
        }
    }
    // Not found
    return null;
}

function buttonBandEdit(element) {
    // Get band id from data-sequence
    let band_id = element.dataset.sequence;
    console.debug('band_id: ' + band_id);
    // Get band from cache
    let band = getBandFromCache(band_id);
    if (band == null) return;
    // Get band data
    let bandNickname = getStringFromDict(band, 'name');
    let bandSequence = getStringFromDict(band, 'sequence');
    // Populate edit bands form
    $('#editBandBandId').val(band_id);
    $('#editBandNickname').val(bandNickname);
    $('#editBandSequence').val(bandSequence);
    // Show edit bands form
    $('#editBandModal').modal('show');
}

function buttonEditBandSave() {
    // Get values
    let bandId = $('#editBandBandId').val();
    let bandNickname = $('#editBandNickname').val();
    let bandSequence = $('#editBandSequence').val();
    // Validate
    if (!isString(bandId) || bandId.length < 1) {
        alert("Please enter a valid Band ID.");
        return;
    }
    // API Call
    makeApiCall('/band/' + bandId, 'PUT',
        function(response, textStatus, jqXHR) {
            // Success
            data = getDataFromSuccessfulApiResponse(response);
            if (data != null && isDict(data)) {
                // Success - Add to table
                getKnownBandsList();
                // Hide modal
                $('#editBandModal').modal('hide');
            } else {
                alert("Failed to add new band. Server returned empty result.");
            }
        },
        function(jqXHR, textStatus, errorThrown) {
            // ERROR
            console.debug("ERROR adding new band:" + errorThrown);
            alert("Failed to add new band. Error contacting server.");
        },
        {id: bandId, name: bandNickname, sequence: bandSequence});
}

function buttonBandDelete(element) {
    // Get band id from data-sequence
    let band_id = element.dataset.sequence;
    console.debug('band_id: ' + band_id);
    // Confirm
    if (!confirm("Are you sure you want to delete band " + band_id + "?")) {
        return;
    }
    // API Call
    makeApiCall('/band/' + band_id, 'DELETE',
        function(response, textStatus, jqXHR) {
            // Success
            data = getDataFromSuccessfulApiResponse(response);
            if (data != null && isDict(data)) {
                // Success - Remove from table
                getKnownBandsList();
            } else {
                alert("Failed to delete band. Server returned empty result.");
            }
        },
        function(jqXHR, textStatus, errorThrown) {
            // ERROR
            console.debug("ERROR deleting band:" + errorThrown);
            alert("Failed to delete band. Error contacting server.");
        });
}


/////// System Control Modals ///////

function showControlModalMagicWand() {
    $('#controlModalContent')
        .removeClass('modal-background-reboot')
        .removeClass('modal-background-shutdown')
        .addClass('modal-background-reboot');
    showControlModal('magicWand');
}

function showControlModalReboot() {
    $('#controlModalContent')
        .removeClass('modal-background-magicWand')
        .removeClass('modal-background-shutdown')
        .addClass('modal-background-reboot');
    showControlModal('reboot');
}

function showControlModalShutdown() {
    $('#controlModalContent')
        .removeClass('modal-background-magicWand')
        .removeClass('modal-background-reboot')
        .addClass('modal-background-shutdown');
    showControlModal('shutdown');
}

function showControlModal(name) {
    // Load modal content
    let modalContent = $('#controlModalContent');
    modalContent.empty();
    modalContent.load("/static/modal-control-" + name + ".html",
        function(response, status, xhr) {
            if (status === "error") {
                console.debug("ERROR loading modal content: " + xhr.status + " " + xhr.statusText);
                modalBody.text("Error loading modal content.");
            }
        }); 
    // Show modal
    $('#controlModal').modal('show');
}

function confirmControlModalMagicWand() {
    // Call API
    controlMagicWand();
    // Hide modal
    $('#controlModal').modal('hide');
}

function confirmControlModalReboot() {
    // Call API
    controlReboot();
    // Hide modal
    $('#controlModal').modal('hide');
}

function confirmControlModalShutdown() {
    // Call API
    controlShutdown();
    // Hide modal
    $('#controlModal').modal('hide');
}

