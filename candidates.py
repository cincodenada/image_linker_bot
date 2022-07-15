from __future__ import print_function
from joelbot import BaseBot
from memedb import MemeDb

bot = BaseBot()
db = MemeDb(bot.config['bot']['dbfile'])

for candidate in db.c.execute("SELECT * FROM candidates ORDER BY ts DESC LIMIT 20"):
    comment = bot.r.comment(candidate['cid'])
    print(candidate['key'], "https://reddit.com/%s" % (comment.permalink,))
