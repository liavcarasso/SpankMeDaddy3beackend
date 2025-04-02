from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to your frontend URL when deploying
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # Allow both GET and POST requests
    allow_headers=["*"],
)

# Load leaderboard from file
try:
    with open("leaderboard.json", "r") as file:
        leaderboard = json.load(file)
except:
    leaderboard = []


class PlayerScore(BaseModel):
    name: str
    score: int


@app.get("/leaderboard")
def get_leaderboard():
    return sorted(leaderboard, key=lambda x: x["score"], reverse=True)[:10]


@app.post("/submit_score")
def submit_score(player: PlayerScore):
    global leaderboard

    # Check if player exists
    for entry in leaderboard:
        if entry["name"] == player.name:
            entry["score"] = max(entry["score"], player.score)
            break
    else:
        leaderboard.append({"name": player.name, "score": player.score})

    # Sort and keep only top 10
    leaderboard = sorted(leaderboard, key=lambda x: x["score"], reverse=True)[:10]

    # Save leaderboard
    with open("leaderboard.json", "w") as file:
        json.dump(leaderboard, file)

    return {"message": "Score submitted!"}
