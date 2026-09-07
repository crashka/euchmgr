# Euchre Manager

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

## Player Identifiers and Rankings

- **Player Num** &ndash; used to identify players for game assignments in the seeding
  bracket.  These numbers used to be determined by drawing ping pong balls from a bag, but
  can now be generated randomly by the platform.  Note that numbers can actually be
  entered through either the admin or mobile interfaces (e.g. if doing the ping pong ball
  thing for nostalgia).
- **Player Rank** (also referred to as "Seed Rank" in the UI) &ndash; the ranking earned
  by players during seeding round play, after tie-breaking rules have been applied (see
  below)&mdash;lower is better, no ties.  This ranking represents the order in which team
  partners are picked.
  - Note that there is a separate "Player *Pos*" stat indicating the player's seeding round
    ranking *before tie-breakers* (ties possible)&mdash;this is available in the admin UI
    for reference.  Tie-breaking rules are then applied to player cohorts with identical
    Player Pos computations in order to determine the Player Rank.

## Team Identifiers and Rankings

- **Team Seed** &ndash; used to identify teams for division and game assignments in the
  round robin tournament brackets.  Team Seed is determined by the average Player Rank for
  the players (2 or 3) on the team.  Ties are broken by the highest ranked player on a
  team.  Note that a *non-champion* three-headed monster team (if any) is always seeded
  last, regardless of average Player Rank.
- **Div Seed** &ndash; represents the relative Team Seed within each division.  This is
  used for game assignments when the division brackets for the tournament are completely
  self-contained (no inter-div matchups).  See Tournament Format (below) for more details.
  - Note that this only applies to multi-division tournaments.  The application may later
    support smaller single-division tournaments (e.g. regional).
- **Div Rank** &ndash; the ranking earned by teams within their division during round
  robin tournament play, after tie-breaking rules have been applied.  The top two teams in
  each division qualify for the final four playoff round.
  - "Div *Pos*" (which appears on the Round Robin Live Dashboard and Tie-Breaker Report)
    indicates ranking within the division *before tie-breakers* (same as with "Player
    Pos", above).  Tie-breaking rules are then applied to team cohorts with identical Div
    Pos computations in order to determine the Div Rank.
- **Team Rank** (pre-playoffs) &ndash; the ranking earned by teams *across divisions*
  during round robin play, after tie-breaking rules have been applied.  The top two teams
  in each division always occupy the first four Team Ranks (though not necessarily in
  final tournament ranking order), and are removed from tie-breaking consideration
  relative to the remaining teams.  Note that Div Rank order is preserved here for teams
  within a division.
  - This identifier is used to denote team seeds for the final four playoff rounds.
  - "Team *Pos*" indicates the overall team ranking (pre-playoff) before tie-breaking (see
    description for Div Pos above).
- **Final Rank** &ndash; represents the final tournament ranking for teams, after playoff
  rounds are complete.  This is the same as Team Rank, except that the Final Four teams
  are ordered by playoff results.  The two semifinal losers are ranked by playoff Win Pct
  followed by Pts Pct (with Team Rank as the final tie-breaker, if at all necessary, to
  reward better round robin play).
  - "Final *Pos*" is essentially the same as Team Pos (above), except that the final four
    teams are always in positions 1 through 4 (with remaining teams in the same order,
    which may include tied positions).

## Tie Breaking Rules

The following rules are applied to players or teams with identical Win Percentage
records&mdash;said to be in the same *position*, or considered to be "cohorts"&mdash;for
the round.

### Seeding Round

1. **Head-to-Head** &ndash; winners for head-to-head matchups (in the round) are always
   ranked above losers (except in the case of "cyclic win groups", see below)
2. **Points Percentage** &ndash; (Pts For) / (Pts For + Pts Against) for the seeding round
3. **Points For** &ndash; for the seeding round
4. **Player Num** &ndash; equivalent to a coin flip (since Player Nums are determined by
   random), but we do it this way for traceability

### Tournament Round Robin

1. **Head-to-Head** &ndash; winners for head-to-head matchups (in the round) are always
   ranked above losers (see below)
2. **Points Percentage** &ndash; (Pts For) / (Pts For + Pts Against) for round robin play
3. **Points For** &ndash; for round robin play
4. **Team Seed** &ndash; to reward better individual player seeding round play (if
   necessary)

### Playoffs

*\[applies to 3rd and 4th place teams only\]*

1. **Game Win Percentage** &ndash; for the semifinal round (as opposed to *Match Win
   Percentage*, which will always be tied at 0%)
2. **Points Percentage** &ndash;  for the semifinal round
3. **Team Rank** &ndash; to reward better round robin play (if necessary)

### Notes on Head-to-Head Comparisons

In terms of implementation, tied players/teams are first sorted by all of the criteria
*other than head-to-head matchups* (e.g. points percentage), and then a head-to-head
"elevation" process is performed.  The elevation process works by starting with the lowest
ranked team within the cohort and elevating it above the current highest ranked team that
it has beat head-to-head in the round.  The same process is then applied to each of the
remaining teams in the cohort (in their original order, bottom-to-top).

**Important**: head-to-head matchups are *ignored for tie-breaking* in the case of
**cyclic win groups** (e.g. A beats B, B beats C, C beats A).  That is, a player/team is
*not elevated* above another player/team that it has beat if they are both part of the
same cyclic win group (see illustrative example below).  Cyclic win groups are shown in
each of the Tie-Breaker Reports.

### Illustrative Examples

#### Example 1 - Head-to-Head and Cyclic Win Groups

Note that the "elevation" process for head-to-head wins *can* actually be used with cyclic
win groups, but this (contructed) example demonstrates why that is not desirable.

Let's say that 6 teams are tied with the same record, each one having beat another of the
cohort teams during round play:

| Team | Pts Pct | Beats |
| :---: | :---: | :---: |
| 1 | **.800** | 3 |
| 2 | **.700** | 4 |
| 3 | **.600** | 5 |
| 4 | **.500** | 6 |
| 5 | **.400** | 1 |
| 6 | **.300** | 2 |

As you can see, Teams 1-3-5 form a cyclic win group, as do Teams 2-4-6.  If we were to
start from the bottom (Team 6) and work our way up with the head-to-head "elevation"
process&mdash;that is: 6 beats 2, 5 beats 1, 4 beats 6, 3 beats 5, 2 beats 4, and 1 beats
3)&mdash;we would end up with the following ranking order:

