#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import praw
import time
from datetime import datetime
import re 
import sys
import argparse
import yaml
from pprint import pprint, pformat
import random
import collections
import signal
import shutil
from mako.template import Template
import traceback
import sqlite3
import inspect

from joelbot import JoelBot
from imagemap import ImageMap

def form_reply(link_list, withfooter = True):
  lines = []
  for (text, link) in link_list.iteritems():
    lines.append("[%s](%s)  " % (text, link))
    (urls, peniskey) = imagemap.get('thatsapenis')
    if(link in urls):
      (revurl, revkey) = imagemap.get('thatsapenisreverse')
      revurl = revurl[0]
      lines.append("^(and, to fulfill the laws of reddit:) ^[%s](%s)  " % ('sinepastaht.gif', revurl))

  reply = "\n".join(lines)
  if(withfooter):
    reply += "\n\n" + bot.config['bot']['footer']
  return reply

def signal_handler(signum, frame):
  if(signum == signal.SIGHUP):
      load_settings()

def generate_statuspage(bot):
  global imagemap
  t = Template(bot.get_template())
  f = open('status.html', 'w')
  t_data = {
    'last_restarted': datetime.fromtimestamp(time.time()),
    'config': bot.config,
    'num_keys': imagemap.num_keys(),
    'num_images': imagemap.num_images(),
    'imagelist': imagemap.get_tuples(),
  }
  f.write(t.render(**t_data))

parser = argparse.ArgumentParser(description="Links text such as themoreyouknow.gif to actual images")

global bot
global imagemap

bot = JoelBot('ilb_test')

signal.signal(signal.SIGHUP,signal_handler)

#Load image map, first from wiki
try:
  imageconf = bot.get_wiki_yaml('conf/imagelist')
except Exception as e:
  imageconf = None

# Fall back to local file
if not imageconf:
  imageconf = yaml.load(open('imagelist.yaml'))
  shutil.copy('imagelist.yaml','imagelist.%d.yaml' % (time.time()))

imagemap = ImageMap(imageconf, bot.config['bot']['animated_extensions'], bot.config['bot']['switchable_extensions'])

markdown = imagemap.get_formatted()

# Update the image map on the wiki
try:
  try:
    curmd = bot.get_wiki('imagelist')
  except praw.errors.NotFound:
    curmd = None

  if(curmd != markdown):
    bot.write_wiki('imagelist', markdown, 'Updating image list')
except Exception as e:
  bot.log("Couldn't update wiki page, updating files:")
  bot.log(str(e))

  # Fall back to shuffling files around
  shutil.copy('imagelist.md','imagelist.%d.md' % (time.time()))
  shutil.copy('imagelist.md','imagelist.previous.md')
  mdf = open('imagelist.md','w')
  mdf.write(markdown)
  mdf.close()

#Update the post
if('imagethread' in bot.config['bot']):
  imagepost = bot.r.get_submission(submission_id=bot.config['bot']['imagethread'])
  header = re.match(r'([\S\s]*)---',imagepost.selftext)
  if(header):
    header = header.group(1)
    imagepost.edit("%s---\n%s" % (header, markdown))

bot.log("Loaded image map:")
pprint(imagemap.get_dict())
sys.stdout.flush()

ext_list = '|'.join(bot.config['bot']['extensions'] + bot.config['bot']['animated_extensions'])
maybeimage = re.compile(r'(^|\s|\^+)(\w+)\.(%s)\b' % (ext_list),re.IGNORECASE)

generate_statuspage(bot)

