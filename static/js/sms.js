function fromlist(thelist) {
    rlist = document.querySelector("#recipientlist");
    var idx = thelist.selectedIndex;
    var txt = thelist.options[idx].text;
    var item = thelist.options[idx].value;
    var options = document.querySelector("#recipientlist").options;
    var found = false;

    for (var counter=0; counter < options.length; counter++) {
        if (options[counter].value == item) {
            found = true;
        }
    }
    
    if (!found) {
        let newoption = document.createElement('option');
        newoption.value = item;
        newoption.text = txt;
        rlist.add(newoption, undefined);
    }
}

function torecipient() {
    memberlist = document.querySelector("#memberlist");
    recipientlist = document.querySelector("#recipientlist");
    var index = memberlist.selectedIndex;
    var item = memberlist.options[index].value;
    var text = memberlist.options[index].text;
    var options = recipientlist.options;
    var found = false;

    for (var counter=0; counter < options.length; counter++) {
        if (options[counter].value == item) {
            found = true;
        }
    }

    if (!found) {
        let newoption = document.createElement('option');
        newoption.value = item;
        newoption.text = text;
        recipientlist.add(newoption, undefined);
    }
}

function tolist(thelist) {
    thelist.remove(thelist.selectedIndex);
}

function deleterecipient() {
    var recipientlist = document.querySelector("#recipientlist");
    recipientlist.remove(recipientlist.selectedIndex);
}

function getrecipients() {
    var recipientlist = document.querySelector("#recipientlist");
    for (var counter=0; counter < recipientlist.options.length; counter++) {
        recipientlist.options[counter].selected = true;
    }

    return true;
}