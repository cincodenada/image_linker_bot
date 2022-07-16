from __future__ import print_function
from joelbot import BaseBot
from memedb import MemeDb

bot = BaseBot()
db = MemeDb(bot.config['bot']['dbfile'])

for candidate in db.c.execute("SELECT * FROM candidates ORDER BY ts DESC LIMIT 5"):
    comment = bot.r.comment(candidate['cid'])
    bot.log(u"\nPossible new image for %s\n%s",(comment.permalink, u'testing'))
