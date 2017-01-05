function dodelete(path) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/delete/' + path);
    xhr.onload = function() { if (xhr.status === 200) { location.reload(); } else { alert('Failure'); } };
    xhr.send();
}

