# Euchre Manager

[Overview](#overview)<br>
[Identifiers and Rankings](#identifiers-and-rankings)<br>
  \- [General Description](#general-description)<br>
  \- [Players](#players)<br>
  \- [Teams](#teams)<br>
[Tie-Breaking Rules](#tie-breaking-rules)<br>
  \- [Seeding Round](#seeding-round)<br>
  \- [Tournament Round Robin](#tournament-round-robin)<br>
  \- [Playoffs](#playoffs)<br>
  \- [Notes on Head-to-Head Matchups](#notes-on-head-to-head-matchups)<br>
  \- [Illustrative Examples](#illustrative-examples)<br>
[Tournament Format](#tournament-format)<br>
  \- [Player Registration](#player-registration)<br>
  \- [Seeding Round](#seeding-round)<br>
  \- [Partner Picking](#partner-picking)<br>
  \- [Tournament Round Robin](#tournament-round-robin)<br>
  \- [Final Four Playoffs](#final-four-playoffs)<br>
[Import/Export Format](#importexport-format)<br>
[Admin and Mobile APIs](#admin-and-mobile-apis)<br>
[UI Screenshots and Descriptions](#ui-screenshots-and-descriptions)<br>

## Overview

The purpose of this application is to help facilitate and/or manage a Beta Upsilon-style
euchre tournament (for anyone who knows what that means).  The basic design mimics the
processes and tracking mechanisms developed over the past twenty-whatever years.  The
introduction of digitization and automation is intended to provide support for the
tournament operators and rules committee, and not to replace them.

There are three user interface components to the application:

- The **Admin UI**, which can be used as the system of record for all scores, stats, and
  standings
- The **Mobile UI**, which can be used as the data entry point for player registration,
  partner picks, and game scores
- The **Charts and Dashboards** layer, which can provide projectable representations of
  the traditionally hand-drawn brackets and scoring posters
  
Behind the scenes is a database and some application server code to help implement the
process flow and ensure the integrity of the data for the tournament.

## Identifiers and Rankings

### General Description

- **"Seed"** levels for a bracket are earned through play in the previous round, and offer
  preferential treatment when it comes to choices (e.g. picking partners), or strength of
  opponents and/or byes in the upcoming round.
- **"Position"** represents the outcome of bracket play, where players or teams with the
  same winning percentage occupy the same position.  Similar to a golf tournament, if two
  players/teams are tied for first, the player/team with the next best record is said to
  be in *third* place (or "position", our case), etc.
  - A tie-breaking process is then applied to the players or teams sharing an identical
  position (see [Tie-Breaking Rules](#tie-breaking-rules) below).
- **"Rank"** represents the final ordering of players or teams after tie-breaking rules
  have been applied to all players or teams sharing positions within the bracket and/or
  context.

### Players

- **Player Num** &ndash; used to identify players for game assignments in the seeding
  bracket.  These numbers used to be determined by drawing ping pong balls from a bag, but
  can now be generated randomly by the platform.  Note that numbers can actually be
  entered through either the admin or mobile interfaces (e.g. if doing the ping pong ball
  thing for nostalgia).
- **Player Rank** (also referred to as "Seed Rank" in the UI) &ndash; the ranking earned
  by players during seeding round play, after tie-breaking rules have been applied (see
  below)&mdash;lower is better, no ties.  This ranking represents the order in which team
  partners are picked.
  - Note that there is a separate **Player Pos** number indicating the player's seeding
    round ranking *before tie-breakers* (thus, may include ties)&mdash;this is available
    in the admin UI for reference.  Tie-breaking rules are then applied to player cohorts
    with identical Player Pos computations in order to determine the Player Rank.

### Teams

- **Team Seed** &ndash; used to identify teams for division and game assignments in the
  round robin tournament brackets.  Team Seed is determined by the average Player Rank for
  the players (2 or 3) on the team.  Ties are broken by the highest ranked player on a
  team.  Note that a *non-champion* three-headed monster team (if any) is always seeded
  last, regardless of average Player Rank.
- **Div Seed** &ndash; represents the relative Team Seed within each division.  This is
  used for game assignments when the division brackets for the tournament are completely
  self-contained (no inter-div matchups).  See [Tournament Format](#tournament-format)
  (below) for more details.
  - Note that this only applies to multi-divisional tournaments.  The application may
    later support smaller, single-division tournaments (e.g. off-season, regional, etc.),
    if there is sufficient interest.
- **Div Rank** &ndash; the ranking earned by teams within their division during round
  robin tournament play, after tie-breaking rules have been applied.  The top two teams in
  each division qualify for the final four playoff round.
  - **Div Pos** (which appears on the Round Robin Live Dashboard and Tie-Breaker Report)
    indicates ranking within the division *before tie-breakers* (same as with Player Pos,
    above).  Tie-breaking rules are then applied to team cohorts with identical Div Pos
    computations in order to determine the Div Rank.
- **Team Rank** (pre-playoffs) &ndash; the ranking earned by teams *across divisions*
  during round robin play, after tie-breaking rules have been applied.  The top two teams
  in each division always occupy the first four Team Ranks (though not necessarily in
  final tournament ranking order), and are removed from tie-breaking consideration
  relative to the remaining teams.  Note that Div Rank order is preserved here for teams
  within a division.
  - This identifier is used to denote team seeds for the final four playoff rounds.
  - **Team Pos** indicates the overall team ranking (pre-playoff) before tie-breaking (see
    description for Div Pos above).
- **Final Rank** &ndash; represents the final tournament ranking for teams, after playoff
  rounds are complete.  This is the same as Team Rank, except that the Final Four teams
  are ordered by playoff results (see [Playoffs](#playoffs) below).
  - **Final Pos** is essentially the same as Team Pos (above), except that the final four
    teams are always in positions 1 through 4 (with remaining teams in the same order,
    which may include tied positions).

## Tie-Breaking Rules

The following rules are applied (in order) to players or teams with identical winning
percentages&mdash;said to be in the same *position*, or considered as "cohorts"&mdash;for
the round and/or context (e.g. division).

### Seeding Round

1. **Points Percentage** &ndash; (Pts For) / (Pts For + Pts Against) for the seeding round
2. **Points For** &ndash; for the seeding round
3. **Player Num** &ndash; equivalent to a coin flip (since Player Nums are determined by
   random), but we do it this way for traceability

### Tournament Round Robin

1. **Head-to-Head** &ndash; winners for head-to-head matchups in the round are always
   ranked above losers (except in the case of "cyclic win groups", see [Notes on
   Head-to-Head Matchups](#notes-on-head-to-head-matchups) below)
2. **Points Percentage** &ndash; (Pts For) / (Pts For + Pts Against) for round robin play
3. **Points For** &ndash; for round robin play
4. **Team Seed** &ndash; to reward better individual player seeding round play (if
   necessary)

### Playoffs

*\[applies to 3rd and 4th place teams only\]*

1. **Game Win Percentage** &ndash; for the semifinal round (as opposed to *Match* win
   percentage, which will always be tied at 0%)
2. **Points Percentage** &ndash;  for the semifinal round
3. **Team Rank** &ndash; to reward better round robin play (if necessary)

### Notes on Head-to-Head Matchups

In terms of implementation, tied players/teams are first sorted by all of the *other*
criteria (e.g. points percentage, points for, etc.), and then a head-to-head "elevation"
process is performed.  The elevation process works by starting with the lowest ranked team
within the cohort and elevating it above the current highest ranked team that it has beat
head-to-head in the round.  The same process is then applied to each of the remaining
teams in the cohort (in their original order, bottom-to-top).

Notice: head-to-head matchups are *ignored* for tie-breaking in the case of **cyclic win
groups** (e.g. A beats B, B beats C, C beats A).  That is, a player/team is *not elevated*
above another player/team that it has beat if they are both part of the same cyclic win
group (see [Example 1](#example-1---head-to-head-and-cyclic-win-groups) below, as an
illustration).  Note that cyclic win groups are shown in all of the Tie-Breaker Reports.

### Illustrative Examples

#### Example 1 - Head-to-Head and Cyclic Win Groups

Note that the "elevation" process for head-to-head wins *can* actually be used with cyclic
win groups, but this (constructed) example demonstrates why that is not desirable.

Let's say that 6 teams are tied with the same record, each one having beat another of the
cohort teams during round play.  Here they are ranked in descending order of Pts Pct:

| Team | Pts Pct | Beat | Lost To |
| :---: | :---: | :---: | :---: |
| 1 | **.800** | 3 | 5 |
| 2 | **.700** | 4 | 6 |
| 3 | **.600** | 5 | 1 |
| 4 | **.500** | 6 | 2 |
| 5 | **.400** | 1 | 3 |
| 6 | **.300** | 2 | 4 |

As can be seen, Teams 1-3-5 form a cyclic win group, as do Teams 2-4-6.  If we were to
start from the bottom (Team 6) and work our way up with the head-to-head "elevation"
process&mdash;that is: 6 beats 2, 5 beats 1, 4 beats 6, 3 beats 5, 2 beats 4, and 1 beats
3)&mdash;we would end up with the following ranking order:

| Team | Pts Pct | Beat | Lost To | Effect |
| :---: | :---: | :---: | :---: | :---: |
| 1 | .800 | 3 | 5 | - |
| 3 | *.600* | 5 | 1 | <span style="color: green;">*Up 1*</span> |
| 5 | *.400* | 1 | 3 | <span style="color: green;">*Up 2*</span> |
| 2 | *.700* | 4 | 6 | <span style="color: red;">*Down 2*</span> |
| 4 | *.500* | 6 | 2 | <span style="color: red;">*Down 1*</span> |
| 6 | .300 | 2 | 4 | - |

Within each cyclic win group (1-3-5 and 2-4-6), the relative positions are maintained
(i.e. they are still in order of Pts Pct), but the *overall* Pts Pct ordering has been
mangled.  Teams 2 and 4 have been penalized because their group "leader" (Team 2) ranks
below the other group "leader" (Team 1); and Teams 3 and 5 have conversely benefitted.

It's clearly better to skip the elevation process when both teams are part of the same
cyclic win group, which would mean keeping the original (fair!) rankings in this case.
The final result will be truer to the tie-breaking rules as stated above.

#### Example 2 - Consideration of Cohort Stats

A possible consideration for tie-breaking between teams with equal Win Pct records (either
within or across divisions) would be the inclusion of cohort-level stats&mdash;namely
head-to-head Win Pct and Pts Pct for games played within (amongst?) the cohort.

To illustrate this notion, we can use the actual 2023 New Orleans tournament final team
rankings as an example.  In the 7th overall position, there were five teams with an equal
.500 win percentage.  Here are the teams listed in descending order of tournament points
percentage, before head-to-head elevations are applied (as described above):

| Team | Div | Tourn<br>Win Pct | Tourn<br>Pts Pct | H2H<br>W-L | H2H<br>Pts Pct | Beat | Lost To |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| Cooper/Mentle [6] | 2 | .500 | **.515** | 1-1 | .486 | Wee/Cureton [2] | Lineman/DiPesa [7] |
| Wee/Cureton [2] | 2 | .500 | **.512** | 0-2 | .412 | | Lineman/DiPesa [7]<br>Cooper/Mentle [6] |
| Rooze/Pound [13] | 1 | .500 | **.508** | 0-1 | .375 | | O’Leary/Mary [8] |
| O’Leary/Mary [8] | 1 | .500 | **.489** | 1-0 | .625 | Rooze/Pound [13] | |
| Lineman/DiPesa [7] | 2 | .500 | **.481** | 2-0 | .606 | Cooper/Mentle [6]<br>Wee/Cureton [2] | |

Here is the final ranking after the head-to-head win elevations are applied (this is
copied from the
[Final Tournament Results](<resources/nola_2023 - Final Tournament Results.html>),
with details further represented in the
[Tie-Breaker Report](<resources/nola_2023 - Final Tournament Tie-Breaker Report.html>)
\[see Position 7\]):

| Team | Div | Tourn<br>Win Pct | Tourn<br>Pts Pct | H2H<br>W-L | H2H<br>Pts Pct | Beat | Lost To | Effect |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- | :---: |
| Lineman/DiPesa [7] | 2 | .500 | .481 | 2-0 | .606 | Cooper/Mentle [6]<br>Wee/Cureton [2] | | <span style="color: green;">*Up 4*</span> |
| Cooper/Mentle [6] | 2 | .500 | .515 | 1-1 | .486 | Wee/Cureton [2] | Lineman/DiPesa [7] | <span style="color: red;">*Down 1*</span> |
| Wee/Cureton [2] | 2 | .500 | .512 | ***0-2*** | .412 | | Lineman/DiPesa [7]<br>Cooper/Mentle [6] | <span style="color: red;">*Down 1*</span> |
| O’Leary/Mary [8] | 1 | .500 | .489 | ***1-0*** | .625 | Rooze/Pound [13] | | - |
| Rooze/Pound [13] | 1 | .500 | .508 | *0-1* | .375 | | O’Leary/Mary [8] | <span style="color: red;">*Down 2*</span> |

While all of the head-to-head wins are reflected in the ranking, one apparent anomaly is
that **O’Leary/Mary [8]** has an unbeated record against other .500 teams and is ranked
4th in this list, while **Wee/Cureton [2]** is winless against .500 teams and yet is
ranked higher (3rd).  A more subtle complaint might be that **Rooze/Pound [13]** has a
*less bad* winless record (at 0-1) against the .500 cohort teams compared to **Wee/Cureton
[2]** (at 0-2), yet is ranked lower.  It should be noted that the elevation process has
inadvertently clustered together teams in the same division with each other (with division
2 in the favored position due to having the team with the highest Pts Pct).

One solution for addessing the anomalies cited above is to consider **H2H W-L** and **H2H
Pts Pct** for all matchups played within the cohort, as a *higher consideration* than
tournament-level Pts Pct, before performing the head-to-head win elevations.  If we do
this, the following ranking obtains (with the effect compared to the previous result
indicated):

| Team | Div | Tourn<br>Win Pct | Tourn<br>Pts Pct | H2H<br>W-L | H2H<br>Pts Pct | Beat | Lost To | Effect |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- | :---: |
| Lineman/DiPesa [7] | 2 | .500 | .481 | **2-0** | .606 | Cooper/Mentle [6]<br>Wee/Cureton [2] | | - |
| O’Leary/Mary [8] | 1 | .500 | .489 | **1-0** | .625 | Rooze/Pound [13] | | <span style="color: green;">*Up 2*</span> |
| Cooper/Mentle [6] | 2 | .500 | .515 | **1-1** | .486 | Wee/Cureton [2] | Lineman/DiPesa [7] | <span style="color: red;">*Down 1*</span> |
| Rooze/Pound [13] | 1 | .500 | .508 | **0-1** | .375 | | O’Leary/Mary [8] | <span style="color: green;">*Up 1*</span> |
| Wee/Cureton [2] | 2 | .500 | .512 | **0-2** | .412 | | Lineman/DiPesa [7]<br>Cooper/Mentle [6] | <span style="color: red;">*Down 2*</span> |

On the surface, this looks pretty good, but the downside is that it is somewhat hard to
understand.  At a technical level, the following criteria have actually been added to the
tie-breaking rules (just above tournament-level Points Percentage):

1. **Cohort Win Percentage** &ndash; (Pts For) / (Pts For + Pts Against) for games played
   within the cohort
2. **Cohort "W-L Factor"** &ndash; this is what makes 2-0 better than 1-0; and 0-2 worse
   than 0-1; and 0-0 worse than 1-1, 2-2, etc.
3. **Cohort Points Percentage** &ndash; (Pts For) / (Pts For + Pts Against) for games
   played within the cohort

Note that cohort stats for tie-breaking (other than head-to-head wins) are **currently
disabled in the application** (but can actually be turned on as an option).  It will be up
to the rules committee to decide whether&mdash;and/or in what form&mdash;to consider this
type of notion for tie-breaking.

## Tournament Format

This is a discussion of the current structure for tournaments, as related to the various
phases of progression (including card playing rounds), and details on bracket generation
and game/match assignments.  Tournaments consist of the following high-level stages:

- Player Registration
- Seeding Round
- Partner Picking
- Tournament Round Robin
- Final Four Playoffs

### Player Registration

During player registration, individual players can enter their desired nick name
(otherwise will be known by their last name).  If we are using physical ping pong balls,
they can also enter their ping pong ball number.  Otherwise, the admin will generate
random Player Nums for everyone.  Admins also have the ability to override the
representation of player names, as they see fit.

### Seeding Round

For seeding round play, we currently have brackets for 23 through 50 players.  Brackets
for higher and lower numbers of players can be generated with a little bit of effort
(esepcially thinking about the number and types of player interactions for the lower
numbers).

Players are able enter game scores through the mobile application.  A member of the
opposing team must confirm a submitted score before it is officially posted.  Admins have
the ability to make corrections to any posted score, as well as adjustments to the final
player ranking after automated tabulations at the end of the round.

### Partner Picking

Partner picking is done based on seeding round player rankings, starting from the top
down.  Once a player is picked, they are skipped when it comes to their turn.  The
reigning championship team (assuming all players are present) are automatically selected
together in the position of their highest ranked player (not that this order really
matters, since team seeds are determined by average player rank).

### Tournament Round Robin

For tournament round robin play, we are currently assuming 8 rounds of play, with teams
split into two separate divisions.  Brackets are generated in such a way that higher
ranked teams are correlated with easier strengths of schedule (proportionally, throughout
the order).  Here is the current level of support (or near-support) for **two divisions**:


- Separate divisional play for 17 to 32 teams (34 to 65 players)
- Some inter-divisional play for 12 to 16 teams (24 to 33 players)
  - Brackets don't currently exist for 13 or 15 teams, but can be generated with a little
    bit of effort

Overall team seeds are computed from average player rank of the team members (after the
seeding round).  Assignment of teams to divisions then follows a "snake pattern", as
follows (assuming division names of **A** and **B**):

| Team Seed | Div | Div Seed |
| :---: | :---: | :---: |
| 1 | A | 1 |
| 2 | B | 1 |
| 3 | B | 2 |
| 4 | A | 2 |
| 5 | A | 3 |
| 6 | B | 3 |
| etc. | | |

Posting of scores, as well as admin-level corrections/adjustments (to game scores or team
rankings), are done similarly to as in the seeding round (described above).

After round robin play, the top two teams in each of the two divisions (after tie-breakers
are applied) advance to the final four playoffs.

#### Single-Division Support

If the need arises to support fewer than 24 players (e.g. a regional tournament), we can
revert to a single-division round robin for main tournament play.  For this format, we
currently have brackets for 8 to 14 teams (16 to 29 players), but it would require a
little bit of enhancement to the application to actualize.  Going below 16 players will
require a little more thinking and effort around format (number of rounds and bracket
requirements).

### Final Four Playoffs

In the final four playoffs, the top ranked team in each division (again, assuming two) is
paired against the second ranked team in the other division for the semifinal round.  The
winner of each pairing, in a best of three match, advances to the finals round.  The
finals round is also a best of three match.  The third place team, among the two
semifinals losers, is determined as described above (under [Tie-Breaking
Rules](#tie-breaking-rules)).

As with the seeding round and tournament round robin, admins will have the ability to
adjust playoff game scores and final tournament rankings, as needed.

## Import/Export Format

*\[coming soon...\]*

## Admin and Mobile APIs

*\[coming soon...\]*

## UI Screenshots and Descriptions

These are all outdated by now (but serviceable as references, until they can be updated):

- [Admin UI](ADMIN-UI.md)
- [Mobile UI](MOBILE-UI.md)
- [Charts and Dashboards](CHART-DASH.md)
