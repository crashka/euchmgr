# To Do List

## Features/Enhancements

- pick partners by typing in leading portion of name (unique partial matching)
- add clear player_num and clear partner picks buttons (for convenience)
- entry and exit criteria for tournament stages
- enable/diabling UI buttons based on entry/exit criteria

- structure for handling/displaying errors from button pushes or content editing
  - use 'err' member of status 200 response vs. dealing with 400/500 status codes?
  - use \<dialog closedby="any"\> HTML elements?

- compute intermediary results/stats when scores are entered
  - related: create teams as picks are made?
- auto-updating monitor view (e.g. charts with fading highlights for updates)

- use head-to-head record for tie-breakers
- implement playoff rounds

## Bugs

- for seeding view (and round robin view), make bye rows readonly
- maintain player\_game and team\_game tables properly when updating scores
  - ...or invalidate, then regenerate when needed

## Refactoring

- redirect to appropriate view after handling submit_func POST
  - need to handle error messages correctly (no redirect?)
- fully define views in server.py (including buttons, etc.)
- convert pl\_layout, sg\_layout, etc. from tuples to dict[str, tuple[...]]
- fix naming (e.g. seed vs seeding, seed vs rank, etc.)

## Framework

- security (flask-login), if non-local hosting is required
- timestamps for database records?
- audit trailing?
- optimistic locking?

## Bracketology

- highest seeds (across divisions) should get all byes (if any)
- measure/ensure fairness for inter-divisional play (if needed, for either bye problem or
  just numbers)
- euchmgr need to use new omni-bracket format
- optimize for combination of r-squared value and RMSE (relative to ideal)
