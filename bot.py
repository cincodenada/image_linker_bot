#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import praw
import prawcore
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
import inspect

from joelbot import JoelBot
from joelbot.util import log, get_sender
from imagemap import ImageMap
from memedb import MemeDb

class LinkerBot(JoelBot):
  def __init__(self, *args, **kwargs):
    JoelBot.__init__(self, *args, **kwargs)

    log("\n", stderr=True)
    log("Starting up...", stderr=True)

    signal.signal(signal.SIGHUP,self.handle_signal)

    self.load_map()
    self.publish_map()

    log("Loaded image map:")
    pprint(self.imagemap.get_dict())
    sys.stdout.flush()

    self.ext_list = '|'.join(self.config['matching']['extensions'] + self.config['matching']['animated_extensions'])
    self.maybeimage = re.compile(r'(^|\s|\^+)(\w+)\.(%s)\b' % (ext_list),re.IGNORECASE)

    self.generate_statuspage()

  def form_reply(self, link_list, footer = 'footer'):
    lines = []
    for (text, link) in link_list.iteritems():
      lines.append("[%s](%s)  " % (text, link))
      (urls, peniskey) = self.imagemap.get('thatsapenis')
      if(link in urls):
        (revurl, revkey) = self.imagemap.get('thatsapenisreverse')
        revurl = revurl[0]
        lines.append("^(and, to fulfill the laws of reddit:) ^[%s](%s)  " % ('sinepastaht.gif', revurl))

    reply = "\n".join(lines)
    if(footer):
      reply += "\n\n" + self.config[footer]
    return reply

  def handle_signal(self, signum, frame):
    if(signum == signal.SIGHUP):
        self.load_settings()

  def generate_statuspage(self):
    t = Template(self.get_template())
    f = open('status.html', 'w')
    t_data = {
      'last_restarted': datetime.fromtimestamp(time.time()),
      'config': self.allconfig,
      'num_keys': self.imagemap.num_keys(),
      'num_images': self.imagemap.num_images(),
      'imagelist': self.imagemap.get_tuples(),
    }
    f.write(t.render(**t_data))

  def load_map(self):
    #Load image map, first from wiki
    try:
      imageconf = self.get_wiki_yaml('botconf/imagelist')
      log('Loaded imagelist from wiki')
    except Exception as e:
      log("Couldn't load imagelist from wiki: " + str(sys.exc_info()[0]))
      imageconf = None

    # Fall back to local file
    if not imageconf:
      imageconf = yaml.load(open('imagelist.yaml'))
      shutil.copy('imagelist.yaml','imagelist.%d.yaml' % (time.time()))
      log('Loaded imagelist from file')

    self.imagemap = ImageMap(imageconf, self.config['matching'])

  def publish_map(self):
    markdown = self.imagemap.get_formatted()

    # Update the image map on the wiki
    try:
      try:
        curmd = self.get_wiki('imagelist')
      except prawcore.exceptions.NotFound:
        curmd = None

      if(curmd != markdown):
        self.write_wiki('imagelist', markdown, 'Updating image list')
        log("Wrote updated imagelist to wiki")
    except Exception as e:
      log("Couldn't update wiki page: " + str(sys.exc_info()[0]))

      log("Updating files...")
      # Fall back to shuffling files around
      shutil.copy('imagelist.md','imagelist.%d.md' % (time.time()))
      shutil.copy('imagelist.md','imagelist.previous.md')
      mdf = open('imagelist.md','w')
      mdf.write(markdown)
      mdf.close()

    #Update the post
    if('imagethread' in self.config):
      imagepost = self.r.submission(id=self.config['imagethread'])
      header = re.match(r'([\S\s]*)---',imagepost.selftext)
      if(header):
        header = header.group(1)
        imagepost.edit("%s---\n%s" % (header, markdown))

  def run(self):
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
            log("Restarted too quickly, refreshing comments and backing off to %d seconds...", sleep_secs)
            if(comment and hasattr(comment, '__dict__')):
              log("Last comment: %s", pformat(comment.__dict__))
            else:
              log("Last comment: %s", pformat(comment))
          except Exception, e:
            print traceback.format_exc()
        else:
          sleep_secs = 5
        time.sleep(sleep_secs)

        log("Opening database...")
        memes = MemeDb(self.config['dbfile'])

        log("Starting comment stream...")
        last_restart = time.time()
        for comment in self.comment_stream:
          start = time.time();

          if hasattr(comment,'body'):
            numchecked += 1

            commentlinks = collections.OrderedDict()
            foundkeys = []
            matches = maybeimage.findall(comment.body)
            if len(matches):
              if(self.should_ignore(comment)):
                continue

              ts = time.time()
              for match in matches:
                # Add the match to the list if it's not a dup
                (prefix, key, ext) = match
                # Strip out underscores/hyphens
                searchkey = key.lower().replace('_','').replace('-','')
                # Remove "meme" from the end
                if searchkey.endswith('meme'):
                  searchkey = searchkey[:-4]
                (urls, imagekey) = self.imagemap.get(searchkey, ext)
                if urls:
                  if imagekey not in foundkeys:
                    foundkeys.append(imagekey)

                    linktext = "%s.%s" % (key,ext)
                    if(len(prefix.strip()) > 0):
                      linktext = prefix + linktext

                    url = random.choice(urls)
                    commentlinks[linktext] = url
                    memes.addMatch(comment, key, ext, ts, imagekey, url)
                else:
                  memes.addCandidate(comment, key, ext, ts)
                  log(u"\nPossible new image for %s\n%s",(comment.permalink, u' '.join(match)))
              
              if len(commentlinks):
                if(not comment.is_root):
                  parent = self.r.comment(comment.parent_id[3:])
                  subreddit = comment.subreddit.display_name.lower()
                  if(parent.author and parent.author.name == self.username and subreddit != self.username):
                    log("Sending warning to %s for reply-reply...",(comment.author))

                    #Always with the plurals
                    plural = 'are the images'
                    if(len(commentlinks) > 1):
                      plural = 'are the images'
                    else:
                      plural = 'is the image'

                    #Construct our message
                    message = 'Here %s you wanted: %s\n\n%s' % (
                      plural,
                      self.form_reply(commentlinks, None),
                      self.config['toomuch']
                    )

                    self.r.redditor(comment.author).message('I\'m glad you like me, but...',message,raise_captcha_exception=True)
                    memes.addComment(comment, message)
                    continue

                replytext = self.form_reply(commentlinks)
                try:
                  log("Commenting on %s (%s)",(comment.permalink, ', '.join(commentlinks.keys())))
                  comment.reply(replytext)
                except praw.exceptions.APIException, e:
                  if(e.error_type == "TOO_OLD"):
                    log("Comment too old!")
                  elif(e.error_type == "SUBREDDIT_OUTBOUND_LINKING_DISALLOWED"):
                    log("Commenting on %s without link:",(comment.permalink))
                    replytext = self.form_reply(commentlinks, 'nolink_footer')
                    comment.reply(replytext)
                  else:
                    # Otherwise assume it's rate limiting...without a sleep time?...ugh
                    sleeptime = 2
                    log("Rate limit exceeded, sleeping %d seconds and trying again...",(sleeptime))
                    time.sleep(sleeptime)
                    log("Re-commenting on %s",(comment.permalink))
                    comment.reply(replytext)
                except prawcore.exceptions.ResponseException, e:
                  log("Got response error: %s", (e))
                  log(e.response.text)
                  if e.response.status_code == 403:
                    # TODO: get_sender being external here is ick
                    self.do_command('ban', get_sender(comment), reason="comment_forbidden")
                  else:
                    raise e

                memes.addComment(comment, replytext)

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
        self.refresh_comments()
                
      except prawcore.exceptions.OAuthException:
        self.refresh_oauth()
      except KeyboardInterrupt:
        log("Shutting down after scanning %d comments...",(numchecked))
        self.save_seen()
        sys.exit("Keyboard interrupt, shutting down...")
      except Exception, e:
        log(u"Error!")
        print traceback.format_exc()

bot = LinkerBot('all')
bot.run()
