# To Do List

*This is my internal todo list (independent plans, observations, ideas, etc.)—items here
may or may not get implemented, depending on overlap and concordance with input/feedback
from the real stakeholders.*

*See `ISSUES.md` for tracking of issues raised in/from key outside discussions, which will
all be addressed and dispositioned by general consensus (and/or the rules committee).*

## Tasks

- tests for posting scores

## Features/Enhancements

- Show number of games complete (for the current round) in Seed/Tourn stage info
- detect end of stage for manual updates (entering player nums, seeding round play,
  partner picking, round robin play)
- handle updates/revisions to completed game scores (i.e. manage stats and denorm)
- implement playoff rounds? (or at least, generate playoff brackets)
- tournament-level rankings?

## Bugs/Nits

- don't overwrite existing scores from `PostScore`
- add transaction boundaries to euchmgr.py
- neatly flag and/or rectify duplicate player nick names
- create teams as picks are made (to support active charting)
- make bye rows readonly, for seeding and round robin views
- set focus on currently active picker, for partner view (and disable picks on other rows)

## Refactoring

- get all HTML and UI display stuff out of schema.py (should be purely functional)
- get rid of schema level caching (and fix requery flags)--REVISIT
- improve HTML and CSS design
  - use \<section\>, \<div\>, \<span\>, \<h1\>, \<h2\>, etc. properly
  - make admin interface more responsive (both height and width)
  - prettier styling in general
- fix naming throughout (e.g. seed vs seeding, seed vs rank, etc.)
- replace `player.nick_name` with `player.name` (except when dealing explicitly with the
  `nick_name` column, e.g. during registration)
- convert pl\_layout, sg\_layout, etc. from tuples to dict[str, tuple[...]]

## Framework

- add passwords (admin and players)
  - named admin users
- dockerize the server
- audit trailing (and/or snapshotting)?
  - created\_by/updated\_by metadata fields
- optimistic locking (or other concurrency control)?

## Bracketology

- highest seeds (across divisions) should get all byes (if any)
- measure/ensure fairness for inter-divisional play (if needed for either the bye problem
  or just numbers)
- euchmgr needs to use new omni-bracket format
- optimize for combination of r-squared value and RMSE (relative to ideal)
