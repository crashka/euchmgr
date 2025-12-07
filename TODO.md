# To Do List

*This is my internal todo list (independent plans, observations, ideas, etc.)—items here
may or may not get implemented, depending on overlap and concordance with input/feedback
from the real stakeholders.*

*See `ISSUES.md` for tracking of issues raised in/from key outside discussions, which will
all be addressed and dispositioned by general consensus (and/or the rules committee).*

## Tasks


## Features/Enhancements

- detect end of stage for manual updates (entering player nums, seeding round play,
  partner picking, round robin play)
- handle updates/revisions to completed game scores (i.e. manage stats and denorm)
- compute/maintain head-to-head and common-opponent stats, for possible use in
  tie-breaking
- implement playoff rounds (or at least, generate playoff brackets)

## Bugs/Nits

- neatly flag and/or rectify duplicate player nick names
- create teams as picks are made (to support active charting)
- make bye rows readonly, for seeding and round robin views
- set focus on currently active picker, for partner view (and disable picks on other rows)
- selector for partner picks (nice to see list of available picks)

## Refactoring

- break /chart, /dash, and /mobile out as separate blueprints
- get rid of schema level caching (and fix requery flags)
- consolidate javascript for DataTable handling across views
- improve HTML and CSS design
  - use \<section\>, \<div\>, \<span\>, \<h1\>, \<h2\>, etc. properly
  - prettier styling in general
- fix naming throughout (e.g. seed vs seeding, seed vs rank, etc.)
- convert pl\_layout, sg\_layout, etc. from tuples to dict[str, tuple[...]]
- define views (including buttons, etc.) and/or charts as data in server.py
  - get rid of replicated code in templates

## Framework

- security (e.g. flask-login), if considering non-local hosting
- dockerize the server
- audit trailing (and/or snapshotting)?
- optimistic locking (or other concurrency control)?

## Bracketology

- highest seeds (across divisions) should get all byes (if any)
- measure/ensure fairness for inter-divisional play (if needed for either the bye problem
  or just numbers)
- euchmgr needs to use new omni-bracket format
- optimize for combination of r-squared value and RMSE (relative to ideal)
