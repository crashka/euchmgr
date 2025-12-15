# Ranking Notes

## General Rules for Ranking

These rules apply in a general fashing to the seeding round, round robin divisional (and
inter-divisional) play, and overall tournament rankings.  Special considerations for any
of these stages/purposes will be called out below.

The first consideration is always **win percentage**.  If players (for seeding) or teams
(for round robin play) have identical win percentages at the end of the stage, they are
said to be tied at the current position within the ranking.  Positions following the tied
group are assigned similar to golf tournaments—for example, if there are two players/teams
tied for first, the player/team with the next best win percentage is said to be in third
place (position).

Ties, at whatever position, are resolved using the following tie-breaking criteria (from
Bobby), in the specified order:

- Individual head-to-head
- In three or more way ties, head-to-head against all other tied teams
- In three or more way ties (if still tied after head-to-head against all other tied
  teams), points percentage within games against tied teams
- Overall points percentage
- Coin flip

## Tie-Breaking Algorithm

We will try and implement the tie-breaking rules specified above as neatly and robustly
as we can.  Note that we will use the term "cohort" here to describe the group (of two or
more teams) currently tied for a particular position (based on win percentage) that we
need to rank against each other.

Here is the high-level outline of the approach:

- **Rank players/teams** using the following criteria (applied successively, as needed to
  distinguish):
  - Win percentage head-to-head within the cohort
  - Points percentage head-to-head within the cohort
  - Overall points percentage (from the larger seeding or round robin stage)
- **Identify cyclic win groups** within the cohort
  - Example: group = \[A, B, C], if A beats B, B beats C, and C beats A
- **Elevate head-to-head winners** above higher-ranked cohort players/teams they beat in
  the stage
  - This is only applied if both are not members of a cyclic win group

More detail and some discussion on these evaluation steps is provided below.  For what
it's worth, we note that some of the more arcane scenarios are much more likely to occur
for tie-breaking in the seeding round rather than tounament play, especially as related to
unequal numbers of games played within a cohort (including none).  I don't think different
rules and/or algorithms are needed between the two stages, but that would be up to the
rules committee.

### Rank Players/Teams

There are several cases where we *may* want to distinguish between players/teams with
identical win percentages within the cohort:

- Favoring more wins for perfect records (e.g. 3-0 is better than 2-0)
- Penalizing more losses for all-losing records (e.g. 0-2 is worse than 0-1)
- Favoring an even record for games played over no games at all within the cohort
  (e.g. 1-1 is better than 0-0)

We can implement this by introducing a "W-L factor" (to be applied on top of win
percentage), which would be generally represented by wins minus lossses (win-loss diff).
To handle the third case above, we would hard-wire a value of `-1` for a inter-cohort
record of 0-0.

Note that W-L factor can (if desired) also be used to distinguish between other instances
of identical win percentages (such as 1-1 vs. 2-2, or 2-1 vs. 4-2), but I'm guessing we
will not want to do that.

I have currently implemented W-L factor as a configurable tie-breaker in the app for the
first three cases above, but I will leave it up to the rules committee to determine the
W-L factor rules they want to deploy (if any).

### Identify Cyclic Win Groups

As indicated above, we will ignore the individual head-to-head matchups for elevating or
demoting teams within each cyclic win group (see below), and fall back on pure cohort win
percentage and points percentage.  The rationale is that the cyclic group represents a
wash between the group members in terms of head-to-head play.

Note that there can (in theory) be more than one cyclic win group within a cohort—and, in
fact, a particular player/team (or even multiple) may even be part of more than one cyclic
group (however unlikely).  If this happens, we will treat each of the groupings
independently.

### Elevate Head-to-Head Winners

If the sorted list (based on the criteria above) contains any players/teams that have
beaten a player/team currently ranked above them for the stage, we will elevate the winner
just above the loser in the ranking order.  If we start from the bottom of the list and
work our way up, it should resolve cleanly, since we are ignoring individual head-to-head
matchup elevations for any *cyclical* groups (as discussed above).

Overall, this is an "optimistic" approach that presumes that the core sort critera (with
or without W-L factor) will yield correct results in the vast majority of cases.  In
particular, it automatically handles most cases of individual head-to-head matchups.  We
expect that the head-to-head winner elevation pass will generally be a no-op.  I only
mention this here to explain why the algorithmic processing order may *appear* to be
reversed from the initial description of the tie-breaking rules at the top of this
document.

## Additional Notes

### Manual Inspection

For transparency and verifiability, I will provide a **Tie-Breaker Report** for both the
seeding and round robin tournament stages.  For each of the cohorts tied for a particular
position, it will show:

- Initial sorting
- Cyclic win groups
- Head-to-head player/team elevations
- Final ranking within the cohort
- Listing of all inter-cohort games (by player or team)
- Flagging residual ties

Preliminary examples of these reports can be found in [examples/](examples), along with
their associated tournament dashboards (for reference).  This is currently *work in
process*, and does not yet include all of the features listed above.

### Math

A comment from Ken about the precision needed in computing points percentages got me
thinking about the number of decimal places we want to show on dashboards or in reports
for this.  Here are a few notes:

- Largest possible denominator (total points) is 152, i.e. 19 points (max per game) * 8
  rounds
- Closest possible ratios are `1/152` and `1/151` (or `150/151` and `151/152`), with a
  difference of `0.00004357`
  - Note that the first pair is not actually attainable in competition, but the one in
    parentheses is (in theory)
- If the ratios are represented as percentages (i.e. multiplied by 100), the smallest
  possible difference is then `0.004357%`
- Thus, 3 decimal places (5 significant digits) will always be suffcient to distinguish
  close ratios from actual ties
- Fun fact: outside of the ratios listed above—in other words, going into the "middle of
  the pack" for random *\[you know what I mean]* non-adjacent leading-/trailing-edge ratio
  pairs—the closest ratios are `51/152` and `50/149` (or the congruent pair of `99/149`
  and `101/152`), with a difference of `0.00004415` (identical to the actual closest case
  to 6 significant digits)

For anyone interested, a little more exploration of this math problem here: [Ratio
Math](https://github.com/crashka/ratio-math/).

### Overall Tournament Rankings

Need to specify the rules for incoporation of game and match results from semi-final and
final round play.
