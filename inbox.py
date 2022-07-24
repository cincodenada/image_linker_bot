from joelbot import CommenterBot
from joelbot.util import log
import traceback
from time import sleep
import sys
import prawcore

bot = CommenterBot('all',useragent='inbox')

while True:
  try:
    bot.check_messages()
    log("Sleeping for %d seconds...", bot.config['inbox_time'])
    sys.stdout.flush()
    sleep(bot.config['inbox_time'])

  except prawcore.exceptions.OAuthException:
    bot.auth_oauth()
  except KeyboardInterrupt:
    log("Shutting down...")
    sys.exit("Keyboard interrupt, shutting down...")
  except Exception, e:
    print traceback.format_exc()
    sleep(5)
