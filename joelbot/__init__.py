#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import praw
import time
import yaml
import json
import sqlite3
from requests import exceptions as req_exceptions
import sys

from scorecheck import ScoreCheck
from ignorelist import IgnoreList
from unseencomments import UnseenComments
from commentstore import CommentStore

class JoelBot:
  def __init__(self, subreddit, config_file='config.yaml', useragent = None):
    #Load config and set up
    self.log("Logging in...")
    self.config = yaml.load(open(config_file))

    if useragent is None: 
      useragent = self.config['bot']['useragent']['default']
    else:
      useragent = self.config['bot']['useragent'][useragent]
    self.r = praw.Reddit(useragent)
    self.r.login(self.config['account']['username'],self.config['account']['password'])

    self.comment_stream = UnseenComments(self.r, subreddit, self.config['bot']['seen_len'])
    self.subreddit = subreddit

    self.load_settings()

    self.inbox = CommentStore(self.config['bot']['dbfile'])
    self.ignores = IgnoreList(self.config['bot']['dbfile'])

  def log(self, format, params=None, stderr=False,newline=True):
    prefix = time.strftime('%Y-%m-%d %H:%M:%S')
    logline = prefix + " " + (format if params is None else (format % params))
    if(newline and stderr):
      logline += "\n"

    if(stderr):
      sys.stderr.write(logline)
    else:
      print(logline)
    
  def load_settings(self):
    self.log("Reloading config...")
    sys.stdout.flush()
    self.config = yaml.load(open('config.yaml'))

    #Load banlist
    self.log("Loading banlists...")
    sys.stdout.flush()
    bottiquette = self.r.get_wiki_page('Bottiquette', 'robots_txt_json')
    banlist = json.loads(bottiquette.content_md)
    btqban = (banlist['disallowed'] +\
        banlist['posts-only'] +\
        banlist['permission'])

    try:
      mybans = self.r.get_wiki_page(self.config['bot']['subreddit'], 'blacklist')
      mybans = [line for line in mybans.content_md.split('\n')\
          if not (line.strip() == '' or line.startswith('#'))]
    except req_exceptions.HTTPError:
      self.log("Couldn't load bot-specific blacklist")
      mybans = []
    
    self.bans = [x.strip().lower() for x in (btqban + mybans)]
    self.log("Ignoring subreddits: %s",(', '.join(self.bans)))

  def should_ignore(self, comment):
    #Don't post in bot-banned subreddits
    subreddit = comment.subreddit.display_name.lower()
    if subreddit in self.bans:
      self.log("Skipping banned subreddit %s",(subreddit))
      return True

    #Don't reply to self, just in case...
    if comment.author.name == self.config['account']['username']:
      return True

    #Check user ignore list
    if self.ignores.check_ignored(comment.author.name):
      self.log("Ignoring user %s",(comment.author.name))
      return True

    return False

  def save_seen(self):
    self.comment_stream.save_state()

  def cleanup(self):
    sc = ScoreCheck(self)
    sc.run()
    sc.print_report()
    sc.save_report()


  def get_template(self):
    if('status_template' in self.config['bot']):
      template = self.config['bot']['status_template']
      if(template.find('\n') == -1):
        template = open(template, 'r').read()
      return template
    else:
      return '<html><head><title>JoelBot</title></head><body>No template found</body></html>'

  def refresh_comments(self):
    self.comment_stream.refresh_comments()

  def check_messages(self):
    last_message = self.inbox.get_last_message()
    last_tid = None if last_message is None else last_message['tid']
    for m in self.r.get_inbox(place_holder=last_tid):
      if(last_message is not None and m.created < last_message['sent']):
        self.log("Found old message, stopping!")
        return False

      if(self.inbox.add_message(m)):
        if(m.body in self.config['bot']['ignore_messages']):
          self.ignores.ignore_sender(m)
          if('ignore_reply' in self.config['bot']):
            self.reply_to(m, 'Ignore Request', self.config['bot']['ignore_reply'])
        elif(m.body in self.config['bot']['unignore_messages']):
          self.ignores.unignore_sender(m)
          if('unignore_reply' in self.config['bot']):
            self.reply_to(m, 'Unignore Request', self.config['bot']['unignore_reply'])
      else:
        self.log("Found duplicate message, stopping!")
        return False

  def reply_to(self, m, subject, reply):
    if(m.subreddit):
      # It's a comment, send a message
      self.r.send_message(m.author, subject, reply, raise_captcha_exception=True)
    else:
      # It's a pm, just reply
      m.reply(reply)
