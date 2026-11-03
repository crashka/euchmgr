# Recent Updates

This is a summary of newer features and/or capabilities in the application (since a little
before Danville), primarily on the admin side&mdash;provided here to help guide additional
feedback and/or test coverage before New Orleans.  At some point, we will fold this back
into the main write-up for the app.

## Mobile App

- **Install as a web app** (on phone home screen)
- **Automatic updates to game scores** and partner picks (5 second polling interval)

## Admin UI

### General

- **Automatic updates of grid data**, for the following views:
  - Seeding
  - Partners
  - Round Robin
  - Playoffs

- **Automatic enabling of buttons for admin actions** when activity for a stage (e.g. game
  play, partner picking) is complete

### Player Roster

For the uploaded roster file and the "Players" admin view:

- **"Late Arrival" flag** for players&mdash;these players are not included in the seeding
  round, but will be added to the player listing for team partner picks (they will be
  ranked at the bottom of the order)
  - There is currently support for any number of late arrivers (within reason)
- **"Early Departure" flag** for players&mdash;these players will compete in the seeding
  round, but are not eligible to pick partners for team round robin play
  - If there is an even number of other players*, an early departer will be automatically
    placed on the three-headed monster team, along with the final partner pick
  - If there is an odd number of other players (i.e. already a three-headed monster)*, the
    early departer is not included in tournament round robin play
  - There is currently support for at most only one early departer (and thus, only a
    single non-champion three-headed monster team)
    
*\* note that the case of a reigning champion three-headed monster team changes the math
here suitably*

### Seeding Round

- **Adjust game scores for completed games** &ndash; "Seeding" admin view
  - Click on the name of the game winner in the grid ("Winner" column) to see the Score
    Posting Report for the game
  - Click the "Adjust score" button to make a correction
    - Note that a reason for the change must be entered
  - The change will be reflected in the Score Posting Report
- **Adjust team divisional rankings** &ndash; "Seeding" admin view
  - After tabulating results for the seeding round, navigate back to the "Seeding" view
    (from the "Partners" view)
  - Click on the "Seeding Round Results" link to get a listing of the player rankings
    after the seeding round (along with game and points stats)
    - The seed ranking history for a player (computed and admin-adjusted) can be seen by
      clicking on the Seed Rank number in the last column of the table
  - Click the "Adjust rankings" button at the bottom to make corrections to the player
    rankings
  - Adjustments can be made by entering a corrected seeding round rank for a player (in
    which case, all affected player rankings will be shifted accordingly), or by using
    the keyboard Up/Down arrows to move a player within the table
  - Hit the "Save adjustments" button to persist the changes
    - Note that a reason for the adjustments must be entered
  - Any changes made will be used in the partner picking order, and reflected in the
    players' Seeding Rank History reports

### Partner Picking

- **Revert partner picks previously made** &ndash; "Partners" admin view
  - ***Double***-click on the name of the partner picked in the grid ("Partner(s)" column)
    to see the list of picks to be reverted (includes all picks subsequent to the one that
    was targeted)
  - Click the "Revert Pick(s)" button to execute the process
  - The data grid in the Partners view should reflect the rollback

### Team Seeds

- **Adjust computed team seeds** &ndash; "Teams" admin view
  - Click on the "Team Seed Details" link to get a listing of the computed team seeds
    (along with individual and average seeding round rankings of the team members)
    - The team seed history can be seen by clicking on the Team Seed number in the last
      column of the report
  - Click the "Adjust seeds" button at the bottom to make corrections to the team seeds
  - Adjustments are made and saved similarly to the process for adjusting player rankings
    (above)
  - Any changes made will be used for round robin bracket assignment, and reflected in the
    Team Seed History reports

### Tournament Round Robin

- **Adjust game scores for completed games** &ndash; "Round Robin" admin view
  - This is done similarly for round robin games as for the seeding round (above)
- **Adjust team divisional rankings** &ndash; "Round Robin" admin view
  - After tabulating results for the main tournament round robin stage, navigate back to
    the "Round Robin" view (from the "Final Four" view)
  - Click on the "Round Robin Results" link to get a listing of the team rankings for each
    of the divisions (along with game and points stats)
    - As with the player rank history (above), the division rank history for a team can be
      viewed by clicking on the Div Rank number in the last column of the table
  - Click the "Adjust rankings" button at the bottom to make corrections to the team
    rankings (within the division)
  - Adjustments are made and saved similarly to the process for adjusting player rankings
    (above)
  - Any changes made will be used for playoff qualification/bracket assignment, and
    reflected in the teams' Division Rank History reports

### Playoffs

- **Fake data generation** has been enabled for both the Semifinals and Finals playoff
  rounds (testing only)
- **Adjust game scores for completed games** &ndash; "Playoffs" admin view
  - This is done similarly for playoff games as for seeding and round robin stages, except
    that game scores (for either playoff round) may not be adjusted after semifinals
    results have been tabulated

### Hidden Features

**Database checkpoints and recovery**

**Admin "power actions"**
- Reset player nums
- Reset seeding round (game results)
- Reset partner picking
- Reset round robin (game results)
- Reset playoff rounds (game results)

**Event logging and audit trailing**
- Tourn log (stage transitions, etc.)
- Game score posting (submit, correct, accept)
- Admin actions
  - Manual seed/score/rank adjustments
  - Power actions
  
**Config file for app behavior**
- Hide fake data generation buttons ("production mode")
- Determine player numbers using random number generator (vs. ping pong balls)
- Set auto-update intervals for mobile and admin interfaces

## To Do List

*Possibly before Nola 2026...*

- **Player comments on games** (and possibly picks, as well) through the mobile app
- **Players view enhancements** (admin UI)
  - Add a player
  - Delete a player
  - Edit player flags (e.g. late arrival, early departure)
