import sys 
import re
import yaml
import json

import prawcore

from .basebot import BaseBot
from .util import log, add_r, get_sender
from ignorelist import IgnoreList
from unseencomments import UnseenComments

class CommenterBot(BaseBot):
  def __init__(self, subreddit=None, **kwargs):
    BaseBot.__init__(self, **kwargs)

    if subreddit:
      self.comment_stream = UnseenComments(self.r, subreddit, self.config['seen_len'])
      self.subreddit = subreddit

    self.load_banlist()

    self.ignores = IgnoreList(self.config['dbfile'], 'ignore')
    self.bans = IgnoreList(self.config['dbfile'], 'ban')

  def reload_settings(self):
    BaseBot.reload_settings(self)
    self.load_banlist()

  def load_banlist(self):
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

  def save_seen(self):
    self.comment_stream.save_state()

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

  def get_wiki(self, page):
    return self.r.subreddit(self.config['subreddit']).wiki[page]

  def write_wiki(self, page, content, reason=None):
    return self.r.subreddit(self.config['subreddit']).wiki[page].edit(content, reason)

  # Transform a wiki'd YAML into normal yaml and parse it
  def get_wiki_yaml(self, page):
    wikipage = self.get_wiki(page)
    cleaned_yaml = re.sub(r'^(\s*)\* ','\\1', wikipage.content_md, flags=re.MULTILINE)
    return yaml.load(cleaned_yaml)
