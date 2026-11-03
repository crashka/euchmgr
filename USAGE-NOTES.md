# Usage Notes

[Overview](#overview)<br>
[Mobile](#mobile)<br>
&nbsp;&nbsp;\- [App Download](#app-download)<br>
&nbsp;&nbsp;\- [Login and Navigation](#login-and-navigation)<br>
&nbsp;&nbsp;\- [Entering Game Scores](#entering-game-scores)<br>
[Admin](#admin)<br>

## Overview

Here are brief notes for the usage of the Euchre Manager application.  The intent is for
the mobile interface, in particular, to be generally simple and intuitive.  The admin
interface has more intricacies, but the basic operation should also be relatively
straightforward (for non-exception scenarios).

## Mobile

### App Download

The application administrator will provide players with a URL for the "Euchmgr" mobile
app.  When the link is clicked, the user should be taken to the Login page rendered in a
mobile browser.  The web app can then be installed on the device, as follows:

- **iOS/Safari** &ndash; Tap the "Share" button on the browser (which may be under the
  '&vellip;' icon/menu) and choose "Add to Home Screen".  Note: you should select the
  "Open as Web App" option, if it is available.
- **Android/Chrome** &ndash; Tap the '&vellip;' icon/menu on the browser and select
  "Install and create shortcut", then from there, choose "Install".  Note that this may
  not add the application icon to your home screen, so you may need/want to do that
  separately.
- **Android/Firefox** &ndash; Tap the '&vellip;' icon/menu on the browser and choose the
  "More" option.  From there, tap on "Add app to Home screen", and then hit the "Add to
  home screen" button.

Now you can close the browser and open Euchmgr through the newly installed application
icon.  You are also able to continue accessing Euchmgr through the mobile browser, but the
browser framing will cut into the usable screen real estate.

### Login and Navigation

From the Login screen, sign in by choosing your name from the User select list, and enter
the password provided by the application administrator.  By default, the app will take you
to the screen representing the current stage of the tournament&mdash;one of:

- Registration
- Seeding
- Partner Picks
- Round Robin
- Semifinals*
- Finals*

*\* only for teams making it into those rounds*

You can navigate to any stage using the "<u>Stage</u>" dropdown at the top of the screen,
or return to the current stage using the "<u>Current</u>" link.

The information shown for the current stage will be automatically updated on a periodic
basis (unless you are in the middle of entering a score or pick).  You can get immediate
updates by tapping the background of the top section of the screen (next to Stage Info),
or tapping on the currently highlighted game (or pick).

### Entering Game Scores

**Submitting** &ndash; at the end of a game, any of the players can enter the score
through the mobile app by selecting the points scored for each team, then hitting the
"Submit Score" button.

**Accepting** &ndash; a player from the opposing team must then acknowledge the submitted
score using the "Accept Score" button, in order for it to be officially posted within the
application.

**Correcting** &ndash; players from either team are able to change an erroneous score by
changing the team points displayed, then hitting the "Correct Score" button.  As with the
original score submission, a player from the opposing team must accept a corrected score
in order for it to be posted.

## Admin

For basic instructions, see [General Note on Application Data/Navigation](ADMIN-UI.md#general-note-on-application-datanavigation).

For more advanced features and capabilities, see [Recent Updates](RECENT-UPDATES.md#admin-ui).
