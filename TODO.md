# TODO


## MAJOR 

- Add versioning to files
- Any config variable changes that are made from ~commands, are to update the appropriate config value for persistance


# VOICE

- ✅ ~join should auto start listening (make "~start" redundant) should also apply to autojoined channels
- if in empty voice channel, check if other channels are empty. leave empty channel and autojoin, if allowed, channels with other members

# GENERAL
 
- check that we dont have dup files that arent being used. eg. configs and data files
- Cleanup stat layouts. Standardise. Perhaps make a image creator function that builds the image from the stats etc

# COMMANDS

- Cleanup commands. make less typying and more configurable. eg. make ~leaderboards bring up a message with buttons to select the one they want to see, then show on submit


# ISSUES

- ~mystats @The_KnobFather not working ( have manually fixed, but not sure what total was for?)

# ADMIN

- Change from app to webserver.
  - to have voice transcripts
  - sound editing, adding and deleting
  - bot monitor statuses/health
  - live config changes (with error checking and a "ARE you fucking sure?" check)