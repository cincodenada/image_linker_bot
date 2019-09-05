import sqlite3
from joelbot import JoelBot

bot = JoelBot('ilb_test')

conn = sqlite3.connect(bot.config['bot']['dbfile'])
conn.row_factory = sqlite3.Row
conn.isolation_level = None
c = conn.cursor()
c_i = conn.cursor()

for msg in c.execute('''SELECT tid FROM inbox WHERE parent_id IS NULL AND tid NOT LIKE \'t4_%\''''):
    msgid = msg[0]
    print "Checking {}...".format(msgid)
    data = bot.r.get_info(thing_id=msgid)
    if data and data.parent_id:
        try:
            print "Updating message {} with parent id {}...".format(data.name, data.parent_id)
            c_i.execute('''UPDATE inbox SET parent_id=? WHERE tid=?''', (data.parent_id, data.name))
            conn.commit()
        except sqlite3.OperationalError:
            pass
