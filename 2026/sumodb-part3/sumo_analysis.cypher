// =============================================================
// SUMO GRAPH ANALYTICS - NEO4J CYPHER QUERIES
// =============================================================
// Companion queries to the Snowflake pipeline.
// Use these for graph exploration, validation, and visualization
// in Neo4j Browser or Bloom.
//
// Prerequisites:
//   - Sumo graph loaded with nodes: Rikishi, Basho, Day, Bout, Kimarite
//   - Relationships: DEFEATED, FOUGHT_IN, HAS_DAY, HAS_BOUT, USED_KIMARITE
//   - GDS library installed for algorithm calls
//   - Node properties written back from Snowflake pipeline:
//     totalBouts2021, pageRankRankWeighted, betweennessScore, styleCluster
// =============================================================


// -------------------------------------------------------------
// SECTION 1: DATA VALIDATION
// Verify the graph is loaded correctly before running analysis
// -------------------------------------------------------------

// Count all node types
MATCH (n)
RETURN labels(n) AS nodeType, count(n) AS count
ORDER BY count DESC;

// Verify DEFEATED relationships exist in the analysis window
MATCH ()-[d:DEFEATED]->()
WHERE d.bashoId >= "202101" AND d.bashoId <= "202511"
RETURN count(d) AS boutCount;

// Check active rikishi (20+ bouts in window)
MATCH (r:Rikishi)
WHERE r.totalBouts2021 >= 20
RETURN count(r) AS activeRikishi;

// Verify node properties were written back from Snowflake
MATCH (r:Rikishi)
WHERE r.totalBouts2021 >= 20
RETURN keys(r) LIMIT 1;

// Check DOMINATES relationships exist
MATCH ()-[d:DOMINATES]->()
RETURN count(d) AS dominatesCount;


// -------------------------------------------------------------
// SECTION 2: RAW WIN COUNT ANALYSIS
// Baseline comparison before graph algorithms are applied
// -------------------------------------------------------------

// Top 20 rikishi by raw win count in the analysis window
MATCH (r:Rikishi)-[d:DEFEATED]->(opponent:Rikishi)
WHERE d.bashoId >= "202101" AND d.bashoId <= "202511"
  AND r.totalBouts2021 >= 20
WITH r, count(d) AS rawWins
MATCH (r)<-[l:DEFEATED]-(anyone:Rikishi)
WHERE l.bashoId >= "202101" AND l.bashoId <= "202511"
WITH r, rawWins, count(l) AS rawLosses
RETURN r.name                                                   AS rikishi,
       rawWins                                                   AS rawWinCount,
       rawLosses                                                 AS rawLossCount,
       rawWins + rawLosses                                       AS totalBouts,
       round(toFloat(rawWins) / (rawWins + rawLosses), 3)       AS winRate
ORDER BY rawWinCount DESC
LIMIT 20;


// -------------------------------------------------------------
// SECTION 3: PAGERANK ANALYSIS
// Rank-weighted PageRank was run in Snowflake and written back
// to the graph as pageRankRankWeighted. These queries explore results.
// -------------------------------------------------------------

// Top 20 rikishi by rank-weighted PageRank
MATCH (r:Rikishi)
WHERE r.totalBouts2021 >= 20
  AND r.pageRankRankWeighted IS NOT NULL
RETURN r.name                                   AS rikishi,
       round(r.pageRankRankWeighted, 3)         AS pageRank,
       r.totalBouts2021                         AS totalBouts
ORDER BY pageRank DESC
LIMIT 20;

// Compare raw wins vs PageRank — positive delta = beats quality opponents
// negative delta = pads wins against weaker competition
MATCH (r:Rikishi)-[d:DEFEATED]->(opponent:Rikishi)
WHERE d.bashoId >= "202101" AND d.bashoId <= "202511"
  AND r.totalBouts2021 >= 20
WITH r, count(d) AS rawWins
WITH collect({rikishi: r, rawWins: rawWins}) AS data,
     max(rawWins)                             AS maxWins,
     max(r.pageRankRankWeighted)              AS maxPR,
     min(r.pageRankRankWeighted)              AS minPR
UNWIND data AS row
WITH row.rikishi                                                          AS r,
     row.rawWins                                                          AS rawWins,
     maxWins, maxPR, minPR,
     round(toFloat(row.rawWins) / maxWins, 3)                             AS normWins,
     round((row.rikishi.pageRankRankWeighted - minPR) / (maxPR - minPR), 3) AS normPR
RETURN r.name                               AS rikishi,
       rawWins                              AS rawWinCount,
       normWins                             AS normalizedWins,
       round(r.pageRankRankWeighted, 3)     AS pageRank,
       normPR                               AS normalizedPageRank,
       round(normPR - normWins, 3)          AS delta
