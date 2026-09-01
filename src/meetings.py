"""Utilidades compartidas para dónde se guarda cada reunión."""

import os
from datetime import datetime

MEETINGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "meetings")


def new_meeting_dir() -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    meeting_dir = os.path.join(MEETINGS_DIR, timestamp)
    os.makedirs(meeting_dir, exist_ok=True)
    return meeting_dir
