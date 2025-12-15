# Issues

*This document is for managing feature requests, bugs, and ideas raised in external
discussion (as opposed to the internal items logged in `TODO.md`).  The volume and needs
should make it easy enough to handle this manually here rather than using a more involved
issue tracker of some sort.*

*Issue numbers are monotonically increasing regardless of issue type, and do not change.
Priorities do not need to be explicitly specified—we can just comment informally on that,
or possibly just reorder items below based on rough priority (while making sure to track
high number for new issue entry).*

## Bugs

**#1** - Seeding and round robin bracket charts should have space for showing (and/or
entering) scores after each player or team in the matchup [Struble]

## Feature/Enhancement Requests

**#5** - Mobile app for entering game scores [Struble]

 - In addition to all tournament brackets and scores, players should be able to see a
   specific list of their own games (for both seeding and round robin)
 - Players can only enter scores for their own games as they are completed
 - Other players in the same game should be notified in the app, and given the ability to
   confirm, correct, or dispute

## Ideas for Further Discussion

## Closed

**#2** - Division assignment for round robin stage should be done in a snake pattern based
on team rank (1, 2, 2, 1, 1, 2,…), rather than alternating (1, 2, 1, 2,…) [Struble]

- *Fixed - Dec 03, 2025*

**#3** - Non-champion three-headed monster should always be seeded last in the round robin
stage (rather than considered by average player rank) [Struble]

- *Fixed - Dec 03, 2025*

**#4** - Seeding and round robin stage rankings (and final tourament rankings) should be
based on win pct, then established tie-breaking rules, as outlined below [Struble]

- Tie-breaking rules (from Bobby):
  - Individual head to head
  - In three or more way ties, head to head against all other tied teams
  - In three or more way ties still tied after head to head against all other tied teams,
    points % within games of tied teams
  - Overall points %
  - Coin flip (non-virtual)
- *Fixed - Dec 08, 2025*
