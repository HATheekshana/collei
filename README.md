# Collei — full MongoDB edition

Deploy this project using your EXISTING activated database.

1. Stop the bot in the hosting panel and back up your existing project.
2. Upload these files to the bot root. Preserve your current .env, especially MONGO_URL and MONGO_TEST_DB.
3. Startup file: main.py. Requirements file: requirements.txt.
4. Restart. No import or activation command is needed again.

All persistent bot content and user data use MongoDB: weapons, artifacts, guide/card image references, character skills/constellations, bosses, banners, endgame datasets and cycles, users/groups, complaints, bans, statistics and saved information menus.

Migration commands and JSON/SQLite import tools are not included. No local JSON/SQLite data files are needed for normal operation. Old files may be removed after retaining backups. Old migration scripts left from an overlay upload are not registered or imported; you can delete them too.

Keep .env and Python configuration. Font/icon caches and generated image files remain on disk; images are stored on Telegram/imgbb with their references in MongoDB. Static command names and aliases remain part of the source code.

The bot checks the existing activation marker at startup to avoid silently using the wrong database. Run one polling instance for this bot. Restart after manually editing database content so its in-memory snapshots reload.

Validation: bundled Python syntax and local named imports checked. Earlier isolated storage/migration tests passed. Live Telegram/database delivery was not tested from this workspace.
