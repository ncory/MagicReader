
/////// Global Variables ///////
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
    displaySequences();
    displayBands();
    getSequenceList();
    getKnownBandsList();
    // Regular status updates
    setInterval(updateStatus, 1000);
});


/////// API Functions ///////

function makeApiCall(endpoint, method='GET', callback_success=null, callback_error=null) {
    url = endpoint
    $.ajax({
        url: url,
        method: method,
        success: callback_success,
        error: callback_error
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


/////// Sequence Functions ///////

function getSequenceList() {
    // API Call
    makeApiCall('/sequences', 'GET',
        function(response, textStatus, jqXHR) {
            // Success
            // Cache sequences list
            sequences = response.data;
            displaySequences();
        },
        function(jqXHR, textStatus, errorThrown) {
            // ERROR
            console.debug("ERROR loading sequences:" + errorThrown);
            sequences = null;
            displaySequences();
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
    div_buttons.append($('<button type="button" class="btn btn-secondary" onclick="clickBandEdit(this)">Edit</button>')
        .attr("data-sequence", band_id));
    // Button - Delete
    div_buttons.append($('<button type="button" class="btn btn-danger" onclick="clickBandDelete(this)">Delete</button>')
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
            let isMagicBand = getBoolFromDict(data, 'isMagicBand');
            let isMagicBandPlus = getBoolFromDict(data, 'isMagicBandPlus');
            // Yes
            let str = "Success! Read RFID:  " + id;
            if (isMagicBandPlus) str = str + " (MagicBand Plus)";
            else if (isMagicBand) str = str + " (MagicBand 1 or 2)";
            $('#readNewBand-result').text(str);
            enableReadNewBandButton();
        },
        function(jqXHR, textStatus, errorThrown) {
            // ERROR
            console.debug("ERROR reading new band:" + errorThrown);
            $('#readNewBand-result').text("FAILED reading RFID. Error contacting server.");
            enableReadNewBandButton();
        });
}

function enableReadNewBandButton() {
    $('#button-readNewBand').removeAttr("disabled");
    $('#button-readerNewBand-spinner').toggleClass('d-none', true);
    $('#button-readNewBand-text').text("Read New Band");
}