ORDER BY pageRank DESC
LIMIT 20;


// -------------------------------------------------------------
// SECTION 4: DOMINANCE GRAPH VISUALIZATION
// Visualize the net head-to-head winner network.
// One directed edge per matchup pair pointing toward net winner.
// -------------------------------------------------------------

// Full DOMINATES graph for active rikishi — best for Bloom visualization
MATCH (r:Rikishi)-[dom:DOMINATES]->(r2:Rikishi)
WHERE r.totalBouts2021 >= 20
  AND r2.totalBouts2021 >= 20
RETURN r, dom, r2;

// If DOMINATES relationships not yet written to graph,
// compute dominance on the fly from DEFEATED relationships
MATCH (a:Rikishi)-[d1:DEFEATED]->(b:Rikishi)
WHERE d1.bashoId >= "202101" AND d1.bashoId <= "202511"
  AND a.totalBouts2021 >= 20
  AND b.totalBouts2021 >= 20
WITH a, b, count(d1) AS aWins
MATCH (b)-[d2:DEFEATED]->(a)
WHERE d2.bashoId >= "202101" AND d2.bashoId <= "202511"
WITH a, b, aWins, count(d2) AS bWins
WHERE aWins > bWins
RETURN a.name                   AS dominant,
       b.name                   AS dominated,
       aWins                    AS wins,
       bWins                    AS losses,
       aWins - bWins            AS margin
ORDER BY margin DESC
LIMIT 30;


// -------------------------------------------------------------
// SECTION 5: BETWEENNESS CENTRALITY
// Betweenness was computed in Snowflake and written back
// as betweennessScore. These queries explore structural position.
// -------------------------------------------------------------

// Top 20 rikishi by betweenness centrality
MATCH (r:Rikishi)
WHERE r.totalBouts2021 >= 20
  AND r.betweennessScore IS NOT NULL
RETURN r.name                           AS rikishi,
       round(r.betweennessScore, 3)     AS betweenness,
       round(r.pageRankRankWeighted, 3) AS pageRank,
       r.styleCluster                   AS styleCluster
ORDER BY betweenness DESC
LIMIT 20;

// Compare PageRank vs Betweenness
// High PageRank + High Betweenness = elite structural pillar
// High PageRank + Low Betweenness  = dominant but isolated
// Low PageRank  + High Betweenness = bridge without elite prestige
MATCH (r:Rikishi)
WHERE r.totalBouts2021 >= 20
  AND r.betweennessScore IS NOT NULL
  AND r.pageRankRankWeighted IS NOT NULL
WITH r,
     round(r.pageRankRankWeighted, 3)   AS pageRank,
     round(r.betweennessScore, 3)       AS betweenness
RETURN r.name       AS rikishi,
       pageRank,
       betweenness,
       CASE
           WHEN pageRank >= 2.0 AND betweenness >= 100 THEN 'Elite Pillar'
           WHEN pageRank >= 2.0 AND betweenness < 100  THEN 'Dominant Isolate'
           WHEN pageRank < 2.0  AND betweenness >= 100 THEN 'Structural Bridge'
           ELSE 'Mid Tier'
       END AS role
ORDER BY pageRank DESC
LIMIT 20;


// -------------------------------------------------------------
// SECTION 6: ROCK-PAPER-SCISSORS CYCLES
// Find non-transitive dominance triangles where
// A beats B, B beats C, and C beats A
// -------------------------------------------------------------

// Find RPS cycles using DOMINATES relationships
MATCH (a:Rikishi)-[d1:DOMINATES]->(b:Rikishi)-[d2:DOMINATES]->(c:Rikishi)-[d3:DOMINATES]->(a)
WHERE a.totalBouts2021 >= 20
  AND b.totalBouts2021 >= 20
  AND c.totalBouts2021 >= 20
  AND elementId(a) < elementId(b)
  AND elementId(a) < elementId(c)
RETURN a.name                                       AS rikishi_a,
       d1.margin                                    AS a_beats_b_by,
       b.name                                       AS rikishi_b,
       d2.margin                                    AS b_beats_c_by,
       c.name                                       AS rikishi_c,
       d3.margin                                    AS c_beats_a_by,
       d1.margin + d2.margin + d3.margin            AS total_cycle_margin
ORDER BY total_cycle_margin DESC
LIMIT 10;

// Which rikishi appear in the most RPS cycles
MATCH (a:Rikishi)-[:DOMINATES]->(b:Rikishi)-[:DOMINATES]->(c:Rikishi)-[:DOMINATES]->(a)
WHERE a.totalBouts2021 >= 20
  AND b.totalBouts2021 >= 20
  AND c.totalBouts2021 >= 20
