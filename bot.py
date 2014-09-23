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
from mako.template import Template
import traceback

from joelbot import JoelBot

class ImageMap:
  as_dict = {}
  as_tuples = []
  hidden_keys = []

  def __init__(self, config, anim_list = [], switch_list = []):
    self.images = config['images']
    self.aliases = config['aliases']
    self.hidden_keys = config['hidden']
    self.anim_list = anim_list
    self.switch_list = switch_list

  def get(self, searchkey, matchext = ''):
    if searchkey in self.get_dict():
      urls = self.get_dict()[searchkey]
      #Follow aliases
      if not isinstance(urls, list):
        searchkey = urls.lower()
        urls = self.get_dict()[searchkey]

      if matchext:
        urls = self.get_closest(urls, matchext)

      return (urls, searchkey)
    else:
      return (False, False)

  def get_closest(self, urls, ext):
    is_anim = (ext in self.anim_list)

    priority_list = [[] for i in range(4)]
    for url in urls:
      parts = url.split('/')
      endparts = parts.pop().rsplit('.', 1)
      if(len(endparts) == 1):
        urlext = 'gfy' #Gfycat can't match any extensions
      else:
        urlext = endparts[-1]

      #We use this a couple times below, might as well make it now
      swapped = '%s/%s.%s' % ('/'.join(parts), endparts[0], ext)

      #If we're gfycat or in the list, we're animated
      urlanim = (urlext in self.anim_list)

      #If we match, add to a better list
      if(urlanim == is_anim):
        if(urlext == ext):
          #If it's an exact match, add it to the greats
          priority_list[0].append(url)
        else:
          if(ext in self.switch_list and urlext in self.switch_list):
            #Otherwise, if we can switch, that's still good
            priority_list[1].append(swapped)
          else:
            #If no switching, at least animation state matches
            priority_list[2].append(url)
      elif(ext in self.switch_list and urlext in self.switch_list):
        priority_list[3].append(swapped)

    #Use the first list that has any entries
    for try_list in priority_list:
      if(len(try_list)):
        return try_list

    #Fall back to the full list
    return urls

  def get_dict(self):
    if(len(self.as_dict.keys()) == 0):
      for key, urls in self.images.iteritems():
        if(not isinstance(urls, list)):
          urls = [urls]
        self.as_dict[key] = urls

      for key, aliases in self.aliases.iteritems():
        if(not isinstance(aliases, list)):
          aliases = [aliases]

        for alias in aliases:
          self.as_dict[alias] = key

    return self.as_dict

  def get_tuples(self):
    if(len(self.as_tuples) == 0):
      hidden_set = set(self.hidden_keys)
      for key, urls in self.images.iteritems():
        if key in self.hidden_keys: continue
        keylist = [key]
        if(not isinstance(urls, list)):
          urls = [urls]
        if(key in self.aliases):
          aliases = self.aliases[key]
          if(not isinstance(aliases, list)):
            aliases = [aliases]
          keylist += list(set(aliases) - hidden_set)
        
        self.as_tuples.append((keylist, urls))

    return self.as_tuples

  def num_keys(self):
    return len(self.get_dict().keys()) - len(self.hidden_keys)

  def num_images(self):
    return sum([1 if (type(l) is str) else len(l) for l in self.images.itervalues()])

  def get_formatted(self, format='markdown'):
    headers = {
      'markdown': "|Triggers|Responses|\n|:-|:-|\n"
    }
    imagelist = headers[format];
      
    if(format == 'markdown'):
      for keylist, urls in self.get_tuples():
        imagelist += "|%s|%s|\n" % (', '.join(keylist), ' '.join(['[%d](%s)' % (i+1,url) for i, url in enumerate(urls)]))

    return imagelist

def form_reply(link_list, withfooter = True):
  lines = ["[%s](%s)  " % keyval for keyval in link_list.iteritems()]
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

#Load image map
imageconf = yaml.load(open('imagelist.yaml'))
imagemap = ImageMap(imageconf, bot.config['bot']['animated_extensions'], bot.config['bot']['switchable_extensions'])
shutil.copy('imagelist.yaml','imagelist.%d.yaml' % (time.time()))

markdown = imagemap.get_formatted()

shutil.copy('imagelist.md','imagelist.%d.md' % (time.time()))
shutil.copy('imagelist.md','imagelist.previous.md')
mdf = open('imagelist.md','w')
mdf.write(markdown)
mdf.close()

bot.log("Loaded image map:")
pprint(imagemap.get_dict())
sys.stdout.flush()

ext_list = '|'.join(bot.config['bot']['extensions'] + bot.config['bot']['animated_extensions'])
maybeimage = re.compile(r'(^|\s|\^+)(\w+)\.(%s)\b' % (ext_list),re.IGNORECASE)

generate_statuspage(bot)

numchecked = 0
numsamples = 0
maxsamples = 1000
totaltime = 0
while True:
  try:
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

                commentlinks[linktext] = random.choice(urls)
            else:
              bot.log(u"\nPossible new image for %s\n%s",(comment.permalink, ' '.join(match)))
          
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

      duration = time.time() - start
      totaltime += duration
      numsamples += 1
      if(numsamples >= maxsamples):
        bot.log("\rChecked %d comments...",(numchecked),True,newline=False)
        bot.log("Average processing time of last %d comments: %.2f ms",(numsamples, totaltime/numsamples*1000))
        numsamples = 0
        totaltime = 0
      
      sys.stdout.flush()
            
  except KeyboardInterrupt:
    bot.log("Shutting down after scanning %d comments...",(numchecked))
    bot.save_seen()
    sys.exit("Keyboard interrupt, shutting down...")
  except Exception, e:
    print traceback.format_exc()
