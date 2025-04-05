import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

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
    # Get your database URL from an environment variable
    DATABASE_URL = os.getenv("DATABASE_URL")
    if DATABASE_URL is None:
        raise Exception("DATABASE_URL is not set in the environment.")
    
    # Connect to PostgreSQL
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def create_table():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create leaderboard table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leaderboard (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            score INTEGER NOT NULL
        )
    ''')

    # Create friends table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friends (
            id SERIAL PRIMARY KEY,
            player_name TEXT NOT NULL,
            friend_name TEXT NOT NULL,
            UNIQUE(player_name, friend_name)
        )
    ''')

    conn.commit()
    cursor.close()
    conn.close()

create_table()

def create_friend_requests_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friend_requests (
            id SERIAL PRIMARY KEY,
            sender_name TEXT NOT NULL,
            receiver_name TEXT NOT NULL
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

create_friend_requests_table()

class PlayerScore(BaseModel):
    name: str
    score: int

@app.post("/submit_score")
def submit_score(player: PlayerScore):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if the player already exists
    cursor.execute("SELECT * FROM leaderboard WHERE name = %s", (player.name,))
    existing_player = cursor.fetchone()

    if existing_player:
        # Update only if new score is higher
        new_score = max(existing_player["score"], player.score)
        cursor.execute("UPDATE leaderboard SET score = %s WHERE name = %s", (new_score, player.name))
    else:
        cursor.execute("INSERT INTO leaderboard (name, score) VALUES (%s, %s)", (player.name, player.score))

    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Score submitted!"}

@app.get("/leaderboard")
def get_leaderboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, score FROM leaderboard ORDER BY score DESC LIMIT 10")
    leaderboard = cursor.fetchall()
    cursor.close()
    conn.close()
    return leaderboard

@app.post("/reset_leaderboard")
def reset_leaderboard(x_api_key: str = Header(None)):

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leaderboard")
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Leaderboard has been reset!"}
    
@app.post("/add_friend")
def add_friend(data: dict):
    player = data["player_name"]
    friend = data["friend_name"]

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if friend exists
    cursor.execute("SELECT * FROM leaderboard WHERE name = %s", (friend,))
    if not cursor.fetchone():
        conn.close()
        return {"message": "That player doesn't exist!"}

    # Check if already friends
    cursor.execute("SELECT * FROM friends WHERE player_name = %s AND friend_name = %s", (player, friend))
    if cursor.fetchone():
        conn.close()
        return {"message": "Already friends!"}

    # Add friendship
    cursor.execute("INSERT INTO friends (player_name, friend_name) VALUES (%s, %s)", (player, friend))
    conn.commit()
    conn.close()
    return {"message": f"{friend} has been added as a friend!"}

@app.get("/friends/{player_name}")
def get_friends(player_name: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT leaderboard.name, leaderboard.score
        FROM friends
        JOIN leaderboard ON friends.friend_name = leaderboard.name
        WHERE friends.player_name = %s
    """, (player_name,))
    
    friends = cursor.fetchall()
    conn.close()
    return friends

@app.get("/get_friend_requests")
def get_friend_requests(username: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sender FROM friend_requests WHERE receiver = %s", (username,))
    requests = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return requests

