#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import sys
import signal
import time
from pprint import pformat
import prawcore
import traceback

from joelbot.util import log
from linkerbot import LinkerBot, EmptyBodyError

def handle_signal(signum, frame):
  global bot
  if(signum == signal.SIGHUP):
      bot.load_settings()

signal.signal(signal.SIGHUP, handle_signal)

bot = LinkerBot('all')
sys.stdout.flush()

numchecked = 0
numsamples = 0
maxsamples = 1000
update_period = 100
totaltime = 0

sleep_secs = 5
max_sleep = 2**16

last_restart = time.time() - sleep_secs*2;
last_comment = None

while True:
  try:
    #Sanity check: sleep a bit before logging things
    #Also some simple escalation: double sleep time if
    #We restart too quickly
    time_since_last_restart = time.time() - last_restart
    if(time_since_last_restart < sleep_secs*2):
      if(sleep_secs < max_sleep):
        sleep_secs = sleep_secs*2

      #Be safe here cause we can spin into disk-eating death if we die before sleeping
      try:
        log("Restarted too quickly, refreshing comments and backing off to %d seconds...", sleep_secs)
        if(last_comment and hasattr(last_comment, '__dict__')):
          log("Last comment: %s", pformat(last_comment.__dict__))
        else:
          log("Last comment: %s", pformat(last_comment))
      except Exception, e:
        print traceback.format_exc()
    else:
      sleep_secs = 5

    log("Letting things settle...")
    time.sleep(sleep_secs)

    log("Starting comment stream...")
    last_restart = time.time()
    sys.stdout.flush()
    while True:
      start = time.time();
      try:
        last_comment = bot.next()
        numchecked += 1
      except EmptyBodyError, e:
        log("Comment without body: %s", e.message)
      duration = time.time() - start

      totaltime += duration
      numsamples += 1
      if(numchecked % update_period == 0):
        log("\rChecked %d comments...",(numchecked),stderr=True,newline=False)
      if(numsamples >= maxsamples):
        log("Average processing time of last %d comments: %.2f ms",(numsamples, totaltime/numsamples*1000))
        numsamples = 0
        totaltime = 0

      sys.stdout.flush()

    # Maybe if we get to the end, we need to get more?
    bot.refresh_comments()

  except prawcore.exceptions.OAuthException:
    log("Refreshing auth...")
    bot.refresh_oauth()
  except KeyboardInterrupt:
    log("Shutting down after scanning %d comments...",(numchecked))
    bot.save_seen()
    sys.exit("Keyboard interrupt, shutting down...")
  except Exception, e:
    log(u"Error!")
    print traceback.format_exc()
