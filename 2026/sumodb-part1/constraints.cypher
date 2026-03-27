CREATE CONSTRAINT rikishi_rikishiId_unique IF NOT EXISTS
FOR (r:Rikishi)
REQUIRE r.rikishiId IS UNIQUE;

CREATE CONSTRAINT basho_bashoId_unique IF NOT EXISTS
FOR (b:Basho)
REQUIRE b.bashoId IS UNIQUE;

CREATE CONSTRAINT day_dayId_unique IF NOT EXISTS
FOR (d:Day)
REQUIRE d.dayId IS UNIQUE;

CREATE CONSTRAINT bout_boutId_unique IF NOT EXISTS
FOR (b:Bout)
REQUIRE b.boutId IS UNIQUE;

CREATE CONSTRAINT kimarite_name_unique IF NOT EXISTS
FOR (k:Kimarite)
REQUIRE k.name IS UNIQUE;
