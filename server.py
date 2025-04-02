from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import sqlite3

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to your frontend URL when deploying
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # Allow both GET and POST requests
    allow_headers=["*"],
)

# Load leaderboard from file
def get_db_connection():
    conn = sqlite3.connect("leaderboard.db")  # Path to the SQLite database
    conn.row_factory = sqlite3.Row  # Allows access to columns by name
    return conn

# Create leaderboard table if it doesn't exist
def create_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS leaderboard (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        score INTEGER NOT NULL)''')
    conn.commit()
    conn.close()

create_table()

class PlayerScore(BaseModel):
    name: str
    score: int


@app.post("/submit_score")
def submit_score(player: PlayerScore):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert or update the player's score (if they already exist in the leaderboard)
    cursor.execute('''
        INSERT OR REPLACE INTO leaderboard (name, score)
        VALUES (?, COALESCE((SELECT score FROM leaderboard WHERE name = ?), 0) + ?)
    ''', (player.name, player.name, player.score))
    conn.commit()
    conn.close()
    return {"message": "Score submitted!"}

@app.get("/leaderboard")
def get_leaderboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch the top 10 scores
    cursor.execute('''SELECT name, score FROM leaderboard ORDER BY score DESC LIMIT 10''')
    leaderboard = cursor.fetchall()
    conn.close()

    # Convert the results to a list of dictionaries
    return [{"name": row["name"], "score": row["score"]} for row in leaderboard]
