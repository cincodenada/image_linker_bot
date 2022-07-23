#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import signal

from .linkerbot import LinkerBot

def handle_signal(signum, frame):
  global bot
  if(signum == signal.SIGHUP):
      bot.load_settings()

signal.signal(signal.SIGHUP, handle_signal)

bot = LinkerBot('all')
bot.run()
