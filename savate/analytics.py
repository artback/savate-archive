"""The analytical shape of the database: one row per fighter per bout.

The bouts table is written corner-first, because that is how a bout is scored.
Almost every question about the sport is asked fighter-first - their record,
their form, who they have met - and answering those from a corner-first table
means union-ing it with itself in every query. So `appearances` does that once,
and everything else is built on it.

On top of that sits `fighter_bouts`, which adds the dimensions a bout does not
state but a timetable implies: what time of day it was, which day of the meet,
how many bouts the fighter had already had, and how long they had rested. Those
are what turn a results table into something you can ask questions of - whether
a fighter fades in the evening, whether a short turnaround costs them, whether
the third bout of the day is where the warnings come.

Two honesties are built in rather than left to the reader:

  * Not every source publishes times. Paper results almost never do. Every
    time-based view is restricted to bouts that actually carry a timestamp, and
    `coverage` says how many that is per tournament, so a finding is never
    quietly computed over a tenth of the data.
  * A championship gives each fighter three to five bouts. That is far too few
    to say anything about one fighter's time of day. The per-fighter views carry
    their own sample size so the number is never read without it, and the
    aggregate views - where the samples are large enough to mean something - are
    the ones to reach for until the archive is deep.
"""

VIEWS = """
-- One row per fighter per bout: the same bout seen from each corner.
-- `fighter_id` is the person, `fighter` the spelling this source used; career
-- questions must group on the id, because two sources rarely spell a name the
-- same way. Where identity is unknown the id falls back to the spelling, so a
-- fighter is never silently dropped from their own record.
CREATE VIEW appearances AS
    SELECT a.*,
           COALESCE(fa.fighter_id, a.fighter) AS fighter_id,
           COALESCE(oa.fighter_id, a.opponent) AS opponent_id
    FROM raw_appearances a
    LEFT JOIN fighter_aliases fa ON fa.alias = a.fighter
    LEFT JOIN fighter_aliases oa ON oa.alias = a.opponent;

CREATE VIEW raw_appearances AS
    SELECT bout_id, tournament, date, time, ring, category, gender, weight_kg,
           weight_bound, phase, poule,
           red AS fighter, red_country AS country,
           blue AS opponent, blue_country AS opponent_country,
           red_points AS points_for, blue_points AS points_against,
           red_warnings AS warnings, blue_warnings AS warnings_against,
           decision, status, 'red' AS corner,
           -- A source can name the winner without publishing a corner: the
           -- French federation's finals sheets do exactly that. Reading the
           -- outcome from the corner alone would throw those results away, so
           -- the name is consulted wherever the corner is silent.
           CASE WHEN winner_corner = 'red' THEN 'win'
                WHEN winner_corner = 'blue' THEN 'loss'
                WHEN winner <> '' AND winner = red THEN 'win'
                WHEN winner <> '' AND winner = blue THEN 'loss' END AS outcome
    FROM bouts
    UNION ALL
    SELECT bout_id, tournament, date, time, ring, category, gender, weight_kg,
           weight_bound, phase, poule,
           blue, blue_country, red, red_country,
           blue_points, red_points, blue_warnings, red_warnings,
           decision, status, 'blue',
           CASE WHEN winner_corner = 'blue' THEN 'win'
                WHEN winner_corner = 'red' THEN 'loss'
                WHEN winner <> '' AND winner = blue THEN 'win'
                WHEN winner <> '' AND winner = red THEN 'loss' END AS outcome
    FROM bouts;

-- Appearances, plus what the timetable implies about each one.
CREATE VIEW fighter_bouts AS
    SELECT a.*,
           CASE WHEN a.time = '' THEN NULL
                ELSE CAST(substr(a.time, 1, 2) AS INTEGER) END AS hour,
           CASE WHEN a.time = '' THEN NULL
                WHEN CAST(substr(a.time, 1, 2) AS INTEGER) < 12 THEN 'morning'
                WHEN CAST(substr(a.time, 1, 2) AS INTEGER) < 17 THEN 'afternoon'
                ELSE 'evening' END AS part_of_day,
           CASE WHEN a.date = '' THEN NULL ELSE
                DENSE_RANK() OVER (PARTITION BY a.tournament
                                   ORDER BY a.date) END AS day_index,
           ROW_NUMBER() OVER (PARTITION BY a.tournament, a.fighter
                              ORDER BY a.date, a.time, a.bout_id) AS bout_index,
           ROW_NUMBER() OVER (PARTITION BY a.tournament, a.fighter, a.date
                              ORDER BY a.time, a.bout_id) AS bout_of_day,
           CAST(ROUND((julianday(a.date || ' ' || a.time) -
                 julianday(LAG(a.date || ' ' || a.time)
                     OVER (PARTITION BY a.tournament, a.fighter
                           ORDER BY a.date, a.time, a.bout_id))) * 1440)
                AS INTEGER) AS minutes_rested,
           CASE WHEN a.points_for = '' OR a.points_against = '' THEN NULL
                ELSE CAST(a.points_for AS INTEGER)
                     - CAST(a.points_against AS INTEGER) END AS margin
    FROM appearances a;

-- What each tournament can actually answer, so no view is read past its data.
CREATE VIEW coverage AS
    SELECT tournament,
           COUNT(*) AS bouts,
           SUM(date <> '') AS with_date,
           SUM(time <> '') AS with_time,
           SUM(red_warnings <> '') AS with_warnings,
           SUM(status = 'decided') AS decided
    FROM bouts GROUP BY tournament;

-- A fighter's career across everything in the database.
CREATE VIEW fighter_record AS
    SELECT a.fighter_id,
           COALESCE(f.name, a.fighter) AS fighter,
           COALESCE(f.countries, a.country) AS country,
           COUNT(*) AS bouts,
           SUM(a.outcome = 'win') AS wins,
           SUM(a.outcome = 'loss') AS losses,
           ROUND(100.0 * SUM(a.outcome = 'win') / NULLIF(COUNT(*), 0), 1) AS win_pct,
           SUM(CAST(NULLIF(a.warnings, '') AS INTEGER)) AS warnings,
           COUNT(DISTINCT a.tournament) AS tournaments,
           COUNT(DISTINCT a.fighter) AS spellings
    FROM appearances a
    LEFT JOIN fighters f ON f.id = a.fighter_id
    WHERE a.outcome IS NOT NULL
    GROUP BY a.fighter_id;

-- The aggregate form question: does the whole field fare differently by hour?
-- Every bout has a winner and a loser, so a 50% rate is the null result; what
-- moves is the shape of the bouts, not who wins them.
CREATE VIEW form_by_part_of_day AS
    SELECT part_of_day,
           COUNT(*) / 2 AS bouts,
           ROUND(AVG(CAST(NULLIF(warnings, '') AS INTEGER)), 2) AS warnings_per_fighter,
           SUM(decision = 'disqualification') / 2 AS disqualifications,
           SUM(decision = 'forfait') / 2 AS forfaits
    FROM fighter_bouts
    WHERE part_of_day IS NOT NULL
    GROUP BY part_of_day;

-- Per fighter, carrying its own sample size: three bouts is not a trend.
CREATE VIEW fighter_by_part_of_day AS
    SELECT fighter_id, MIN(fighter) AS fighter, part_of_day,
           COUNT(*) AS bouts,
           SUM(outcome = 'win') AS wins,
           ROUND(100.0 * SUM(outcome = 'win') / NULLIF(COUNT(*), 0), 1) AS win_pct
    FROM fighter_bouts
    WHERE part_of_day IS NOT NULL AND outcome IS NOT NULL
    GROUP BY fighter_id, part_of_day;

-- Does a fighter's form move as their day goes on?
CREATE VIEW form_by_bout_of_day AS
    SELECT bout_of_day,
           COUNT(*) AS appearances,
           ROUND(100.0 * SUM(outcome = 'win') / NULLIF(COUNT(*), 0), 1) AS win_pct,
           ROUND(AVG(CAST(NULLIF(warnings, '') AS INTEGER)), 2) AS warnings
    FROM fighter_bouts
    WHERE outcome IS NOT NULL AND date <> ''
    GROUP BY bout_of_day;

-- Short turnaround against long: rest is bucketed because the exact minute is
-- noise and the hour is not.
CREATE VIEW form_by_rest AS
    SELECT CASE WHEN minutes_rested IS NULL THEN 'first bout'
                WHEN minutes_rested < 60 THEN 'under an hour'
                WHEN minutes_rested < 180 THEN '1-3 hours'
                WHEN minutes_rested < 1440 THEN 'same day, 3+ hours'
                ELSE 'a day or more' END AS rest,
           COUNT(*) AS appearances,
           ROUND(100.0 * SUM(outcome = 'win') / NULLIF(COUNT(*), 0), 1) AS win_pct
    FROM fighter_bouts
    WHERE outcome IS NOT NULL AND date <> ''
    GROUP BY rest;

-- Every meeting between two fighters, wherever and whenever.
CREATE VIEW head_to_head AS
    SELECT fighter_id, opponent_id,
           MIN(fighter) AS fighter, MIN(opponent) AS opponent,
           COUNT(*) AS meetings,
           SUM(outcome = 'win') AS wins,
           GROUP_CONCAT(DISTINCT tournament) AS tournaments
    FROM appearances
    WHERE outcome IS NOT NULL
    GROUP BY fighter_id, opponent_id;

-- Every final that has a winner: the medal table across every tournament.
CREATE VIEW champions AS
    SELECT tournament, category, gender, weight_kg, weight_bound,
           winner AS champion,
           CASE WHEN winner <> '' AND winner = blue THEN blue_country
                WHEN winner_corner = 'blue' THEN blue_country
                ELSE red_country END
               AS champion_country,
           loser AS runner_up,
           CASE WHEN winner <> '' AND winner = blue THEN red_country
                WHEN winner_corner = 'blue' THEN red_country
                ELSE blue_country END
               AS runner_up_country
    FROM bouts
    WHERE phase = 'final' AND status = 'decided';

-- Placings, joined to the person and to what the tournament was.
-- For most years this is the only record that exists, so a career view that
-- reads only the bouts table stops in 2023 and looks like a career that ended.
CREATE VIEW podium AS
    SELECT p.placing_id, p.tournament, t.name AS event, t.year, t.level,
           t.discipline, p.category, p.gender, p.age_class, p.weight_kg,
           p.weight_bound, p.rank, p.medal, p.fighter, p.country,
           COALESCE(fa.fighter_id, p.fighter) AS fighter_id
    FROM placings p
    LEFT JOIN fighter_aliases fa ON fa.alias = p.fighter
    LEFT JOIN tournaments t ON t.slug = p.tournament;

-- A fighter's honours, which is what most of the archive can actually answer.
CREATE VIEW fighter_medals AS
    SELECT fighter_id,
           MIN(fighter) AS fighter,
           SUM(medal = 'gold') AS golds,
           SUM(medal = 'silver') AS silvers,
           SUM(medal = 'bronze') AS bronzes,
           COUNT(*) AS medals,
           MIN(year) AS first_year, MAX(year) AS last_year,
           COUNT(DISTINCT tournament) AS events
    FROM podium
    GROUP BY fighter_id;

-- Nations by medal, from the placings - a far longer run of years than the
-- finals table, which only exists where bout-by-bout results were published.
CREATE VIEW medal_table AS
    SELECT country,
           SUM(medal = 'gold') AS golds,
           SUM(medal = 'silver') AS silvers,
           SUM(medal = 'bronze') AS bronzes,
           COUNT(*) AS medals,
           MIN(year) AS first_year, MAX(year) AS last_year
    FROM podium
    WHERE country <> ''
    GROUP BY country;
"""
