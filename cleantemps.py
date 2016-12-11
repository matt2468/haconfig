#!/usr/bin/env python3 
import json
import sqlite3
try:
    # Find errneous temp states reported by the thermostat
    # If SET is outside (50,85) or MEASURED is outside (45,100) delete
    conn = sqlite3.connect("home-assistant_v2.db")
    todel = list()
    for row in conn.execute("select state_id,attributes from states where domain='climate'"):
        attr = json.loads(row[1])
        if attr.get('temperature', 70) not in range(50, 85) or attr.get('current_temperature', 70) not in range(45, 100):
            todel.append(str(row[0]))
    count = conn.execute("delete from states where state_id in ({})".format(','.join(todel))).rowcount
    print("Deleted {} rows".format(count))
    conn.commit()
    conn.close()
except Exception as e:
    print("Failed to clean: {}".format(e))

