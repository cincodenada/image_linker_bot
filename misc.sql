-- Get subreddit counts/avgs
SELECT COUNT(*), AVG(score), subreddit FROM comment_scores GROUP BY subreddit ORDER BY AVG(score) DESC;