| Team | Pts Pct | Beats | Effect |
| :---: | :---: | :---: | :---: |
| 1 | .800 | 3 | - |
| 3 | .600 | 5 | <span style="color: green;">*Up 1*</span> |
| 5 | .400 | 1 | <span style="color: green;">*Up 2*</span> |
| 2 | .700 | 4 | <span style="color: red;">*Down 2*</span> |
| 4 | .500 | 6 | <span style="color: red;">*Down 1*</span> |
| 6 | .300 | 2 | - |

Within each cyclic win group (1-3-5 and 2-4-6), the relative positions are maintained
(i.e. they are still in order of Pts Pct), but the *overall Pts Pct* ordering has been
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
| --- | :---: | :---: | :---: | :---: | :---: | --- | --- |
| Cooper/Mentle [6] | 2 | .500 | **.515** | 1-1 | .486 | Wee/Cureton [2] | Lineman/DiPesa [7] |
| Wee/Cureton [2] | 2 | .500 | **.512** | 0-2 | .412 | | Lineman/DiPesa [7]<br>Cooper/Mentle [6] |
| Rooze/Pound [13] | 1 | .500 | **.508** | 0-1 | .375 | | O’Leary/Mary [8] |
| O’Leary/Mary [8] | 1 | .500 | **.489** | 1-0 | .625 | Rooze/Pound [13] | |
| Lineman/DiPesa [7] | 2 | .500 | **.481** | 2-0 | .606 | Cooper/Mentle [6]<br>Wee/Cureton [2] | |

Here is the final ranking after the head-to-head win elevations are applied (this is
copied from the
[Final Tournament Results](<resources/nola_2023 - Final Tournament Results.png>),
with details further represented in the
[Tie-Breaker Report](<resources/nola_2023 - Final Tournament Tie-Breaker Report.png>)):

| Team | Div | Tourn<br>Win Pct | Tourn<br>Pts Pct | H2H<br>W-L | H2H<br>Pts Pct | Beat | Lost To | Effect |
| --- | :---: | :---: | :---: | :---: | :---: | --- | --- | :---: |
| Lineman/DiPesa [7] | 2 | .500 | .481 | 2-0 | .606 | Cooper/Mentle [6]<br>Wee/Cureton [2] | | <span style="color: green;">*Up 4*</span> |
| Cooper/Mentle [6] | 2 | .500 | .515 | 1-1 | .486 | Wee/Cureton [2] | Lineman/DiPesa [7] | <span style="color: red;">*Down 1*</span> |
| Wee/Cureton [2] | 2 | .500 | .512 | ***0-2*** | .412 | | Lineman/DiPesa [7]<br>Cooper/Mentle [6] | <span style="color: red;">*Down 1*</span> |
| O’Leary/Mary [8] | 1 | .500 | .489 | ***1-0*** | .625 | Rooze/Pound [13] | | - |
| Rooze/Pound [13] | 1 | .500 | .508 | *0-1* | .375 | | O’Leary/Mary [8] | <span style="color: red;">*Down 2*</span> |

While all of the head-to-head wins are reflected in the ranking, one apparent anomaly is
that Team 8 (O’Leary/Mary) has an unbeated record against other .500 teams and is ranked
4th in this list, while Team 2 (Wee/Cureton) is winless against .500 teams and is ranked
higher (in 3rd).  A more subtle complaint might be that Team 13 (Rooze/Pound) has a *less
bad* winless record (at 0-1) compared to Team 2 (at 0-2) against the .500 cohort teams,
yet is ranked higher.  The elevation process has inadvertently clustered the teams in the
same division with each other (with division 2 in the favored position due to having the
team with the highest Pts Pct).

One solution for addessing the anomalies cited above is to consider **W-L and Pts Pct for
all matchups played within the cohort**, as a *higher consideration than tournament-level
Pts Pct*, before performing the head-to-head win elevations.  If we do this, the following
ranking obtains (with the effect compared to the previous result indicated):

| Team | Div | Tourn<br>Win Pct | Tourn<br>Pts Pct | H2H<br>W-L | H2H<br>Pts Pct | Beat | Lost To | Effect |
| --- | :---: | :---: | :---: | :---: | :---: | --- | --- | :---: |
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

Note that cohort stats for tie-breaking (other than heaad-to-head wins) are **currently
disabled in the application** (but can actually be turned on as an option).  It will be up
to the rules committee to decide whether&mdash;and/or in what form&mdash;to consider this
type of notion for tie-breaking.

## Tournament Format

*\[coming soon...\]*

## Import/Export Format

*\[coming soon...\]*

## Admin and Mobile APIs

*\[coming soon...\]*

## UI Screenshots and Descriptions

These are all outdated by now (but serviceable as references, until they can be updated):

- [Admin UI](ADMIN-UI.md)
- [Mobile UI](MOBILE-UI.md)
- [Charts and Dashboards](CHART-DASH.md)
