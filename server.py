import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import sqlite3

app = FastAPI()

RESET_API_KEY = os.getenv("RESET_API_KEY")
if RESET_API_KEY is None:
    raise Exception("RESET_API_KEY is not set in the environment.")

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

@app.post("/reset_leaderboard")
def reset_leaderboard(api_key: str = Header(None)):
    print("Received API key:", api_key)
    if api_key != RESET_API_KEY:
        raise HTTPException(status_code=401, detail="Not authorized to reset leaderboard")
        print("The right key:", RESET_API_KEY)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leaderboard")
    conn.commit()
    conn.close()

    return {"message": "Leaderboard has been reset!"}


@app.post("/submit_score")
def submit_score(player: PlayerScore):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if the player already exists in the leaderboard
    cursor.execute("SELECT * FROM leaderboard WHERE name = ?", (player.name,))
    existing_player = cursor.fetchone()

    if existing_player:
        # If the player exists, update their score
        cursor.execute('''
            UPDATE leaderboard
            SET score = ?
            WHERE name = ?
        ''', (max(existing_player["score"], player.score), player.name))
    else:
        # If the player doesn't exist, insert them as a new entry
        cursor.execute('''
            INSERT INTO leaderboard (name, score)
            VALUES (?, ?)
        ''', (player.name, player.score))

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
