#!/usr/bin/python
# -*- coding: utf-8 -*-
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

num_checked = 0
num_samples = 0
max_samples = 1000
update_period = 100
total_overall = 0
total_processing = 0

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
        (last_comment, processing_time) = bot.next()
        num_checked += 1
      except EmptyBodyError, e:
        log("Comment without body: %s", e.message)
      overall_time = time.time() - start

      total_overall += overall_time
      total_processing += processing_time
      num_samples += 1
      if(num_checked % update_period == 0):
        log("\rChecked %d comments...",(num_checked),stderr=True,newline=False)
      if(num_samples >= max_samples):
        log(u"Average processing/total time of last %d comments: %.2f µs/%.2f ms",(num_samples, total_processing/num_samples*1e6, total_overall/num_samples*1e3))
        num_samples = 0
        total_overall = 0
        total_processing = 0

      sys.stdout.flush()

    # Maybe if we get to the end, we need to get more?
    bot.refresh_comments()

  except prawcore.exceptions.OAuthException:
    log("Refreshing auth...")
    bot.refresh_oauth()
  except KeyboardInterrupt:
    log("Shutting down after scanning %d comments...",(num_checked))
    bot.save_seen()
    sys.exit("Keyboard interrupt, shutting down...")
  except Exception, e:
    log(u"Error!")
    print traceback.format_exc()
