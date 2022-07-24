#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import sys
import praw
import prawcore
import time
from datetime import datetime
import re
import yaml
from pprint import pprint
import random
import collections
import shutil
from mako.template import Template

from joelbot import JoelBot
from joelbot.util import log, get_sender
from imagemap import ImageMap
from memedb import MemeDb

class EmptyBodyError(RuntimeError):
  pass

class LinkerBot(JoelBot):
  def __init__(self, *args, **kwargs):
    JoelBot.__init__(self, *args, **kwargs)

    log("\n", stderr=True)
    log("Starting up...", stderr=True)

    self.load_map()
    self.publish_map()

    log("Loaded image map:")
    pprint(self.imagemap.get_dict())
    sys.stdout.flush()

    log("Generating statuspage...")
    self.generate_statuspage()

    log("Opening database...")
    self.memelog = MemeDb(self.config['dbfile'])

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

  def generate_statuspage(self):
    t = Template(self.get_template())
    f = open('status.html', 'w')
    t_data = {
      'last_restarted': datetime.fromtimestamp(time.time()),
      'config': {
        'bot': self.config,
        'account': self.account_config,
      },
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

  def get_links(self, comment):
    matches = self.imagemap.find_candidates(comment.body)
    if not len(matches):
      return None

    # Do this here because it's a db call, don't want to do it unless we match
    if(self.should_ignore(comment)):
      return None

    ts = time.time()
    commentlinks = collections.OrderedDict()
    for imagekey, (prefix, key, ext, urls) in self.get_images(matches).iteritems():
      if urls:
        linktext = "%s.%s" % (key,ext)
        if(len(prefix.strip()) > 0):
          linktext = prefix + linktext

        url = random.choice(urls)
        commentlinks[linktext] = url
        self.memelog.addMatch(comment, key, ext, ts, imagekey, url)
      else:
        self.memelog.addCandidate(comment, key, ext, ts)
        log(u"\nPossible new image for %s\n%s %s %s",(comment.permalink, prefix, key, ext))

    return commentlinks

  def next(self):
    comment = self.comment_stream.next()
    if not hasattr(comment, 'body'):
      raise EmptyBodyError(str(comment))

    start = time.time()

    commentlinks = self.get_links(comment)
    if commentlinks:
      if self.is_reply_reply(comment):
        reply = self.reply_warn(comment, commentlinks)
      else:
        reply = self.reply(comment, commentlinks)

      self.memelog.addComment(comment, reply)

    return (comment, time.time() - start)

  def get_images(self, matches):
    results = collections.OrderedDict()

    for match in matches:
      (prefix, key, ext) = match
      # Strip out underscores/hyphens
      searchkey = key.lower().replace('_','').replace('-','')
      # Remove "meme" from the end
      if searchkey.endswith('meme'):
        searchkey = searchkey[:-4]

      (urls, imagekey) = self.imagemap.get(searchkey, ext)

      # Add the match to the list if it's not a dup
      if imagekey not in results:
        results[imagekey] = (prefix, key, ext, urls)

    return results

  def is_reply_reply(self, comment):
    if comment.is_root:
      return False

    parent = self.r.comment(comment.parent_id[3:])
    subreddit = comment.subreddit.display_name.lower()
    return parent.author and parent.author.name == self.username and subreddit != self.username

  def reply(self, comment, commentlinks):
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

    return replytext

  def reply_warn(self, comment, commentlinks):
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
    return message
