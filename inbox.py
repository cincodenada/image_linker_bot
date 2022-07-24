from joelbot import InboxBot
from joelbot.util import log
import traceback
import time
import sys
import prawcore

bot = InboxBot()

last_restart = time.time()
too_fast = 5

while True:
  try:
    bot.check_messages()
    log("Sleeping for %d seconds...", bot.config['inbox_time'])
    sys.stdout.flush()
    time.sleep(bot.config['inbox_time'])

  except prawcore.exceptions.OAuthException:
    bot.auth_oauth()
  except KeyboardInterrupt:
    log("Shutting down...")
    sys.exit("Keyboard interrupt, shutting down...")
  except Exception, e:
    print traceback.format_exc()
    if time.time() - last_restart < too_fast:
        sys.exit("Restarting too fast!")
    time.sleep(5)
