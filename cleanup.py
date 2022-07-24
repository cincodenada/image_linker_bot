from joelbot import CleanupBot
import traceback
from time import sleep
import sys
import praw
import prawcore

bot = CleanupBot()

while True:
  try:
    bot.run()
    bot.print_report()
    bot.save_report()
    bot.log("Sleeping for %d seconds...", bot.config['cleanup_time'])
    sleep(bot.config['cleanup_time'])

  except prawcore.exceptions.OAuthException:
    bot.refresh_oauth()
  except KeyboardInterrupt:
    bot.log("Shutting down...")
    sys.exit("Keyboard interrupt, shutting down...")
  except Exception, e:
    print traceback.format_exc()
    sleep(5)
