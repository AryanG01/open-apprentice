# Run 0: setup failure, no model reached, no spend
The first Stage A pass was started with the server's demo budget cap set to $0.25. The app refuses a model session unless the
cap can absorb a conservative reserve (about $0.48: `RESERVE_USD` in `api/teach.py`), so every upload returned the manual
template with the note "the model budget for this server is used up ($0.00 of $0.25)". **No model was called and nothing was
spent** (`calls.jsonl` was never created). The images and the app's resized PNGs are identical to what a later run uses.
This is kept, not deleted. Nothing here is an extraction result. The real first attempt is `../run1`.
