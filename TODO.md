# To Do List

*This is my internal todo list (independent plans, observations, ideas, etc.)—items here
may or may not get implemented, depending on overlap and concordance with input/feedback
from the real stakeholders.*

*See `ISSUES.md` for tracking of issues raised in/from key outside discussions, which will
all be addressed and dispositioned by general consensus (and/or the rules committee).*

## Tasks

- documentation for admin and mobile APIs

## Features/Enhancements

- record posting by "admin" (or "fake results") on score posting report
- show number of games complete (for the current round) in Seed/Tourn stage info
- handle updates/revisions to completed game scores (i.e. manage stats and denorm)

## Bugs/Nits

- invalidate player sessions when switching (and pausing?) tournaments
- don't overwrite existing scores from `PostScore`
- add transaction boundaries to euchmgr.py
- neatly flag and/or rectify duplicate player nick names
- create teams as picks are made (to support active charting)
- make bye rows readonly, for seeding and round robin views
- set focus on currently active picker, for partner view (and disable picks on other rows)

## Refactoring

- convert pl\_layout, sg\_layout, etc. from tuples to dict[str, tuple[...]]

## Framework

- auth/password management (admin and players)
  - add change password to mobile (registration/user admin)
  - confirm new password (tourn admin and mobile)
- named admin users
- merge application-level logging with flask/gunicorn logging?
- audit trailing (and/or snapshotting/archiving)?
- optimistic locking (or other concurrency control)?

## Bracketology

- highest seeds (across divisions) should get all byes (if any)
- measure/ensure fairness for inter-divisional play (if needed for either the bye problem
  or just based on numbers)
- euchmgr needs to use new omni-bracket format
