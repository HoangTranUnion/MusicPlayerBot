# MusicPlayerBot
a simple discord bot to play music, but this bot has resolved some of the "minor" issues in music bots.

- Audio added to the end of the currently played audio will not be unplayable.
- If two videos are added relatively quickly at the almost same time, the player will handle the videos appropriately - whichever comes first is handled first.
- Videos that are added to queue that has current play time more than 6 hours will be downloaded automatically. Other videos will be streamed instead
- Playlist is supported.
- There is now a way to loop a song a number of times, instead looping indefinitely by default.
- There is also a way to skip a song that is being looped.
- The player will not handle videos over 6 hours in length - the loading time will be far too long.
- The bot can be used in multiple servers at the same time.

# How to test the bot
- Create a new Discord bot from the Discord Developer Portal.
- Get the token for the bot from the Portal.
- Use the token in constants.py in the TOKEN constant.
- Type your desired prefix for the bot
- Run the bot in main.py and have fun.