These JSON files match the format expected by app.seed_loader.run_seed().

To use them as your new baseline:
  1. Back up your current seeds/ folder if needed.
  2. Copy (or move) all .json files from this export/ folder into seeds/.
  3. Run: python -m app.seed_loader

Warning: seeding clears the database and reloads from seeds/*.json.
