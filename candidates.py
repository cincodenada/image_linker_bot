from __future__ import print_function
import sys

from joelbot import BaseBot
from memedb import MemeDb

bot = BaseBot()
db = MemeDb(bot.config['bot']['dbfile'])

check_days = int(sys.argv[1]) if len(sys.argv) > 1 else 365

count_query = """
SELECT
  total_count, 
  recent_count,
  key,
  cid
FROM (
  SELECT
      COUNT(*) AS total_count,
      SUM(case when (strftime("%s") - ts) < 60*60*24*{} then 1 else 0 end) AS recent_count,
      LOWER(key) AS key,
      cid
    FROM candidates
    GROUP BY LOWER(key)
) totals
WHERE recent_count > 0 AND total_count > 100
ORDER BY total_count DESC
""".format(check_days)

print(count_query)

for candidate in db.c.execute(count_query):
    comment = bot.r.comment(candidate['cid'])
    print(u"%s (%d/%d) - https://reddit.com%s" % (candidate['key'], candidate['total_count'], candidate['recent_count'], comment.permalink))
