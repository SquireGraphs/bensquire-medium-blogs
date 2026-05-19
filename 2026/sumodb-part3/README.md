# Sumo Graph Analytics

A graph analytics pipeline combining **Neo4j Graph Analytics for Snowflake** with **Snowflake SQL** to uncover competitive insights from professional sumo bout history. This repository accompanies the blog post *"From Bouts to Insights: Chaining Graph Algorithms on the Dohyō"*.

## What This Analysis Does

Finding the best wrestlers in the current era of sumo turns out to be a far more complex question than it first appears. Raw win counts favor volume over quality. PageRank surfaces prestige but misses structure. Betweenness Centrality finds the structural pillars but ignores who they beat. Only by chaining these algorithms together does a complete picture emerge.

This pipeline produces three core outputs:

- **PageRank Score** — which wrestlers beat the strongest opponents, weighted by loser rank
- **Betweenness Centrality Score** — which wrestlers hold the dominance hierarchy together
- **Chaos Score** — a composite metric combining PageRank, Betweenness, and rock-paper-scissors cycle involvement

## Repository Structure

```
sumo-graph-analytics/
├── README.md
├── snowflake/
│   └── sumo_graph_analytics.ipynb    # Full Snowflake SQL pipeline as a Python notebook
└── cypher/
    └── sumo_analysis.cypher          # Neo4j Cypher queries for graph exploration and validation
```

## Data Source

The analysis is built on `DEMO_DB.PUBLIC.DEVREL_SUMO_DB_20260512`, a table of professional sumo bouts with one row per bout containing wrestler identities, ranks, and winning technique (kimarite). The pipeline filters to **Makuuchi division bouts between January 2021 and November 2025** to focus on the current competitive era.

## Prerequisites

### Snowflake
- Snowflake account with `ACCOUNTADMIN` access for initial setup
- Neo4j Graph Analytics for Snowflake native app installed (`NEO4J_GRAPH_ANALYTICS`)
- A warehouse named `GDSONSNOWFLAKE` or updated to match your environment
- Access to `DEMO_DB.PUBLIC.DEVREL_SUMO_DB_20260512`

### Neo4j
- Neo4j instance with the sumo graph loaded
- Graph Data Science (GDS) library installed
- Nodes: `Rikishi`, `Basho`, `Day`, `Bout`, `Kimarite`
- Relationships: `DEFEATED`, `FOUGHT_IN`, `HAS_DAY`, `HAS_BOUT`, `USED_KIMARITE`

## Pipeline Overview

```
DEVREL_SUMO_DB_20260512 (raw bouts)
        |
        v
SUMO_BOUTS_RECENT          -- Makuuchi only, 2021-2025
        |
        v
SUMO_RIKISHI_ACTIVE        -- Canonical roster, one name per ID, 20+ bouts
        |
        v
SUMO_RANK_WEIGHTS          -- Rank prestige lookup table
        |
        v
SUMO_DEFEATED_EDGES_AGG    -- Rank-weighted directed edges, winner to loser
        |
        v
[GDS] PageRank             -- Prestige: who beat the strongest opponents?
        |
        v
SUMO_DOMINATES             -- Net head-to-head winner per matchup pair
        |
        v
[GDS] Betweenness          -- Structure: who bridges the dominance hierarchy?
        |
        v
SUMO_RPS_CYCLES            -- Rock-paper-scissors cycle enumeration
        |
        v
SUMO_CHAOS_SCORE           -- Composite: PageRank x Betweenness x Cycles
```

## Key Findings

- **Hoshoryu** leads rank-weighted PageRank in the 2021-2025 era, reflecting consistent victories over high-ranked opposition
- Several wrestlers with fewer total bouts (Terunofuji, Takakeisho, Onosato) maintain competitive PageRank scores, reflecting high-quality competition during limited appearances likely due to injury
- The DOMINATES graph reveals 290+ rock-paper-scissors cycles, demonstrating that the current Makuuchi division cannot be reduced to a simple linear hierarchy
- High Chaos Score wrestlers are simultaneously elite, structurally important, and resistant to simple ranking

## Notes on Name Changes

Several wrestlers changed their ring name (shikona) during the analysis window, notably Kirishima/Kiribayama and Kotonowaka/Kotozakura. The pipeline handles this by grouping all metrics by numeric `RIKISHI_ID` and joining the most recent name at the final output stage.

## Algorithm Orientation

PageRank is run with `REVERSE` orientation because the DEFEATED edge points from winner to loser. Without reversal, prestige would flow toward losers. Reversing the orientation ensures prestige accumulates on the winners of high-value bouts.

## License

MIT
