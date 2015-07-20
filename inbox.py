from joelbot import JoelBot
import traceback
from time import sleep
import sys

bot = JoelBot('all',useragent='inbox')

while True:
  try:
    bot.check_messages()
    bot.log("Sleeping for %d seconds...", bot.config['bot']['inbox_time'])
    sys.stdout.flush()
    sleep(bot.config['bot']['inbox_time'])

  except KeyboardInterrupt:
    bot.log("Shutting down...")
    sys.exit("Keyboard interrupt, shutting down...")
  except Exception, e:
    print traceback.format_exc()
    sleep(5)
