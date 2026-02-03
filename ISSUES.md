# Issues

*This document is for managing feature requests, bugs, and ideas raised in external
discussion (as opposed to the internal items logged in `TODO.md`).  The volume and needs
should make it easy enough to handle this manually here rather than using a more involved
issue tracker of some sort.*

*Issue numbers are monotonically increasing regardless of issue type, and do not change.
Priorities do not need to be explicitly specified—we can just comment informally on that,
or possibly just reorder items below based on rough priority (while making sure to track
high number for new issue entry).*

## Bugs/Fixes

**#8** - For Scoring Sheet chart - byes should be easier to see [Struble]

- *Created - Jan 19, 2026*
- Currently just a small dash, could be bigger/bolder, an "X", the word "bye", etc.
- *\[Update - Jan 28, 2026\]* changed hyphen to an en-dash for now, but will try out some
  other alternatives to present and see if we can get to consensus

**#9** - For Partner Picks dashboard - strike through names of picked players on available list (rather than removing them) [Struble]

- *Created - Jan 19, 2026*
- Note: can implement both visualizations and let admin toggle between them
- Can also provide the ability to toggle between listing available players by rank or by name

## Feature/Enhancement Requests

**#11** - Ability to add comments to games in mobile app [Rooze]

- *Created - Jan 19, 2026*

**#12** - Ability to type in name of partner pick in mobile app (as opposed to dropdown list) [Kramer]

- *Created - Jan 19, 2026*
- Could show autocompletion for unique prefixes as typing

## Core Requirements

**#7** - Final tournament rankings need to include playoff results [Struble]

- *Created - Dec 15, 2025*
- First and second place are determined by finals result
- Third and fourth place are determined by playoff win pct, followed by playoff pts pct
  - If stats are identical, a tie for third is declared

**#13** - Support for seeding round absentees (e.g. travel delays), make them pickable for the tournament [Struble]

- *Created - Jan 19, 2026*
- Tangentially related to Issue #14 (both possibly pertaining to travel issues)
- Admins should be able to manually adjust availability list any time before partner picking starts

**#14** - Support for fractional-tournament substitute players (e.g. seeding round subs) [Struble]

- *Created - Jan 19, 2026*
- Tangentially related to Issue #13 (both possibly pertaining to travel issues)
- Needed to ensure association of game stats with the actual individual players (and not the
  tournament-level team/role identity)

**#15** - Support for admin manual edits/overrides for data/results in all stages (players, game scores, rankings, etc.)

- *Created - Jan 19, 2026*
- Edits/overrides should be logged for traceability
- Would be good to capture comments on manual changes

**#16** - Ensure integrity/fairness for pre-generated brackets before round matchups are deployed [Struble]

- *Created - Jan 19, 2026*
- Metadata/stats for pre-generated brackets actually used needs to be available for
  inspection/validation

## Topics/Ideas for Further Discussion

**#17** - Continued discussion on tie-breaking algorithm details, both principles and codification

- *Created - Jan 19, 2026*
- Technical write-up on current implementation: [here](RANKING.md)
- Template for specifying test scenarios: [here](resources/examples/tie-breaker%20scenario%20template.xlsx)

**#18** - Ability to configure and deploy for smaller, local tournaments [Rooze]

- *Created - Jan 19, 2026*
- Might include specifying number of divisions, rounds of play, playoff format (if any), etc.

## Closed

**#2** - Division assignment for round robin stage should be done in a snake pattern based
on team rank (1, 2, 2, 1, 1, 2,…), rather than alternating (1, 2, 1, 2,…) [Struble]

- *Created - Dec 01, 2025*
- *Fixed - Dec 03, 2025*

**#3** - Non-champion three-headed monster should always be seeded last in the round robin
stage (rather than considered by average player rank) [Struble]

- *Created - Dec 01, 2025*
- *Fixed - Dec 03, 2025*

**#4** - Seeding and round robin stage rankings (and final tournament rankings) should be
based on win pct, then established tie-breaking rules, as outlined below [Struble]

- *Created - Dec 01, 2025*
- Tie-breaking rules (from Bobby):
  - Individual head to head
  - In three or more way ties, head to head against all other tied teams
  - In three or more way ties still tied after head to head against all other tied teams,
    points % within games of tied teams
  - Overall points %
  - Coin flip (non-virtual)
- *Fixed - Dec 08, 2025*

**#6** - Seeding round should not use head-to-head matchups for ranking/tie-breaking; only
criteria should be: win pct, points pct, then (virtual?) coin flip [Struble]

- *Created - Dec 15, 2025*
- *Fixed - Dec 18, 2025*

**#1** - Seeding and round robin bracket charts should have space for showing (and/or
entering) scores after each player or team in the matchup [Struble]

- *Created - Dec 01, 2025*
- *Fixed - Dec 27, 2025*

**#5** - Mobile app for entering game scores [Struble]

- *Created - Dec 01, 2025*
- In addition to all tournament brackets and scores, players should be able to see a
  specific list of their own games (for both seeding and round robin)
- Players can only enter scores for their own games as they are completed
- Other players in the same game should be notified in the app, and given the ability to
  confirm, correct, or dispute
- *Fixed - Jan 12, 2026*

**#10** - Show Pts Pct (instead of PF-PA) within the cohort as tie-breaking stats [multiple]

- *Created - Jan 19, 2026*
- Some people like the 4-digit decimal version (e.g. .6853 over 68.53%) better—will get
  consensus on the format
- Related topic: probably leave W-L as is (rather than Win Pct) within the cohort for same
  views (e.g. so that 1-0 shows as distinct from 2-0)
- *Fixed - Jan 28, 2026*
