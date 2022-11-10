#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import time
import re
from difflib import get_close_matches

class ImageMap:
  as_dict = {}
  as_tuples = []
  hidden_keys = []

  def __init__(self, meme_config, match_config):
    self.images = meme_config['images']
    self.aliases = meme_config['aliases']
    self.hidden_keys = meme_config['hidden']
    self.anim_list = match_config['animated_extensions']
    self.switch_list = match_config['switchable_extensions']
    self.fuzzy_min_len = match_config.get('fuzzy_min_len', 5)
    self.fuzzy_threshold = match_config.get('fuzzy_threshold', 0.6)

    ext_list = '|'.join(match_config['extensions'] + match_config['animated_extensions'])
    self.maybeimage = re.compile(r'(^|\s|\^+)(\w+)\.(%s)\b' % (ext_list),re.IGNORECASE)

  def find_candidates(self, text):
    return self.maybeimage.findall(text)

  def fuzzy_match(self, searchkey):
    if searchkey in self.get_dict():
      return searchkey

    if len(searchkey) >= self.fuzzy_min_len:
      fuzzy_matches = get_close_matches(searchkey, list(self.get_dict().keys()), 1, self.fuzzy_threshold)
      if len(fuzzy_matches):
        return fuzzy_matches[0]

    return None

  def get_urls(self, searchkey):
    entry = self.get_dict()[searchkey]
    if not isinstance(entry, list):
      # If it's not a list, it's an alias we need to follow
      searchkey = entry.lower()
      entry = self.get_dict()[searchkey]

    return (entry, searchkey)

  def get(self, searchkey, matchext = ''):
    match = self.fuzzy_match(searchkey)

    if match:
      (urls, matched) = self.get_urls(match)
      if matchext:
        urls = self.get_closest(urls, matchext)

      return (urls, matched)
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
    if(len(list(self.as_dict.keys())) == 0):
      for key, urls in self.images.items():
        if(not isinstance(urls, list)):
          urls = [urls]
        self.as_dict[key] = urls

      for key, aliases in self.aliases.items():
        if(not isinstance(aliases, list)):
          aliases = [aliases]

        for alias in aliases:
          self.as_dict[alias] = key

    return self.as_dict

  def get_tuples(self):
    if(len(self.as_tuples) == 0):
      hidden_set = set(self.hidden_keys)
      for key, urls in self.images.items():
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
    return len(list(self.get_dict().keys())) - len(self.hidden_keys)

  def num_images(self):
    return sum([1 if (type(l) is str) else len(l) for l in self.images.values()])

  def get_formatted(self, format='markdown'):
    datestr = time.strftime("%I:%M %p PST, %m/%d")
    headers = {
      'markdown': "Current list in use as of " + datestr + ":\n\n|Triggers|Responses|\n|:-|:-|\n"
    }
    imagelist = headers[format];
      
    if(format == 'markdown'):
      for keylist, urls in self.get_tuples():
        imagelist += "|%s|%s|\n" % (', '.join(keylist), ' '.join(['[%d](%s)' % (i+1,url) for i, url in enumerate(urls)]))

    return imagelist
