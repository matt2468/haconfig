from flask import Flask, Response, redirect, request, abort
import os
import json

app = Flask(__name__)

HEADER = [
    '<!DOCTYPE html>',
    '<html lang="en-US">',
    '<head>',
    '<title>Cameras</title>',
    '<link rel="stylesheet" type="text/css" href="/indexer.css">',
    '<script type="text/javascript" src="/indexer.js"></script>',
    '</head>',
    '<body>'
]

FOOTER = [
    '</body>',
    '</html>'
]

DRIVEROOT = "/var/video"
CAMERAS = ['driveway', 'frontyard']

@app.route('/indexer.css')
def css():
    with open(os.path.join(os.path.dirname(__file__), "indexer.css")) as fp:
        return Response(fp.read(), mimetype='text/css')

@app.route('/indexer.js')
def js():
    with open(os.path.join(os.path.dirname(__file__), "indexer.js")) as fp:
        return Response(fp.read(), mimetype='text/javascript')
    
@app.route('/delete/<path:path>')
def delete(path):
    target = os.path.join(DRIVEROOT, path)
    if os.path.isfile(target) and target.endswith('mp4'):
        os.remove(target)
        snap = target[:-3] + "jpg"
        if os.path.isfile(snap):
            os.remove(snap)
        return json.dumps({'success':True}), 200, {'ContentType':'application/json'} 
    else:
        abort(403)

@app.route('/driveway')
@app.route('/frontyard')
def listing():
    try:
        camera = request.path[1:]
        diskpath = os.path.join(DRIVEROOT, camera)
        lines = list()
        for f in sorted(os.listdir(diskpath)):
            if f.endswith('mp4'):
                mp4 = os.path.join(camera, f)
                time = f[:-4].replace('_', ' ')
                snap = mp4[:-3] + "jpg"
                lines.append("<div class='box'><a href='/{}'><img src='/{}'/></a><span class='cap'>{}</span><button onclick='dodelete(\"{}\")'>X</button></div>".format(mp4, snap, time, mp4))

        return '\n'.join(HEADER + lines + FOOTER)
    except Exception as e: 
        return "Error {}".format(e)

@app.route('/')
def index():
    lines = ["<div class='box'><a href='/{}'>{}</a></div>".format(f, f) for f in CAMERAS]
    return '\n'.join(HEADER + lines + FOOTER)

@app.route('/<path:path>')
def default(path):
    return "Nope {}".format(path)

