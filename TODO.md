# To Do List

## Tasks

- fix empty stats formats for sd\_scores and rr\_scores
- updates to rr\_scores (to match rr\_dash)
- updates to sd\_scores

## Features/Enhancements

- auto-updating monitor view (e.g. charts with fading highlights for updates)
- detect end of stage for manual updates (entering player nums, seeding round play,
  partner picking, round robin play)
- handle updates/revisions to completed game scores (i.e. manage stats and denorm)

- use head-to-head record for tie-breakers
- implement playoff rounds (or at least, generate playoff brackets)

## Bugs/Nits

- neatly flag and/or rectify duplicate player nick names
- create teams as picks are made (would only be to support active charting)
- make bye rows readonly, for seeding and round robin views
- set focus on currently active picker, for partner view (and disable picks on other rows)
- selector for partner picks (nice to see list of available picks)

## Refactoring

- redirect to appropriate view after handling submit_func POST
  - need to handle error messages correctly (and no redirect?)
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
- created/updated timestamps for database records?
- audit trailing (and/or snapshotting)?
- optimistic locking (or other concurrency control)?

## Bracketology

- highest seeds (across divisions) should get all byes (if any)
- measure/ensure fairness for inter-divisional play (if needed for either the bye problem
  or just numbers)
- euchmgr needs to use new omni-bracket format
- optimize for combination of r-squared value and RMSE (relative to ideal)
