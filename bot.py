#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import praw
import time
from datetime import datetime
import re 
import sys
import argparse
import yaml
from pprint import pprint
import random
import collections
import signal
import shutil
from jinja2 import Template

from joelbot import JoelBot

def load_imagelist(config):
  matchlist = {}
  for key, urls in config['images'].iteritems():
    if(not isinstance(urls, list)):
      urls = [urls]
    matchlist[key] = urls

  for key, aliases in config['aliases'].iteritems():
    if(not isinstance(aliases, list)):
      aliases = [aliases]

    for alias in aliases:
      matchlist[alias] = key

  return matchlist

def print_imagelist(config, format = 'markdown'):
  headers = {
    'markdown': "|Triggers|Responses|\n|:-|:-|\n"
  }
  imagelist = headers[format];
  for key, urls in config['images'].iteritems():
    keylist = [key]
    if(not isinstance(urls, list)):
      urls = [urls]
    if(key in config['aliases']):
      aliases = config['aliases'][key]
      if(not isinstance(aliases, list)):
        aliases = [aliases]
      keylist += aliases
    
    if(format == 'markdown'):
       imagelist += "|%s|%s|\n" % (', '.join(keylist), ' '.join(['[%d](%s)' % (i+1,url) for i, url in enumerate(urls)]))

  return imagelist

def form_reply(link_list):
  lines = ["[%s](%s)  " % keyval for keyval in link_list.iteritems()]
  reply = "\n".join(lines) + "\n\n" + bot.config['bot']['footer']
  return reply

def signal_handler(signum, frame):
  if(signum == signal.SIGHUP):
      load_settings()

def cleanup():
  global last_cleaned

  if(last_cleaned and last_cleaned > (time.time() - bot.config['bot']['cleanup_time'])):
    return

  last_cleaned = time.time()
  return bot.cleanup()

def generate_statuspage(bot):
  global imagemap
  t = Template(bot.get_template())
  f = open('status.html', 'w')
  t_data = {
    'last_restarted': datetime.fromtimestamp(time.time()),
    'config': bot.config,
    'num_keys': len(imagemap.keys()),
    'num_images': sum([0 if (type(l) is str) else len(l) for l in imagemap.itervalues()]),
  }
  f.write(t.render(t_data))

parser = argparse.ArgumentParser(description="Links text such as themoreyouknow.gif to actual images")

global bot
global last_cleaned
global imagemap

bot = JoelBot('ilb_test')
last_cleaned = 0

signal.signal(signal.SIGHUP,signal_handler)

#Load image map
imageconf = yaml.load(open('imagelist.yaml'))
imagemap = load_imagelist(imageconf)

markdown = print_imagelist(imageconf)

shutil.copy('imagelist.md','imagelist.previous.md')
mdf = open('imagelist.md','w')
mdf.write(markdown)
mdf.close()

print "Loaded image map:"
pprint(imagemap)
sys.stdout.flush()

ext_list = '|'.join(bot.config['bot']['extensions'])
maybeimage = re.compile(r'(^|\s|\^+)(\w+)\.(%s)\b' % (ext_list),re.IGNORECASE)

generate_statuspage(bot)

numchecked = 0
while True:
  try:
    for comment in bot.comment_stream:
      cleanup()

      if hasattr(comment,'body'):
        numchecked += 1
        sys.stderr.write("\rChecked %d comments..." % (numchecked))

        commentlinks = collections.OrderedDict()
        foundkeys = []
        matches = maybeimage.findall(comment.body)
        if len(matches):
          if(bot.should_ignore(comment)):
            continue

          for match in matches:
            #Add the match to the list if it's not a dup
            (prefix, key, ext) = match
            searchkey = key.lower()
            if searchkey not in foundkeys:
              if searchkey in imagemap:
                urls = imagemap[searchkey]
                #Follow aliases
                if not isinstance(urls, list):
                  searchkey = urls.lower()
                  if searchkey in foundkeys: continue
                  urls = imagemap[searchkey]

                foundkeys.append(searchkey)
                linktext = "%s.%s" % (key,ext)
                if(len(prefix.strip()) > 0):
                  linktext = prefix + linktext
                commentlinks[linktext] = random.choice(urls)
              else:
                print u"\nPossible new image for %s\n%s" % (comment.permalink, ' '.join(match))
          
          if len(commentlinks):
            if(not comment.is_root):
              parent = bot.r.get_info(thing_id=comment.parent_id)
              subreddit = comment.subreddit.display_name.lower()
              if(parent.author.name == bot.config['account']['username'] and subreddit != bot.config['account']['username']):
                print "Sending warning to %s for reply-reply..." % (comment.author)
                bot.r.send_message(comment.author,'I\'m glad you like me, but...',bot.config['bot']['toomuch'],raise_captcha_exception=True)
                continue

            replytext = form_reply(commentlinks)
            try:
              print "Commenting on %s (%s)" % (comment.permalink, ', '.join(commentlinks.keys()))
              comment.reply(replytext)
            except praw.errors.RateLimitExceeded, e:
              print "Rate limit exceeded, sleeping %d seconds and trying again..." % (e.sleep_time)
              time.sleep(e.sleep_time)
              print "Re-commenting on %s" % (comment.permalink)
              comment.reply(replytext)

      sys.stdout.flush()
            
  except KeyboardInterrupt:
    print "Shutting down after scanning %d comments..." % (numchecked)
    bot.save_seen()
    sys.exit("Keyboard interrupt, shutting down...")
# except Exception, e:
#   pprint(e)
