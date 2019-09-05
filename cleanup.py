from joelbot import JoelBot
import traceback
from time import sleep
import sys
import praw

bot = JoelBot('all',useragent='cleanup')

while True:
  try:
    bot.cleanup()
    bot.log("Sleeping for %d seconds...", bot.config['bot']['cleanup_time'])
    sleep(bot.config['bot']['cleanup_time'])

  except praw.errors.OAuthException:
    bot.refresh_oauth()
  except KeyboardInterrupt:
    bot.log("Shutting down...")
    sys.exit("Keyboard interrupt, shutting down...")
  except Exception, e:
    print traceback.format_exc()
    sleep(5)
