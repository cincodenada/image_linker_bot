from joelbot import CleanupBot
import traceback
from time import sleep
import sys
import praw
import prawcore

from joelbot.util import log

bot = CleanupBot()

while True:
  try:
    bot.run()
    bot.print_report()
    bot.save_report()
    log("Sleeping for %d seconds...", bot.config['cleanup_time'])
    sleep(bot.config['cleanup_time'])

  except prawcore.exceptions.OAuthException:
    bot.auth_oauth()
  except KeyboardInterrupt:
    log("Shutting down...")
    sys.exit("Keyboard interrupt, shutting down...")
  except Exception, e:
    print traceback.format_exc()
    sleep(5)
