#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import praw
import prawcore
import time
import yaml
import json
import sqlite3
import sys
import re
import urlparse
import random

from scorecheck import ScoreCheck
from ignorelist import IgnoreList
from unseencomments import UnseenComments
from commentstore import CommentStore
from .util import log, add_r, get_sender

class BaseBot:
  max_retries = 50
  backoff = 2

  def __init__(self, config_file='config.yaml', useragent = 'default', skip_remote_config=False):
    #Load config and set up
    log("Logging in...")

    allconfig = yaml.load(open(config_file))
    self.config = allconfig['bot']
    self.account_config = allconfig['account']
    self.username = self.account_config['username']

    self.start_time = time.time()

    self.useragent = useragent
    self.r = None

    if self.account_config['oauth']:
      while True:
        try:
          self.auth_oauth()
          break
        except praw.exceptions.APIException:
          self.backoff *= 2
          log("Error logging in! Trying again in {} seconds...".format(self.backoff), stderr=True)
        time.sleep(self.backoff)
    else:
      log("Error! Password login no longer supported!", stderr=True)
      sys.exit()

  def auth_oauth(self):
    if self.get_refresh_token():
      self.r = praw.Reddit(
        user_agent = self.config['useragent'][self.useragent],
        refresh_token = self.refresh_token,
        **self.account_config['oauth']
      )
    else:
      self.r = praw.Reddit(
        user_agent = self.config['useragent'][self.useragent],
        **self.account_config['oauth']
      )
      rt = self.authorize_oauth()
      if rt:
        rtfile = open('refresh_token','w')
        rtfile.write(rt)
      else:
        raise prawcore.exceptions.OAuthException("Couldn't fetch refresh token!")

  def authorize_oauth(self):
    self.oauth_state = str(random.randint(0, 65000))
    auth_url = self.r.auth.url(
      self.config['oauth_scopes'],
      self.oauth_state,
      "permanent"
    )

    log('Go to the following URL, copy the URL that you are redirected to, then come back and paste it here:')
    log(auth_url)
    redirect_url = raw_input("Redirected URL: ")

    urlparts = urlparse.urlsplit(redirect_url)
    querydata = urlparse.parse_qs(urlparts.query)
    self.refresh_token = self.r.auth.authorize(querydata['code'])
    return self.refresh_token

  def get_refresh_token(self):
    # Check if we have a refresh token available
    try:
      rtfile = open('refresh_token','r')
      rt = rtfile.readline().rstrip()
      self.refresh_token = rt
      rtfile.close()
    except IOError:
      return None

    return self.refresh_token

  def id_string(self):
    return "{:s} ({:s}) {:f}".format(
      self.username,
      self.useragent or 'default',
      self.start_time
    )

class JoelBot(BaseBot):
  def __init__(self, subreddit=None, **kwargs):
    BaseBot.__init__(self, **kwargs)

    if subreddit:
      self.comment_stream = UnseenComments(self.r, subreddit, self.config['seen_len'])
      self.subreddit = subreddit

    self.load_settings()

    self.inbox = CommentStore(self.config['dbfile'])
    self.ignores = IgnoreList(self.config['dbfile'], 'ignore')
    self.bans = IgnoreList(self.config['dbfile'], 'ban')

  def load_settings(self):
    log("Reloading config...")
    sys.stdout.flush()

    #Load banlist
    log("Loading banlists...")
    sys.stdout.flush()
    bottiquette = self.r.subreddit('Bottiquette').wiki['robots_txt_json']
    banlist = json.loads(bottiquette.content_md)
    btqban = (banlist['disallowed'] +\
        banlist['posts-only'] +\
        banlist['permission'])

    try:
      mybans = self.get_wiki('botconf/banlist')
      mybans = [line.lstrip(' *-') for line in mybans.content_md.split('\n')\
          if not (line.strip() == '' or line.startswith('#'))]
    except prawcore.exceptions.ResponseException as e:
      print e
      log("Couldn't load bot-specific banlist")
      mybans = []

    self.config_bans = [x.strip().lower() for x in (btqban + mybans)]
    log("Ignoring subreddits: %s",(', '.join(self.config_bans)))

  def should_ignore(self, comment):
    #Don't post in bot-banned subreddits
    subreddit = comment.subreddit.display_name
    if subreddit.lower() in self.config_bans or self.bans.is_ignored(add_r(subreddit)):
      log("Skipping banned subreddit %s",(subreddit))
      return True

    #Don't reply to self, just in case...
    if comment.author.name == self.username:
      return True

    #Check user ignore list
    if self.ignores.is_ignored(comment.author.name):
      log("Ignoring user %s",(comment.author.name))
      return True

    return False

  def matches_action(self, message, action):
    return any([match in message for match in self.config['{}_messages'.format(action)]])

  def save_seen(self):
    self.comment_stream.save_state()

  def cleanup(self):
    sc = ScoreCheck(self)
    sc.run()
    sc.print_report()
    sc.save_report()

  def get_template(self):
    if('status_template' in self.config):
      template = self.config['status_template']
      if(template.find('\n') == -1):
        template = open(template, 'r').read()
      return template
    else:
      return '<html><head><title>JoelBot</title></head><body>No template found</body></html>'

  def refresh_comments(self):
    self.comment_stream.refresh_comments()

  def check_messages(self):
    last_tid = None
    last_message = self.inbox.get_last_message()
    if last_message is not None:
      _, last_tid = last_message['tid'].split('_', 1)
    # TODO: Make continuous/stream-based?
    for m in self.r.inbox.messages(params={'after': last_tid}):
      if(last_message is not None and m.created < last_message['sent']):
        log("Found old message, stopping!")
        return False

      if(self.inbox.add_message(m)):
        action = self.get_command(m.body)
        if action:
          self.do_command(action, get_sender(m), m.name)
          config = self.config['actions'][action]
          if config['reply']:
            self.reply_to(m, config.get('subject'), config['reply'])
      else:
        log("Found duplicate message, stopping!")
        return False

  def get_command(self, message):
    for action in self.config['actions'].items():
      if(self.matches_action(message, action)):
        return action
    return None

  def do_command(self, action, target, ref_id=None, reason=None):
    if action == 'ignore':
      log("Ignoring {:s}...".format(target))
      self.ignores.ignore_sender(target, ref_id, reason or "message")

    elif action == 'unignore':
      log("Unignoring {:s}...".format(target))
      self.ignores.unignore_sender(target)

    elif action == 'ban':
      log("Recording ban from {:s}...".format(target))
      self.bans.ignore_sender(target, ref_id, reason or "ban")

    elif action == 'softban':
      log("Recording soft ban from {:s}...".format(target))
      self.bans.ignore_sender(target, ref_id, reason or "softban")

  def reply_to(self, m, subject, reply):
    if(m.subreddit):
      # It's a comment, send a message
      self.r.send_message(m.author, subject, reply, raise_captcha_exception=True)
    else:
      # It's a pm, just reply
      m.reply(reply)

  def get_wiki(self, page):
    return self.r.subreddit(self.config['subreddit']).wiki[page]

  def write_wiki(self, page, content, reason=None):
    return self.r.subreddit(self.config['subreddit']).wiki[page].edit(content, reason)

  # Transform a wiki'd YAML into normal yaml and parse it
  def get_wiki_yaml(self, page):
    wikipage = self.get_wiki(page)
    cleaned_yaml = re.sub(r'^(\s*)\* ','\\1', wikipage.content_md, flags=re.MULTILINE)
    return yaml.load(cleaned_yaml)
