from flask import Flask
from flask import request
import os

app = Flask(__name__)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def hello_world(path):
    try:
        root = request.headers.get('IndexRoot')
        diskpath = os.path.join(root, path)
        lines = list()
        lines.append("<style>")
        lines.append("img  { max-width: 150px; }")
        lines.append(".cap { display: block; }")
        lines.append(".box { border: 1px solid grey; padding: 10px; vertical-align: top; display: inline-block; text-align: center; width: 180px; margin: 10px; }")
        lines.append("</style>")
        for f in sorted(os.listdir(diskpath)):
            if os.path.isdir(os.path.join(diskpath, f)):
                dir = os.path.join(path, f)
                lines.append("<div class='box'><a href='{}'>{}</a></div>".format(dir, f))
                
            elif f.endswith('mp4'):
                mp4 = os.path.join(path, f)
                time = f[:-4].replace('_', ' ')
                snap = mp4[:-3] + "jpg"
                lines.append("<div class='box'><a href='{}'><img src='{}'/></a><span class='cap'>{}</span></div>".format(mp4, snap, time))

        return '\n'.join(lines)
    except Exception as e: 
        return "Nope"

