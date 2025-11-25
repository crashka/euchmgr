# To Do List

## Features/Enhancements

- compute intermediary results/stats when scores are entered
- maintain player\_game and team\_game tables properly when updating scores
  - ...or invalidate, then regenerate when needed
- create teams as picks are made?
- auto-updating monitor view (e.g. charts with fading highlights for updates)

- use head-to-head record for tie-breakers
- implement playoff rounds (or at least, generate playoff brackets)

## Bugs

- make bye rows readonly, for seeding and round robin views
- set focus on currently active picker in partner view (and disable picks on other rows)
- selector for partner picks (not sure we really need this)?

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

- security (flask-login?), if considering non-local hosting
- created/updated timestamps for database records?
- audit trailing (and/or snapshotting)?
- optimistic locking (or other concurrency control)?

## Bracketology

- highest seeds (across divisions) should get all byes (if any)
- measure/ensure fairness for inter-divisional play (if needed for either the bye problem
  or just numbers)
- euchmgr needs to use new omni-bracket format
- optimize for combination of r-squared value and RMSE (relative to ideal)