numchecked = 0
numsamples = 0
maxsamples = 1000
update_period = 100
totaltime = 0
last_restart = time.time() - 10;
sleep_secs = 5
max_sleep = 2**16
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
        bot.log("Restarted too quickly, refreshing comments and backing off to %d seconds...", sleep_secs)
        if(comment and hasattr(comment, '__dict__')):
          bot.log("Last comment: %s", pformat(comment.__dict__))
        else:
          bot.log("Last comment: %s", pformat(comment))
      except Exception, e:
        print traceback.format_exc()
    else:
      sleep_secs = 5
    time.sleep(sleep_secs)

    bot.log("Opening database...")
    conn = sqlite3.connect(bot.config['bot']['dbfile'])
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS matches
        (subreddit TEXT, key TEXT, trigger TEXT, ext TEXT, url TEXT, thread_id TEXT, trigger_id TEXT, was_reply INTEGER, ts INTEGER)''')

    c.execute('''CREATE TABLE IF NOT EXISTS comments
        (cid TEXT, text TEXT, data TEXT)''')
    c.execute('''CREATE INDEX IF NOT EXISTS cd_cid ON comments(cid)''')

    c.execute('''CREATE TABLE IF NOT EXISTS candidates
        (key TEXT, ext TEXT, cid TEXT, ts INTEGER)''')
    c.execute('''CREATE INDEX IF NOT EXISTS key_ext ON candidates(key, ext)''')

    bot.log("Starting comment stream...")
    last_restart = time.time()
    for comment in bot.comment_stream:
      start = time.time();

      if hasattr(comment,'body'):
        numchecked += 1

        commentlinks = collections.OrderedDict()
        foundkeys = []
        matches = maybeimage.findall(comment.body)
        if len(matches):
          if(bot.should_ignore(comment)):
            continue

          ts = time.time()
          for match in matches:
            #Add the match to the list if it's not a dup
            (prefix, key, ext) = match
            searchkey = key.lower().replace('_','')
            (urls, imagekey) = imagemap.get(searchkey, ext)
            if urls:
              if imagekey not in foundkeys:
                foundkeys.append(imagekey)

                linktext = "%s.%s" % (key,ext)
                if(len(prefix.strip()) > 0):
                  linktext = prefix + linktext

                url = random.choice(urls)
                commentlinks[linktext] = url
                c.execute('''INSERT INTO matches VALUES(?,?,?,?,?,?,?,?,?)''',
                    (comment.subreddit.display_name, comment.link_id, imagekey, key, ext, url, comment.id, 0, ts))
            else:
              bot.log(u"\nPossible new image for %s\n%s",(comment.permalink, ' '.join(match)))
              c.execute('''INSERT INTO candidates VALUES(?,?,?,?)''', (key, ext, comment.id, ts))
          
          if len(commentlinks):
            if(not comment.is_root):
              parent = bot.r.get_info(thing_id=comment.parent_id)
              subreddit = comment.subreddit.display_name.lower()
              if(parent.author.name == bot.config['account']['username'] and subreddit != bot.config['account']['username']):
                bot.log("Sending warning to %s for reply-reply...",(comment.author))

                #Always with the plurals
                plural = 'are the images'
                if(len(commentlinks) > 1):
                  plural = 'are the images'
                else:
                  plural = 'is the image'

                #Construct our message
                message = 'Here %s you wanted: %s\n\n%s' % (
                  plural,
                  form_reply(commentlinks, False),
                  bot.config['bot']['toomuch']
                )

                bot.r.send_message(comment.author,'I\'m glad you like me, but...',message,raise_captcha_exception=True)
                c.execute('''INSERT INTO comments VALUES(?,?,?)''',
                    (comment.id, message, time.time()))
                continue

            replytext = form_reply(commentlinks)
            try:
              bot.log("Commenting on %s (%s)",(comment.permalink, ', '.join(commentlinks.keys())))
              comment.reply(replytext)
            except praw.errors.RateLimitExceeded, e:
              bot.log("Rate limit exceeded, sleeping %d seconds and trying again...",(e.sleep_time))
              time.sleep(e.sleep_time)
              bot.log("Re-commenting on %s",(comment.permalink))
              comment.reply(replytext)

            c.execute('''INSERT INTO comments VALUES(?,?,?)''',
                (comment.id, replytext, time.time()))

      duration = time.time() - start
      totaltime += duration
      numsamples += 1
      if(numchecked % update_period == 0):
        bot.log("\rChecked %d comments...",(numchecked),True,newline=False)
      if(numsamples >= maxsamples):
        bot.log("Average processing time of last %d comments: %.2f ms",(numsamples, totaltime/numsamples*1000))
        numsamples = 0
        totaltime = 0
      
      sys.stdout.flush()

    # Maybe if we get to the end, we need to get more?
    bot.refresh_comments()
            
  except praw.errors.OAuthException:
    bot.refresh_oauth()
  except KeyboardInterrupt:
    bot.log("Shutting down after scanning %d comments...",(numchecked))
    bot.save_seen()
    sys.exit("Keyboard interrupt, shutting down...")
  except Exception, e:
    bot.log(u"Error!")
    print traceback.format_exc()