WITH [a, b, c] AS trio
UNWIND trio AS r
WITH r, count(*) AS cycleCount
RETURN r.name                               AS rikishi,
       cycleCount                           AS cycleAppearances,
       round(r.pageRankRankWeighted, 3)     AS pageRank,
       round(r.betweennessScore, 3)         AS betweenness
ORDER BY cycleAppearances DESC
LIMIT 15;

// Visualize a specific RPS cycle
// Replace rikishi names with actual results from query above
MATCH path = (a:Rikishi)-[:DOMINATES]->(b:Rikishi)-[:DOMINATES]->(c:Rikishi)-[:DOMINATES]->(a)
WHERE a.name = 'Hoshoryu'
  AND elementId(a) < elementId(b)
  AND elementId(a) < elementId(c)
RETURN path
LIMIT 5;


// -------------------------------------------------------------
// SECTION 7: CHAOS SCORE
// Composite metric combining PageRank, Betweenness, and cycle count
// Identifies wrestlers who are elite, structurally important,
// and resistant to simple linear ranking simultaneously
// -------------------------------------------------------------

// Compute chaos score directly in Cypher
// (mirrors the Snowflake SUMO_CHAOS_SCORE table)
MATCH (a:Rikishi)-[:DOMINATES]->(b:Rikishi)-[:DOMINATES]->(c:Rikishi)-[:DOMINATES]->(a)
WHERE a.totalBouts2021 >= 20
  AND b.totalBouts2021 >= 20
  AND c.totalBouts2021 >= 20
WITH [a, b, c] AS trio
UNWIND trio AS r
WITH r, count(*) AS cycleCount

WITH collect({r: r, cycleCount: cycleCount}) AS data,
     max(r.pageRankRankWeighted)              AS maxPR,
     max(r.betweennessScore)                  AS maxBetween,
     max(cycleCount)                          AS maxCycles

UNWIND data AS row
WITH row.r                                                          AS r,
     row.cycleCount                                                 AS cycleCount,
     round(row.r.pageRankRankWeighted / maxPR, 3)                  AS normPR,
     round(row.r.betweennessScore / maxBetween, 3)                  AS normBetween,
     round(toFloat(row.cycleCount) / maxCycles, 3)                  AS normCycles
RETURN r.name                                                       AS rikishi,
       round(r.pageRankRankWeighted, 3)                             AS pageRank,
       round(r.betweennessScore, 3)                                 AS betweenness,
       cycleCount,
       normPR,
       normBetween,
       normCycles,
       round(normPR + normBetween + normCycles, 3)                  AS chaosScore
ORDER BY chaosScore DESC
LIMIT 20;


// -------------------------------------------------------------
// SECTION 8: STYLE CLUSTER ANALYSIS
// Style clusters were computed in Snowflake and written back
// as styleCluster: 0=Mixed, 1=Pure Oshi, 2=Yotsu/Belt
// -------------------------------------------------------------

// Rikishi by style cluster
MATCH (r:Rikishi)
WHERE r.totalBouts2021 >= 20
  AND r.styleCluster IS NOT NULL
RETURN r.styleCluster                       AS cluster,
       CASE r.styleCluster
           WHEN 0 THEN 'Mixed/Balanced'
           WHEN 1 THEN 'Pure Oshi'
           WHEN 2 THEN 'Yotsu/Belt'
       END                                 AS styleLabel,
       count(r)                            AS members,
       collect(r.name)[..8]               AS sampleWrestlers
ORDER BY cluster;

// Cross-style win rates — does style predict outcomes?
MATCH (winner:Rikishi)-[d:DEFEATED]->(loser:Rikishi)
WHERE d.bashoId >= "202101" AND d.bashoId <= "202511"
  AND winner.totalBouts2021 >= 20
  AND loser.totalBouts2021 >= 20
  AND winner.styleCluster IS NOT NULL
  AND loser.styleCluster IS NOT NULL
  AND winner.styleCluster <> loser.styleCluster
WITH winner.styleCluster AS winnerCluster,
     loser.styleCluster  AS loserCluster,
     count(d)            AS wins
MATCH (b:Rikishi)-[d2:DEFEATED]->(a:Rikishi)
WHERE d2.bashoId >= "202101" AND d2.bashoId <= "202511"
  AND b.styleCluster = loserCluster
  AND a.styleCluster = winnerCluster
  AND b.totalBouts2021 >= 20
  AND a.totalBouts2021 >= 20
WITH winnerCluster, loserCluster, wins, count(d2) AS losses
RETURN winnerCluster,
       loserCluster,
       wins,
       losses,
       wins + losses                                    AS totalBouts,
       round(toFloat(wins) / (wins + losses), 3)       AS winRate
ORDER BY winnerCluster, winRate DESC;
