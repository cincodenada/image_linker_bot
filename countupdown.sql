SELECT 
	COUNT(*),
	type,
	ts
FROM
(SELECT 
	(CASE
		WHEN score<1 THEN 'down'
		WHEN score==1 THEN 'none'
		-- WHEN score>=10 THEN 'up10'
		ELSE 'up' 
	END) as type,
	ts
	FROM comment_scores
)
GROUP BY type, ts
ORDER BY ts DESC, type ASC;

SELECT COUNT(*), AVG(score), subreddit FROM comment_scores GROUP BY subreddit ORDER BY AVG(score) DESC;